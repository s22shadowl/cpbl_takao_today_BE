# app/scraper.py

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import sqlite3
import datetime
import time
import logging
import os
from urllib.parse import urlparse, parse_qs
import argparse

# 假設 db.py 在同一層級的 app/ 目錄下
from .db import get_db_connection

# --- 設定目標球隊與球員 ---
TARGET_TEAM_NAME = "台鋼雄鷹"
TARGET_PLAYER_NAMES = ["王柏融", "魔鷹", "吳念庭"]

# 建立球隊代碼的對應字典，方便動態產生 URL
TEAM_CLUB_CODES = {
    "中信兄弟": "ACN",
    "統一7-ELEVEn獅": "ADD",
    "樂天桃猿": "AJL",
    "富邦悍將": "AEO",
    "味全龍": "AAA",
    "台鋼雄鷹": "AKP"
}

# --- 設定日誌 ---
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s', handlers=[logging.FileHandler(os.path.join(LOG_DIR, "scraper.log"), mode='a', encoding='utf-8'), logging.StreamHandler()])

# --- 輔助函式：獲取網頁內容 ---
def get_static_page_content(url):
    """使用 requests 獲取靜態網頁內容"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        logging.error(f"請求 URL {url} 失敗: {e}")
        return None

def get_dynamic_page_content(url, click_selector=None, wait_for_selector=None, timeout=60000):
    """使用 Playwright 獲取動態網頁內容。"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            logging.info(f"Playwright: 導航至 {url}")
            page.goto(url, timeout=timeout)
            if click_selector:
                logging.info(f"Playwright: 正在點擊元素 '{click_selector}'")
                page.click(click_selector)
            if wait_for_selector:
                logging.info(f"Playwright: 正在等待元素 '{wait_for_selector}' 變為可見")
                page.wait_for_selector(wait_for_selector, state='visible', timeout=timeout)
            else:
                page.wait_for_load_state('networkidle', timeout=timeout)
            logging.info("Playwright: 頁面元素已載入，正在獲取內容。")
            content = page.content()
            browser.close()
            return content
    except Exception as e:
        logging.error(f"使用 Playwright 獲取 URL {url} 失敗: {e}", exc_info=True)
        return None
    
# --- 抓取球季累積數據 ---
def scrape_and_store_season_stats(conn):
    """
    【擴充版】抓取並儲存目標球隊中，目標球員的所有球季累積數據。
    """
    club_no = TEAM_CLUB_CODES.get(TARGET_TEAM_NAME)
    if not club_no:
        logging.error(f"在 TEAM_CLUB_CODES 字典中找不到球隊 [{TARGET_TEAM_NAME}] 的代碼 (ClubNo)。")
        return

    team_stats_url = f"https://www.cpbl.com.tw/team/teamscore?ClubNo={club_no}"
    logging.info(f"--- 開始抓取球季累積數據，URL: {team_stats_url} ---")
    
    html_content = get_dynamic_page_content(team_stats_url, wait_for_selector="div.RecordTable")
    if not html_content:
        logging.error("無法獲取球隊數據頁面內容。")
        return
        
    soup = BeautifulSoup(html_content, 'lxml')
    cursor = conn.cursor()

    batting_table = soup.find('div', class_='RecordTable')
    if not batting_table:
        logging.warning("在球隊頁面找不到打擊數據表格 (class='RecordTable')。")
        return

    tbody = batting_table.find('tbody')
    if not tbody:
        logging.warning("在打擊數據表格中找不到 tbody 元素。")
        return
        
    player_rows = tbody.find_all('tr')
    
    # 建立一個完整的 mapping 來對應中文標題和資料庫欄位
    header_map = {
        '出賽數': 'games_played', '打席': 'plate_appearances', '打數': 'at_bats',
        '打點': 'rbi', '得分': 'runs_scored', '安打': 'hits', '一安': 'singles',
        '二安': 'doubles', '三安': 'triples', '全壘打': 'homeruns', '壘打數': 'total_bases',
        '被三振': 'strikeouts', '盜壘': 'stolen_bases', '上壘率': 'obp',
        '長打率': 'slg', '打擊率': 'avg', '雙殺打': 'gidp', '犧短': 'sacrifice_hits',
        '犧飛': 'sacrifice_flies', '四壞球': 'walks', '（故四）': 'intentional_walks',
        '死球': 'hit_by_pitch', '盜壘刺': 'caught_stealing', '滾地出局': 'ground_outs',
        '高飛出局': 'fly_outs', '滾飛出局比': 'go_ao_ratio', '盜壘率': 'sb_percentage',
        '整體攻擊指數': 'ops', '銀棒指數': 'silver_slugger_index'
    }
    
    header_cells = [h.text.strip() for h in player_rows[0].find_all('th')]
    player_data_rows = player_rows[1:] # 實際的球員數據從第二行開始

    for row in player_data_rows:
        cells = row.find_all('td')
        if not cells or len(cells) < 2: continue # 確保有足夠的欄位

        player_name_cell = cells[0].find('a')
        player_name = player_name_cell.text.strip() if player_name_cell else cells[0].text.strip()

        if player_name in TARGET_PLAYER_NAMES:
            logging.info(f"找到目標球員 [{player_name}] 的球季累積數據，準備提取...")
            try:
                stats_data = {
                    "player_name": player_name,
                    "team_name": TARGET_TEAM_NAME,
                    "data_retrieved_date": datetime.date.today().strftime("%Y-%m-%d"),
                }
                
                # 根據標題和 mapping 動態提取所有統計數據
                for i, header_text in enumerate(header_cells):
                    db_col_name = header_map.get(header_text)
                    if db_col_name and (i < len(cells)):
                        value_str = cells[i].text.strip()
                        # 處理浮點數欄位
                        if db_col_name in ['avg', 'obp', 'slg', 'ops', 'go_ao_ratio', 'sb_percentage', 'silver_slugger_index']:
                            stats_data[db_col_name] = float(value_str) if value_str and value_str != '.' else 0.0
                        # 處理整數欄位
                        else:
                            stats_data[db_col_name] = int(value_str) if value_str.isdigit() else 0
                
                # 建立一個與資料庫欄位順序完全一致的欄位列表
                db_fields_ordered = [
                    'player_name', 'team_name', 'data_retrieved_date', 'games_played', 'plate_appearances', 
                    'at_bats', 'runs_scored', 'hits', 'rbi', 'homeruns', 'singles', 'doubles', 'triples',
                    'total_bases', 'strikeouts', 'stolen_bases', 'gidp', 'sacrifice_hits', 
                    'sacrifice_flies', 'walks', 'intentional_walks', 'hit_by_pitch', 'caught_stealing',
                    'ground_outs', 'fly_outs', 'avg', 'obp', 'slg', 'ops', 'go_ao_ratio', 
                    'sb_percentage', 'silver_slugger_index'
                ]

                # 準備要插入的值，如果字典中沒有該鍵，則提供一個安全的預設值
                values_to_insert = [stats_data.get(field, 0) for field in db_fields_ordered]

                # 為了確保數據最新，先刪除舊記錄再插入
                cursor.execute("DELETE FROM player_season_stats WHERE player_name = ?", (player_name,))
                
                cursor.execute(
                    f"INSERT INTO player_season_stats ({', '.join(db_fields_ordered)}) VALUES ({', '.join(['?'] * len(db_fields_ordered))})",
                    values_to_insert
                )

                logging.info(f"成功儲存/更新球員 [{player_name}] 的完整球季累積數據。")

            except (IndexError, ValueError) as e:
                logging.error(f"解析球員 [{player_name}] 的累積數據時出錯: {e}", exc_info=True)

    conn.commit()
    logging.info(f"--- 球季累積數據抓取完畢 ---")

# --- 共用的資料處理函式 ---

def fetch_and_parse_monthly_schedule():
    """
    【步驟1】抓取並解析當月的賽程頁面，返回所有比賽的列表。
    """
    schedule_page_url = "https://www.cpbl.com.tw/schedule"
    logging.info(f"正在從 {schedule_page_url} 獲取賽程頁面...")
    html_content = get_dynamic_page_content(
        url=schedule_page_url,
        click_selector='a[title="列表顯示"]',
        wait_for_selector=".ScheduleTableList"
    )
    if not html_content:
        logging.error("無法獲取賽程頁面的動態 HTML 內容。")
        return []

    return parse_all_games_from_month_html(html_content)

def parse_all_games_from_month_html(html_content):
    """
    【步驟2】從給定的賽程頁面 HTML 內容中，解析出該月份「所有」的比賽基本資訊。
    """
    logging.info("開始從 HTML 內容中解析當月所有比賽...")
    soup = BeautifulSoup(html_content, 'lxml')
    parsed_games = []
    
    list_view_container = soup.select_one('div.tab_cont.list')
    if not list_view_container:
        logging.warning("在 HTML 中找不到 '列表顯示' (CSS selector: 'div.tab_cont.list') 的區塊。")
        return []
        
    schedule_table = list_view_container.find('div', class_='ScheduleTableList')
    if not schedule_table:
        logging.warning("在 '列表顯示' 區塊中找不到賽程表格 (class='ScheduleTableList')。")
        return []

    all_rows = schedule_table.find_all('tr')
    current_date_in_loop = None
    
    year = None
    first_box_link = schedule_table.find('a', href=lambda href: href and 'box' in href)
    if first_box_link:
        try:
            parsed_url = urlparse(first_box_link['href'])
            query_params = parse_qs(parsed_url.query)
            year = query_params.get('year', [None])[0]
            if year: logging.info(f"從頁面中解析到年份為: {year}")
        except Exception as e:
            logging.warning(f"解析年份時出錯: {e}")

    if not year:
        year = str(datetime.date.today().year)
        logging.warning(f"無法從 HTML 中解析年份，將使用當前年份: {year}")

    for row in all_rows:
        date_cell = row.find('td', class_='date')
        if date_cell:
            date_text = date_cell.text.strip().split('(')[0]
            month_str, day_str = date_text.split('/')
            current_date_in_loop = datetime.date(int(year), int(month_str), int(day_str))

        game_no_cell = row.find('td', class_='game_no')
        if not game_no_cell or not current_date_in_loop: continue

        try:
            game_data = {'game_date': current_date_in_loop.strftime('%Y-%m-%d')}
            box_link_tag = game_no_cell.find('a')
            if box_link_tag and box_link_tag.has_attr('href'):
                relative_url = box_link_tag['href']
                game_data['box_score_url'] = f"https://www.cpbl.com.tw{relative_url}" if relative_url.startswith('/') else f"https://www.cpbl.com.tw/{relative_url}"
                qs = parse_qs(urlparse(relative_url).query)
                game_data['cpbl_game_id'] = qs.get('gameSno', [None])[0]
            
            team_cell = row.find('td', class_='team')
            if team_cell:
                game_data['away_team'] = team_cell.find('div', class_='name away').text.strip()
                game_data['home_team'] = team_cell.find('div', class_='name home').text.strip()
                away_score_tag = team_cell.find('div', class_='num away')
                home_score_tag = team_cell.find('div', class_='num home')
                game_data['away_score'] = int(away_score_tag.text.strip()) if away_score_tag and away_score_tag.text.strip().isdigit() else None
                game_data['home_score'] = int(home_score_tag.text.strip()) if home_score_tag and home_score_tag.text.strip().isdigit() else None

            info_cell = row.find('td', class_='info')
            if info_cell:
                place_tag = info_cell.find('div', class_='place')
                game_data['venue'] = place_tag.span.text.strip() if place_tag and place_tag.span else None
                time_tag = info_cell.find('div', class_='time')
                game_data['game_time'] = time_tag.span.text.strip() if time_tag and time_tag.span else None
                play_time_tag = info_cell.find('div', class_='play_time')
                game_data['game_duration'] = play_time_tag.span.text.strip() if play_time_tag and play_time_tag.span else None
                
            remark_cell = row.find('td', class_='remark')
            if remark_cell:
                note_tag = remark_cell.find('div', class_='note')
                if note_tag:
                    game_data['status'] = note_tag.text.strip()
                elif game_data.get('home_score') is not None:
                    game_data['status'] = '已完成'
                else:
                    game_data['status'] = '未開始'
            
            parsed_games.append(game_data)
        except Exception as e:
            logging.error(f"解析單場比賽概要時出錯: {e}", exc_info=True)
            
    logging.info(f"從賽程頁面總共解析到 {len(parsed_games)} 場比賽。")
    return parsed_games

def _process_filtered_games(games_to_process):
    """【步驟3】處理已篩選的比賽列表，訪問每場比賽的 Box Score 頁面並解析。"""
    if not games_to_process:
        logging.info("沒有需要處理的比賽。")
        return

    logging.info(f"準備處理 {len(games_to_process)} 場已篩選的比賽...")
    conn = get_db_connection()
    for game_info in games_to_process:
        # 只處理狀態為「已完成」的比賽
        if game_info.get('status') != "已完成":
            logging.info(f"跳過未完成的比賽 (CPBL ID: {game_info.get('cpbl_game_id')}, 狀態: {game_info.get('status')})")
            continue

        # 只處理目標球隊的比賽
        if TARGET_TEAM_NAME == game_info.get('home_team') or TARGET_TEAM_NAME == game_info.get('away_team'):
            logging.info(f"處理目標球隊 [{TARGET_TEAM_NAME}] 的比賽 (CPBL ID: {game_info.get('cpbl_game_id')})...")
            
            # 儲存比賽概要資訊並獲取DB中的ID
            game_id_in_db = store_single_game_result(conn, game_info)
            if not game_id_in_db:
                logging.warning(f"未能儲存比賽結果或獲取 DB game_id，跳過處理此比賽。")
                continue

            box_score_url = game_info.get('box_score_url')
            if not box_score_url:
                logging.warning(f"比賽 (DB game_id: {game_id_in_db}) 缺少 Box Score URL。")
                continue
            
            # 【核心步驟】訪問 Box Score 頁面
            logging.info(f"正在抓取 Box Score: {box_score_url}")
            # Box Score 頁面通常是靜態的，先嘗試用 requests，如果失敗再考慮換成 Playwright
            box_score_html = get_dynamic_page_content(
                url=box_score_url,
                wait_for_selector="div.GameBoxDetail"  # 等待包含所有數據的大區塊出現
            )
            time.sleep(2) # 友善延遲

            if box_score_html:
                # 將 Box Score 頁面的 HTML 傳遞給解析函式
                parse_and_store_target_players_stats_from_box(conn, box_score_html, game_id_in_db, game_info['game_date'])
            else:
                logging.warning(f"無法獲取比賽 (DB game_id: {game_id_in_db}) 的 Box Score 內容。")
    conn.close()

def store_single_game_result(conn, game_data):
    """將單場比賽概要資訊存入 game_results 並返回資料庫中的 game id"""
    cursor = conn.cursor()
    try:
        fields = ['cpbl_game_id', 'game_date', 'game_time', 'home_team', 'away_team', 'home_score', 'away_score', 'venue', 'status', 'winning_pitcher', 'losing_pitcher', 'save_pitcher', 'mvp', 'game_duration', 'attendance']
        values_to_insert = [game_data.get(f) for f in fields]
        cursor.execute("INSERT OR IGNORE INTO game_results ({}) VALUES ({})".format(', '.join(fields), ', '.join(['?'] * len(fields))), tuple(values_to_insert))
        conn.commit()
        if cursor.lastrowid:
             return cursor.lastrowid
        else:
            query_cpbl_id = game_data.get('cpbl_game_id')
            if query_cpbl_id:
                cursor.execute("SELECT id FROM game_results WHERE cpbl_game_id = ?", (query_cpbl_id,))
            else:
                cursor.execute("SELECT id FROM game_results WHERE game_date = ? AND home_team = ? AND away_team = ?", (game_data.get('game_date'), game_data.get('home_team'), game_data.get('away_team')))
            row = cursor.fetchone()
            return row['id'] if row else None
    except sqlite3.Error as e:
        logging.error(f"儲存比賽結果到資料庫時出錯: {e}")
        return None
    
def parse_and_store_target_players_stats_from_box(conn, html_content, game_id_in_db, game_date_str):
    """
    解析 Box Score HTML，篩選目標球隊的目標球員數據，並儲存。
    """
    logging.info(f"正在解析 Box Score (DB game_id: {game_id_in_db}) 中的球員數據...")
    soup = BeautifulSoup(html_content, 'lxml')
    cursor = conn.cursor()
    
    team_stat_blocks = soup.select('div.GameBoxDetail > div.tab_container > div.tab_cont')

    if not team_stat_blocks:
        logging.warning(f"在 Box Score 頁面 (DB game_id: {game_id_in_db}) 中找不到任何球隊數據區塊。")
        return

    for block in team_stat_blocks:
        # --- 【核心修改處】使用更精準的選擇器 ---
        team_name_tag = block.select_one('th.player > a')
        if not team_name_tag:
            logging.debug("在一個球隊區塊中找不到隊名標籤(<th>)，跳過。")
            continue
        
        current_team_name = team_name_tag.text.strip()
        
        if current_team_name != TARGET_TEAM_NAME:
            logging.debug(f"解析到隊名 '{current_team_name}'，與目標 '{TARGET_TEAM_NAME}' 不符，跳過。")
            continue
        
        # 如果程式能執行到這裡，代表隊名比對成功了
        logging.info(f"成功匹配到目標球隊 [{current_team_name}] 的數據區塊，開始解析球員...")
        
        # 找到「打擊成績」的總表 (Batting Stats Table)
        batting_stats_table = block.select_one('div.DistTitle:has(h3:contains("打擊成績")) + div.RecordTableWrap table')
        if not batting_stats_table:
            logging.warning(f"找不到球隊 [{current_team_name}] 的打擊成績總表。")
            continue
            
        player_summary_rows = batting_stats_table.find('tbody').find_all('tr', class_=lambda c: c != 'total')

        for player_row in player_summary_rows:
            player_name_tag = player_row.find('span', class_='name')
            if not player_name_tag: continue
            
            player_name = player_name_tag.text.strip()
            
            if player_name not in TARGET_PLAYER_NAMES:
                continue # 如果不是目標球員，靜默跳過
            
            logging.info(f"找到目標球員 [{player_name}] 的數據，準備提取並儲存...")
            try:
                # --- 您的數據提取和儲存邏輯 ---
                # 為了保持您可能已有的修改，此處的內部邏輯維持原樣
                # ... (省略) ...
                
                # --- 如果您還未修改，以下是我們上次建立的參考版本 ---
                cells = player_row.find_all('td', class_='num')
                col_map = ['at_bats', 'runs_scored', 'hits', 'rbi', 'doubles', 'triples', 'homeruns', 'gidp', 'walks', 'intentional_walks', 'hit_by_pitch', 'strikeouts', 'sacrifice_hits', 'sacrifice_flies', 'stolen_bases', 'caught_stealing', 'errors', 'avg_cumulative']
                summary_data = { "player_name": player_name, "team_name": current_team_name, "game_id": game_id_in_db }
                
                order_pos_cell = player_row.find('td', class_='player')
                if order_pos_cell:
                    summary_data['batting_order'] = order_pos_cell.find('span', class_='order').text.strip()
                    summary_data['position'] = order_pos_cell.find('span', class_='position').text.strip()
                
                for i, field_name in enumerate(col_map):
                    if field_name == 'intentional_walks':
                        ibb_text = cells[i-1].text.strip()
                        summary_data[field_name] = int(ibb_text.split('（')[1].replace('）', '')) if '（' in ibb_text else 0
                        continue
                    if i < len(cells):
                        value_str = cells[i].text.strip()
                        if field_name.endswith('_cumulative'):
                            summary_data[field_name] = float(value_str) if value_str and value_str != '.' else 0.0
                        else:
                            summary_data[field_name] = int(value_str) if value_str.isdigit() else 0
                
                summary_data['obp_cumulative'] = None
                summary_data['slg_cumulative'] = None
                summary_data['ops_cumulative'] = None

                play_by_play_table = block.select_one('div.DistTitle:has(h3:contains("戰況表")) + div.RecordTableWrap table')
                at_bat_summary_list = []
                if play_by_play_table:
                    pbp_row = play_by_play_table.find('span', class_='name', string=player_name)
                    if pbp_row:
                        pbp_row = pbp_row.find_parent('tr')
                        at_bat_cells = pbp_row.find_all('td')[1:-6]
                        for cell in at_bat_cells:
                            if cell.text.strip(): at_bat_summary_list.append(cell.text.strip())
                summary_data['at_bat_results_summary'] = ",".join(at_bat_summary_list)
                
                fields_to_insert = ['game_id', 'player_name', 'team_name', 'batting_order', 'position', 'at_bats', 'runs_scored', 'hits', 'rbi', 'doubles', 'triples', 'homeruns', 'gidp', 'walks', 'intentional_walks', 'hit_by_pitch', 'strikeouts', 'sacrifice_hits', 'sacrifice_flies', 'stolen_bases', 'caught_stealing', 'avg_cumulative', 'at_bat_results_summary']
                summary_data['plate_appearances'] = summary_data.get('at_bats',0) + summary_data.get('walks',0) + summary_data.get('hit_by_pitch',0) + summary_data.get('sacrifice_hits',0) + summary_data.get('sacrifice_flies',0)
                fields_to_insert.insert(5, 'plate_appearances')

                values_tuple = tuple(summary_data.get(f) for f in fields_to_insert)

                cursor.execute(f"INSERT OR REPLACE INTO player_game_summary ({', '.join(fields_to_insert)}) VALUES ({', '.join(['?'] * len(fields_to_insert))})", values_tuple)
                
                player_game_summary_id = cursor.lastrowid
                if not player_game_summary_id:
                    cursor.execute("SELECT id FROM player_game_summary WHERE game_id = ? AND player_name = ? AND team_name = ?", (game_id_in_db, player_name, current_team_name))
                    fetched = cursor.fetchone()
                    if fetched: player_game_summary_id = fetched['id']

                logging.info(f"成功儲存球員 [{player_name}] 的單場總結數據。")
                
                if player_game_summary_id and at_bat_summary_list:
                    for i, result in enumerate(at_bat_summary_list):
                        cursor.execute("INSERT OR IGNORE INTO at_bat_details (player_game_summary_id, sequence_in_game, result_short) VALUES (?, ?, ?)", (player_game_summary_id, i + 1, result))
                    logging.info(f"成功儲存球員 [{player_name}] 的 {len(at_bat_summary_list)} 筆逐打席簡易記錄。")

            except Exception as e:
                logging.error(f"解析或儲存球員 [{player_name}] 數據時發生嚴重錯誤: {e}", exc_info=True)

    conn.commit()


# --- 主要的、可被外部呼叫的任務函式 ---

def scrape_single_day(specific_date=None):
    """
    【功能一】抓取並處理指定單日的比賽數據。
    """
    target_date_str = specific_date if specific_date else datetime.date.today().strftime("%Y-%m-%d")
    logging.info(f"--- 開始執行 [單日模式]，目標日期: {target_date_str} ---")

    # --- 【新增步驟】在單日模式開始時，先更新一次球季累積數據 ---
    conn = get_db_connection()
    try:
        scrape_and_store_season_stats(conn)
    finally:
        # 確保連線被關閉
        if conn:
            conn.close()
    # --------------------------------------------------------
    
    all_month_games = fetch_and_parse_monthly_schedule()
    if not all_month_games:
        logging.info(f"--- [單日模式] 因無法獲取月賽程而中止 ---")
        return

    games_for_day = [game for game in all_month_games if game.get('game_date') == target_date_str]
    _process_filtered_games(games_for_day)
    logging.info(f"--- [單日模式] 執行完畢 ---")

def scrape_entire_month():
    """
    【功能二】抓取並處理當前月份的所有「已完成」比賽數據。
    """
    logging.info(f"--- 開始執行 [整月模式] ---")
    
    all_month_games = fetch_and_parse_monthly_schedule()
    if not all_month_games:
        logging.info(f"--- [整月模式] 因無法獲取月賽程而中止 ---")
        return
        
    _process_filtered_games(all_month_games)
    logging.info(f"--- [整月模式] 執行完畢 ---")

# --- 命令列執行入口 ---

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="CPBL 數據爬蟲手動執行工具")
    subparsers = parser.add_subparsers(dest='mode', help='執行模式', required=True)

    parser_daily = subparsers.add_parser('daily', help='抓取指定單日的數據 (預設為今天)')
    parser_daily.add_argument('--date', type=str, help="指定日期，格式為YYYY-MM-DD")

    parser_monthly = subparsers.add_parser('monthly', help='抓取當前顯示月份的所有數據')
    args = parser.parse_args()

    if args.mode == 'daily':
        scrape_single_day(specific_date=args.date)
    elif args.mode == 'monthly':
        scrape_entire_month()