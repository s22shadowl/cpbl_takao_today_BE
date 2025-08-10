# tests/api/test_api_system.py

from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import fakeredis

from app.config import settings
# 即使原始的 redis_client 是 None，我們仍然匯入它，
# 因為 patch 將在測試執行時替換它。


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
    # 【修正】: patch 的目標是物件被「使用」的地方。
    # health_check 函式位於 app.api.system 模組，它參考了 Session。
    # 因此，正確的 patch 路徑是 'app.api.system.Session.execute'。
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
    # 情況一：沒有提供 API 金鑰
    response_no_key = client.post("/api/system/clear-cache")
    assert response_no_key.status_code == 422  # FastAPI 對缺失 Header 的預設回應

    # 情況二：提供錯誤的 API 金鑰
    response_wrong_key = client.post(
        "/api/system/clear-cache", headers={"X-API-Key": "wrong-key"}
    )
    assert response_wrong_key.status_code == 401


def test_clear_cache_integration(client: TestClient):
    """
    測試快取清除的完整整合流程。
    流程：
    1. 呼叫一個被快取的端點，以確保 Redis 中有快取資料。
    2. 驗證快取鍵確實存在於 Redis 中。
    3. 呼叫 /api/system/clear-cache 端點。
    4. 驗證先前建立的快取鍵已被刪除。
    """
    # --- 準備 (Arrange) ---

    # 1. 創建一個 fakeredis 實例來模擬 Redis。
    fake_redis_instance = fakeredis.FakeStrictRedis(decode_responses=True)

    # 2. 使用 patch 來在測試的上下文中，將相關模組中的 'redis_client' 替換為我們的 fake_redis_instance。
    #    我們 patch 物件的來源 ('app.cache.redis_client') 以及它被使用的主要地方。
    with (
        patch("app.cache.redis_client", fake_redis_instance),
        patch("app.api.system.redis_client", fake_redis_instance, create=True),
        patch("app.api.analysis.redis_client", fake_redis_instance, create=True),
    ):
        # 3. 呼叫一個被快取的端點來產生快取。
        analysis_url = "/api/analysis/streaks?definition_name=consecutive_hits"
        client.get(analysis_url, headers={"X-API-Key": settings.API_KEY})

        # 4. 驗證快取鍵已存在。
        expected_cache_key = (
            "app.api.analysis:get_on_base_streaks:definition_name=consecutive_hits"
        )

        # 為了讓測試更穩定，我們也手動設定一個，確保測試的後續步驟可以正常進行。
        fake_redis_instance.set(expected_cache_key, "some_test_data")

        # 【修正】: 直接使用我們在函式內建立的 fake_redis_instance 進行斷言，
        # 而不是使用在模組層級匯入、值可能為 None 的 redis_client。
        assert fake_redis_instance.exists(expected_cache_key), (
            "前置步驟失敗：快取未被成功建立。"
        )

        # --- 執行 (Act) ---

        # 5. 呼叫清除快取端點。
        clear_response = client.post(
            "/api/system/clear-cache", headers={"X-API-Key": settings.API_KEY}
        )
        assert clear_response.status_code == 200
        assert "Successfully cleared 1 cache keys" in clear_response.json()["message"]

        # --- 驗證 (Assert) ---

        # 6. 【修正】: 同樣，使用 fake_redis_instance 來驗證快取鍵已被刪除。
        assert not fake_redis_instance.exists(expected_cache_key), (
            "快取清除失敗：目標快取鍵仍然存在。"
        )


# --- ▼▼▼ 新增: 測試 /api/system/trigger-daily-crawl 端點 ▼▼▼ ---


def test_trigger_daily_crawl_unauthorized(client: TestClient):
    """測試在沒有提供或提供錯誤 API 金鑰時，觸發每日爬蟲端點應回傳 401/422。"""
    # 情況一：沒有提供 API 金鑰
    response_no_key = client.post("/api/system/trigger-daily-crawl")
    assert response_no_key.status_code == 422  # FastAPI 對缺失 Header 的預設回應

    # 情況二：提供錯誤的 API 金鑰
    response_wrong_key = client.post(
        "/api/system/trigger-daily-crawl", headers={"X-API-Key": "wrong-key"}
    )
    assert response_wrong_key.status_code == 401


def test_trigger_daily_crawl_task_success(client: TestClient):
    """測試成功觸發每日爬蟲任務。"""
    # 使用 patch 來模擬 task_run_daily_crawl.send 方法
    with patch("app.api.system.task_run_daily_crawl.send") as mock_send:
        # 讓 mock 的 send() 方法返回一個帶有 id 屬性的 mock 物件
        mock_task = MagicMock()
        mock_task.id = "mock_task_id_123"
        mock_send.return_value = mock_task

        response = client.post(
            "/api/system/trigger-daily-crawl", headers={"X-API-Key": settings.API_KEY}
        )

        # 驗證回應
        assert response.status_code == 202
        json_response = response.json()
        assert json_response["message"] == "Daily crawl task successfully triggered."
        assert json_response["task_id"] == "mock_task_id_123"

        # 驗證背景任務的 send 方法被呼叫了一次
        mock_send.assert_called_once()


def test_trigger_daily_crawl_task_failure(client: TestClient):
    """測試當任務入隊失敗時，端點應回傳 500 錯誤。"""
    with patch("app.api.system.task_run_daily_crawl.send") as mock_send:
        # 模擬 send() 方法拋出例外
        mock_send.side_effect = Exception("Broker connection error")

        response = client.post(
            "/api/system/trigger-daily-crawl", headers={"X-API-Key": settings.API_KEY}
        )

        # 驗證回應
        assert response.status_code == 500
        assert "Failed to enqueue daily crawl task" in response.json()["detail"]

        # 驗證 send 方法被呼叫了
        mock_send.assert_called_once()


# --- ▲▲▲ 新增: 測試 /api/system/trigger-daily-crawl 端點 ▲▲▲ ---
