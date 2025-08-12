# tests/api/test_api_system.py

from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import fakeredis
import pytest

from app.main import app
from app.config import settings
from app.db import get_db
from dramatiq.results.errors import ResultMissing
import redis
from app.exceptions import APIErrorCode


# --- 測試 /api/system/health 端點 ---


@patch("app.api.system.redis_client", MagicMock())
def test_health_check_all_ok(client: TestClient):
    """測試當所有服務 (DB, Redis) 都正常時，回傳 200 OK。"""
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True

    with patch("app.api.system.redis_client", mock_redis):
        response = client.get("/api/system/health")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "database": "ok",
            "redis": "ok",
        }


def test_health_check_db_error(client: TestClient):
    """測試當資料庫連線失敗時，回傳 503 Service Unavailable。"""

    def get_db_override():
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("Database connection error")
        yield mock_db

    app.dependency_overrides[get_db] = get_db_override

    response = client.get("/api/system/health")
    assert response.status_code == 503
    json_response = response.json()
    assert json_response["code"] == APIErrorCode.SERVICE_UNAVAILABLE.value
    assert "Database connection error" in json_response["message"]

    app.dependency_overrides.clear()


@patch("app.api.system.redis_client", MagicMock())
def test_health_check_redis_error(client: TestClient):
    """[新增] 測試當 Redis 連線失敗時，回傳 503 Service Unavailable。"""
    mock_redis = MagicMock()
    mock_redis.ping.side_effect = redis.exceptions.ConnectionError(
        "Redis connection error"
    )

    with patch("app.api.system.redis_client", mock_redis):
        response = client.get("/api/system/health")
        assert response.status_code == 503
        json_response = response.json()
        assert json_response["code"] == APIErrorCode.SERVICE_UNAVAILABLE.value
        assert "Redis connection error" in json_response["message"]


# --- 測試 /api/system/clear-cache 端點 ---


@pytest.fixture
def fake_redis():
    """提供一個 fakeredis 實例用於測試。"""
    return fakeredis.FakeStrictRedis(decode_responses=True)


def test_clear_cache_unauthorized(client: TestClient):
    """測試在提供錯誤 API 金鑰時，清除快取端點應回傳 401。"""
    response_wrong_key = client.post(
        "/api/system/clear-cache", headers={"X-API-Key": "wrong-key"}
    )
    assert response_wrong_key.status_code == 401
    json_response = response_wrong_key.json()
    assert json_response["code"] == APIErrorCode.INVALID_CREDENTIALS.value


def test_clear_cache_success(client: TestClient, fake_redis: fakeredis.FakeStrictRedis):
    """測試成功清除符合模式的快取。"""
    with patch("app.api.system.redis_client", fake_redis, create=True):
        fake_redis.set("app.api.analysis:key1", "data1")
        fake_redis.set("app.api.analysis:key2", "data2")
        fake_redis.set("other_prefix:key3", "data3")

        response = client.post(
            "/api/system/clear-cache", headers={"X-API-Key": settings.API_KEY}
        )

        assert response.status_code == 200
        assert "Successfully cleared 2 cache keys" in response.json()["message"]
        assert not fake_redis.exists("app.api.analysis:key1")
        assert not fake_redis.exists("app.api.analysis:key2")
        assert fake_redis.exists("other_prefix:key3")


def test_clear_cache_no_matching_keys(
    client: TestClient, fake_redis: fakeredis.FakeStrictRedis
):
    """[新增] 測試當沒有符合模式的快取鍵時，函式能正常處理。"""
    with patch("app.api.system.redis_client", fake_redis, create=True):
        fake_redis.set("other_prefix:key1", "data1")

        response = client.post(
            "/api/system/clear-cache", headers={"X-API-Key": settings.API_KEY}
        )

        assert response.status_code == 200
        assert "No matching cache keys found" in response.json()["message"]
        assert fake_redis.exists("other_prefix:key1")


def test_clear_cache_redis_error(
    client: TestClient, fake_redis: fakeredis.FakeStrictRedis
):
    """[新增] 測試當 Redis 操作失敗時，端點應回傳 503 錯誤。"""
    mock_redis = MagicMock()
    mock_redis.scan_iter.side_effect = redis.exceptions.RedisError("Scan failed")

    with patch("app.api.system.redis_client", mock_redis, create=True):
        response = client.post(
            "/api/system/clear-cache", headers={"X-API-Key": settings.API_KEY}
        )
        # [修正] 驗證 ServiceUnavailableException 的回應
        assert response.status_code == 503
        json_response = response.json()
        assert json_response["code"] == APIErrorCode.SERVICE_UNAVAILABLE.value
        assert "Failed to communicate with Redis" in json_response["message"]


# --- 測試 /api/system/trigger-daily-crawl 端點 ---


def test_trigger_daily_crawl_success(client: TestClient):
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


def test_trigger_daily_crawl_broker_error(client: TestClient):
    """[修改] 測試當任務入隊因 Broker 錯誤而失敗時，端點應回傳 503。"""
    with patch("app.api.system.task_run_daily_crawl.send") as mock_send:
        mock_send.side_effect = Exception("Broker connection error")

        response = client.post(
            "/api/system/trigger-daily-crawl", headers={"X-API-Key": settings.API_KEY}
        )

        # [修正] 驗證 ServiceUnavailableException 的回應
        assert response.status_code == 503
        json_response = response.json()
        assert json_response["code"] == APIErrorCode.SERVICE_UNAVAILABLE.value
        assert "Failed to enqueue task" in json_response["message"]
        mock_send.assert_called_once()


# --- 測試 /api/system/task-status/{task_id} 端點 ---


@pytest.fixture
def mock_broker():
    """提供一個 mock 的 Dramatiq broker。"""
    with patch("app.api.system.dramatiq.get_broker") as mock_get_broker:
        mock_broker_instance = MagicMock()
        mock_result_backend = MagicMock()
        mock_broker_instance.get_result_backend.return_value = mock_result_backend
        mock_get_broker.return_value = mock_broker_instance
        yield mock_broker_instance


def test_get_task_status_succeeded(client: TestClient, mock_broker: MagicMock):
    """測試查詢已成功完成的任務狀態。"""
    mock_broker.get_result_backend().get_result.return_value = "some_result"

    response = client.get(
        "/api/system/task-status/some_task_id", headers={"X-API-Key": settings.API_KEY}
    )

    assert response.status_code == 200
    assert response.json() == {"task_id": "some_task_id", "status": "succeeded"}


def test_get_task_status_failed(client: TestClient, mock_broker: MagicMock):
    """測試查詢已失敗的任務狀態。"""
    mock_broker.get_result_backend().get_result.return_value = ValueError("Task failed")

    response = client.get(
        "/api/system/task-status/some_task_id", headers={"X-API-Key": settings.API_KEY}
    )

    assert response.status_code == 200
    assert response.json() == {"task_id": "some_task_id", "status": "failed"}


def test_get_task_status_running(client: TestClient, mock_broker: MagicMock):
    """測試查詢仍在運行中的任務狀態 (因 ResultMissing 異常)。"""
    mock_broker.get_result_backend().get_result.side_effect = ResultMissing(
        "Result not ready."
    )

    response = client.get(
        "/api/system/task-status/some_task_id", headers={"X-API-Key": settings.API_KEY}
    )

    assert response.status_code == 200
    assert response.json() == {"task_id": "some_task_id", "status": "running"}


def test_get_task_status_unknown_id(client: TestClient, mock_broker: MagicMock):
    """[新增] 測試查詢一個不存在或結果已過期的任務 ID。"""
    # [修正] 建立 ResultMissing 實例時提供必要的 message 參數
    mock_broker.get_result_backend().get_result.side_effect = ResultMissing(
        "Result not ready."
    )

    response = client.get(
        "/api/system/task-status/a_non_existent_id",
        headers={"X-API-Key": settings.API_KEY},
    )

    assert response.status_code == 200
    # 根據目前的邏輯，ResultMissing 會被視為 running
    assert response.json() == {"task_id": "a_non_existent_id", "status": "running"}


def test_get_task_status_no_backend_configured(
    client: TestClient, mock_broker: MagicMock
):
    """測試當 result backend 未設定時，應回傳 501 錯誤。"""
    mock_broker.get_result_backend.return_value = None

    response = client.get(
        "/api/system/task-status/some_task_id", headers={"X-API-Key": settings.API_KEY}
    )

    assert response.status_code == 501
    json_response = response.json()
    assert json_response["code"] == APIErrorCode.RESULT_BACKEND_NOT_CONFIGURED.value
