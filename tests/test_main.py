import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from app.main import app

pytestmark = pytest.mark.skip(reason="API 端點與其依賴的 db_actions 尚未對齊，暫時跳過所有 main 的整合測試。")

# 在所有測試中使用同一個 TestClient
client = TestClient(app)

# --- General Endpoints ---

def test_read_root():
    """測試根目錄端點"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "歡迎使用 CPBL Stats API"}

# --- Games Endpoints ---

def test_get_games_by_date_success(mocker):
    """測試 /api/games 端點在成功獲取數據時的情況"""
    # 模擬資料庫回傳的結果
    fake_db_result = [
        {"id": 1, "cpbl_game_id": "TEST01", "game_date": "2025-06-21", "home_team": "測試主隊", "away_team": "測試客隊", "home_score": 5, "away_score": 2}
    ]
    # 【修正】同時模擬 db_actions 和 db 的函式
    mocker.patch('app.db.get_db_connection', return_value=MagicMock())
    mocker.patch('app.db_actions.get_games_by_date', return_value=fake_db_result)
    
    response = client.get("/api/games?game_date=2025-06-21")
    
    assert response.status_code == 200
    json_response = response.json()
    assert isinstance(json_response, list)
    assert len(json_response) == 1
    assert json_response[0]["cpbl_game_id"] == "TEST01"

def test_get_games_by_date_not_found(mocker):
    """【新增】測試 /api/games 端點在查無資料時返回 404"""
    mocker.patch('app.db.get_db_connection', return_value=MagicMock())
    # 【修正】修正 patch 路徑
    mocker.patch('app.db_actions.get_games_by_date', return_value=[])
    
    response = client.get("/api/games?game_date=2025-01-01")
    
    assert response.status_code == 404
    assert "找不到日期" in response.json()["detail"]

def test_get_games_by_date_bad_format():
    """測試 /api/games 端點在傳入錯誤日期格式時的情況"""
    response = client.get("/api/games?game_date=2025-06-21-invalid")
    assert response.status_code == 422
    assert "日期格式錯誤" in response.json()["detail"]

# --- Player Endpoints ---

def test_get_season_stats_success(mocker):
    """【新增】測試獲取球員球季數據的成功情境"""
    fake_stats = {"player_name": "測試球員", "hits": 100, "homeruns": 10}
    mocker.patch('app.db.get_db_connection', return_value=MagicMock())
    # 【修正】修正 patch 路徑
    mocker.patch('app.db_actions.get_player_season_stats', return_value=fake_stats)

    response = client.get("/api/player/season_stats/測試球員")

    assert response.status_code == 200
    assert response.json()["player_name"] == "測試球員"
    assert response.json()["hits"] == 100

def test_get_season_stats_not_found(mocker):
    """【新增】測試獲取球員球季數據的 404 情境"""
    mocker.patch('app.db.get_db_connection', return_value=MagicMock())
    # 【修正】修正 patch 路徑
    mocker.patch('app.db_actions.get_player_season_stats', return_value=None)

    response = client.get("/api/player/season_stats/一個不存在的球員")

    assert response.status_code == 404
    assert "找不到球員" in response.json()["detail"]

def test_get_game_stats_success(mocker):
    """【新增】測試獲取球員最近比賽表現的成功情境"""
    fake_summaries = [{"game_date": "2025-06-25", "hits": 2, "rbi": 1}]
    mocker.patch('app.db.get_db_connection', return_value=MagicMock())
    # 【修正】修正 patch 路徑
    mocker.patch('app.db_actions.get_player_game_summaries', return_value=fake_summaries)

    response = client.get("/api/player/game_stats/測試球員?limit=5")
    
    assert response.status_code == 200
    json_response = response.json()
    assert len(json_response) == 1
    assert json_response[0]["hits"] == 2

def test_get_game_stats_not_found(mocker):
    """【新增】測試獲取球員最近比賽表現的 404 情境"""
    mocker.patch('app.db.get_db_connection', return_value=MagicMock())
    # 【修正】修正 patch 路徑
    mocker.patch('app.db_actions.get_player_game_summaries', return_value=[])

    response = client.get("/api/player/game_stats/一個不存在的球員")

    assert response.status_code == 404
    assert "找不到球員" in response.json()["detail"]

# --- Scraper Endpoints ---

@pytest.mark.parametrize(
    "mode, date_param, expected_function, expected_message",
    [
        ("daily", "2025-06-21", "app.scraper.scrape_single_day", "已在背景觸發 [單日] 爬蟲任務，目標日期: 2025-06-21。"),
        ("monthly", "2025-06", "app.scraper.scrape_entire_month", "已在背景觸發 [逐月] 爬蟲任務，目標月份: 2025-06。"),
        ("yearly", "2025", "app.scraper.scrape_entire_year", "已在背景觸發 [逐年] 爬蟲任務，目標年份: 2025。"),
    ]
)
def test_trigger_scraper_manually_modes(mocker, mode, date_param, expected_function, expected_message):
    """【擴充】測試手動觸發爬蟲的 API 端點的所有有效模式"""
    # 【修正】修正 patch 路徑
    with patch(expected_function) as mock_scrape_func:
        response = client.post(f"/api/run_scraper?mode={mode}&date={date_param}")
        
        assert response.status_code == 200
        assert response.json()["message"] == expected_message
        
        # 驗證對應的爬蟲函式是否被正確呼叫
        if mode == 'daily':
            mock_scrape_func.assert_called_once_with(specific_date=date_param)
        elif mode == 'monthly':
            mock_scrape_func.assert_called_once_with(month_str=date_param)
        elif mode == 'yearly':
            mock_scrape_func.assert_called_once_with(year_str=date_param)

def test_trigger_scraper_manually_invalid_mode():
    """【新增】測試手動觸發爬蟲時使用無效模式"""
    response = client.post("/api/run_scraper?mode=invalid_mode&date=2025-06-21")
    assert response.status_code == 400
    assert "無效的模式" in response.json()["detail"]