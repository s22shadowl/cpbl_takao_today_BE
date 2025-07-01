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
    if not game_time or not isinstance(game_time, str) or ":" not in game_time:
        scheduler_logger.info(f"比賽 on {game_date} ({matchup}) 時間未定，將預設排程設定於 22:00。")
        game_time = "18:35"

    try:
        game_datetime_str = f"{game_date} {game_time}"
        naive_game_dt = datetime.strptime(game_datetime_str, "%Y-%m-%d %H:%M")
        aware_game_dt = naive_game_dt.astimezone(scheduler.timezone)
        
        # 【修正】: 觸發時間應為比賽時間本身，而非再往後加。
        # 排程器會在指定時間點執行 scraper.scrape_single_day，這個爬蟲本身應處理比賽是否已結束。
        # 若要維持賽後 3.5 小時觸發，則 run_date 的計算是正確的。此處暫不修改。
        run_date = aware_game_dt + timedelta(hours=3, minutes=30)
        
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
    except ValueError as ve:
        scheduler_logger.error(f"解析時間字串時發生錯誤 for game {game_date} ('{game_datetime_str}'): {ve}")
    except Exception as e:
        scheduler_logger.error(f"設定排程任務時發生未知錯誤 for game {game_date}: {e}")

def setup_scheduler(scrape_all_season: bool = False):
    """
    從資料庫讀取賽程，並設定所有每日爬蟲的排程。
    預設只會排程今天及未來的比賽。
    :param scrape_all_season: 若為 True，則會為資料庫中所有日期的比賽設定排程。
    """
    scheduler_logger.info("正在啟動並設定比賽排程器...")
    
    if scheduler.running:
        scheduler.pause()

    scheduler.remove_all_jobs()
    scheduler_logger.info("已移除所有舊的排程任務。")

    conn = get_db_connection()
    try:
        schedules = db_actions.get_all_schedules(conn)
    finally:
        conn.close()

    if not schedules:
        scheduler_logger.warning("資料庫中沒有找到任何比賽排程，排程器將不會設定任何任務。")
    else:
        today = datetime.now(scheduler.timezone).date()
        scheduled_count = 0
        for game in schedules:
            try:
                game_date_obj = datetime.strptime(game['game_date'], "%Y-%m-%d").date()
                if not scrape_all_season and game_date_obj < today:
                    continue
            except (ValueError, TypeError):
                scheduler_logger.warning(f"跳過比賽，因日期格式錯誤: {game.get('game_date')}")
                continue

            _schedule_daily_scraper(game['game_date'], game['game_time'], game.get('matchup', 'N/A'))
            scheduled_count += 1
        scheduler_logger.info(f"排程設定完成，共處理了 {scheduled_count} 場比賽。")

    # 【核心修正】: 將 '顯示下一次任務' 的邏輯移到 scheduler 啟動之後
    if scheduler.state == 2: # 2 is STATE_PAUSED
        scheduler.resume()
        scheduler_logger.info("排程器已恢復運行。")
    elif not scheduler.running:
        scheduler.start()
        scheduler_logger.info("排程器已成功啟動。")

    # 在排程器確定運行後，才安全地取得任務資訊
    jobs = scheduler.get_jobs()
    if jobs:
        try:
            next_job = min(jobs, key=lambda job: job.next_run_time)
            scheduler_logger.info(f"--- 下一次排程任務 ---")
            scheduler_logger.info(f"執行時間: {next_job.next_run_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            scheduler_logger.info(f"任務內容: {next_job.name}")
            scheduler_logger.info(f"----------------------")
        except Exception as e:
            scheduler_logger.error(f"尋找下一個任務時發生錯誤: {e}")
    else:
        scheduler_logger.info("目前沒有任何已排程的未來任務。")
