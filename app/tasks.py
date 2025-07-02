# app/tasks.py

import logging
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from typing import Optional

# 專案內部模組
from app.config import settings
from app.core import schedule_scraper
from app.scheduler import setup_scheduler
# 【新】匯入 scraper 模組，以便呼叫其中的函式
from app import scraper

# --- Dramatiq Broker 設定 ---
redis_broker = RedisBroker(url=settings.DRAMATIQ_BROKER_URL)
dramatiq.set_broker(redis_broker)

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s'
)
task_logger = logging.getLogger(__name__)


# --- 任務定義 (Actors) ---

@dramatiq.actor
def task_update_schedule_and_reschedule():
    """
    【Dramatiq版】這是一個背景任務，負責執行完整的賽程更新與排程器重設。
    """
    task_logger.info("--- Dramatiq Worker: 已接收到賽程更新任務，開始執行 ---")
    try:
        schedule_scraper.scrape_cpbl_schedule(2025, 3, 10, include_past_games=True)
        setup_scheduler()
        task_logger.info("--- Dramatiq Worker: 賽程更新任務執行完畢 ---")
    except Exception as e:
        task_logger.error(f"Dramatiq Worker 在執行賽程更新任務時發生嚴重錯誤: {e}", exc_info=True)

# 【新】每日爬蟲任務
@dramatiq.actor
def task_scrape_single_day(date_str: Optional[str] = None):
    """
    【Dramatiq版】抓取單日比賽數據的任務。
    """
    task_logger.info(f"--- Dramatiq Worker: 執行單日爬蟲任務 for {date_str or '今天'} ---")
    try:
        scraper.scrape_single_day(date_str)
        task_logger.info(f"--- Dramatiq Worker: 單日爬蟲任務 for {date_str or '今天'} 執行完畢 ---")
    except Exception as e:
        task_logger.error(f"Dramatiq Worker 在執行單日爬蟲任務時發生嚴重錯誤: {e}", exc_info=True)

# 【新】每月爬蟲任務
@dramatiq.actor
def task_scrape_entire_month(month_str: Optional[str] = None):
    """
    【Dramatiq版】抓取整月比賽數據的任務。
    """
    task_logger.info(f"--- Dramatiq Worker: 執行逐月爬蟲任務 for {month_str or '本月'} ---")
    try:
        scraper.scrape_entire_month(month_str)
        task_logger.info(f"--- Dramatiq Worker: 逐月爬蟲任務 for {month_str or '本月'} 執行完畢 ---")
    except Exception as e:
        task_logger.error(f"Dramatiq Worker 在執行逐月爬蟲任務時發生嚴重錯誤: {e}", exc_info=True)

# 【新】每年爬蟲任務
@dramatiq.actor
def task_scrape_entire_year(year_str: Optional[str] = None):
    """
    【Dramatiq版】抓取全年比賽數據的任務。
    """
    task_logger.info(f"--- Dramatiq Worker: 執行逐年爬蟲任務 for {year_str or '今年'} ---")
    try:
        scraper.scrape_entire_year(year_str)
        task_logger.info(f"--- Dramatiq Worker: 逐年爬蟲任務 for {year_str or '今年'} 執行完畢 ---")
    except Exception as e:
        task_logger.error(f"Dramatiq Worker 在執行逐年爬蟲任務時發生嚴重錯誤: {e}", exc_info=True)