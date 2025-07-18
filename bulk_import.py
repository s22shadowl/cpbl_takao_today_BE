import os
import logging
import time
from datetime import date, timedelta

from dotenv import load_dotenv
from sqlalchemy.orm import Session

# 匯入你的資料庫設定與爬蟲核心邏輯
# 【注意】請根據你的專案結構，確認以下 import 路徑是否正確
from app.db import SessionLocal
from app.scraper import scrape_single_day
from app.logging_config import setup_logging

# 設定日誌
setup_logging()
logger = logging.getLogger(__name__)


def bulk_scrape_date_range(db: Session, start_date: date, end_date: date):
    """
    遍歷指定日期範圍，對每一天執行爬蟲並將資料存入資料庫。

    :param db: SQLAlchemy Session 物件。
    :param start_date: 開始日期。
    :param end_date: 結束日期。
    """
    current_date = start_date
    total_days = (end_date - start_date).days + 1
    day_count = 0

    logger.info(f"準備開始批次爬取，範圍: {start_date} 至 {end_date}")

    while current_date <= end_date:
        day_count += 1
        date_str = current_date.strftime("%Y-%m-%d")
        logger.info(f"({day_count}/{total_days}) - 正在處理日期: {date_str}")

        try:
            # 直接呼叫爬蟲的核心函式
            # 假設 scrape_single_day 接收 db session 和日期字串
            scrape_single_day(db, date_str)
            logger.info(f"成功完成日期: {date_str}")
        except Exception as e:
            # 即使某一天失敗，也記錄下來並繼續
            logger.error(f"處理日期 {date_str} 時發生錯誤: {e}", exc_info=True)

        # 為了避免對目標網站造成過大壓力，在每次請求間加入延遲
        time.sleep(5)  # 暫停 5 秒，可以根據情況調整

        current_date += timedelta(days=1)

    logger.info("所有日期的批次爬取任務已完成。")


if __name__ == "__main__":
    # 載入 .env.prod 檔案中的環境變數
    env_path = os.path.join(os.path.dirname(__file__), ".env.prod")
    if not os.path.exists(env_path):
        logger.error("錯誤: 找不到環境設定檔 .env.prod。請先建立此檔案。")
    else:
        logger.info("成功載入 .env.prod 設定檔。")
        load_dotenv(dotenv_path=env_path)

        # 建立資料庫連線
        db_session = SessionLocal()

        try:
            # --- 在這裡設定你要爬取的日期範圍 ---
            START_DATE = date(2025, 3, 1)
            END_DATE = date.today()
            # ------------------------------------

            bulk_scrape_date_range(
                db=db_session, start_date=START_DATE, end_date=END_DATE
            )
        finally:
            # 確保 session 被關閉
            db_session.close()
