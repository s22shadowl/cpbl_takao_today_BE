# app/tasks.py

import logging
import dramatiq
from dramatiq.brokers.redis import RedisBroker

# 專案內部模組
from app.config import settings
from app.core import schedule_scraper
from app.scheduler import setup_scheduler

# --- Dramatiq Broker 設定 ---
# 根據 .env 中的設定，建立一個 Redis Broker
# 這會告訴 Dramatiq 如何連接到我們的 Redis 服務
redis_broker = RedisBroker(url=settings.DRAMATIQ_BROKER_URL)
dramatiq.set_broker(redis_broker)

# --- 日誌設定 ---
# 確保在獨立的 worker 行程中也能看到日誌
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s'
)
task_logger = logging.getLogger(__name__)


# --- 任務定義 (Actors) ---

# @dramatiq.actor 是一個裝飾器，它會將一個普通的 Python 函式
# 轉換為一個可以被背景 Worker 執行的「任務」(Actor)。
@dramatiq.actor
def task_update_schedule_and_reschedule():
    """
    【Dramatiq版】這是一個背景任務，負責執行完整的賽程更新與排程器重設。
    這個函式將會在獨立的 Dramatiq worker 行程中執行。
    """
    task_logger.info("--- Dramatiq Worker: 已接收到賽程更新任務，開始執行 ---")
    try:
        # 執行耗時的爬蟲任務
        schedule_scraper.scrape_cpbl_schedule(2025, 3, 10, include_past_games=True)
        
        # 重新設定排程器
        setup_scheduler()
        
        task_logger.info("--- Dramatiq Worker: 賽程更新任務執行完畢 ---")
    except Exception as e:
        task_logger.error(f"Dramatiq Worker 在執行賽程更新任務時發生嚴重錯誤: {e}", exc_info=True)

# 未來可以定義更多任務，例如：
# @dramatiq.actor
# def task_scrape_single_day(date_str: str):
#     """
#     【Dramatiq版】抓取單日比賽的任務
#     """
#     task_logger.info(f"--- Dramatiq Worker: 執行單日爬蟲任務 for {date_str} ---")
#     from app.scraper import scrape_single_day
#     scrape_single_day(date_str)