# app/tasks.py

import logging
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from typing import Optional, List, Dict
import ssl

from app.config import settings
from app import scraper

# 新增：匯入自訂的錯誤類別
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

redis_broker = RedisBroker(url=broker_url, **broker_options)
dramatiq.set_broker(redis_broker)


# --- 輔助函式 ---


def should_retry_scraper_task(retries_so_far: int, exception: Exception) -> bool:
    """
    Dramatiq 的重試判斷函式。
    只有當拋出的錯誤是 RetryableScraperError 的實例時，才回傳 True 進行重試。
    """
    return isinstance(exception, RetryableScraperError)


# --- 任務定義 (Actors) ---


# 核心修正：為賽程更新任務加上重試機制
@dramatiq.actor(
    max_retries=2,
    min_backoff=300000,  # 300 秒
    retry_when=should_retry_scraper_task,
)
def task_update_schedule_and_reschedule():
    """
    【Dramatiq版】背景任務，負責執行完整的賽程更新與排程器重設。
    """
    from app.scheduler import setup_scheduler
    from app.core import schedule_scraper

    logger.info("--- Dramatiq Worker: 已接收到賽程更新任務，開始執行 ---")
    try:
        schedule_scraper.scrape_cpbl_schedule(2025, 3, 10, include_past_games=True)
        setup_scheduler()
        logger.info("--- Dramatiq Worker: 賽程更新任務執行完畢 ---")
    except FatalScraperError as e:
        # 捕捉到致命錯誤，記錄後不再重試
        logger.error(
            f"Dramatiq Worker 在執行賽程更新時發生致命錯誤: {e}", exc_info=True
        )


# 核心修正：為單日爬蟲任務加上重試機制
@dramatiq.actor(
    max_retries=2,
    min_backoff=300000,  # 30 秒
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
        logger.info(f"--- Dramatiq Worker: 單日爬蟲任務 for {date_str} 執行完畢 ---")
    except (FatalScraperError, GameNotFinalError) as e:
        # 捕捉到致命錯誤或非最終比賽狀態的錯誤，記錄後不再重試
        logger.error(
            f"Dramatiq Worker 在執行單日爬蟲任務時發生不可重試的錯誤: {e}",
            exc_info=True,
        )


# 核心修正：為逐月爬蟲任務加上重試機制
@dramatiq.actor(
    max_retries=2,
    min_backoff=300000,  # 300 秒
    retry_when=should_retry_scraper_task,
)
def task_scrape_entire_month(month_str: Optional[str] = None):
    """
    【Dramatiq版】抓取整月比賽數據的任務。
    """
    logger.info(f"--- Dramatiq Worker: 執行逐月爬蟲任務 for {month_str or '本月'} ---")
    try:
        scraper.scrape_entire_month(month_str)
        logger.info(
            f"--- Dramatiq Worker: 逐月爬蟲任務 for {month_str or '本月'} 執行完畢 ---"
        )
    except FatalScraperError as e:
        # 捕捉到致命錯誤，記錄後不再重試
        logger.error(
            f"Dramatiq Worker 在執行逐月爬蟲任務時發生致命錯誤: {e}", exc_info=True
        )


# 逐年爬蟲有自己的內部錯誤處理，因此不在 actor 層級進行重試
@dramatiq.actor
def task_scrape_entire_year(year_str: Optional[str] = None):
    """
    【Dramatiq版】抓取全年比賽數據的任務。
    """
    logger.info(f"--- Dramatiq Worker: 執行逐年爬蟲任務 for {year_str or '今年'} ---")
    try:
        scraper.scrape_entire_year(year_str)
        logger.info(
            f"--- Dramatiq Worker: 逐年爬蟲任務 for {year_str or '今年'} 執行完畢 ---"
        )
    except Exception as e:
        logger.error(
            f"Dramatiq Worker 在執行逐年爬蟲任務時發生嚴重錯誤: {e}", exc_info=True
        )
