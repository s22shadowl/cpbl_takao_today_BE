# tests/test_main.py

from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from app.main import app
from app import models # 為了 response_model 也需要 import

client = TestClient(app)

def test_get_games_by_date_success(mocker):
    """測試 /api/games 端點在成功獲取數據時的情況"""
    fake_db_result = [{"id": 1, "cpbl_game_id": "TEST01", "game_date": "2025-06-21", "home_team": "測試主隊", "away_team": "測試客隊", "home_score": 5, "away_score": 2}]
    mocker.patch('app.main.db_actions.get_games_by_date', return_value=fake_db_result)
    response = client.get("/api/games?game_date=2025-06-21")
    assert response.status_code == 200
    assert response.json()[0]["cpbl_game_id"] == "TEST01"

def test_get_games_by_date_bad_format():
    """測試 /api/games 端點在傳入錯誤日期格式時的情況"""
    response = client.get("/api/games?game_date=2025/06/21") # 使用錯誤的格式
    assert response.status_code == 422
    assert "日期格式錯誤" in response.json()["detail"]

def test_trigger_scraper_manually(mocker):
    """測試手動觸發爬蟲的 API 端點"""
    mock_scrape = mocker.patch('app.main.scraper.scrape_single_day')
    
    response = client.post("/api/run_scraper?mode=daily&date=2025-06-21")
    
    assert response.status_code == 200
    assert response.json()["message"] == "已在背景觸發 [單日] 爬蟲任務，目標日期: 2025-06-21。"
    mock_scrape.assert_called_once_with(specific_date='2025-06-21')