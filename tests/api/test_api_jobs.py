# tests/api/test_api_jobs.py

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_api_key
from app.main import app
from app.config import settings
from app.exceptions import APIErrorCode


@pytest.fixture
def client() -> TestClient:
    """提供一個基本的、未經認證的 TestClient 實例。"""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def authenticated_client(client: TestClient):
    """提供一個已通過 API 金鑰驗證的 TestClient。"""

    def override_get_api_key_success():
        return settings.API_KEY

    app.dependency_overrides[get_api_key] = override_get_api_key_success
    yield client
    # 測試結束後清除 override
    del app.dependency_overrides[get_api_key]


# --- 手動觸發任務的端點 ---


@pytest.mark.parametrize(
    "mode, date_param, expected_task_str",
    [
        ("daily", "2025-06-21", "app.api.jobs.task_scrape_single_day"),
        ("monthly", "2025-06", "app.api.jobs.task_scrape_entire_month"),
        ("yearly", "2025", "app.api.jobs.task_scrape_entire_year"),
    ],
)
def test_run_scraper_manually(
    authenticated_client: TestClient, mocker, mode, date_param, expected_task_str
):
    """
    測試 /api/run_scraper 端點能根據模式，正確地分派任務。
    """
    mock_task = mocker.patch(expected_task_str)
    request_payload = {"mode": mode, "date": date_param}

    response = authenticated_client.post("/api/run_scraper", json=request_payload)

    assert response.status_code == 202
    mock_task.send.assert_called_once_with(date_param)


def test_run_scraper_manually_invalid_mode(authenticated_client: TestClient):
    """測試當傳入無效模式時，應回傳 400 錯誤。"""
    request_payload = {"mode": "invalid_mode", "date": None}
    response = authenticated_client.post("/api/run_scraper", json=request_payload)
    assert response.status_code == 400
    # [新增] 驗證新的錯誤回應格式
    json_response = response.json()
    assert json_response["code"] == APIErrorCode.INVALID_INPUT.value
    assert "Invalid mode" in json_response["message"]


def test_run_scraper_manually_invalid_date_format(authenticated_client: TestClient):
    """測試當 daily 模式傳入無效日期格式時，應回傳 400 錯誤。"""
    request_payload = {"mode": "daily", "date": "2025-13-01"}
    response = authenticated_client.post("/api/run_scraper", json=request_payload)
    # [修改] 驗證新的錯誤狀態碼與回應格式
    assert response.status_code == 400
    json_response = response.json()
    assert json_response["code"] == APIErrorCode.INVALID_INPUT.value
    assert "Invalid date format" in json_response["message"]


def test_update_schedule_manually(authenticated_client: TestClient, mocker):
    """測試 /api/update_schedule 端點能成功觸發任務。"""
    mock_task = mocker.patch("app.api.jobs.task_update_schedule_and_reschedule")
    response = authenticated_client.post("/api/update_schedule")
    assert response.status_code == 202
    mock_task.send.assert_called_once()


# --- API 金鑰保護 ---


def test_post_endpoints_unauthorized(client: TestClient):
    """測試在提供錯誤 API 金鑰時，所有 POST 端點應回傳 401。"""
    headers = {"X-API-Key": "wrong-key"}
    response_run_wrong = client.post(
        "/api/run_scraper",
        headers=headers,
        json={"mode": "daily", "date": "2025-01-01"},
    )
    # [修改] 驗證新的錯誤狀態碼與回應格式
    assert response_run_wrong.status_code == 401
    json_response = response_run_wrong.json()
    assert json_response["code"] == APIErrorCode.INVALID_CREDENTIALS.value

    response_update_wrong = client.post("/api/update_schedule", headers=headers)
    assert response_update_wrong.status_code == 401
