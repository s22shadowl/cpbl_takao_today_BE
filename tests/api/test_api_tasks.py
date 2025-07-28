# tests/api/test_api_tasks.py

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_api_key
from app.main import app

# --- 輔助函式 (Overrides) ---


def override_get_api_key_success():
    """一個假的 get_api_key 函式，直接回傳成功。"""
    return "test-api-key"


# --- 手動觸發任務的端點 ---


@pytest.mark.parametrize(
    "mode, date_param, expected_task_str",
    [
        ("daily", "2025-06-21", "app.api.tasks.task_scrape_single_day"),
        ("monthly", "2025-06", "app.api.tasks.task_scrape_entire_month"),
        ("yearly", "2025", "app.api.tasks.task_scrape_entire_year"),
    ],
)
def test_run_scraper_manually(
    client: TestClient, mocker, mode, date_param, expected_task_str
):
    mock_task = mocker.patch(expected_task_str)
    app.dependency_overrides[get_api_key] = override_get_api_key_success
    headers = {"X-API-Key": "any-key-will-do"}
    request_payload = {"mode": mode, "date": date_param}
    response = client.post("/api/run_scraper", headers=headers, json=request_payload)
    del app.dependency_overrides[get_api_key]
    assert response.status_code == 202
    mock_task.send.assert_called_once_with(date_param)


def test_run_scraper_manually_invalid_mode(client: TestClient):
    app.dependency_overrides[get_api_key] = override_get_api_key_success
    headers = {"X-API-Key": "any-key-will-do"}
    request_payload = {"mode": "invalid_mode", "date": None}
    response = client.post("/api/run_scraper", headers=headers, json=request_payload)
    del app.dependency_overrides[get_api_key]
    assert response.status_code == 400


def test_update_schedule_manually(client: TestClient, mocker):
    mock_task = mocker.patch("app.api.tasks.task_update_schedule_and_reschedule")
    app.dependency_overrides[get_api_key] = override_get_api_key_success
    headers = {"X-API-Key": "any-key-will-do"}
    response = client.post("/api/update_schedule", headers=headers)
    del app.dependency_overrides[get_api_key]
    assert response.status_code == 202
    mock_task.send.assert_called_once()


# --- API 金鑰保護 ---


def test_post_endpoints_no_api_key(client: TestClient):
    response_run = client.post(
        "/api/run_scraper", json={"mode": "daily", "date": "2025-01-01"}
    )
    assert response_run.status_code == 403
    response_update = client.post("/api/update_schedule")
    assert response_update.status_code == 403


def test_post_endpoints_wrong_api_key(client: TestClient):
    headers = {"X-API-Key": "wrong-key"}
    response_run = client.post(
        "/api/run_scraper",
        headers=headers,
        json={"mode": "daily", "date": "2025-01-01"},
    )
    assert response_run.status_code == 403
    response_update = client.post("/api/update_schedule", headers=headers)
    assert response_update.status_code == 403
