# tests/test_main.py

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

# 導入我們要測試的 app 物件和依賴函式
from app.main import app, get_db, get_api_key
from app import models

# --- 假的依賴函式 (Overrides) ---

mock_db_session = MagicMock()


def override_get_db():
    """一個假的 get_db 函式，回傳我們可控制的 mock session。"""
    yield mock_db_session


def override_get_api_key_success():
    """一個假的 get_api_key 函式，直接回傳成功。"""
    return "test-api-key"


# 在所有測試執行前，只覆寫資料庫依賴
app.dependency_overrides[get_db] = override_get_db


# --- Fixtures ---


@pytest.fixture(autouse=True)
def reset_mocks_before_each_test():
    """自動執行的 fixture，在每個測試前重置 mock 物件。"""
    mock_db_session.reset_mock()


@pytest.fixture
def client():
    """提供一個 TestClient 實例。"""
    with TestClient(app) as test_client:
        yield test_client


# --- 測試案例 ---


# 測試 /api/games/{game_date} 端點
def test_get_games_by_date_success(client):
    """測試 /api/games/{game_date} 端點在成功獲取數據時的情況"""
    fake_game = models.GameResultDB(
        id=1,
        cpbl_game_id="TEST01",
        game_date="2025-06-21",
        home_team="測試主隊",
        away_team="測試客隊",
    )
    mock_db_session.query.return_value.filter.return_value.all.return_value = [
        fake_game
    ]

    response = client.get("/api/games/2025-06-21")

    assert response.status_code == 200
    json_response = response.json()
    assert len(json_response) == 1
    assert json_response[0]["cpbl_game_id"] == "TEST01"

    mock_db_session.query.assert_called_once_with(models.GameResultDB)
    mock_db_session.query.return_value.filter.assert_called_once()


def test_get_games_by_date_not_found(client):
    """測試 /api/games/{game_date} 端點在查無資料時返回 404"""
    mock_db_session.query.return_value.filter.return_value.all.return_value = []

    response = client.get("/api/games/2025-01-01")

    assert response.status_code == 404
    assert "找不到日期" in response.json()["detail"]


def test_get_games_by_date_bad_format(client):
    """測試 /api/games/{game_date} 端點在傳入錯誤日期格式時的情況"""
    response = client.get("/api/games/2025-06-21-invalid")
    assert response.status_code == 422


# 測試 /api/run_scraper 端點
@pytest.mark.parametrize(
    "mode, date_param, expected_task_str",
    [
        ("daily", "2025-06-21", "app.main.task_scrape_single_day"),
        ("monthly", "2025-06", "app.main.task_scrape_entire_month"),
        ("yearly", "2025", "app.main.task_scrape_entire_year"),
    ],
)
def test_run_scraper_manually(client, mocker, mode, date_param, expected_task_str):
    """測試手動觸發爬蟲的 API 端點，驗證對應的 Dramatiq 任務是否被發送"""
    mock_task = mocker.patch(expected_task_str)

    # 【核心修正】: 在測試函式內部，精準地覆寫 API 金鑰依賴
    app.dependency_overrides[get_api_key] = override_get_api_key_success

    headers = {"X-API-Key": "any-key-will-do"}
    # 【修正】: 將參數作為 JSON 請求主體發送
    request_payload = {"mode": mode, "date": date_param}
    response = client.post("/api/run_scraper", headers=headers, json=request_payload)

    # 【核心修正】: 測試結束後，清理掉覆寫，以免影響其他測試
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_get_db  # 重新設定 db 覆寫

    assert response.status_code == 202
    mock_task.send.assert_called_once_with(date_param)


def test_run_scraper_manually_invalid_mode(client):
    """測試手動觸發爬蟲時使用無效模式"""
    app.dependency_overrides[get_api_key] = override_get_api_key_success
    headers = {"X-API-Key": "any-key-will-do"}
    # 【修正】: 將參數作為 JSON 請求主體發送
    request_payload = {"mode": "invalid_mode", "date": None}
    response = client.post("/api/run_scraper", headers=headers, json=request_payload)
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_get_db

    assert response.status_code == 400


# 測試 /api/update_schedule 端點
def test_update_schedule_manually(client, mocker):
    """測試手動觸發賽程更新的 API 端點"""
    mock_task = mocker.patch("app.main.task_update_schedule_and_reschedule")

    app.dependency_overrides[get_api_key] = override_get_api_key_success
    headers = {"X-API-Key": "any-key-will-do"}
    response = client.post("/api/update_schedule", headers=headers)
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_get_db

    assert response.status_code == 202
    mock_task.send.assert_called_once()


# 測試 API 金鑰保護
def test_post_endpoints_no_api_key(client):
    """測試在沒有提供 API 金鑰時，POST 端點應返回 403"""
    # 【修正】: 因為現在需要請求主體，提供一個空的 JSON
    response_run = client.post(
        "/api/run_scraper", json={"mode": "daily", "date": "2025-01-01"}
    )
    assert response_run.status_code == 403

    response_update = client.post("/api/update_schedule")
    assert response_update.status_code == 403


def test_post_endpoints_wrong_api_key(client):
    """測試在提供錯誤 API 金鑰時，POST 端點應返回 403"""
    headers = {"X-API-Key": "wrong-key"}
    # 【修正】: 因為現在需要請求主體，提供一個空的 JSON
    response_run = client.post(
        "/api/run_scraper",
        headers=headers,
        json={"mode": "daily", "date": "2025-01-01"},
    )
    assert response_run.status_code == 403

    response_update = client.post("/api/update_schedule", headers=headers)
    assert response_update.status_code == 403
