# tests/core/test_db_actions.py

import pytest
import sqlite3
from pathlib import Path

from app import db_actions
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
    
    # 1. 第一次插入，應該會成功並回傳 id 1
    game_id = db_actions.store_game_and_get_id(conn, game_info)
    assert game_id == 1
    
    # 2. 第二次插入相同的比賽，應該因為 INSERT OR IGNORE 而被忽略
    # 但函式依然應該查詢並回傳已存在的 id 1
    game_id_again = db_actions.store_game_and_get_id(conn, game_info)
    assert game_id_again == 1
    
    # 3. 檢查資料庫中確實只有一筆資料
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM game_results")
    count = cursor.fetchone()[0]
    assert count == 1
    
    conn.close()


def test_update_player_season_stats(initialized_db):
    """測試 update_player_season_stats 函式"""
    conn = initialized_db()
    
    # 準備假的球員球季數據
    stats_list = [
        {'player_name': '測試員A', 'team_name': '測試隊', 'avg': 0.300},
        {'player_name': '測試員B', 'team_name': '測試隊', 'avg': 0.250, 'homeruns': 5},
    ]
    
    # 1. 第一次更新 (實際上是插入)
    db_actions.update_player_season_stats(conn, stats_list)
    
    # 驗證數據是否已寫入
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM player_season_stats WHERE player_name = ?", ('測試員A',))
    player_a = cursor.fetchone()
    assert player_a is not None
    assert player_a['avg'] == 0.300
    
    # 2. 準備新的數據來測試更新
    updated_stats_list = [
        {'player_name': '測試員A', 'team_name': '測試隊', 'avg': 0.305, 'hits': 10},
    ]
    db_actions.update_player_season_stats(conn, updated_stats_list)
    
    # 驗證數據是否已更新
    cursor.execute("SELECT * FROM player_season_stats WHERE player_name = ?", ('測試員A',))
    player_a_updated = cursor.fetchone()
    assert player_a_updated['avg'] == 0.305
    assert player_a_updated['hits'] == 10 # 驗證其他欄位也被更新
    
    # 驗證總筆數依然是 2
    cursor.execute("SELECT COUNT(*) FROM player_season_stats")
    count = cursor.fetchone()[0]
    assert count == 2
    
    conn.close()

def test_store_player_game_data(initialized_db):
    """測試 store_player_game_data 函式"""
    conn = initialized_db()
    
    # 1. 先建立一筆比賽記錄
    game_info = {'cpbl_game_id': 'TEST02', 'game_date': '2025-06-21', 'home_team': 'H', 'away_team': 'A'}
    game_id = db_actions.store_game_and_get_id(conn, game_info)
    assert game_id is not None
    
    # 2. 準備假的球員單場數據
    player_data_list = [
        {
            "summary": {"player_name": "測試員C", "team_name": "測試隊", "at_bats": 4, "hits": 2},
            "at_bats_list": ["一安", "三振", "二安", "滾地"]
        },
        {
            "summary": {"player_name": "測試員D", "team_name": "測試隊", "at_bats": 1, "hits": 1, "homeruns": 1},
            "at_bats_list": ["全壘打"]
        }
    ]
    
    # 3. 執行儲存操作
    db_actions.store_player_game_data(conn, game_id, player_data_list)
    
    # 4. 驗證結果
    cursor = conn.cursor()
    # 驗證 player_game_summary 表
    cursor.execute("SELECT * FROM player_game_summary WHERE game_id = ?", (game_id,))
    summaries = cursor.fetchall()
    assert len(summaries) == 2
    
    # 驗證 at_bat_details 表
    cursor.execute("SELECT id FROM player_game_summary WHERE player_name = ?", ('測試員C',))
    summary_id_c = cursor.fetchone()[0]
    
    cursor.execute("SELECT * FROM at_bat_details WHERE player_game_summary_id = ?", (summary_id_c,))
    details_c = cursor.fetchall()
    assert len(details_c) == 4
    assert details_c[0]['result_short'] == '一安'
    
    conn.close()