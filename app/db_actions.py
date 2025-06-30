# app/db_actions.py

import logging
import sqlite3
import datetime

def store_game_and_get_id(conn, game_info):
    """
    將單場比賽概要資訊存入 game_results 表格。
    如果比賽記錄已存在，則不進行任何操作。
    無論如何，都會查詢並返回該筆記錄在資料庫中的主鍵 id。

    :param conn: 資料庫連線物件
    :param game_info: 包含單場比賽資訊的字典
    :return: 該筆比賽記錄在資料庫中的 id (int)，如果失敗則返回 None
    """
    cursor = conn.cursor()
    try:
        fields = [
            'cpbl_game_id', 'game_date', 'game_time', 'home_team', 'away_team',
            'home_score', 'away_score', 'venue', 'status'
        ]
        values = tuple(game_info.get(f) for f in fields)

        cursor.execute(f"INSERT OR IGNORE INTO game_results ({', '.join(fields)}) VALUES ({', '.join(['?'] * len(fields))})", values)
        
        if game_info.get('cpbl_game_id'):
            cursor.execute("SELECT id FROM game_results WHERE cpbl_game_id = ?", (game_info['cpbl_game_id'],))
            row = cursor.fetchone()
            if row:
                conn.commit()
                return row[0]
        
        # 如果沒有 cpbl_game_id 或查詢失敗，回滾並返回 None
        conn.rollback()
        return None

    except sqlite3.Error as e:
        logging.error(f"儲存比賽結果時出錯: {e}")
        conn.rollback()
    return None

def update_player_season_stats(conn, season_stats_list):
    """
    使用 executemany 批次更新多位球員的球季累積數據。
    採用「先刪除後插入」的策略，確保數據永遠是最新。
    """
    if not season_stats_list:
        return

    logging.info(f"準備批次更新 {len(season_stats_list)} 位球員的球季累積數據...")
    cursor = conn.cursor()
    
    db_fields_ordered = [
        'player_name', 'team_name', 'data_retrieved_date', 'games_played', 'plate_appearances', 
        'at_bats', 'runs_scored', 'hits', 'rbi', 'homeruns', 'singles', 'doubles', 'triples',
        'total_bases', 'strikeouts', 'stolen_bases', 'gidp', 'sacrifice_hits', 
        'sacrifice_flies', 'walks', 'intentional_walks', 'hit_by_pitch', 'caught_stealing',
        'ground_outs', 'fly_outs', 'avg', 'obp', 'slg', 'ops', 'go_ao_ratio', 
        'sb_percentage', 'silver_slugger_index'
    ]
    
    data_to_insert = []
    for stats in season_stats_list:
        stats['data_retrieved_date'] = datetime.date.today().strftime("%Y-%m-%d")
        # 準備元組，若字典中缺少某個 key，則提供安全的預設值
        values = tuple(stats.get(field, 0.0 if any(k in field for k in ['avg', 'obp', 'slg', 'ops', 'ratio', 'percentage', 'index']) else 0) for field in db_fields_ordered)
        data_to_insert.append(values)
    
    try:
        # 使用 executemany 一次性刪除所有舊記錄
        player_names_to_delete = [(stats['player_name'],) for stats in season_stats_list]
        cursor.executemany("DELETE FROM player_season_stats WHERE player_name = ?", player_names_to_delete)
        
        # 使用 executemany 一次性插入所有新記錄，效能更佳
        cursor.executemany(
            f"INSERT INTO player_season_stats ({', '.join(db_fields_ordered)}) VALUES ({', '.join(['?'] * len(db_fields_ordered))})",
            data_to_insert
        )
        conn.commit()
        logging.info(f"成功批次更新 {len(data_to_insert)} 筆球員球季數據。")
    except sqlite3.Error as e:
        logging.error(f"批次更新球員球季數據時出錯: {e}")
        conn.rollback()

def store_player_game_data(conn, game_id, all_players_data):
    """【最終修正版】儲存多位球員的單場總結與完整的逐打席記錄。"""
    if not all_players_data: return
    cursor = conn.cursor()
    for player_data in all_players_data:
        summary = player_data.get("summary", {})
        at_bats_details = player_data.get("at_bats_details", [])
        if not summary or not at_bats_details: continue
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

            if player_game_summary_id:
                initial_details = [
                    (player_game_summary_id, d.get('sequence_in_game'), d.get('result_short'), d.get('inning'))
                    for d in at_bats_details
                ]
                cursor.executemany("INSERT OR IGNORE INTO at_bat_details (player_game_summary_id, sequence_in_game, result_short, inning) VALUES (?, ?, ?, ?)", initial_details)
                
                details_to_update = [
                    (
                        d.get('outs_before'),
                        d.get('runners_on_base_before'),
                        d.get('result_description_full'),
                        d.get('opposing_pitcher_name'),
                        d.get('pitch_sequence_details'),
                        player_game_summary_id,
                        d.get('sequence_in_game')
                    ) for d in at_bats_details
                ]
                cursor.executemany("""
                    UPDATE at_bat_details SET
                        outs_before = ?,
                        runners_on_base_before = ?,
                        result_description_full = ?,
                        opposing_pitcher_name = ?,
                        pitch_sequence_details = ?
                    WHERE player_game_summary_id = ? AND sequence_in_game = ?
                """, details_to_update)
                logging.info(f"成功更新/儲存球員 [{summary['player_name']}] 的 {len(at_bats_details)} 筆逐打席詳細記錄。")
        except sqlite3.Error as e:
            logging.error(f"儲存球員 [{summary.get('player_name')}] 的單場比賽數據時出錯: {e}", exc_info=True)
            conn.rollback()
    conn.commit()

def update_game_schedules(conn, games_list: list):
        """【全新】更新比賽排程表。採用「先清空後批次插入」的策略，確保排程永遠是最新的。"""
        if not games_list:
            logging.info("沒有新的比賽排程需要更新。")
            return
            
        logging.info(f"準備更新資料庫中的比賽排程，共 {len(games_list)} 場...")
        cursor = conn.cursor()
        
        # 準備要插入的資料
        data_to_insert = [
            (game.get("game_id"), game.get("date"), game.get("time"))
            for game in games_list
        ]
        
        try:
            # 1. 為了確保資料最新，先刪除所有舊的排程
            cursor.execute("DELETE FROM game_schedules;")
            logging.info("已清空舊的比賽排程。")
            
            # 2. 使用 executemany 一次性插入所有新排程
            cursor.executemany(
                "INSERT INTO game_schedules (game_id, game_date, game_time) VALUES (?, ?, ?)",
                data_to_insert
            )
            conn.commit()
            logging.info(f"成功寫入 {len(data_to_insert)} 筆新的比賽排程。")
        except sqlite3.Error as e:
            logging.error(f"更新比賽排程時發生錯誤: {e}")
            conn.rollback()

def get_all_schedules(conn) -> list:
    """【全新】從資料庫獲取所有已儲存的比賽排程。"""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM game_schedules ORDER BY game_date, game_time;")
        schedules = cursor.fetchall()
        # 將 sqlite3.Row 物件轉換為字典列表
        return [dict(row) for row in schedules]
    except sqlite3.Error as e:
        logging.error(f"獲取比賽排程時發生錯誤: {e}")
        return []