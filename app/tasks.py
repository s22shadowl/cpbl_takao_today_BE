# app/tasks.py

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
from app.db import SessionLocal
from app.crud import games as crud_games

from app.config import settings
from app import scraper

from app.exceptions import RetryableScraperError, FatalScraperError, GameNotFinalError

logger = logging.getLogger(__name__)

# --- Broker 設定 (保持不變) ---
broker_url = settings.DRAMATIQ_BROKER_URL
broker_options = {}

if broker_url.startswith("rediss://"):
    broker_options = {
        "ssl": True,
        "ssl_cert_reqs": ssl.CERT_NONE,
        "socket_connect_timeout": 10,
        "socket_timeout": 10,
    }

# 設定 Result Backend
result_backend = RedisBackend(url=broker_url, **broker_options)

# 設定 Broker，並掛載 Results middleware
redis_broker = RedisBroker(url=broker_url, **broker_options)
redis_broker.add_middleware(Results(backend=result_backend))

dramatiq.set_broker(redis_broker)


# --- 輔助函式 (保持不變) ---


def _trigger_cache_clear():
    """
    向 Web 服務發送請求，以清除 Redis 中的分析快取。
    """
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
    """
    Dramatiq 的重試判斷函式。
    """
    return isinstance(exception, RetryableScraperError)


# --- ▼▼▼ 新增/修改這個任務 ▼▼▼ ---
@dramatiq.actor(max_retries=0)
def task_run_daily_crawl():
    """
    由 API 觸發的每日例行爬蟲任務的進入點。
    此任務的職責是：
    1. 檢查今天是否有比賽。
    2. 如果有，則觸發真正的爬蟲任務 `task_scrape_single_day`。
    """

    # 1. 取得台北時區的今天日期
    tz = pytz.timezone("Asia/Taipei")
    today_date = datetime.now(tz).date()
    today_str = today_date.strftime("%Y-%m-%d")
    logger.info(f"[Daily Crawl] Executing daily crawl check for {today_str}.")

    db = SessionLocal()
    try:
        # 2. 從資料庫查詢今天是否有「排程」
        games_scheduled_today = crud_games.get_games_by_date(db, today_date)

        if not games_scheduled_today:
            logger.info(f"[Daily Crawl] No games scheduled for {today_str}. Skipping.")
            return

        # 3. 將查詢到的 GameSchedule 物件轉換為任務所需的格式 (dict)
        games_for_day_data = [
            {
                "cpbl_game_id": g.game_id,  # 使用 GameSchedule 的 game_id
                "game_date": g.game_date.strftime("%Y-%m-%d"),
                "game_time": g.game_time,
                "matchup": g.matchup,
            }
            for g in games_scheduled_today
        ]

        logger.info(
            f"[Daily Crawl] Found {len(games_for_day_data)} game(s) for {today_str}. Triggering scrape task."
        )
        # 4. 觸發真正的爬蟲任務
        task_scrape_single_day.send(today_str, games_for_day_data)

    except Exception as e:
        logger.error(
            f"[Daily Crawl] An error occurred during daily crawl check: {e}",
            exc_info=True,
        )
    finally:
        db.close()


# --- ▲▲▲ 新增/修改這個任務 ▲▲▲ ---


# --- 任務定義 (Actors) (保持不變) ---


@dramatiq.actor(
    max_retries=settings.DRAMATIQ_MAX_RETRIES,
    min_backoff=settings.DRAMATIQ_RETRY_BACKOFF,
    retry_when=should_retry_scraper_task,
)
def task_update_schedule_and_reschedule():
    """
    【Dramatiq版】背景任務，負責執行完整的賽程更新。
    注意：此任務現在只更新資料庫，不再與 APScheduler 互動。
    """
    from app.core import schedule_scraper

    logger.info("--- Dramatiq Worker: 已接收到賽程更新任務，開始執行 ---")
    try:
        # 這裡的 scrape_cpbl_schedule 應該會呼叫 crud.update_game_schedules
        schedule_scraper.scrape_cpbl_schedule(
            datetime.now().year,  # 將年份改為動態
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
    date_str: str, games_for_day: List[Dict[str, Optional[str]]]
):
    """
    【Dramatiq版】抓取單日比賽數據的任務。
    """
    logger.info(f"--- Dramatiq Worker: 執行單日爬蟲任務 for {date_str} ---")
    try:
        scraper.scrape_single_day(date_str, games_for_day)
        _trigger_cache_clear()
        logger.info(f"--- Dramatiq Worker: 單日爬蟲任務 for {date_str} 執行完畢 ---")
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
    """
    【Dramatiq版】抓取整月比賽數據的任務。
    """
    logger.info(f"--- Dramatiq Worker: 執行逐月爬蟲任務 for {month_str or '本月'} ---")
    try:
        scraper.scrape_entire_month(month_str)
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
    """
    【Dramatiq版】抓取全年比賽數據的任務。
    """
    logger.info(f"--- Dramatiq Worker: 執行逐年爬蟲任務 for {year_str or '今年'} ---")
    try:
        scraper.scrape_entire_year(year_str)
        _trigger_cache_clear()
        logger.info(
            f"--- Dramatiq Worker: 逐年爬蟲任務 for {year_str or '今年'} 執行完畢 ---"
        )
    except Exception as e:
        logger.error(
            f"Dramatiq Worker 在執行逐年爬蟲任務時發生嚴重錯誤: {e}", exc_info=True
        )
