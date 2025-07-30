# tests/api/test_api_system.py

from fastapi.testclient import TestClient
from unittest.mock import patch


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
