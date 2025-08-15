# tests/api/test_api_dashboard.py

import datetime

from fastapi.testclient import TestClient

from app.api.dependencies import get_dashboard_service
from app.main import app
from app.schemas import (
    DashboardHasGamesResponse,
    DashboardNoGamesResponse,
    GameResultWithDetails,
)


def test_get_today_dashboard_has_games(client: TestClient):
    """
    測試 GET /api/dashboard/today 端點在「當天有比賽」情境下的行為。
    """
    # 1. 準備模擬的 Service 回傳資料
    mock_game = GameResultWithDetails(
        id=1,
        cpbl_game_id="DASH_API_01",
        game_date="2025-08-15",
        home_team="測試A隊",
        away_team="測試B隊",
        status="Final",
    )
    mock_response_data = DashboardHasGamesResponse(
        status="HAS_TODAY_GAMES", games=[mock_game]
    )

    # 2. 定義一個會覆寫 (override) 原始依賴的函式
    def override_get_dashboard_service():
        # 這個假的 Service 不需要任何參數，它只做一件事：回傳我們準備好的資料
        class MockDashboardService:
            def get_today_dashboard_data(self):
                return mock_response_data

        return MockDashboardService()

    # 3. 將 App 的依賴換成我們的模擬版本
    app.dependency_overrides[get_dashboard_service] = override_get_dashboard_service

    # 4. 發送 API 請求
    response = client.get("/api/dashboard/today")

    # 5. 清理依賴覆寫，避免影響其他測試
    app.dependency_overrides.clear()

    # 6. 驗證結果
    assert response.status_code == 200
    expected_json = {
        "status": "HAS_TODAY_GAMES",
        "games": [
            {
                "id": 1,
                "cpbl_game_id": "DASH_API_01",
                "game_date": "2025-08-15",
                "game_time": None,
                "home_team": "測試A隊",
                "away_team": "測試B隊",
                "home_score": None,
                "away_score": None,
                "venue": None,
                "status": "Final",
                "player_summaries": [],  # Pydantic model 會填上預設值
            }
        ],
    }
    assert response.json() == expected_json


def test_get_today_dashboard_no_games(client: TestClient):
    """
    測試 GET /api/dashboard/today 端點在「當天無比賽」情境下的行為。
    """
    # 1. 準備模擬的 Service 回傳資料
    mock_response_data = DashboardNoGamesResponse(
        status="NO_TODAY_GAMES",
        next_game_date=datetime.date(2025, 8, 17),
        last_target_team_game=None,
    )

    # 2. 定義依賴覆寫
    def override_get_dashboard_service():
        class MockDashboardService:
            def get_today_dashboard_data(self):
                return mock_response_data

        return MockDashboardService()

    # 3. 替換 App 的依賴
    app.dependency_overrides[get_dashboard_service] = override_get_dashboard_service

    # 4. 發送 API 請求
    response = client.get("/api/dashboard/today")

    # 5. 清理
    app.dependency_overrides.clear()

    # 6. 驗證結果
    assert response.status_code == 200
    expected_json = {
        "status": "NO_TODAY_GAMES",
        "next_game_date": "2025-08-17",
        "last_target_team_game": None,
    }
    assert response.json() == expected_json
