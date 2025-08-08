# app/tasks.py

import logging
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from typing import Optional, List, Dict
import ssl
import requests  # 新增：匯入 requests 函式庫

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


def _trigger_cache_clear():
    """
    向 Web 服務發送請求，以清除 Redis 中的分析快取。
    """
    # 假設 Web 服務在 Docker Compose 中的服務名稱為 'web'，監聽 8000 port
    # 這個 URL 是為容器內部通訊設計的
    url = "http://web:8000/api/system/clear-cache"
    headers = {"X-API-Key": settings.API_KEY}

    try:
        logger.info("任務完成，正在觸發快取清除...")
        response = requests.post(url, headers=headers, timeout=10)
        response.raise_for_status()  # 如果狀態碼不是 2xx，則拋出異常
        logger.info(f"快取清除成功: {response.json().get('message')}")
    except requests.exceptions.RequestException as e:
        # 在背景任務中，即使快取清除失敗，我們也不希望整個任務失敗
        # 因此只記錄錯誤，不向上拋出異常
        logger.error(f"呼叫快取清除 API 時發生錯誤: {e}", exc_info=True)


def should_retry_scraper_task(retries_so_far: int, exception: Exception) -> bool:
    """
    Dramatiq 的重試判斷函式。
    只有當拋出的錯誤是 RetryableScraperError 的實例時，才回傳 True 進行重試。
    """
    return isinstance(exception, RetryableScraperError)


# --- 任務定義 (Actors) ---


@dramatiq.actor(
    max_retries=settings.DRAMATIQ_MAX_RETRIES,
    min_backoff=settings.DRAMATIQ_RETRY_BACKOFF,
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
        schedule_scraper.scrape_cpbl_schedule(
            2025,
            settings.CPBL_SEASON_START_MONTH,
            settings.CPBL_SEASON_END_MONTH,
            include_past_games=True,
        )
        setup_scheduler()

        # 賽程更新可能會影響分析結果，因此也觸發快取清除
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

        # 爬蟲成功後，觸發快取清除
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

        # 爬蟲成功後，觸發快取清除
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

        # 爬蟲成功後，觸發快取清除
        _trigger_cache_clear()

        logger.info(
            f"--- Dramatiq Worker: 逐年爬蟲任務 for {year_str or '今年'} 執行完畢 ---"
        )
    except Exception as e:
        logger.error(
            f"Dramatiq Worker 在執行逐年爬蟲任務時發生嚴重錯誤: {e}", exc_info=True
        )
