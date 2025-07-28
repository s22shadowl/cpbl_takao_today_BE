# tests/api/test_api_players.py

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import datetime
from app import models


def test_get_player_stats_history_success(client: TestClient, db_session: Session):
    """【擴充】測試獲取球員球季數據歷史紀錄的端點，確保能正確過濾球員"""
    history_A1 = models.PlayerSeasonStatsHistoryDB(
        player_name="歷史哥A", avg=0.250, created_at=datetime.datetime(2025, 7, 20)
    )
    history_A2 = models.PlayerSeasonStatsHistoryDB(
        player_name="歷史哥A", avg=0.255, created_at=datetime.datetime(2025, 7, 21)
    )
    history_B1 = models.PlayerSeasonStatsHistoryDB(
        player_name="歷史哥B", avg=0.300, created_at=datetime.datetime(2025, 7, 21)
    )
    db_session.add_all([history_A1, history_A2, history_B1])
    db_session.commit()

    response = client.get("/api/players/歷史哥A/stats/history")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["avg"] == 0.250
    assert data[1]["avg"] == 0.255
    assert all(item["player_name"] == "歷史哥A" for item in data)


def test_get_player_stats_history_not_found(client: TestClient):
    """測試查詢不存在的球員歷史數據時返回 404"""
    response = client.get("/api/players/路人甲/stats/history")
    assert response.status_code == 404
