import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# 導入我們要測試的 app 物件和依賴函式
from app.main import app, get_api_key

# 導入 models 和 db_actions 以便在測試中準備資料
from app import db_actions

# --- 輔助函式 (Overrides) ---


def override_get_api_key_success():
    """一個假的 get_api_key 函式，直接回傳成功。"""
    return "test-api-key"


# --- 測試案例 ---


# 測試 /api/games/{game_date} 端點
def test_get_games_by_date_success(client: TestClient, db_session: Session):
    """測試 /api/games/{game_date} 端點在成功獲取數據時的情況"""
    # 步驟 1: 準備測試資料
    # 使用 db_session fixture 直接寫入資料到記憶體資料庫
    game_info_1 = {
        "cpbl_game_id": "TEST_MAIN_01",
        "game_date": "2025-06-21",
        "home_team": "測試主隊",
        "away_team": "測試客隊",
        "status": "已完成",
    }
    db_actions.store_game_and_get_id(db_session, game_info_1)
    db_session.commit()

    # 步驟 2: 透過 TestClient 呼叫 API
    # 這個 API 呼叫會實際查詢我們剛寫入資料的記憶體資料庫
    response = client.get("/api/games/2025-06-21")

    # 步驟 3: 驗證回應
    assert response.status_code == 200
    json_response = response.json()
    assert len(json_response) == 1
    assert json_response[0]["cpbl_game_id"] == "TEST_MAIN_01"


def test_get_games_by_date_not_found(client: TestClient):
    """測試 /api/games/{game_date} 端點在查無資料時返回 404"""
    # 直接呼叫一個不存在資料的日期，因為資料庫是乾淨的，所以應返回 404
    response = client.get("/api/games/2025-01-01")

    assert response.status_code == 404
    assert "找不到日期" in response.json()["detail"]


def test_get_games_by_date_bad_format(client: TestClient):
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
def test_run_scraper_manually(
    client: TestClient, mocker, mode, date_param, expected_task_str
):
    """測試手動觸發爬蟲的 API 端點，驗證對應的 Dramatiq 任務是否被發送"""
    mock_task = mocker.patch(expected_task_str)

    # 在測試函式內部，精準地覆寫 API 金鑰依賴
    app.dependency_overrides[get_api_key] = override_get_api_key_success

    headers = {"X-API-Key": "any-key-will-do"}
    request_payload = {"mode": mode, "date": date_param}
    response = client.post("/api/run_scraper", headers=headers, json=request_payload)

    # 測試結束後，清理掉覆寫，以免影響其他測試
    del app.dependency_overrides[get_api_key]

    assert response.status_code == 202
    mock_task.send.assert_called_once_with(date_param)


def test_run_scraper_manually_invalid_mode(client: TestClient):
    """測試手動觸發爬蟲時使用無效模式"""
    app.dependency_overrides[get_api_key] = override_get_api_key_success
    headers = {"X-API-Key": "any-key-will-do"}
    request_payload = {"mode": "invalid_mode", "date": None}
    response = client.post("/api/run_scraper", headers=headers, json=request_payload)
    del app.dependency_overrides[get_api_key]

    assert response.status_code == 400


# 測試 /api/update_schedule 端點
def test_update_schedule_manually(client: TestClient, mocker):
    """測試手動觸發賽程更新的 API 端點"""
    mock_task = mocker.patch("app.main.task_update_schedule_and_reschedule")

    app.dependency_overrides[get_api_key] = override_get_api_key_success
    headers = {"X-API-Key": "any-key-will-do"}
    response = client.post("/api/update_schedule", headers=headers)
    del app.dependency_overrides[get_api_key]

    assert response.status_code == 202
    mock_task.send.assert_called_once()


# 測試 API 金鑰保護 (這些測試不需要覆寫 get_api_key)
def test_post_endpoints_no_api_key(client: TestClient):
    """測試在沒有提供 API 金鑰時，POST 端點應返回 403"""
    response_run = client.post(
        "/api/run_scraper", json={"mode": "daily", "date": "2025-01-01"}
    )
    assert response_run.status_code == 403

    response_update = client.post("/api/update_schedule")
    assert response_update.status_code == 403


def test_post_endpoints_wrong_api_key(client: TestClient):
    """測試在提供錯誤 API 金鑰時，POST 端點應返回 403"""
    headers = {"X-API-Key": "wrong-key"}
    response_run = client.post(
        "/api/run_scraper",
        headers=headers,
        json={"mode": "daily", "date": "2025-01-01"},
    )
    assert response_run.status_code == 403

    response_update = client.post("/api/update_schedule", headers=headers)
    assert response_update.status_code == 403
