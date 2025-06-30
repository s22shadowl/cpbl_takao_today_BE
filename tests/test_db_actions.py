# tests/core/test_db_actions.py

import pytest
import sqlite3
import datetime
from pathlib import Path

# 導入我們要測試的資料庫操作函式
from app import db_actions
# 導入我們需要用來初始化測試資料庫的函式
from app.db import init_db as init_real_db

@pytest.fixture
def initialized_db(monkeypatch, tmp_path: Path):
    """
    一個穩健的 fixture，它會：
    1. 使用 monkeypatch 來動態修改 db.py 中的資料庫路徑，使其指向一個臨時檔案。
    2. 呼叫您真實的 init_db() 來建立所有表格結構。
    3. 提供一個 get_conn 函式，讓測試案例可以獲取到這個臨時資料庫的連線。
    """
    db_path = tmp_path / "test.db"
    # 使用 monkeypatch 來在測試期間，動態地替換掉 db.py 中定義的資料庫路徑
    monkeypatch.setattr('app.db.DATABASE_NAME', str(db_path))
    
    # 現在呼叫真實的 init_db，它會作用在我們的 test.db 上
    init_real_db()
    
    # 提供一個可以建立新連線的函式給測試案例
    def get_conn():
        conn = sqlite3.connect(db_path)
        # 讓查詢結果可以用欄位名稱存取，方便測試
        conn.row_factory = sqlite3.Row
        return conn
        
    return get_conn

# --- 測試案例 ---

def test_store_game_and_get_id(initialized_db):
    """測試 store_game_and_get_id 函式"""
    conn = initialized_db() # 獲取一個到臨時資料庫的連線
    
    game_info = {
        'cpbl_game_id': 'TEST01',
        'game_date': '2025-06-21',
        'home_team': '測試主隊',
        'away_team': '測試客隊',
        'status': '已完成'
    }
    
    game_id = db_actions.store_game_and_get_id(conn, game_info)
    assert game_id == 1
    
    game_id_again = db_actions.store_game_and_get_id(conn, game_info)
    assert game_id_again == 1
    
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM game_results")
    count = cursor.fetchone()[0]
    assert count == 1
    
    conn.close()


def test_update_player_season_stats(initialized_db):
    """測試 update_player_season_stats 函式"""
    conn = initialized_db()
    
    stats_list = [
        {'player_name': '測試員A', 'team_name': '測試隊', 'avg': 0.300},
        {'player_name': '測試員B', 'team_name': '測試隊', 'avg': 0.250, 'homeruns': 5},
    ]
    
    db_actions.update_player_season_stats(conn, stats_list)
    
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM player_season_stats WHERE player_name = ?", ('測試員A',))
    player_a = cursor.fetchone()
    assert player_a is not None
    assert player_a['avg'] == 0.300
    
    updated_stats_list = [
        {'player_name': '測試員A', 'team_name': '測試隊', 'avg': 0.305, 'hits': 10},
    ]
    db_actions.update_player_season_stats(conn, updated_stats_list)
    
    cursor.execute("SELECT * FROM player_season_stats WHERE player_name = ?", ('測試員A',))
    player_a_updated = cursor.fetchone()
    assert player_a_updated['avg'] == 0.305
    assert player_a_updated['hits'] == 10
    
    cursor.execute("SELECT COUNT(*) FROM player_season_stats")
    count = cursor.fetchone()[0]
    assert count == 2
    
    conn.close()

def test_store_player_game_data_with_details(initialized_db):
    """【更新版】測試 store_player_game_data 函式，包含詳細打席資訊"""
    conn = initialized_db()
    
    game_info = {'cpbl_game_id': 'TEST02', 'game_date': '2025-06-21', 'home_team': 'H', 'away_team': 'A'}
    game_id = db_actions.store_game_and_get_id(conn, game_info)
    assert game_id is not None
    
    player_data_list = [
        {
            "summary": {"player_name": "測試員C", "team_name": "測試隊"},
            "at_bats_details": [
                {
                    "sequence_in_game": 1,
                    "result_short": "一安",
                    "inning": 1,
                    "outs_before": 0,
                    "runners_on_base_before": "壘上無人",
                    "result_description_full": "擊出右外野滾地球，一壘安打。"
                },
                {
                    "sequence_in_game": 2,
                    "result_short": "三振",
                    "inning": 3,
                    "outs_before": 1,
                    "runners_on_base_before": "一壘有人",
                    "pitch_sequence_details": "[...]"
                }
            ]
        }
    ]
    
    db_actions.store_player_game_data(conn, game_id, player_data_list)
    
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM player_game_summary WHERE player_name = ?", ('測試員C',))
    summary_id = cursor.fetchone()[0]
    
    cursor.execute("SELECT * FROM at_bat_details WHERE player_game_summary_id = ? ORDER BY sequence_in_game", (summary_id,))
    details = cursor.fetchall()
    
    assert len(details) == 2
    
    first_at_bat = details[0]
    assert first_at_bat['sequence_in_game'] == 1
    assert first_at_bat['inning'] == 1
    assert first_at_bat['outs_before'] == 0
    assert "一壘安打" in first_at_bat['result_description_full']
    
    second_at_bat = details[1]
    assert second_at_bat['inning'] == 3
    assert second_at_bat['pitch_sequence_details'] == "[...]"
    
    conn.close()

def test_update_and_get_game_schedules(initialized_db):
    """【新增】測試 update_game_schedules 和 get_all_schedules 函式。"""
    conn = initialized_db()
    
    # 1. 準備第一批假的賽程資料
    initial_schedules = [
        {"game_id": "176", "date": "2025-06-21", "time": "17:05", "matchup": "台鋼雄鷹 vs 樂天桃猿"},
        {"game_id": "179", "date": "2025-06-22", "time": "17:05", "matchup": "台鋼雄鷹 vs 樂天桃猿"}
    ]
    
    # 2. 第一次更新 (插入)
    db_actions.update_game_schedules(conn, initial_schedules)
    
    # 3. 獲取並驗證
    schedules_from_db = db_actions.get_all_schedules(conn)
    assert len(schedules_from_db) == 2
    assert schedules_from_db[0]['game_id'] == '176'
    assert schedules_from_db[1]['game_date'] == '2025-06-22'

    # 4. 準備第二批假的賽程資料 (模擬賽程更新)
    updated_schedules = [
        {"game_id": "180", "date": "2025-06-22", "time": "18:35", "matchup": "統一7-ELEVEn獅 vs 味全龍"},
    ]
    
    # 5. 第二次更新 (應先清空再插入)
    db_actions.update_game_schedules(conn, updated_schedules)
    
    # 6. 再次獲取並驗證
    schedules_from_db_updated = db_actions.get_all_schedules(conn)
    assert len(schedules_from_db_updated) == 1
    assert schedules_from_db_updated[0]['game_id'] == '180'
    assert schedules_from_db_updated[0]['game_time'] == '18:35'
    
    conn.close()
