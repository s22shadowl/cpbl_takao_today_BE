import datetime
import os
import logging
import time
import argparse
from datetime import date
from dateutil.relativedelta import relativedelta

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from app.core import fetcher
from app.parsers import schedule
from app.scraper import scrape_single_day, scrape_and_store_season_stats

# --- 設定 ---
from app.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


def run_scrape(start_date: date, end_date: date):
    """
    執行第一步：將指定日期範圍的資料爬取並儲存到本地開發資料庫。
    """
    logger.info("--- 步驟 1: 開始爬取資料至本地 PostgreSQL 資料庫 ---")

    # 載入 .env 檔案以設定本地資料庫連線
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        logger.error("錯誤: 找不到 .env 檔案。請先建立此檔案以設定本地資料庫。")
        return
    load_dotenv(dotenv_path=env_path)
    logger.info("成功載入 .env 設定檔。")

    # **關鍵**: 延遲導入，確保 app 模組在讀取 DATABASE_URL 時，讀到的是 .env 的設定
    from app.db import Base, engine as local_engine

    # 建立本地資料庫的表格結構 (如果不存在)
    logger.info("正在檢查並建立本地資料庫表格...")
    Base.metadata.create_all(bind=local_engine)

    # 計算需要爬取的月份範圍
    start_month_obj = start_date.replace(day=1)
    end_month_obj = end_date.replace(day=1)

    all_games_in_range = []
    current_month_iter = start_month_obj

    # --- START: 核心修改區塊 ---
    while current_month_iter <= end_month_obj:
        year = current_month_iter.year
        month = current_month_iter.month
        logger.info(f"正在獲取 {year} 年 {month} 月的賽程頁面...")

        # 步驟 1: 抓取該月份賽程頁的 HTML
        html_content = fetcher.fetch_schedule_page(year, month)
        if not html_content:
            logger.warning(f"無法獲取 {year}-{month} 的賽程頁面，跳過此月份。")
            current_month_iter += relativedelta(months=1)
            time.sleep(5)  # 即使失敗也延遲，避免頻繁請求
            continue

        # 步驟 2: 解析 HTML 以獲取包含完整資訊的比賽列表
        logger.info(f"正在解析 {year} 年 {month} 月的賽程...")
        month_games = schedule.parse_schedule_page(html_content, year)

        if month_games:
            logger.info(f"解析到 {len(month_games)} 場比賽。")
            all_games_in_range.extend(month_games)
        else:
            logger.info("此月份沒有解析到任何比賽。")

        current_month_iter += relativedelta(months=1)
        time.sleep(5)  # 友善爬取延遲
    # --- END: 核心修改區塊 ---

    # 從所有比賽中篩選出在指定日期範圍內且不重複的日期
    unique_game_dates = set()
    # 將所有比賽按日期分組，方便後續傳遞給 scrape_single_day
    games_by_date = {}

    for game in all_games_in_range:
        # **注意**: schedule.parse_schedule_page 回傳的 key 是 'game_date'
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
                    games_by_date[game_date_str].append(
                        game
                    )  # 將比賽資訊儲存到對應的日期
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

        # 獲取當天所有相關的比賽資訊
        current_day_games = games_by_date.get(date_str, [])

        try:
            # 呼叫 scrape_single_day，傳入當天的比賽列表和 update_season_stats=False
            scrape_single_day(
                specific_date=date_str,
                games_for_day=current_day_games,  # 傳遞當天比賽列表
                update_season_stats=False,
            )
            logger.info(f"成功完成日期: {date_str}")
        except Exception as e:
            logger.error(f"處理日期 {date_str} 時發生錯誤: {e}", exc_info=True)

        time.sleep(5)  # 友善爬取延遲

    # 在所有比賽處理完畢後，執行一次球季累積數據的抓取
    logger.info("所有比賽資料處理完畢，正在更新當前球季累積數據...")
    scrape_and_store_season_stats()

    logger.info("--- 步驟 1: 所有日期的批次爬取任務已完成 ---")


def run_upload():
    """
    執行第二步：將本地 PostgreSQL 資料庫的資料上傳同步至雲端資料庫。
    """
    logger.info("--- 步驟 2: 開始從本地資料庫上傳資料至雲端 ---")

    # 載入本地資料庫設定
    env_path_local = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path_local):
        logger.error("錯誤: 找不到 .env 檔案，無法連線至本地資料庫。")
        return
    load_dotenv(dotenv_path=env_path_local, override=True)
    local_db_url = os.getenv("DATABASE_URL")

    # 載入雲端資料庫設定
    env_path_cloud = os.path.join(os.path.dirname(__file__), ".env.prod")
    if not os.path.exists(env_path_cloud):
        logger.error("錯誤: 找不到 .env.prod 檔案，無法連線至雲端資料庫。")
        return
    load_dotenv(dotenv_path=env_path_cloud, override=True)
    cloud_db_url = os.getenv("DATABASE_URL")

    if not local_db_url or not cloud_db_url:
        logger.error("錯誤: 本地或雲端資料庫的 DATABASE_URL 未設定。")
        return

    # 延遲導入，避免與 scrape 步驟的 DATABASE_URL 設定衝突
    from app.db import Base
    from app.models import (
        GameResultDB,
        PlayerGameSummaryDB,
        AtBatDetailDB,
        PlayerSeasonStatsDB,
        PlayerSeasonStatsHistoryDB,
    )

    # 建立本地與雲端資料庫的獨立連線
    local_engine = create_engine(local_db_url)
    cloud_engine = create_engine(cloud_db_url)

    LocalSession = sessionmaker(bind=local_engine)
    CloudSession = sessionmaker(bind=cloud_engine)

    db_local = LocalSession()
    db_cloud = CloudSession()

    # 確保雲端資料庫的表格都已存在
    Base.metadata.create_all(bind=cloud_engine)

    # 定義要同步的資料表模型順序 (父表在前)
    MODELS_TO_SYNC = [
        GameResultDB,
        PlayerGameSummaryDB,
        AtBatDetailDB,
        PlayerSeasonStatsDB,
        PlayerSeasonStatsHistoryDB,
    ]

    try:
        for model in MODELS_TO_SYNC:
            table_name = model.__tablename__
            logger.info(f"正在同步資料表: {table_name}...")

            local_records = db_local.query(model).all()
            if not local_records:
                logger.info(f"資料表 {table_name} 在本地沒有資料，跳過。")
                continue

            count = 0
            for record in local_records:
                # 將物件從本地 session 中分離，以便附加到雲端 session
                db_local.expunge(record)
                # 使用 merge 來實現 "upsert"
                db_cloud.merge(record)
                count += 1

            logger.info(f"已準備 {count} 筆來自 {table_name} 的資料待提交。")

        logger.info("正在提交所有變更至雲端資料庫...")
        db_cloud.commit()
        logger.info("資料已成功同步至雲端！")

    except IntegrityError as e:
        logger.error(
            f"上傳資料時發生完整性約束錯誤 (可能資料已存在且內容不同): {e}",
            exc_info=True,
        )
        db_cloud.rollback()
    except Exception as e:
        logger.error(f"上傳資料時發生錯誤，交易已復原: {e}", exc_info=True)
        db_cloud.rollback()
    finally:
        db_local.close()
        db_cloud.close()

    logger.info("--- 步驟 2: 上傳任務執行完畢 ---")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CPBL 歷史資料批次處理工具。分為兩步驟：1. scrape (爬取至本地), 2. upload (從本地上傳至雲端)。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- 'scrape' 指令的參數設定 ---
    parser_scrape = subparsers.add_parser(
        "scrape", help="執行步驟一：爬取資料並儲存至本地 PostgreSQL 資料庫。"
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

    # --- 'upload' 指令的參數設定 ---
    parser_upload = subparsers.add_parser(
        "upload", help="執行步驟二：將本地 PostgreSQL 資料庫的內容上傳至雲端。"
    )

    args = parser.parse_args()

    if args.command == "scrape":
        if args.start > args.end:
            logger.error("錯誤：開始日期不能晚於結束日期。")
        else:
            run_scrape(start_date=args.start, end_date=args.end)
    elif args.command == "upload":
        run_upload()
