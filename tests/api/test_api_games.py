# tests/api/test_api_games.py

import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.crud import games
from app import models
from app.exceptions import APIErrorCode


def test_get_games_by_date_success(client: TestClient, db_session: Session):
    """測試 /api/games/{game_date} 端點在成功獲取數據時的情況"""
    game_info_1 = {
        "cpbl_game_id": "TEST_MAIN_01",
        "game_date": "2025-06-21",
        "home_team": "測試主隊A",
        "away_team": "測試客隊B",
        "status": "已完成",
    }
    game_info_2 = {
        "cpbl_game_id": "TEST_MAIN_02",
        "game_date": "2025-06-21",
        "home_team": "測試主隊C",
        "away_team": "測試客隊D",
        "status": "已完成",
    }
    games.create_game_and_get_id(db_session, game_info_1)
    games.create_game_and_get_id(db_session, game_info_2)
    db_session.commit()

    response = client.get("/api/games/2025-06-21")

    assert response.status_code == 200
    json_response = response.json()
    assert len(json_response) == 2


def test_get_games_by_date_with_team_filter(client: TestClient, db_session: Session):
    """[新增] 測試依隊伍名稱篩選比賽的功能"""
    game_info_1 = {
        "cpbl_game_id": "TEST_TEAM_FILTER_01",
        "game_date": "2025-08-01",
        "home_team": "雄鷹",
        "away_team": "猛獅",
        "status": "已完成",
    }
    game_info_2 = {
        "cpbl_game_id": "TEST_TEAM_FILTER_02",
        "game_date": "2025-08-01",
        "home_team": "悍將",
        "away_team": "桃猿",
        "status": "已完成",
    }
    games.create_game_and_get_id(db_session, game_info_1)
    games.create_game_and_get_id(db_session, game_info_2)
    db_session.commit()

    response = client.get("/api/games/2025-08-01?team_name=雄鷹")
    assert response.status_code == 200
    json_response = response.json()
    assert len(json_response) == 1
    assert json_response[0]["cpbl_game_id"] == "TEST_TEAM_FILTER_01"


def test_get_games_by_date_not_found(client: TestClient):
    """測試 /api/games/{game_date} 端點在查無資料時返回 200 和空列表"""
    response = client.get("/api/games/2025-01-01")
    assert response.status_code == 200
    assert response.json() == []


def test_get_games_by_date_bad_format(client: TestClient):
    """測試 /api/games/{game_date} 端點在傳入錯誤日期格式時的情況"""
    response = client.get("/api/games/2025-06-21-invalid")
    # [修改] 驗證新的錯誤狀態碼與回應格式
    assert response.status_code == 400
    json_response = response.json()
    assert json_response["code"] == APIErrorCode.INVALID_INPUT.value
    assert "Invalid date format" in json_response["message"]


def setup_game_detail_data(db_session: Session) -> models.GameResultDB:
    """[新增] 建立一筆包含多球員與多打席的比賽資料以供測試"""
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
    return game


def test_get_game_details_success(client: TestClient, db_session: Session):
    """測試獲取單場比賽完整細節的端點，包含多球員與多打席情境"""
    game = setup_game_detail_data(db_session)
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
    # [修改] 驗證新的錯誤狀態碼與回應格式
    assert response.status_code == 404
    json_response = response.json()
    assert json_response["code"] == APIErrorCode.RESOURCE_NOT_FOUND.value
    assert "Game with ID 9999 not found" in json_response["message"]


def test_get_game_details_no_player_data(client: TestClient, db_session: Session):
    """[新增] 測試查詢一場存在但沒有任何球員資料的比賽"""
    game = models.GameResultDB(
        cpbl_game_id="NO_PLAYER_DATA",
        game_date=datetime.date(2025, 1, 1),
        home_team="H",
        away_team="A",
    )
    db_session.add(game)
    db_session.commit()

    response = client.get(f"/api/games/details/{game.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["cpbl_game_id"] == "NO_PLAYER_DATA"
    assert data["player_summaries"] == []


def test_get_game_details_player_with_no_at_bats(
    client: TestClient, db_session: Session
):
    """[新增] 測試比賽中有球員出賽但沒有打席紀錄的情況"""
    game = models.GameResultDB(
        cpbl_game_id="NO_AT_BATS",
        game_date=datetime.date(2025, 1, 2),
        home_team="H",
        away_team="A",
    )
    db_session.add(game)
    db_session.flush()
    summary = models.PlayerGameSummaryDB(
        game_id=game.id, player_name="代跑哥", team_name="測試隊"
    )
    db_session.add(summary)
    db_session.commit()

    response = client.get(f"/api/games/details/{game.id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["player_summaries"]) == 1
    player_summary = data["player_summaries"][0]
    assert player_summary["player_name"] == "代跑哥"
    assert player_summary["at_bat_details"] == []


# [T29 新增] 測試 /api/games/season 端點
def test_get_season_games(client: TestClient, db_session: Session, monkeypatch):
    """測試 /api/games/season 端點的各種情境"""
    # Mock settings
    monkeypatch.setattr("app.config.settings.TARGET_TEAMS", ["測試雄鷹"])
    team_name = "測試雄鷹"

    # 準備測試資料
    game1 = models.GameResultDB(
        id=1,
        game_date=datetime.date(2025, 4, 1),
        home_team=team_name,
        away_team="測試龍",
        status="已完成",
    )
    game2 = models.GameResultDB(
        id=2,
        game_date=datetime.date(2025, 4, 2),
        home_team="測試獅",
        away_team=team_name,
        status="已完成",
    )
    game3 = models.GameResultDB(
        id=3,
        game_date=datetime.date(2025, 4, 3),
        home_team=team_name,
        away_team="測試象",
        status="未開始",
    )
    game4 = models.GameResultDB(
        id=4,
        game_date=datetime.date(2024, 5, 5),
        home_team=team_name,
        away_team="測試猿",
        status="已完成",
    )
    db_session.add_all([game1, game2, game3, game4])
    db_session.commit()

    # 測試情境 1: 預設參數 (今年, all)
    # 假設今年是 2025
    response_default = client.get("/api/games/season?year=2025")
    assert response_default.status_code == 200
    data_default = response_default.json()
    assert len(data_default) == 3
    assert {d["game_id"] for d in data_default} == {1, 2, 3}

    # 測試情境 2: 指定年份
    response_2024 = client.get("/api/games/season?year=2024")
    assert response_2024.status_code == 200
    data_2024 = response_2024.json()
    assert len(data_2024) == 1
    assert data_2024[0]["game_id"] == 4

    # 測試情境 3: 只看已完成
    response_completed = client.get("/api/games/season?year=2025&completed_only=true")
    assert response_completed.status_code == 200
    data_completed = response_completed.json()
    assert len(data_completed) == 2
    assert {d["game_id"] for d in data_completed} == {1, 2}

    # 測試情境 4: 查無資料
    response_no_data = client.get("/api/games/season?year=2026")
    assert response_no_data.status_code == 200
    assert response_no_data.json() == []
