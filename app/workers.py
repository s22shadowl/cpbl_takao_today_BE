# app/workers.py

import logging
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.results import Results
from dramatiq.results.backends.redis import RedisBackend
from typing import Optional, List, Dict
import ssl
import requests
from datetime import datetime
import pytz
import time

from app.db import SessionLocal
from app.crud import games as crud_games
from app.core import fetcher
from app.parsers import schedule
from app.config import settings

# [重構] 匯入新的 services 模組
from app.services import game_data, schedule as schedule_service
from app.exceptions import RetryableScraperError, FatalScraperError, GameNotFinalError

logger = logging.getLogger(__name__)

# --- Broker 設定 ---
broker_url = settings.DRAMATIQ_BROKER_URL
broker_options = {}

if broker_url.startswith("rediss://"):
    broker_options = {
        "ssl": True,
        "ssl_cert_reqs": ssl.CERT_NONE,
        "socket_connect_timeout": 10,
        "socket_timeout": 10,
    }

result_backend = RedisBackend(url=broker_url, **broker_options)
redis_broker = RedisBroker(url=broker_url, **broker_options)
redis_broker.add_middleware(Results(backend=result_backend))
dramatiq.set_broker(redis_broker)


# --- 輔助函式 ---


def _trigger_cache_clear():
    """向 Web 服務發送請求，以清除 Redis 中的分析快取。"""
    url = "http://web:8000/api/system/clear-cache"
    headers = {"X-API-Key": settings.API_KEY}
    try:
        logger.info("任務完成，正在觸發快取清除...")
        response = requests.post(url, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info(f"快取清除成功: {response.json().get('message')}")
    except requests.exceptions.RequestException as e:
        logger.error(f"呼叫快取清除 API 時發生錯誤: {e}", exc_info=True)


def should_retry_scraper_task(retries_so_far: int, exception: Exception) -> bool:
    """Dramatiq 的重試判斷函式。"""
    return isinstance(exception, RetryableScraperError)


# --- 任務定義 (Actors) ---


@dramatiq.actor(max_retries=0)
def task_run_daily_crawl():
    """
    由 GHA 自動化流程觸發的每日例行爬蟲任務的進入點。
    此任務從資料庫讀取當日賽程，並觸發 `task_scrape_single_day`。
    """
    tz = pytz.timezone("Asia/Taipei")
    today_date = datetime.now(tz).date()
    today_str = today_date.strftime("%Y-%m-%d")
    logger.info(f"[Daily Crawl] Executing daily crawl check for {today_str}.")

    db = SessionLocal()
    try:
        games_scheduled_today = crud_games.get_games_by_date(db, today_date)
        if not games_scheduled_today:
            logger.info(f"[Daily Crawl] No games scheduled for {today_str}. Skipping.")
            return

        games_for_day_data = [
            {
                "cpbl_game_id": g.game_id,
                "game_date": g.game_date.strftime("%Y-%m-%d"),
                "game_time": g.game_time,
                "home_team": g.home_team,
                "away_team": g.away_team,
                "venue": g.venue,
                "status": g.status,
            }
            for g in games_scheduled_today
        ]
        logger.info(
            f"[Daily Crawl] Found {len(games_for_day_data)} game(s) for {today_str}. Triggering scrape task."
        )
        task_scrape_single_day.send(today_str, games_for_day_data)
    except Exception as e:
        logger.error(
            f"[Daily Crawl] An error occurred during daily crawl check: {e}",
            exc_info=True,
        )
    finally:
        db.close()


@dramatiq.actor(
    max_retries=settings.DRAMATIQ_MAX_RETRIES,
    min_backoff=settings.DRAMATIQ_RETRY_BACKOFF,
    retry_when=should_retry_scraper_task,
)
def task_update_schedule_and_reschedule():
    """背景任務，負責執行完整的賽程更新。"""
    logger.info("--- Dramatiq Worker: 已接收到賽程更新任務，開始執行 ---")
    try:
        # [重構] 使用新的 service 函式
        schedule_service.scrape_cpbl_schedule(
            datetime.now().year,
            settings.CPBL_SEASON_START_MONTH,
            settings.CPBL_SEASON_END_MONTH,
            include_past_games=True,
        )
        _trigger_cache_clear()
        logger.info("--- Dramatiq Worker: 賽程更新任務執行完畢 ---")
    except FatalScraperError as e:
        logger.error(
            f"Dramatiq Worker 在執行賽程更新時發生致命錯誤: {e}", exc_info=True
        )


@dramatiq.actor(
    max_retries=settings.DRAMATIQ_MAX_RETRIES,
    min_backoff=settings.DRAMATIQ_RETRY_BACKOFF,
    retry_when=should_retry_scraper_task,
)
def task_scrape_single_day(
    date_str: Optional[str] = None,
    games_for_day: Optional[List[Dict[str, Optional[str]]]] = None,
):
    """
    抓取單日比賽數據的任務。
    此任務現在能處理兩種情況：
    1. `games_for_day` 已提供 (由自動化流程觸發)。
    2. `games_for_day` 未提供 (由手動 API 觸發)，此時需自行獲取賽程。
    """
    tz = pytz.timezone("Asia/Taipei")
    target_date_obj = (
        datetime.strptime(date_str, "%Y-%m-%d").date()
        if date_str
        else datetime.now(tz).date()
    )
    target_date_str = target_date_obj.strftime("%Y-%m-%d")

    logger.info(f"--- Dramatiq Worker: 執行單日爬蟲任務 for {target_date_str} ---")

    try:
        if games_for_day is None:
            logger.info(f"未提供賽程列表，為日期 {target_date_str} 執行線上抓取...")
            html_content = fetcher.fetch_schedule_page(
                target_date_obj.year, target_date_obj.month
            )
            if not html_content:
                raise FatalScraperError(
                    f"無法獲取 {target_date_obj.strftime('%Y-%m')} 的賽程頁面。"
                )
            all_month_games = schedule.parse_schedule_page(
                html_content, target_date_obj.year
            )
            games_for_day = [
                game for game in all_month_games if game["game_date"] == target_date_str
            ]

        # [重構] 使用新的 service 函式
        game_data.scrape_single_day(target_date_str, games_for_day)
        _trigger_cache_clear()
        logger.info(
            f"--- Dramatiq Worker: 單日爬蟲任務 for {target_date_str} 執行完畢 ---"
        )
    except (FatalScraperError, GameNotFinalError) as e:
        logger.error(
            f"Dramatiq Worker 在執行單日爬蟲任務時發生不可重試的錯誤: {e}",
            exc_info=True,
        )


@dramatiq.actor(
    max_retries=settings.DRAMATIQ_MAX_RETRIES,
    min_backoff=settings.DRAMATIQ_RETRY_BACKOFF,
    retry_when=should_retry_scraper_task,
)
def task_scrape_entire_month(month_str: Optional[str] = None):
    """抓取整月比賽數據的任務。"""
    logger.info(f"--- Dramatiq Worker: 執行逐月爬蟲任務 for {month_str or '本月'} ---")
    try:
        # [重構] 使用新的 service 函式
        game_data.scrape_entire_month(month_str)
        _trigger_cache_clear()
        logger.info(
            f"--- Dramatiq Worker: 逐月爬蟲任務 for {month_str or '本月'} 執行完畢 ---"
        )
    except FatalScraperError as e:
        logger.error(
            f"Dramatiq Worker 在執行逐月爬蟲任務時發生致命錯誤: {e}", exc_info=True
        )


@dramatiq.actor
def task_scrape_entire_year(year_str: Optional[str] = None):
    """抓取全年比賽數據的任務。"""
    logger.info(f"--- Dramatiq Worker: 執行逐年爬蟲任務 for {year_str or '今年'} ---")
    try:
        # [重構] 使用新的 service 函式
        game_data.scrape_entire_year(year_str)
        _trigger_cache_clear()
        logger.info(
            f"--- Dramatiq Worker: 逐年爬蟲任務 for {year_str or '今年'} 執行完畢 ---"
        )
    except Exception as e:
        logger.error(
            f"Dramatiq Worker 在執行逐年爬蟲任務時發生嚴重錯誤: {e}", exc_info=True
        )


@dramatiq.actor(max_retries=0, time_limit=60 * 1000)  # 1 分鐘超時
def task_e2e_workflow_test():
    """
    [僅供 T11 E2E 測試使用]
    一個輕量級的測試任務，僅等待數秒後就成功返回。
    """
    logger.info("背景任務: E2E 測試任務已啟動，將等待 5 秒...")
    time.sleep(5)
    logger.info("背景任務: E2E 測試任務已成功完成。")
