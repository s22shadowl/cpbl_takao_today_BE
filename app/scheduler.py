# app/scheduler.py

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from app.db import get_db_connection
from app import db_actions, scraper

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
scheduler_logger = logging.getLogger(__name__)

# 初始化排程器
scheduler = BackgroundScheduler(timezone="Asia/Taipei")

def _schedule_daily_scraper(game_date: str, game_time: str, matchup: str):
    """
    根據比賽日期和時間，計算並設定每日爬蟲的觸發時間。
    """
    try:
        game_datetime_str = f"{game_date} {game_time}"
        # 1. 解析出一個 "天真" 的時間物件
        naive_game_dt = datetime.strptime(game_datetime_str, "%Y-%m-%d %H:%M")
        
        # 2. 【核心修改處】將 "天真" 的時間物件，轉換為帶有排程器時區的 "聰明" 時間物件
        aware_game_dt = naive_game_dt.astimezone(scheduler.timezone)

        # 3. 根據 "聰明" 時間計算觸發時間
        run_date = aware_game_dt + timedelta(hours=3, minutes=30)
        
        # 4. 用 "聰明" 的時間進行比較
        if run_date > datetime.now(scheduler.timezone):
            job_id = f"daily_scrape_{game_date.replace('-', '')}_{game_time.replace(':', '')}"
            
            scheduler.add_job(
                scraper.scrape_single_day,
                trigger=DateTrigger(run_date=run_date),
                args=[game_date],
                id=job_id,
                name=f"Daily scraper for {game_date} ({matchup})",
                replace_existing=True
            )
    except Exception as e:
        scheduler_logger.error(f"設定排程任務時發生錯誤 for game {game_date}: {e}")

def setup_scheduler():
    """
    從資料庫讀取賽程，並設定所有每日爬蟲的排程。
    """
    scheduler_logger.info("正在啟動並設定比賽排程器...")
    
    scheduler.remove_all_jobs()
    scheduler_logger.info("已移除所有舊的排程任務。")

    conn = get_db_connection()
    try:
        schedules = db_actions.get_all_schedules(conn)
    finally:
        conn.close()

    if not schedules:
        scheduler_logger.warning("資料庫中沒有找到任何比賽排程，排程器將不會設定任何任務。")
        if not scheduler.running:
            scheduler.start()
        return

    for game in schedules:
        _schedule_daily_scraper(game['game_date'], game['game_time'], game['matchup'])
    
    # 顯示下一次最近的排程時間
    jobs = scheduler.get_jobs()
    if jobs:
        next_job = min(jobs, key=lambda job: job.next_run_time)
        scheduler_logger.info(f"--- 下一次排程任務 ---")
        scheduler_logger.info(f"執行時間: {next_job.next_run_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        scheduler_logger.info(f"任務內容: {next_job.name}")
        scheduler_logger.info(f"----------------------")
    else:
        scheduler_logger.info("目前沒有任何已排程的未來任務。")

    if not scheduler.running:
        scheduler.start()
        scheduler_logger.info("排程器已成功啟動。")