# app/tasks.py

import logging
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from typing import Optional

# 專案內部模組
from app.logging_config import setup_logging
from app.config import settings
from app.core import schedule_scraper

# 【核心修正】: 移除此處的 scheduler 匯入，以打破循環依賴
# from app.scheduler import setup_scheduler
from app import scraper

setup_logging()
redis_broker = RedisBroker(url=settings.DRAMATIQ_BROKER_URL)
dramatiq.set_broker(redis_broker)
logger = logging.getLogger(__name__)


# --- 任務定義 (Actors) ---


@dramatiq.actor
def task_update_schedule_and_reschedule():
    """
    【Dramatiq版】這是一個背景任務，負責執行完整的賽程更新與排程器重設。
    """
    # 【核心修正】: 將 scheduler 的匯入移至函式內部
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
