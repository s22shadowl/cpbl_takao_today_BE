# tests/api/test_api_system.py

from fastapi.testclient import TestClient
from unittest.mock import patch
from app.cache import redis_client
from app.config import settings


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
    # 使用 patch 來模擬 db.execute() 拋出異常
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

    # 1. 呼叫一個被快取的端點來產生快取
    # 我們選擇 /api/analysis/streaks 作為目標
    # 注意：此處的 db_session fixture 會提供一個空的記憶體資料庫，
    # 所以 API 會回傳空列表，但這不影響快取功能的測試。
    analysis_url = "/api/analysis/streaks?definition_name=consecutive_hits"
    client.get(analysis_url, headers={"X-API-Key": settings.API_KEY})

    # 2. 驗證快取鍵已存在
    # 根據 cache.py 的命名規則手動建立預期的快取鍵
    expected_cache_key = (
        "app.api.analysis:get_on_base_streaks:definition_name=consecutive_hits"
    )
    assert redis_client.exists(expected_cache_key), "前置步驟失敗：快取未被成功建立。"

    # --- 執行 (Act) ---

    # 3. 呼叫清除快取端點
    clear_response = client.post(
        "/api/system/clear-cache", headers={"X-API-Key": settings.API_KEY}
    )
    assert clear_response.status_code == 200
    assert "Successfully cleared" in clear_response.json()["message"]

    # --- 驗證 (Assert) ---

    # 4. 驗證快取鍵已被刪除
    assert not redis_client.exists(expected_cache_key), (
        "快取清除失敗：目標快取鍵仍然存在。"
    )
