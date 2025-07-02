# app/scheduler.py

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

# 修正：匯入新的 SQLAlchemy Session 工廠
from app.db import SessionLocal
from app import db_actions
# 【新】從 tasks 中匯入任務，因為排程器現在需要呼叫 Dramatiq 任務
from app.tasks import task_scrape_single_day

# 【核心修正】: 移除舊的 basicConfig，只取得 logger
# logger 會自動繼承由 app/tasks.py 或 app/main.py 初始化的全域設定
logger = logging.getLogger(__name__)

# 初始化排程器
scheduler = BackgroundScheduler(timezone="Asia/Taipei")

def _schedule_daily_scraper(game_date: str, game_time: str, matchup: str):
    """
    根據比賽日期和時間，計算並設定每日爬蟲的觸發時間。
    """
    if not game_time or not isinstance(game_time, str) or ":" not in game_time:
        logger.info(f"比賽 on {game_date} ({matchup}) 時間未定，將預設排程設定於 22:00。")
        game_time = "18:35"

    try:
        game_datetime_str = f"{game_date} {game_time}"
        naive_game_dt = datetime.strptime(game_datetime_str, "%Y-%m-%d %H:%M")
        aware_game_dt = naive_game_dt.astimezone(scheduler.timezone)
        
        run_date = aware_game_dt + timedelta(hours=3, minutes=30)
        
        if run_date > datetime.now(scheduler.timezone):
            job_id = f"daily_scrape_{game_date.replace('-', '')}_{game_time.replace(':', '')}"
            
            # 【核心修正】: add_job 的目標函式改為呼叫 Dramatiq 任務的 .send() 方法
            # 這確保了即使排程器在 API 行程中運行，實際的爬蟲也會在獨立的 worker 行程中執行
            scheduler.add_job(
                task_scrape_single_day.send,
                trigger=DateTrigger(run_date=run_date),
                args=[game_date],
                id=job_id,
                name=f"Daily scraper for {game_date} ({matchup})",
                replace_existing=True
            )
    except ValueError as ve:
        logger.error(f"解析時間字串時發生錯誤 for game {game_date} ('{game_datetime_str}'): {ve}")
    except Exception as e:
        logger.error(f"設定排程任務時發生未知錯誤 for game {game_date}: {e}")

def setup_scheduler(scrape_all_season: bool = False):
    """
    從資料庫讀取賽程，並設定所有每日爬蟲的排程。
    預設只會排程今天及未來的比賽。
    :param scrape_all_season: 若為 True，則會為資料庫中所有日期的比賽設定排程。
    """
    logger.info("正在啟動並設定比賽排程器...")
    
    if scheduler.running:
        scheduler.pause()

    scheduler.remove_all_jobs()
    logger.info("已移除所有舊的排程任務。")

    db = SessionLocal()
    try:
        schedules = db_actions.get_all_schedules(db)
    finally:
        db.close()

    if not schedules:
        logger.warning("資料庫中沒有找到任何比賽排程，排程器將不會設定任何任務。")
    else:
        today = datetime.now(scheduler.timezone).date()
        scheduled_count = 0
        for game in schedules:
            try:
                game_date_str = game.game_date.strftime("%Y-%m-%d")
                game_date_obj = game.game_date
                
                if not scrape_all_season and game_date_obj < today:
                    continue
            except (ValueError, TypeError, AttributeError):
                logger.warning(f"跳過比賽，因日期格式錯誤或物件屬性問題: {game}")
                continue

            _schedule_daily_scraper(game_date_str, game.game_time, game.matchup)
            scheduled_count += 1
        logger.info(f"排程設定完成，共處理了 {scheduled_count} 場比賽。")

    if scheduler.state == 2: # 2 is STATE_PAUSED
        scheduler.resume()
        logger.info("排程器已恢復運行。")
    elif not scheduler.running:
        scheduler.start()
        logger.info("排程器已成功啟動。")

    jobs = scheduler.get_jobs()
    if jobs:
        try:
            next_job = min(jobs, key=lambda job: job.next_run_time)
            logger.info(f"--- 下一次排程任務 ---")
            logger.info(f"執行時間: {next_job.next_run_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            logger.info(f"任務內容: {next_job.name}")
            logger.info(f"----------------------")
        except Exception as e:
            logger.error(f"尋找下一個任務時發生錯誤: {e}")
    else:
        logger.info("目前沒有任何已排程的未來任務。")