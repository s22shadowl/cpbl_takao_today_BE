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
        # 為了確保欄位順序和數量正確，明確列出
        fields = [
            'cpbl_game_id', 'game_date', 'game_time', 'home_team', 'away_team',
            'home_score', 'away_score', 'venue', 'status'
        ]
        values = tuple(game_info.get(f) for f in fields)

        # 使用 INSERT OR IGNORE，如果 UNIQUE 約束(cpbl_game_id)衝突，則忽略此次插入
        cursor.execute(f"""
            INSERT OR IGNORE INTO game_results ({', '.join(fields)})
            VALUES ({', '.join(['?'] * len(fields))})
        """, values)
        conn.commit()

        # 無論是新插入還是已存在，都根據 cpbl_game_id 查詢其主鍵 id
        if game_info.get('cpbl_game_id'):
            cursor.execute("SELECT id FROM game_results WHERE cpbl_game_id = ?", (game_info['cpbl_game_id'],))
            row = cursor.fetchone()
            return row[0] if row else None
        else:
            logging.warning("比賽資訊中缺少 'cpbl_game_id'，無法查詢 id。")
            return None

    except sqlite3.Error as e:
        logging.error(f"儲存比賽結果到資料庫時出錯: {e} - 資料: {game_info}")
        return None

def update_player_season_stats(conn, season_stats_list):
    """
    批次更新多位球員的球季累積數據。
    採用「先刪除後插入」的策略，確保數據永遠是最新。

    :param conn: 資料庫連線物件
    :param season_stats_list: 包含多位球員球季數據字典的列表
    """
    if not season_stats_list:
        return

    logging.info(f"準備更新 {len(season_stats_list)} 位球員的球季累積數據...")
    cursor = conn.cursor()
    
    # 定義要插入的欄位順序，確保與資料庫表格一致
    db_fields_ordered = [
        'player_name', 'team_name', 'data_retrieved_date', 'games_played', 'plate_appearances', 
        'at_bats', 'runs_scored', 'hits', 'rbi', 'homeruns', 'singles', 'doubles', 'triples',
        'total_bases', 'strikeouts', 'stolen_bases', 'gidp', 'sacrifice_hits', 
        'sacrifice_flies', 'walks', 'intentional_walks', 'hit_by_pitch', 'caught_stealing',
        'ground_outs', 'fly_outs', 'avg', 'obp', 'slg', 'ops', 'go_ao_ratio', 
        'sb_percentage', 'silver_slugger_index'
    ]
    
    # 將字典列表轉換為元組列表以便批次操作
    data_to_insert = []
    player_names_to_delete = []
    for stats_data in season_stats_list:
        player_names_to_delete.append(stats_data['player_name'])
        # 準備元組，若字典中缺少某個 key，則提供安全的預設值 0 或 0.0
        values = tuple(stats_data.get(field, 0.0 if field in ['avg','obp','slg','ops','go_ao_ratio','sb_percentage','silver_slugger_index'] else 0) for field in db_fields_ordered)
        data_to_insert.append(values)

    try:
        # 使用 executemany 一次性刪除所有舊記錄
        cursor.executemany("DELETE FROM player_season_stats WHERE player_name = ?", [(name,) for name in player_names_to_delete])
        
        # 使用 executemany 一次性插入所有新記錄
        cursor.executemany(
            f"INSERT INTO player_season_stats ({', '.join(db_fields_ordered)}) VALUES ({', '.join(['?'] * len(db_fields_ordered))})",
            data_to_insert
        )
        conn.commit()
        logging.info(f"成功批次更新 {len(data_to_insert)} 筆球員球季數據。")
    except sqlite3.Error as e:
        logging.error(f"批次更新球員球季數據時出錯: {e}")
        conn.rollback() # 如果出錯，撤銷本次所有操作

def store_player_game_data(conn, game_id, player_data_list):
    """
    儲存多位球員的單場總結與逐打席記錄。

    :param conn: 資料庫連線物件
    :param game_id: 該場比賽在 game_results 表中的主鍵 id
    :param player_data_list: 從 parser 回傳的球員數據列表
    """
    if not player_data_list:
        return
        
    cursor = conn.cursor()
    
    for player_data in player_data_list:
        summary_data = player_data.get("summary", {})
        at_bats_list = player_data.get("at_bats_list", [])
        
        if not summary_data: continue

        summary_data['game_id'] = game_id # 將比賽 id 加入字典中

        try:
            # 準備插入 player_game_summary
            summary_fields = list(summary_data.keys())
            summary_values = tuple(summary_data.values())
            
            cursor.execute(f"INSERT OR REPLACE INTO player_game_summary ({', '.join(summary_fields)}) VALUES ({', '.join(['?'] * len(summary_fields))})", summary_values)
            
            # 獲取剛插入的 player_game_summary 的主鍵 id
            player_game_summary_id = cursor.lastrowid
            if not player_game_summary_id:
                cursor.execute("SELECT id FROM player_game_summary WHERE game_id = ? AND player_name = ?", (game_id, summary_data['player_name']))
                fetched = cursor.fetchone()
                if fetched: player_game_summary_id = fetched[0]

            logging.info(f"成功儲存球員 [{summary_data['player_name']}] 的單場總結數據。")

            # 準備批次插入 at_bat_details
            if player_game_summary_id and at_bats_list:
                details_to_insert = [
                    (player_game_summary_id, i + 1, result) for i, result in enumerate(at_bats_list)
                ]
                cursor.executemany(
                    "INSERT OR IGNORE INTO at_bat_details (player_game_summary_id, sequence_in_game, result_short) VALUES (?, ?, ?)",
                    details_to_insert
                )
                logging.info(f"成功儲存球員 [{summary_data['player_name']}] 的 {len(details_to_insert)} 筆逐打席簡易記錄。")

        except sqlite3.Error as e:
            logging.error(f"儲存球員 [{summary_data.get('player_name')}] 的單場比賽數據時出錯: {e}")
            conn.rollback() # 如果單一球員出錯，撤銷對該球員的操作

    conn.commit()