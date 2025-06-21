# app/scraper.py

import datetime
import time
import logging
import argparse
import os

from app import config
from app.core import fetcher
from app.core import parser as html_parser
import app.db_actions as db_actions
from app.db import get_db_connection

# --- 【日誌設定】 ---
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s', 
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "scraper.log"), mode='a', encoding='utf-8'), 
        logging.StreamHandler()
    ]
)
# --- 【日誌設定】 ---

# --- 主要爬蟲邏輯函式 ---

def scrape_and_store_season_stats():
    """抓取並儲存目標球員的球季累積數據。"""
    club_no = config.TEAM_CLUB_CODES.get(config.TARGET_TEAM_NAME)
    if not club_no:
        logging.error(f"在設定中找不到球隊 [{config.TARGET_TEAM_NAME}] 的代碼 (ClubNo)。")
        return

    team_stats_url = f"{config.TEAM_SCORE_URL}?ClubNo={club_no}"
    logging.info(f"--- 開始抓取球季累積數據，URL: {team_stats_url} ---")
    
    html_content = fetcher.get_dynamic_page_content(team_stats_url, wait_for_selector="div.RecordTable")
    if not html_content:
        logging.error("無法獲取球隊數據頁面內容。")
        return
    
    season_stats_list = html_parser.parse_season_stats_page(html_content)
    if not season_stats_list:
        logging.info("未解析到任何目標球員的球季數據。")
        return
        
    conn = get_db_connection()
    try:
        db_actions.update_player_season_stats(conn, season_stats_list)
    finally:
        if conn:
            conn.close()
    
    logging.info(f"--- 球季累積數據抓取完畢 ---")


def _process_filtered_games(games_to_process):
    """【內部輔助函式】處理已篩選的比賽列表，儲存數據並抓取 Box Score。"""
    if not games_to_process:
        logging.info("此時間範圍內沒有需要處理的已完成比賽。")
        return

    logging.info(f"準備處理 {len(games_to_process)} 場已篩選的比賽...")
    conn = get_db_connection()
    try:
        for game_info in games_to_process:
            if game_info.get('status') != "已完成":
                logging.info(f"跳過未完成的比賽 (CPBL ID: {game_info.get('cpbl_game_id')})")
                continue

            if config.TARGET_TEAM_NAME in [game_info.get('home_team'), game_info.get('away_team')]:
                logging.info(f"處理目標球隊 [{config.TARGET_TEAM_NAME}] 的比賽 (CPBL ID: {game_info.get('cpbl_game_id')})...")
                
                game_id_in_db = db_actions.store_game_and_get_id(conn, game_info)
                if not game_id_in_db:
                    logging.warning(f"未能儲存比賽結果或獲取 DB game_id，跳過處理此比賽。")
                    continue

                box_score_url = game_info.get('box_score_url')
                if not box_score_url:
                    logging.warning(f"比賽 (DB game_id: {game_id_in_db}) 缺少 Box Score URL。")
                    continue
                
                box_score_html = fetcher.get_dynamic_page_content(box_score_url, wait_for_selector="div.GameBoxDetail")
                time.sleep(config.FRIENDLY_SCRAPING_DELAY)

                if box_score_html:
                    # 【修改處】使用新的別名 html_parser
                    all_players_data = html_parser.parse_box_score_page(box_score_html)
                    if all_players_data:
                        db_actions.store_player_game_data(conn, game_id_in_db, all_players_data)
            else:
                logging.info(f"跳過非目標球隊的比賽: {game_info.get('away_team')} @ {game_info.get('home_team')}")
    finally:
        if conn:
            conn.close()


# --- 主要的、可被外部呼叫的任務函式 ---

def scrape_single_day(specific_date=None):
    """【功能一】專門抓取並處理指定單日的比賽數據。"""
    today = datetime.date.today()
    target_date_str = specific_date if specific_date else today.strftime("%Y-%m-%d")
    logging.info(f"--- 開始執行 [單日模式]，目標日期: {target_date_str} ---")
    
    try:
        target_date_obj = datetime.datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except ValueError:
        logging.error(f"日期格式錯誤: {target_date_str}")
        return
        
    if target_date_obj > today:
        logging.warning(f"目標日期 {target_date_str} 是未來日期，任務中止。")
        return

    scrape_and_store_season_stats()
    
    html_content = fetcher.fetch_schedule_page(target_date_obj.year, target_date_obj.month)
    if not html_content:
        logging.info(f"--- [單日模式] 因無法獲取月賽程而中止 ---")
        return

    all_month_games = html_parser.parse_schedule_page(html_content, target_date_obj.year)
    games_for_day = [game for game in all_month_games if game.get('game_date') == target_date_str]
    _process_filtered_games(games_for_day)
    logging.info(f"--- [單日模式] 執行完畢 ---")

def scrape_entire_month(month_str=None):
    """【功能二】專門抓取並處理指定月份的所有「已完成」比賽數據。"""
    today = datetime.date.today()
    target_date_obj = datetime.datetime.strptime(month_str, "%Y-%m").date().replace(day=1) if month_str else today.replace(day=1)
    logging.info(f"--- 開始執行 [逐月模式]，目標月份: {target_date_obj.strftime('%Y-%m')} ---")
    
    if target_date_obj.year > today.year or (target_date_obj.year == today.year and target_date_obj.month > today.month):
        logging.warning(f"目標月份 {target_date_obj.strftime('%Y-%m')} 是未來月份，任務中止。")
        return

    html_content = fetcher.fetch_schedule_page(target_date_obj.year, target_date_obj.month)
    if not html_content: return
        
    all_month_games = html_parser.parse_schedule_page(html_content, target_date_obj.year)
    
    if target_date_obj.year == today.year and target_date_obj.month == today.month:
        games_to_process = [game for game in all_month_games if datetime.datetime.strptime(game['game_date'], "%Y-%m-%d").date() <= today]
        _process_filtered_games(games_to_process)
    else:
        _process_filtered_games(all_month_games)
        
    logging.info(f"--- [逐月模式] 執行完畢 ---")

def scrape_entire_year(year_str=None):
    """【功能三】專門抓取並處理指定年份的所有「已完成」比賽數據。"""
    today = datetime.date.today()
    year_to_scrape = int(year_str) if year_str else today.year
    logging.info(f"--- 開始執行 [逐年模式]，目標年份: {year_to_scrape} ---")

    if year_to_scrape > today.year:
        logging.warning(f"目標年份 {year_to_scrape} 是未來年份，任務中止。")
        return
        
    end_month = today.month if year_to_scrape == today.year else 11
    start_month = 3
    
    for month in range(start_month, end_month + 1):
        html_content = fetcher.fetch_schedule_page(year_to_scrape, month)
        if html_content:
            all_month_games = html_parser.parse_schedule_page(html_content, year_to_scrape)
            logging.info(f"月份 {year_to_scrape}-{month:02d} 共解析到 {len(all_month_games)} 場比賽。")
            if all_month_games:
                games_to_process = [game for game in all_month_games if datetime.datetime.strptime(game['game_date'], "%Y-%m-%d").date() <= today]
                _process_filtered_games(games_to_process)
        logging.info(f"處理完 {year_to_scrape}-{month:02d}，稍作等待...")
        time.sleep(config.FRIENDLY_SCRAPING_DELAY)
    logging.info(f"--- [逐年模式] 執行完畢 ---")

# --- 命令列執行入口 ---
if __name__ == '__main__':
    # 此處的 parser 變數只作用在此區塊，不會與上方導入的模組衝突
    parser = argparse.ArgumentParser(description="CPBL 數據爬蟲手動執行工具")
    subparsers = parser.add_subparsers(dest='mode', help='執行模式 (daily, monthly, yearly)', required=True)

    parser_daily = subparsers.add_parser('daily', help='抓取指定單日的數據 (預設為今天)')
    parser_daily.add_argument('date', nargs='?', default=None, help="可選，指定日期，格式為YYYY-MM-DD")

    parser_monthly = subparsers.add_parser('monthly', help='抓取指定月份的所有數據 (預設為本月)')
    parser_monthly.add_argument('month', nargs='?', default=None, help="可選，指定月份，格式為YYYY-MM")
    
    parser_yearly = subparsers.add_parser('yearly', help='抓取指定年份的所有數據 (預設為本年)')
    parser_yearly.add_argument('year', nargs='?', default=None, help="可選，指定年份，格式為YYYY")
    
    args = parser.parse_args()

    # 根據參數調用對應的功能函式
    if args.mode == 'daily':
        if args.date:
            try:
                datetime.datetime.strptime(args.date, "%Y-%m-%d")
                scrape_single_day(specific_date=args.date)
            except ValueError:
                print("\n錯誤：日期格式不正確。請使用YYYY-MM-DD 格式。\n")
        else:
            scrape_single_day()
    elif args.mode == 'monthly':
        if args.month:
            try:
                datetime.datetime.strptime(args.month, "%Y-%m")
                scrape_entire_month(month_str=args.month)
            except ValueError:
                print("\n錯誤：月份格式不正確。請使用YYYY-MM 格式。\n")
        else:
            scrape_entire_month()
    elif args.mode == 'yearly':
        if args.year:
            try:
                if not (args.year.isdigit() and len(args.year) == 4): raise ValueError
                scrape_entire_year(year_str=args.year)
            except ValueError:
                print("\n錯誤：年份格式不正確。請使用YYYY 格式（例如：2025）。\n")
        else:
            scrape_entire_year()