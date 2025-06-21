# app/db_actions.py

import logging
import sqlite3
import datetime

def store_game_and_get_id(conn, game_info):
    """將單場比賽概要資訊存入 game_results 並返回資料庫中的 id。"""
    cursor = conn.cursor()
    try:
        fields = ['cpbl_game_id', 'game_date', 'game_time', 'home_team', 'away_team', 'home_score', 'away_score', 'venue', 'status']
        values = tuple(game_info.get(f) for f in fields)
        cursor.execute(f"INSERT OR IGNORE INTO game_results ({', '.join(fields)}) VALUES ({', '.join(['?'] * len(fields))})", values)
        conn.commit()
        
        if game_info.get('cpbl_game_id'):
            cursor.execute("SELECT id FROM game_results WHERE cpbl_game_id = ?", (game_info['cpbl_game_id'],))
            row = cursor.fetchone()
            return row[0] if row else None
    except sqlite3.Error as e:
        logging.error(f"儲存比賽結果時出錯: {e}")
        conn.rollback()
    return None

def update_player_season_stats(conn, season_stats_list):
    """使用 executemany 批次更新多位球員的球季累積數據。"""
    if not season_stats_list: return
    logging.info(f"準備批次更新 {len(season_stats_list)} 位球員的球季累積數據...")
    cursor = conn.cursor()
    
    db_fields_ordered = ['player_name', 'team_name', 'data_retrieved_date', 'games_played', 'plate_appearances', 'at_bats', 'runs_scored', 'hits', 'rbi', 'homeruns', 'singles', 'doubles', 'triples', 'total_bases', 'strikeouts', 'stolen_bases', 'gidp', 'sacrifice_hits', 'sacrifice_flies', 'walks', 'intentional_walks', 'hit_by_pitch', 'caught_stealing', 'ground_outs', 'fly_outs', 'avg', 'obp', 'slg', 'ops', 'go_ao_ratio', 'sb_percentage', 'silver_slugger_index']
    
    data_to_insert = []
    for stats in season_stats_list:
        stats['data_retrieved_date'] = datetime.date.today().strftime("%Y-%m-%d")
        data_to_insert.append(tuple(stats.get(field, 0) for field in db_fields_ordered))
    
    try:
        player_names_to_delete = [(stats['player_name'],) for stats in season_stats_list]
        cursor.executemany("DELETE FROM player_season_stats WHERE player_name = ?", player_names_to_delete)
        cursor.executemany(f"INSERT INTO player_season_stats ({', '.join(db_fields_ordered)}) VALUES ({', '.join(['?'] * len(db_fields_ordered))})", data_to_insert)
        conn.commit()
        logging.info(f"成功批次更新 {len(data_to_insert)} 筆球員球季數據。")
    except sqlite3.Error as e:
        logging.error(f"批次更新球員球季數據時出錯: {e}")
        conn.rollback()

def store_player_game_data(conn, game_id, all_players_data):
    """儲存多位球員的單場總結與逐打席記錄。"""
    if not all_players_data: return
    cursor = conn.cursor()
    
    all_at_bats_to_insert = []

    for player_data in all_players_data:
        summary = player_data.get("summary", {})
        at_bats = player_data.get("at_bats_list", [])
        if not summary: continue
        summary['game_id'] = game_id

        try:
            summary_fields = list(summary.keys())
            summary_values = tuple(summary.values())
            cursor.execute(f"INSERT OR REPLACE INTO player_game_summary ({', '.join(summary_fields)}) VALUES ({', '.join(['?'] * len(summary_fields))})", summary_values)
            
            player_game_summary_id = cursor.lastrowid
            if not player_game_summary_id:
                cursor.execute("SELECT id FROM player_game_summary WHERE game_id = ? AND player_name = ?", (game_id, summary['player_name']))
                fetched = cursor.fetchone()
                if fetched: player_game_summary_id = fetched[0]

            logging.info(f"成功儲存球員 [{summary['player_name']}] 的單場總結數據。")
            
            if player_game_summary_id and at_bats:
                for i, result in enumerate(at_bats):
                    all_at_bats_to_insert.append((player_game_summary_id, i + 1, result))

        except sqlite3.Error as e:
            logging.error(f"儲存球員 [{summary.get('player_name')}] 的單場比賽數據時出錯: {e}")
            conn.rollback()
            return # 單一球員出錯時，後續的批次插入也應中止

    # 在所有球員的 at_bats 都收集完畢後，進行一次性的批次插入
    if all_at_bats_to_insert:
        try:
            cursor.executemany("INSERT OR IGNORE INTO at_bat_details (player_game_summary_id, sequence_in_game, result_short) VALUES (?, ?, ?)", all_at_bats_to_insert)
            logging.info(f"成功批次儲存 {len(all_at_bats_to_insert)} 筆逐打席記錄。")
        except sqlite3.Error as e:
            logging.error(f"批次儲存逐打席記錄時出錯: {e}")
            conn.rollback()

    conn.commit()