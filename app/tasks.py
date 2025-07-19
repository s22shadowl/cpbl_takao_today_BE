# app/tasks.py

import logging
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from typing import Optional

from urllib.parse import urlparse
import ssl

# 專案內部模組
# 不再需要從這裡呼叫 setup_logging
from app.config import settings
from app.core import schedule_scraper
from app import scraper

# **核心修正**: 移除在模組頂層的 setup_logging() 呼叫
# setup_logging()

logger = logging.getLogger(__name__)

# --- 核心修正 ---
# 手動解析 Redis URL 並明確設定連線參數，以確保 SSL 設定正確傳遞

# 1. 解析從 settings 讀取到的 Redis URL
parsed_url = urlparse(settings.DRAMATIQ_BROKER_URL)

# 建立一個包含 SSL 和超時選項的字典
connection_kwargs = {
    "ssl": True,
    "ssl_cert_reqs": ssl.CERT_NONE,
    # --- 新增 ---
    # 設定連線到 Redis 的超時時間為 10 秒
    "socket_connect_timeout": 10,
    # 設定連線後，讀取/寫入操作的超時時間為 10 秒
    "socket_timeout": 10,
}

# 2. 建立一個包含 SSL 選項的字典
#    - ssl=True: 啟用 SSL/TLS 加密 (因為 URL scheme 是 rediss://)
#    - ssl_cert_reqs=ssl.CERT_NONE: 告知客戶端不要驗證伺服器的 SSL 憑證，
#      這能解決在某些環境下憑證鏈不完整的連線問題。
connection_kwargs = {
    "ssl": True,
    "ssl_cert_reqs": ssl.CERT_NONE,
}

# 3. 建立 RedisBroker 實例，傳入解析後的獨立參數
redis_broker = RedisBroker(
    host=parsed_url.hostname,
    port=parsed_url.port,
    password=parsed_url.password,
    **connection_kwargs,
)

dramatiq.set_broker(redis_broker)


# --- 任務定義 (Actors) ---


@dramatiq.actor
def task_update_schedule_and_reschedule():
    """
    【Dramatiq版】這是一個背景任務，負責執行完整的賽程更新與排程器重設。
    """
    from app.scheduler import setup_scheduler

    logger.info("--- Dramatiq Worker: 已接收到賽程更新任務，開始執行 ---")
    try:
        schedule_scraper.scrape_cpbl_schedule(2025, 3, 10, include_past_games=True)
        setup_scheduler()
        logger.info("--- Dramatiq Worker: 賽程更新任務執行完畢 ---")
    except Exception as e:
        logger.error(
            f"Dramatiq Worker 在執行賽程更新任務時發生嚴重錯誤: {e}", exc_info=True
        )


@dramatiq.actor
def task_scrape_single_day(date_str: Optional[str] = None):
    """
    【Dramatiq版】抓取單日比賽數據的任務。
    """
    logger.info(f"--- Dramatiq Worker: 執行單日爬蟲任務 for {date_str or '今天'} ---")
    try:
        scraper.scrape_single_day(date_str)
        logger.info(
            f"--- Dramatiq Worker: 單日爬蟲任務 for {date_str or '今天'} 執行完畢 ---"
        )
    except Exception as e:
        logger.error(
            f"Dramatiq Worker 在執行單日爬蟲任務時發生嚴重錯誤: {e}", exc_info=True
        )


@dramatiq.actor
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
    except Exception as e:
        logger.error(
            f"Dramatiq Worker 在執行逐月爬蟲任務時發生嚴重錯誤: {e}", exc_info=True
        )


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
