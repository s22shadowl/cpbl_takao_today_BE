# app/core/schedule_scraper.py

import logging
import json
from typing import List, Dict, Optional

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

from app import config
from app.db import get_db_connection
from app import db_actions

def scrape_cpbl_schedule(year: int, start_month: int, end_month: int) -> List[Dict[str, Optional[str]]]:
    """
    從中華職棒官網爬取指定年份和月份區間的賽程，並篩選目標球隊，最終存入資料庫。
    """
    schedule_page_url = "https://www.cpbl.com.tw/schedule"
    all_games: List[Dict[str, Optional[str]]] = []
    scraped_game_ids = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        logging.info(f"正在啟動瀏覽器並前往 {schedule_page_url}...")
        page.goto(schedule_page_url, timeout=60000)

        try:
            page.wait_for_selector(".ScheduleSearch .month select", timeout=20000)
        except Exception as e:
            logging.error(f"錯誤：頁面載入超時或找不到關鍵元件。 {e}")
            browser.close()
            return []
        
        logging.info("頁面載入完成。")

        for month in range(start_month, end_month + 1):
            try:
                logging.info(f"正在設定查詢條件： {year} 年 {month} 月")
                
                page.select_option(".ScheduleSearch .year select", value=str(year))
                page.select_option(".ScheduleSearch .month select", value=str(month - 1))
                
                # 等待 Vue.js 透過 AJAX 更新內容
                page.wait_for_selector(".blockUI", state="hidden", timeout=15000)
                logging.info(f"取得 {year} 年 {month} 月的資料成功。")

                html_content = page.content()
                soup = BeautifulSoup(html_content, 'html.parser')
                
                schedule_table = soup.find('div', class_='ScheduleTableList')
                if not schedule_table:
                    logging.info(f"{year} 年 {month} 月沒有賽程資料。")
                    continue
                    
                game_rows = schedule_table.find('tbody').find_all('tr')
                current_date = ""

                for row in game_rows:
                    date_cell = row.find('td', class_='date')
                    if date_cell:
                        current_date_text = date_cell.get_text(strip=True).split('(')[0].strip()
                        current_date = f"{year}-{current_date_text.replace('/', '-')}"

                    game_id_cell = row.find('td', class_='game_no')
                    team_cell = row.find('td', class_='team')
                    info_cell = row.find('td', class_='info')

                    if not all([game_id_cell, team_cell, info_cell]):
                        continue
                    
                    game_id = game_id_cell.get_text(strip=True)
                    if game_id in scraped_game_ids:
                        continue

                    away_team = team_cell.find('div', class_='name away').get_text(strip=True)
                    home_team = team_cell.find('div', class_='name home').get_text(strip=True)

                    if config.TARGET_TEAM_NAME not in [home_team, away_team]:
                        continue

                    start_time = info_cell.find('div', class_='time').find('span').get_text(strip=True) if info_cell.find('div', class_='time') else ""
                    
                    game_info = {
                        "date": current_date,
                        "game_id": game_id,
                        "matchup": f"{away_team} vs {home_team}",
                        "time": start_time
                    }
                    all_games.append(game_info)
                    scraped_game_ids.add(game_id)
            
            except Exception as e:
                logging.error(f"錯誤：處理 {year} 年 {month} 月資料時發生未知錯誤: {e}")

        browser.close()
        logging.info(f"\n爬取完成，總共取得 {len(all_games)} 場目標球隊的比賽。")
        
        # 【核心修改處 2】將爬取到的賽程存入資料庫
        if all_games:
            conn = get_db_connection()
            try:
                db_actions.update_game_schedules(conn, all_games)
            finally:
                conn.close()

        return all_games

if __name__ == '__main__':
    TARGET_YEAR = 2025
    START_MONTH = 3
    END_MONTH = 10
    
    schedule_data = scrape_cpbl_schedule(TARGET_YEAR, START_MONTH, END_MONTH)

    if schedule_data:
        print("\n--- 爬取結果 ---")
        print(json.dumps(schedule_data, indent=2, ensure_ascii=False))