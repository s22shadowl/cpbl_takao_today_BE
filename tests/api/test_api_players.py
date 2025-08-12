# tests/api/test_api_players.py

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import datetime
from app import models


def setup_test_data(db_session: Session):
    """建立並提交一組用於測試的歷史數據。"""
    db_session.query(models.PlayerSeasonStatsHistoryDB).delete()
    db_session.commit()

    history_data = [
        models.PlayerSeasonStatsHistoryDB(
            player_name="歷史哥A", avg=0.250, created_at=datetime.datetime(2025, 7, 20)
        ),
        models.PlayerSeasonStatsHistoryDB(
            player_name="歷史哥A", avg=0.255, created_at=datetime.datetime(2025, 7, 21)
        ),
        models.PlayerSeasonStatsHistoryDB(
            player_name="歷史哥A", avg=0.260, created_at=datetime.datetime(2025, 7, 22)
        ),
        models.PlayerSeasonStatsHistoryDB(
            player_name="歷史哥B", avg=0.300, created_at=datetime.datetime(2025, 7, 21)
        ),
    ]
    db_session.add_all(history_data)
    db_session.commit()
    return history_data


def test_get_player_stats_history_success(client: TestClient, db_session: Session):
    """測試獲取球員球季數據歷史紀錄的端點，確保能正確過濾球員。"""
    setup_test_data(db_session)

    response = client.get("/api/players/歷史哥A/stats/history")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert data[0]["avg"] == 0.250
    assert data[1]["avg"] == 0.255
    assert data[2]["avg"] == 0.260
    assert all(item["player_name"] == "歷史哥A" for item in data)


def test_get_player_stats_history_not_found(client: TestClient):
    """測試查詢不存在的球員歷史數據時返回 404。"""
    response = client.get("/api/players/路人甲/stats/history")
    assert response.status_code == 404


def test_get_player_stats_history_pagination(client: TestClient, db_session: Session):
    """[新增] 測試分頁功能 (skip, limit)。"""
    setup_test_data(db_session)

    # 測試 limit
    response_limit = client.get("/api/players/歷史哥A/stats/history?limit=1")
    assert response_limit.status_code == 200
    data_limit = response_limit.json()
    assert len(data_limit) == 1
    assert data_limit[0]["avg"] == 0.250

    # 測試 skip
    response_skip = client.get("/api/players/歷史哥A/stats/history?skip=1&limit=1")
    assert response_skip.status_code == 200
    data_skip = response_skip.json()
    assert len(data_skip) == 1
    assert data_skip[0]["avg"] == 0.255

    # 測試 skip 超過總數
    response_skip_high = client.get("/api/players/歷史哥A/stats/history?skip=10")
    assert response_skip_high.status_code == 200
    assert response_skip_high.json() == []


def test_get_player_stats_history_date_filter(client: TestClient, db_session: Session):
    """[新增] 測試日期區間篩選功能。"""
    setup_test_data(db_session)

    # 測試 start_date
    response_start = client.get(
        "/api/players/歷史哥A/stats/history?start_date=2025-07-21"
    )
    assert response_start.status_code == 200
    data_start = response_start.json()
    assert len(data_start) == 2
    assert data_start[0]["avg"] == 0.255

    # 測試 end_date
    response_end = client.get("/api/players/歷史哥A/stats/history?end_date=2025-07-21")
    assert response_end.status_code == 200
    data_end = response_end.json()
    assert len(data_end) == 2
    assert data_end[1]["avg"] == 0.255

    # 測試 start_date 和 end_date
    response_range = client.get(
        "/api/players/歷史哥A/stats/history?start_date=2025-07-21&end_date=2025-07-21"
    )
    assert response_range.status_code == 200
    data_range = response_range.json()
    assert len(data_range) == 1
    assert data_range[0]["avg"] == 0.255


def test_get_player_stats_history_date_filter_no_results(
    client: TestClient, db_session: Session
):
    """[新增] 測試當日期區間內無資料時，應回傳空列表。"""
    setup_test_data(db_session)

    response = client.get("/api/players/歷史哥A/stats/history?start_date=2026-01-01")
    assert response.status_code == 200
    assert response.json() == []
