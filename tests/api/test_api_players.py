# tests/api/test_api_players.py

import datetime
from fastapi.testclient import TestClient

from app import models


def test_get_player_stats_history_single_player(client: TestClient, db_session):
    """
    測試舊有行為：查詢單一球員的歷史數據。
    """
    # 準備資料
    player_name = "測試球員A"
    db_session.add(
        models.PlayerSeasonStatsHistoryDB(
            player_name=player_name,
            created_at=datetime.datetime(2025, 8, 1, 10, 0, 0),
            hits=10,
        )
    )
    db_session.commit()

    # 執行 API 請求
    response = client.get(f"/api/players/stats/history?player_name={player_name}")

    # 驗證
    assert response.status_code == 200
    data = response.json()
    assert player_name in data
    assert isinstance(data[player_name], list)
    assert len(data[player_name]) == 1
    assert data[player_name][0]["hits"] == 10


def test_get_player_stats_history_multiple_players(client: TestClient, db_session):
    """
    測試新功能：一次查詢多位球員的歷史數據，並驗證回傳格式是否正確分組。
    """
    # 準備資料
    player1_name = "王柏融"
    player2_name = "陳傑憲"
    records = [
        models.PlayerSeasonStatsHistoryDB(
            player_name=player1_name,
            created_at=datetime.datetime(2025, 8, 1, 10, 0, 0),
            avg=0.290,
        ),
        models.PlayerSeasonStatsHistoryDB(
            player_name=player1_name,
            created_at=datetime.datetime(2025, 8, 2, 10, 0, 0),
            avg=0.292,
        ),
        models.PlayerSeasonStatsHistoryDB(
            player_name=player2_name,
            created_at=datetime.datetime(2025, 8, 1, 10, 0, 0),
            avg=0.310,
        ),
    ]
    db_session.add_all(records)
    db_session.commit()

    # 執行 API 請求
    response = client.get(
        f"/api/players/stats/history?player_name={player1_name}&player_name={player2_name}"
    )

    # 驗證
    assert response.status_code == 200
    data = response.json()

    # 驗證結構
    assert isinstance(data, dict)
    assert player1_name in data
    assert player2_name in data

    # 驗證內容
    assert len(data[player1_name]) == 2
    assert len(data[player2_name]) == 1
    assert data[player1_name][0]["avg"] == 0.290
    assert data[player1_name][1]["avg"] == 0.292
    assert data[player2_name][0]["avg"] == 0.310


def test_get_player_stats_history_with_date_filter(client: TestClient, db_session):
    """
    測試多球員查詢搭配日期篩選。
    """
    # 準備資料
    player_name = "林立"
    records = [
        models.PlayerSeasonStatsHistoryDB(
            player_name=player_name,
            created_at=datetime.datetime(2025, 7, 31, 10, 0, 0),
            hits=50,
        ),
        models.PlayerSeasonStatsHistoryDB(
            player_name=player_name,
            created_at=datetime.datetime(2025, 8, 1, 10, 0, 0),
            hits=52,
        ),
    ]
    db_session.add_all(records)
    db_session.commit()

    # 執行 API 請求 (只查詢 8/1 當天)
    response = client.get(
        f"/api/players/stats/history?player_name={player_name}&start_date=2025-08-01&end_date=2025-08-01"
    )

    # 驗證
    assert response.status_code == 200
    data = response.json()
    assert player_name in data
    assert len(data[player_name]) == 1
    assert data[player_name][0]["hits"] == 52


def test_get_player_stats_history_player_not_found(client: TestClient):
    """
    測試查詢一個完全不存在的球員時，應回傳 404 錯誤。
    """
    player_name = "不存在的球員"
    response = client.get(f"/api/players/stats/history?player_name={player_name}")

    assert response.status_code == 404
    assert response.json()["code"] == "PLAYER_NOT_FOUND"
