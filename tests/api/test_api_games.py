# tests/api/test_api_games.py

import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.crud import games
from app import models


def test_get_games_by_date_success(client: TestClient, db_session: Session):
    """測試 /api/games/{game_date} 端點在成功獲取數據時的情況"""
    game_info_1 = {
        "cpbl_game_id": "TEST_MAIN_01",
        "game_date": "2025-06-21",
        "home_team": "測試主隊",
        "away_team": "測試客隊",
        "status": "已完成",
    }
    games.create_game_and_get_id(db_session, game_info_1)
    db_session.commit()

    response = client.get("/api/games/2025-06-21")

    assert response.status_code == 200
    json_response = response.json()
    assert len(json_response) == 1
    assert json_response[0]["cpbl_game_id"] == "TEST_MAIN_01"


def test_get_games_by_date_not_found(client: TestClient):
    """【修改】測試 /api/games/{game_date} 端點在查無資料時返回 200 和空列表"""
    response = client.get("/api/games/2025-01-01")
    assert response.status_code == 200
    assert response.json() == []


def test_get_games_by_date_bad_format(client: TestClient):
    """測試 /api/games/{game_date} 端點在傳入錯誤日期格式時的情況"""
    response = client.get("/api/games/2025-06-21-invalid")
    assert response.status_code == 422


def test_get_game_details_success(client: TestClient, db_session: Session):
    """【擴充】測試獲取單場比賽完整細節的端點，包含多球員與多打席情境"""
    game = models.GameResultDB(
        cpbl_game_id="TEST_DETAIL_API",
        game_date=datetime.date(2025, 7, 22),
        home_team="H",
        away_team="A",
    )
    db_session.add(game)
    db_session.flush()

    summary1 = models.PlayerGameSummaryDB(
        game_id=game.id, player_name="測試員API_1", team_name="測試隊"
    )
    db_session.add(summary1)
    db_session.flush()
    detail1_1 = models.AtBatDetailDB(
        player_game_summary_id=summary1.id, sequence_in_game=1, result_short="全壘打"
    )
    detail1_2 = models.AtBatDetailDB(
        player_game_summary_id=summary1.id, sequence_in_game=2, result_short="三振"
    )
    db_session.add_all([detail1_1, detail1_2])

    summary2 = models.PlayerGameSummaryDB(
        game_id=game.id, player_name="測試員API_2", team_name="測試隊"
    )
    db_session.add(summary2)
    db_session.flush()
    detail2_1 = models.AtBatDetailDB(
        player_game_summary_id=summary2.id, sequence_in_game=1, result_short="一壘安打"
    )
    db_session.add(detail2_1)

    db_session.commit()

    response = client.get(f"/api/games/details/{game.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["cpbl_game_id"] == "TEST_DETAIL_API"
    assert len(data["player_summaries"]) == 2

    player1_summary = next(
        p for p in data["player_summaries"] if p["player_name"] == "測試員API_1"
    )
    assert len(player1_summary["at_bat_details"]) == 2
    assert player1_summary["at_bat_details"][0]["result_short"] == "全壘打"

    player2_summary = next(
        p for p in data["player_summaries"] if p["player_name"] == "測試員API_2"
    )
    assert len(player2_summary["at_bat_details"]) == 1
    assert player2_summary["at_bat_details"][0]["result_short"] == "一壘安打"


def test_get_game_details_not_found(client: TestClient):
    """測試查詢不存在的比賽 ID 時返回 404"""
    response = client.get("/api/games/details/9999")
    assert response.status_code == 404
