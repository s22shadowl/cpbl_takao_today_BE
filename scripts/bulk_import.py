# 新版 bulk_import.py 使用步驟
# 這個工具現在完全在 Docker 容器內運作。

# --- 主要流程 ---

# 步驟一：爬取「比賽」資料至「暫存資料庫」
# 此步驟會將指定日期範圍的歷史比賽數據，爬取並儲存到 Docker 環境中的暫存資料庫。
# 最後，它會觸發一次官網賽程的更新。
# 指令：
# docker compose run --rm worker sh -c "Xvfb :99 -screen 0 1280x1024x24 & export DISPLAY=:99 && python -m scripts.bulk_import scrape --start YYYY-MM-DD --end YYYY-MM-DD"
# 範例：
# docker compose run --rm worker sh -c "Xvfb :99 -screen 0 1280x1024x24 & export DISPLAY=:99 && python -m scripts.bulk_import scrape --start 2025-03-01 --end 2025-04-30"

# --- 輔助流程 ---

# (可選) 步驟 A：爬取「球員生涯」資料至「暫存資料庫」
# 此步驟會爬取球隊名單上所有球員的生涯數據，並存入暫存資料庫。通常在 scrape 後執行，或用於手動更新所有球員的生涯數據。
# 指令：
# docker compose run --rm worker sh -c "Xvfb :99 -screen 0 1280x1024x24 & export DISPLAY=:99 && python -m scripts.bulk_import scrape-career"

# (可選) 步驟 B：僅更新官網賽程
# 如果你只需要從官網同步最新的賽程資料，可以執行此指令。
# 指令：
# docker compose run --rm worker sh -c "python -m scripts.bulk_import update-schedule"


# --- 最終流程 ---

# 步驟二：[手動] 驗證暫存資料
# 在將資料同步到雲端之前，你必須親自連線到暫存資料庫，確認資料的完整性與正確性。
# 連線資訊應對應 .env 檔案中的 DATABASE_URL (主機為 localhost，Port 為 5432)。

# 步驟三：從「暫存資料庫」上傳至「生產資料庫」
# 在確認步驟二的資料完全無誤後，執行此指令。它會讀取暫存資料庫中的所有資料，並將其同步 (merge) 至雲端上的生產資料庫。
# 指令：
# docker compose run --rm worker sh -c "python -m scripts.bulk_import upload"

import datetime
import logging
import time
import argparse
from datetime import date
from dateutil.relativedelta import relativedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

# --- [修正] 確保 Broker 設定在載入任何 actor 之前執行 ---
# 必須先匯入此模組來設定全域 Broker，
# 否則 worker 模組中的 actor 會被綁定到預設的 localhost broker。
import app.broker_setup  # noqa: F401

from app.config import settings, Settings
from app.core import fetcher
from app.parsers import schedule
from app.services.game_data import scrape_single_day, scrape_and_store_season_stats
from app.db import Base
from app.models import (
    GameResultDB,
    PlayerGameSummaryDB,
    AtBatDetailDB,
    PlayerSeasonStatsDB,
    PlayerSeasonStatsHistoryDB,
    PlayerCareerStatsDB,
    PlayerFieldingStatsDB,
)
from app.logging_config import setup_logging
from app.workers import task_update_schedule_and_reschedule


# --- 初始化 ---
setup_logging()
logger = logging.getLogger(__name__)


# --- `scrape` 指令函式 ---
def run_scrape(settings: Settings, start_date: date, end_date: date):
    """
    執行第一步：將指定日期範圍的資料爬取並儲存到暫存資料庫。
    """
    logger.info("--- 步驟 1: 開始爬取資料至暫存 (Staging) PostgreSQL 資料庫 ---")
    logger.info(f"目標資料庫: {settings.STAGING_DATABASE_URL.split('@')[-1]}")

    staging_engine = create_engine(settings.STAGING_DATABASE_URL)

    logger.info("正在檢查並建立暫存資料庫表格...")
    Base.metadata.create_all(bind=staging_engine)

    start_month_obj = start_date.replace(day=1)
    end_month_obj = end_date.replace(day=1)

    all_games_in_range = []
    current_month_iter = start_month_obj

    while current_month_iter <= end_month_obj:
        year = current_month_iter.year
        month = current_month_iter.month
        logger.info(f"正在獲取 {year} 年 {month} 月的賽程頁面...")

        html_content = fetcher.fetch_schedule_page(year, month)
        if not html_content:
            logger.warning(f"無法獲取 {year}-{month} 的賽程頁面，跳過此月份。")
            current_month_iter += relativedelta(months=1)
            time.sleep(settings.BULK_IMPORT_DELAY_SECONDS)
            continue

        logger.info(f"正在解析 {year} 年 {month} 月的賽程...")
        month_games = schedule.parse_schedule_page(html_content, year)

        if month_games:
            logger.info(f"解析到 {len(month_games)} 場比賽。")
            all_games_in_range.extend(month_games)
        else:
            logger.info("此月份沒有解析到任何比賽。")

        current_month_iter += relativedelta(months=1)
        time.sleep(settings.BULK_IMPORT_DELAY_SECONDS)

    unique_game_dates = set()
    games_by_date = {}

    for game in all_games_in_range:
        game_date_str = game.get("game_date")
        if game_date_str:
            try:
                game_date_obj = datetime.datetime.strptime(
                    game_date_str, "%Y-%m-%d"
                ).date()
                if start_date <= game_date_obj <= end_date:
                    unique_game_dates.add(game_date_str)
                    if game_date_str not in games_by_date:
                        games_by_date[game_date_str] = []
                    games_by_date[game_date_str].append(game)
            except ValueError:
                logger.warning(f"賽程資料中發現無效日期格式: {game_date_str}")

    sorted_game_dates = sorted(list(unique_game_dates))
    total_games_to_process = len(sorted_game_dates)

    if not sorted_game_dates:
        logger.info(
            f"在 {start_date} 至 {end_date} 範圍內沒有找到任何比賽日期，任務結束。"
        )
        logger.info("--- 步驟 1: 所有日期的批次爬取任務已完成 ---")
        return

    logger.info(
        f"準備開始批次爬取，範圍: {start_date} 至 {end_date}，共 {total_games_to_process} 個比賽日"
    )

    day_count = 0
    for date_str in sorted_game_dates:
        day_count += 1
        logger.info(
            f"({day_count}/{total_games_to_process}) - 正在處理日期: {date_str}"
        )

        current_day_games = games_by_date.get(date_str, [])

        try:
            scrape_single_day(
                specific_date=date_str,
                games_for_day=current_day_games,
                update_season_stats=False,
            )
            logger.info(f"成功完成日期: {date_str}")
        except Exception as e:
            logger.error(f"處理日期 {date_str} 時發生錯誤: {e}", exc_info=True)

        time.sleep(settings.BULK_IMPORT_DELAY_SECONDS)

    logger.info("所有比賽資料處理完畢，正在更新當前球季累積數據...")
    scrape_and_store_season_stats(update_career_stats_for_all=False)

    logger.info("正在觸發官網賽程更新任務...")
    task_update_schedule_and_reschedule.send()
    logger.info("賽程更新任務已送出。")

    logger.info("--- 步驟 1: 所有日期的批次爬取任務已完成 ---")


# --- `scrape-career` 指令函式 ---
def run_scrape_career_stats(settings: Settings):
    """
    執行輔助步驟：爬取球隊所有球員的生涯數據。
    """
    logger.info("--- 步驟 A: 開始爬取所有球員的生涯數據 ---")
    scrape_and_store_season_stats(update_career_stats_for_all=True)
    logger.info("--- 步驟 A: 所有球員生涯數據更新完畢 ---")


# --- `update-schedule` 指令函式 ---
def run_update_schedule():
    """
    執行更新賽程步驟：觸發 Dramatiq 任務以從官網更新賽程。
    """
    logger.info("--- 開始觸發官網賽程更新任務 ---")
    task_update_schedule_and_reschedule.send()
    logger.info("賽程更新任務已成功送出。")
    logger.info("--- 賽程更新任務執行完畢 ---")


# --- `upload` 指令函式 ---
def run_upload(settings: Settings):
    """
    執行第二步：將暫存資料庫的資料上傳同步至生產資料庫。
    """
    logger.info("--- 步驟 2: 開始從暫存資料庫上傳資料至生產資料庫 ---")
    logger.info(f"來源 (Staging): {settings.STAGING_DATABASE_URL.split('@')[-1]}")
    logger.info(f"目標 (Production): {settings.PRODUCTION_DATABASE_URL.split('@')[-1]}")

    staging_engine = create_engine(settings.STAGING_DATABASE_URL)
    production_engine = create_engine(settings.PRODUCTION_DATABASE_URL)

    StagingSession = sessionmaker(bind=staging_engine)
    ProductionSession = sessionmaker(bind=production_engine)

    db_staging = StagingSession()
    db_production = ProductionSession()

    Base.metadata.create_all(bind=production_engine)

    MODELS_TO_SYNC = [
        GameResultDB,
        PlayerGameSummaryDB,
        AtBatDetailDB,
        PlayerSeasonStatsDB,
        PlayerSeasonStatsHistoryDB,
        PlayerCareerStatsDB,
        PlayerFieldingStatsDB,
    ]

    try:
        for model in MODELS_TO_SYNC:
            table_name = model.__tablename__
            logger.info(f"正在同步資料表: {table_name}...")

            staging_records = db_staging.query(model).all()
            if not staging_records:
                logger.info(f"資料表 {table_name} 在暫存資料庫沒有資料，跳過。")
                continue

            count = 0
            for record in staging_records:
                db_staging.expunge(record)
                db_production.merge(record)
                count += 1

            logger.info(f"已準備 {count} 筆來自 {table_name} 的資料待提交。")

        logger.info("正在提交所有變更至生產資料庫...")
        db_production.commit()
        logger.info("資料已成功同步至生產資料庫！")

    except IntegrityError as e:
        logger.error(
            f"上傳資料時發生完整性約束錯誤: {e}",
            exc_info=True,
        )
        db_production.rollback()
    except Exception as e:
        logger.error(f"上傳資料時發生錯誤，交易已復原: {e}", exc_info=True)
        db_production.rollback()
    finally:
        db_staging.close()
        db_production.close()

    logger.info("--- 步驟 2: 上傳任務執行完畢 ---")


# --- 主程式進入點 ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CPBL 歷史資料批次處理工具。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_scrape = subparsers.add_parser(
        "scrape",
        help="執行步驟一：爬取比賽資料並儲存至 STAGING_DATABASE_URL 指定的資料庫。",
    )
    parser_scrape.add_argument(
        "--start",
        required=True,
        help="爬取開始日期 (格式: YYYY-MM-DD)",
        type=lambda s: datetime.datetime.strptime(s, "%Y-%m-%d").date(),
    )
    parser_scrape.add_argument(
        "--end",
        default=date.today(),
        help="爬取結束日期 (格式: YYYY-MM-DD)，預設為今天。",
        type=lambda s: datetime.datetime.strptime(s, "%Y-%m-%d").date(),
    )

    parser_scrape_career = subparsers.add_parser(
        "scrape-career",
        help="執行輔助步驟：爬取所有球員的生涯數據至 STAGING_DATABASE_URL。",
    )

    parser_update_schedule = subparsers.add_parser(
        "update-schedule",
        help="僅從官網更新最新賽程。",
    )

    parser_upload = subparsers.add_parser(
        "upload",
        help="執行步驟二：將暫存資料庫的內容上傳至 PRODUCTION_DATABASE_URL 指定的資料庫。",
    )

    args = parser.parse_args()

    if args.command == "scrape":
        if not settings.STAGING_DATABASE_URL:
            logger.error(
                "錯誤：環境變數 STAGING_DATABASE_URL 未設定，無法執行 scrape。"
            )
            exit(1)
        if args.start > args.end:
            logger.error("錯誤：開始日期不能晚於結束日期。")
        else:
            run_scrape(settings=settings, start_date=args.start, end_date=args.end)

    elif args.command == "scrape-career":
        if not settings.STAGING_DATABASE_URL:
            logger.error(
                "錯誤：環境變數 STAGING_DATABASE_URL 未設定，無法執行 scrape-career。"
            )
            exit(1)
        run_scrape_career_stats(settings=settings)

    elif args.command == "update-schedule":
        run_update_schedule()

    elif args.command == "upload":
        if not settings.STAGING_DATABASE_URL or not settings.PRODUCTION_DATABASE_URL:
            logger.error(
                "錯誤：環境變數 STAGING_DATABASE_URL 或 PRODUCTION_DATABASE_URL 未設定，無法執行 upload。"
            )
            exit(1)
        run_upload(settings=settings)
