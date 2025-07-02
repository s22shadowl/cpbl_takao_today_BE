# app/core/parser.py

import json
import logging
import datetime
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from app.config import settings

def parse_schedule_page(html_content, year):
    """
    從賽程頁面的 HTML 中，解析出該月份「所有」的比賽基本資訊。
    """
    if not html_content:
        logging.warning("傳入的賽程頁面 HTML 內容為空，無法進行解析。")
        return []
        
    logging.info(f"開始從 HTML 內容中解析年份為 {year} 的比賽...")
    soup = BeautifulSoup(html_content, 'lxml')
    parsed_games = []
    
    list_view_container = soup.select_one('div.tab_cont.list')
    if not list_view_container:
        logging.warning("在賽程頁 HTML 中找不到 '列表顯示' 的區塊。")
        return []
        
    schedule_table = list_view_container.find('div', class_='ScheduleTableList')
    if not schedule_table:
        logging.warning("在 '列表顯示' 區塊中找不到賽程表格。")
        return []

    all_rows = schedule_table.find_all('tr')
    current_date_in_loop = None
    
    for row in all_rows:
        try:
            # 處理 rowspan，日期儲存格只在每天的第一個比賽列出現
            date_cell = row.find('td', class_='date')
            if date_cell:
                date_text = date_cell.text.strip().split('(')[0]
                month_str, day_str = date_text.split('/')
                current_date_in_loop = datetime.date(int(year), int(month_str), int(day_str))

            game_no_cell = row.find('td', class_='game_no')
            if not game_no_cell or not current_date_in_loop:
                continue

            game_data = {'game_date': current_date_in_loop.strftime('%Y-%m-%d')}
            box_link_tag = game_no_cell.find('a')
            if box_link_tag and box_link_tag.has_attr('href'):
                relative_url = box_link_tag['href']
                game_data['box_score_url'] = f"{settings.BASE_URL}{relative_url}" if relative_url.startswith('/') else f"{settings.BASE_URL}/{relative_url}"
                qs = parse_qs(urlparse(relative_url).query)
                game_data['cpbl_game_id'] = qs.get('gameSno', [None])[0]
            
            team_cell = row.find('td', class_='team')
            if team_cell:
                game_data['away_team'] = team_cell.find('div', class_='name away').text.strip()
                game_data['home_team'] = team_cell.find('div', class_='name home').text.strip()
                away_score_tag, home_score_tag = team_cell.find('div', class_='num away'), team_cell.find('div', class_='num home')
                game_data['away_score'] = int(away_score_tag.text.strip()) if away_score_tag and away_score_tag.text.strip().isdigit() else None
                game_data['home_score'] = int(home_score_tag.text.strip()) if home_score_tag and home_score_tag.text.strip().isdigit() else None

            info_cell = row.find('td', class_='info')
            if info_cell:
                game_data['venue'] = (info_cell.find('div', class_='place').span.text.strip() if info_cell.find('div', class_='place') and info_cell.find('div', class_='place').span else None)
                game_data['game_time'] = (info_cell.find('div', class_='time').span.text.strip() if info_cell.find('div', class_='time') and info_cell.find('div', class_='time').span else None)
                
            remark_cell = row.find('td', class_='remark')
            if remark_cell:
                note_tag = remark_cell.find('div', class_='note')
                if note_tag:
                    game_data['status'] = note_tag.text.strip()
                elif game_data.get('home_score') is not None:
                    game_data['status'] = '已完成'
                else:
                    game_data['status'] = '未開始'
            else:
                if game_data.get('home_score') is not None:
                    game_data['status'] = '已完成'
                else:
                    game_data['status'] = '未開始'

            parsed_games.append(game_data)
        except Exception as e:
            logging.error(f"解析單場比賽概要時出錯，已跳過此行: {e}", exc_info=True)
            
    logging.info(f"從賽程頁面總共解析到 {len(parsed_games)} 場比賽。")
    return parsed_games

def parse_box_score_page(html_content):
    """從 Box Score 頁面 HTML 中，解析出目標球隊的目標球員基本數據和簡易打席列表。"""
    if not html_content:
        return []
    soup = BeautifulSoup(html_content, 'lxml')
    all_players_data = []

    team_stat_blocks = soup.select('div.GameBoxDetail > div.tab_container > div.tab_cont')
    if not team_stat_blocks:
        return []

    for block in team_stat_blocks:
        try:
            team_name_tag = block.select_one('th.player > a')
            if not team_name_tag:
                continue
            current_team_name = team_name_tag.text.strip()
            
            if current_team_name != settings.TARGET_TEAM_NAME:
                continue

            logging.info(f"成功匹配到目標球隊 [{current_team_name}] 的數據區塊，開始解析球員...")
            batting_stats_table = block.select_one('div.DistTitle:has(h3:-soup-contains("打擊成績")) + div.RecordTableWrap table')
            if not batting_stats_table:
                continue
                
            player_summary_rows = batting_stats_table.find('tbody').find_all('tr', class_=lambda c: c != 'total')
            for player_row in player_summary_rows:
                try:
                    player_name_tag = player_row.find('span', class_='name')
                    if not player_name_tag:
                        continue
                    player_name = player_name_tag.text.strip()
                    
                    if player_name not in settings.TARGET_PLAYER_NAMES:
                        continue
                    
                    logging.info(f"找到目標球員 [{player_name}] 的數據，準備提取...")
                    cells = player_row.find_all('td', class_='num')
                    col_map = ['at_bats', 'runs_scored', 'hits', 'rbi', 'doubles', 'triples', 'homeruns', 'gidp', 'walks', 'intentional_walks', 'hit_by_pitch', 'strikeouts', 'sacrifice_hits', 'sacrifice_flies', 'stolen_bases', 'caught_stealing', 'errors', 'avg_cumulative']
                    summary_data = { "player_name": player_name, "team_name": current_team_name }
                    
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
                    
                    play_by_play_table = block.select_one('div.DistTitle:has(h3:-soup-contains("戰況表")) + div.RecordTableWrap table')
                    at_bat_summary_list = []
                    if play_by_play_table:
                        pbp_row = play_by_play_table.find('span', class_='name', string=player_name)
                        if pbp_row:
                            pbp_row = pbp_row.find_parent('tr')
                            at_bat_cells = pbp_row.find_all('td')[1:-6]
                            for cell in at_bat_cells:
                                if cell.text.strip():
                                    at_bat_summary_list.append(cell.text.strip())
                    summary_data['at_bat_results_summary'] = ",".join(at_bat_summary_list)
                    summary_data['plate_appearances'] = sum([summary_data.get(k,0) for k in ['at_bats', 'walks', 'hit_by_pitch', 'sacrifice_hits', 'sacrifice_flies']])
                    
                    player_full_data = {"summary": summary_data, "at_bats_list": at_bat_summary_list}
                    all_players_data.append(player_full_data)
                except Exception as e:
                    logging.error(f"解析球員 [{player_name or '未知'}] 的 Box Score 數據時發生錯誤，跳過此球員: {e}", exc_info=True)
        except Exception as e:
            logging.error(f"解析球隊數據區塊時發生錯誤: {e}", exc_info=True)
    return all_players_data

def parse_active_inning_details(inning_html_content, inning):
    """【全新】從單一局數的 HTML 內容中，解析出所有事件。"""
    if not inning_html_content:
        return []
    soup = BeautifulSoup(inning_html_content, 'lxml')
    inning_events = []
    
    event_items = soup.select("div.item.play, div.no-pitch-action-remind")
    for item in event_items:
        try:
            event_data = {'inning': inning}
            if 'no-pitch-action-remind' in item.get('class', []):
                event_data['type'] = 'no_pitch_action'
                event_data['description'] = item.text.strip()
            elif 'play' in item.get('class', []):
                event_data['type'] = 'at_bat'
                hitter_name_tag = item.select_one("div.player > a > span")
                desc_tag = item.select_one("div.info > div.desc")
                if not hitter_name_tag or not desc_tag:
                    continue
                
                event_data["hitter_name"] = hitter_name_tag.text.strip()
                description_text = ' '.join(desc_tag.stripped_strings)
                event_data["description"] = re.sub(r'^\s*第\d+棒\s+[A-Z0-9]+\s+[\u4e00-\u9fa5]+\s*：\s*', '', description_text).strip()
                event_data["result_description_full"] = re.sub(r'^\s*第\d+棒\s+[A-Z0-9]+\s+[\u4e00-\u9fa5]+\s*：\s*', '', description_text).strip()

                pitch_detail_block = item.find('div', class_='detail')
                if pitch_detail_block:
                    pitcher_name_tag = pitch_detail_block.select_one("div.detail_item.pitcher a")
                    if pitcher_name_tag:
                        event_data['opposing_pitcher_name'] = pitcher_name_tag.text.strip()
                    
                    pitch_sequence_tags = pitch_detail_block.select("div.detail_item[class*='pitch-']")
                    pitch_list = []
                    for tag in pitch_sequence_tags:
                        pitch_num_tag = tag.select_one("div.pitch_num span")
                        call_desc_tag = tag.select_one("div.call_desc")
                        pitches_count_tag = tag.select_one("div.pitches_count")
                        pitch_list.append({
                            "num": pitch_num_tag.text.strip() if pitch_num_tag else None,
                            "desc": call_desc_tag.text.strip() if call_desc_tag else None,
                            "count": pitches_count_tag.text.strip() if pitches_count_tag else None
                        })
                    if pitch_list:
                        event_data['pitch_sequence_details'] = json.dumps(pitch_list, ensure_ascii=False)
                else:
                    continue
                inning_events.append(event_data)
        except Exception as e:
            logging.error(f"解析單一打席事件時出錯: {e}", exc_info=True)
    return inning_events

def parse_season_stats_page(html_content):
    """從球隊成績頁面 HTML 中，解析出目標球員的球季累積數據。"""
    if not html_content:
        return []
    logging.info("正在解析球季累積數據...")
    soup = BeautifulSoup(html_content, 'lxml')
    parsed_stats = []
    batting_table = soup.find('div', class_='RecordTable')
    if not batting_table:
        return []
    tbody = batting_table.find('tbody')
    if not tbody:
        return []
    player_rows = tbody.find_all('tr')
    header_map = { '出賽數': 'games_played', '打席': 'plate_appearances', '打數': 'at_bats', '打點': 'rbi', '得分': 'runs_scored', '安打': 'hits', '一安': 'singles', '二安': 'doubles', '三安': 'triples', '全壘打': 'homeruns', '壘打數': 'total_bases', '被三振': 'strikeouts', '盜壘': 'stolen_bases', '上壘率': 'obp', '長打率': 'slg', '打擊率': 'avg', '雙殺打': 'gidp', '犧短': 'sacrifice_hits', '犧飛': 'sacrifice_flies', '四壞球': 'walks', '（故四）': 'intentional_walks', '死球': 'hit_by_pitch', '盜壘刺': 'caught_stealing', '滾地出局': 'ground_outs', '高飛出局': 'fly_outs', '滾飛出局比': 'go_ao_ratio', '盜壘率': 'sb_percentage', '整體攻擊指數': 'ops', '銀棒指數': 'silver_slugger_index' }
    header_cells = [h.text.strip() for h in player_rows[0].find_all('th')]
    player_data_rows = player_rows[1:]

    for row in player_data_rows:
        try:
            cells = row.find_all('td')
            if not cells or len(cells) < 2:
                continue
            player_name_cell = cells[0].find('a')
            player_name = player_name_cell.text.strip() if player_name_cell else cells[0].text.strip()
            if player_name in settings.TARGET_PLAYER_NAMES:
                stats_data = { "player_name": player_name, "team_name": settings.TARGET_TEAM_NAME }
                for i, header_text in enumerate(header_cells):
                    db_col_name = header_map.get(header_text)
                    if db_col_name and (i < len(cells)):
                        value_str = cells[i].text.strip()
                        if db_col_name in ['avg', 'obp', 'slg', 'ops', 'go_ao_ratio', 'sb_percentage', 'silver_slugger_index']:
                            stats_data[db_col_name] = float(value_str) if value_str and value_str != '.' else 0.0
                        else:
                            stats_data[db_col_name] = int(value_str) if value_str.isdigit() else 0
                parsed_stats.append(stats_data)
        except (IndexError, ValueError) as e:
            logging.error(f"解析球員 [{player_name or '未知'}] 的累積數據時出錯，跳過此行: {e}", exc_info=True)
            
    logging.info(f"從球隊頁面解析到 {len(parsed_stats)} 名目標球員的累積數據。")
    return parsed_stats