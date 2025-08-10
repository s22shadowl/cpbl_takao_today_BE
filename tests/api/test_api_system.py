from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import fakeredis

from app.config import settings
from dramatiq.results.errors import ResultMissing


def test_health_check_success(client: TestClient):
    """
    測試當資料庫連線正常時，/api/system/health 端點回傳 200 OK。
    """
    response = client.get("/api/system/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_check_db_error(client: TestClient):
    """
    測試當資料庫連線失敗時，/api/system/health 端點回傳 503 Service Unavailable。
    """
    with patch("app.api.system.Session.execute") as mock_execute:
        mock_execute.side_effect = Exception("Database connection error")

        response = client.get("/api/system/health")
        assert response.status_code == 503
        json_response = response.json()
        assert "detail" in json_response
        assert "Database connection error" in json_response["detail"]


# --- 測試 /api/system/clear-cache 端點 ---


def test_clear_cache_unauthorized(client: TestClient):
    """
    測試在沒有提供或提供錯誤 API 金鑰時，清除快取端點應回傳 401 未授權。
    """
    response_no_key = client.post("/api/system/clear-cache")
    assert response_no_key.status_code == 422

    response_wrong_key = client.post(
        "/api/system/clear-cache", headers={"X-API-Key": "wrong-key"}
    )
    assert response_wrong_key.status_code == 401


def test_clear_cache_integration(client: TestClient):
    """
    測試快取清除的完整整合流程。
    """
    fake_redis_instance = fakeredis.FakeStrictRedis(decode_responses=True)

    with (
        patch("app.cache.redis_client", fake_redis_instance),
        patch("app.api.system.redis_client", fake_redis_instance, create=True),
        patch("app.api.analysis.redis_client", fake_redis_instance, create=True),
    ):
        analysis_url = "/api/analysis/streaks?definition_name=consecutive_hits"
        client.get(analysis_url, headers={"X-API-Key": settings.API_KEY})

        expected_cache_key = (
            "app.api.analysis:get_on_base_streaks:definition_name=consecutive_hits"
        )
        fake_redis_instance.set(expected_cache_key, "some_test_data")
        assert fake_redis_instance.exists(expected_cache_key)

        clear_response = client.post(
            "/api/system/clear-cache", headers={"X-API-Key": settings.API_KEY}
        )
        assert clear_response.status_code == 200
        assert "Successfully cleared 1 cache keys" in clear_response.json()["message"]

        assert not fake_redis_instance.exists(expected_cache_key)


# --- 測試 /api/system/trigger-daily-crawl 端點 ---


def test_trigger_daily_crawl_unauthorized(client: TestClient):
    """測試在沒有提供或提供錯誤 API 金鑰時，觸發每日爬蟲端點應回傳 401/422。"""
    response_no_key = client.post("/api/system/trigger-daily-crawl")
    assert response_no_key.status_code == 422

    response_wrong_key = client.post(
        "/api/system/trigger-daily-crawl", headers={"X-API-Key": "wrong-key"}
    )
    assert response_wrong_key.status_code == 401


def test_trigger_daily_crawl_task_success(client: TestClient):
    """測試成功觸發每日爬蟲任務。"""
    with patch("app.api.system.task_run_daily_crawl.send") as mock_send:
        mock_task = MagicMock()
        mock_task.id = "mock_task_id_123"
        mock_send.return_value = mock_task

        response = client.post(
            "/api/system/trigger-daily-crawl", headers={"X-API-Key": settings.API_KEY}
        )

        assert response.status_code == 202
        json_response = response.json()
        assert json_response["message"] == "Daily crawl task successfully triggered."
        assert json_response["task_id"] == "mock_task_id_123"
        mock_send.assert_called_once()


def test_trigger_daily_crawl_task_failure(client: TestClient):
    """測試當任務入隊失敗時，端點應回傳 500 錯誤。"""
    with patch("app.api.system.task_run_daily_crawl.send") as mock_send:
        mock_send.side_effect = Exception("Broker connection error")

        response = client.post(
            "/api/system/trigger-daily-crawl", headers={"X-API-Key": settings.API_KEY}
        )

        assert response.status_code == 500
        assert "Failed to enqueue daily crawl task" in response.json()["detail"]
        mock_send.assert_called_once()


# --- 測試 /api/system/task-status/{task_id} 端點 ---


@patch("app.api.system.dramatiq.get_broker")
def test_get_task_status_succeeded(mock_get_broker, client: TestClient):
    """測試查詢已成功完成的任務狀態。"""
    mock_result_backend = MagicMock()
    mock_result_backend.get_result.return_value = "some_result"  # 任何非 Exception 的值
    mock_get_broker.return_value.get_result_backend.return_value = mock_result_backend

    response = client.get(
        "/api/system/task-status/some_task_id", headers={"X-API-Key": settings.API_KEY}
    )

    assert response.status_code == 200
    assert response.json() == {"task_id": "some_task_id", "status": "succeeded"}
    mock_result_backend.get_result.assert_called_once()


@patch("app.api.system.dramatiq.get_broker")
def test_get_task_status_failed(mock_get_broker, client: TestClient):
    """測試查詢已失敗的任務狀態。"""
    mock_result_backend = MagicMock()
    mock_result_backend.get_result.return_value = ValueError(
        "Task failed"
    )  # 返回一個 Exception 實例
    mock_get_broker.return_value.get_result_backend.return_value = mock_result_backend

    response = client.get(
        "/api/system/task-status/some_task_id", headers={"X-API-Key": settings.API_KEY}
    )

    assert response.status_code == 200
    assert response.json() == {"task_id": "some_task_id", "status": "failed"}
    mock_result_backend.get_result.assert_called_once()


@patch("app.api.system.dramatiq.get_broker")
def test_get_task_status_running(mock_get_broker, client: TestClient):
    """測試查詢仍在運行中的任務狀態。"""
    mock_result_backend = MagicMock()
    # ▼▼▼ 修正: 建立 ResultMissing 實例時提供必要的 message 參數 ▼▼▼
    mock_result_backend.get_result.side_effect = ResultMissing("Result not ready.")
    mock_get_broker.return_value.get_result_backend.return_value = mock_result_backend

    response = client.get(
        "/api/system/task-status/some_task_id", headers={"X-API-Key": settings.API_KEY}
    )

    assert response.status_code == 200
    assert response.json() == {"task_id": "some_task_id", "status": "running"}
    mock_result_backend.get_result.assert_called_once()


@patch("app.api.system.dramatiq.get_broker")
def test_get_task_status_no_backend_configured(mock_get_broker, client: TestClient):
    """測試當 result backend 未設定時，應回傳 501 錯誤。"""
    mock_get_broker.return_value.get_result_backend.return_value = None  # 模擬未設定

    response = client.get(
        "/api/system/task-status/some_task_id", headers={"X-API-Key": settings.API_KEY}
    )

    assert response.status_code == 501
    assert "Result backend is not configured" in response.json()["detail"]
