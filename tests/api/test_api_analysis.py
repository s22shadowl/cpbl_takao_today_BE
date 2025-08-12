# tests/api/test_api_analysis.py

import pytest
import datetime
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app import models
from app.cache import redis_client

# --- 測試資料設定 Fixture ---


@pytest.fixture(scope="function", autouse=True)
def auto_clear_cache():
    """[新增] 自動使用的 fixture，在每個測試函式執行後自動清除所有快取。"""
    yield
    if redis_client:
        redis_client.flushdb()


@pytest.fixture(scope="function")
def setup_streak_test_data(db_session: Session):
    """建立一個用於測試「連線」功能的比賽場景。"""
    game = models.GameResultDB(
        cpbl_game_id="STREAK_TEST_GAME",
        game_date=datetime.date(2025, 8, 15),
        home_team="H",
        away_team="A",
    )
    db_session.add(game)
    db_session.flush()

    summaries = {}
    players = [("A", "1"), ("B", "2"), ("C", "3"), ("D", "4"), ("E", "5"), ("F", "6")]
    for name, order in players:
        summary = models.PlayerGameSummaryDB(
            game_id=game.id,
            player_name=f"球員{name}",
            batting_order=int(order),  # 確保棒次是整數
            team_name="測試隊",
        )
        db_session.add(summary)
        summaries[name] = summary
    db_session.flush()

    db_session.add_all(
        [
            models.AtBatDetailDB(
                player_game_summary_id=summaries["A"].id,
                game_id=game.id,
                inning=1,
                sequence_in_game=1,
                result_short="一安",
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["B"].id,
                game_id=game.id,
                inning=1,
                sequence_in_game=2,
                result_short="四壞",
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["C"].id,
                game_id=game.id,
                inning=1,
                sequence_in_game=3,
                result_short="二安",
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["D"].id,
                game_id=game.id,
                inning=1,
                sequence_in_game=4,
                result_short="三振",
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["E"].id,
                game_id=game.id,
                inning=2,
                sequence_in_game=5,
                result_short="全打",
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["F"].id,
                game_id=game.id,
                inning=2,
                sequence_in_game=6,
                result_short="一安",
            ),
        ]
    )
    db_session.commit()
    return game


@pytest.fixture(scope="function")
def setup_ibb_impact_test_data(db_session: Session):
    """建立一個用於測試「IBB 影響」功能的比賽場景。"""
    game = models.GameResultDB(
        cpbl_game_id="IBB_IMPACT_TEST_GAME",
        game_date=datetime.date(2025, 8, 16),
        home_team="H",
        away_team="A",
    )
    db_session.add(game)
    db_session.flush()

    summaries = {}
    players = [("A", "1"), ("B", "2"), ("C", "3"), ("D", "4")]
    for name, order in players:
        summary = models.PlayerGameSummaryDB(
            game_id=game.id,
            player_name=f"影響者{name}",
            batting_order=int(order),  # 確保棒次是整數
            team_name="測試隊",
        )
        db_session.add(summary)
        summaries[name] = summary
    db_session.flush()

    db_session.add_all(
        [
            models.AtBatDetailDB(
                player_game_summary_id=summaries["A"].id,
                game_id=game.id,
                inning=1,
                result_short="一安",
                runs_scored_on_play=0,
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["B"].id,
                game_id=game.id,
                inning=1,
                result_description_full="故意四壞",
                runs_scored_on_play=0,
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["C"].id,
                game_id=game.id,
                inning=1,
                result_short="二安",
                runs_scored_on_play=1,
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["D"].id,
                game_id=game.id,
                inning=1,
                result_short="全打",
                runs_scored_on_play=2,
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["A"].id,
                game_id=game.id,
                inning=2,
                result_short="滾地",
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["B"].id,
                game_id=game.id,
                inning=2,
                result_description_full="故意四壞",
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["C"].id,
                game_id=game.id,
                inning=2,
                result_short="三振",
            ),
        ]
    )
    db_session.commit()
    return game


# --- 進階分析端點測試 ---


def test_get_games_with_players_pagination(client: TestClient, db_session: Session):
    """測試查詢指定球員群組是否同時出賽，並驗證分頁功能。"""
    g1 = models.GameResultDB(
        cpbl_game_id="G1",
        game_date=datetime.date(2025, 8, 1),
        home_team="H",
        away_team="A",
    )
    g2 = models.GameResultDB(
        cpbl_game_id="G2",
        game_date=datetime.date(2025, 8, 2),
        home_team="H",
        away_team="A",
    )
    db_session.add_all([g1, g2])
    db_session.flush()
    s1a = models.PlayerGameSummaryDB(game_id=g1.id, player_name="球員A", position="RF")
    s1b = models.PlayerGameSummaryDB(game_id=g1.id, player_name="球員B", position="PH")
    s2a = models.PlayerGameSummaryDB(game_id=g2.id, player_name="球員A", position="RF")
    s2b = models.PlayerGameSummaryDB(game_id=g2.id, player_name="球員B", position="CF")
    db_session.add_all([s1a, s1b, s2a, s2b])
    db_session.commit()

    # 查詢 A, B -> 應回傳 G2, G1 (因日期倒序)
    response = client.get(
        "/api/analysis/games-with-players?players=球員A&players=球員B&limit=1"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["cpbl_game_id"] == "G2"

    response_skip = client.get(
        "/api/analysis/games-with-players?players=球員A&players=球員B&skip=1&limit=1"
    )
    assert response_skip.status_code == 200
    data_skip = response_skip.json()
    assert len(data_skip) == 1
    assert data_skip[0]["cpbl_game_id"] == "G1"


def test_get_last_homerun_with_stats(client: TestClient, db_session: Session):
    """測試查詢球員的最後一轟，並驗證回傳的統計數據。"""
    freezed_today = datetime.date(2025, 8, 10)
    g1 = models.GameResultDB(
        cpbl_game_id="G_HR1",
        game_date=datetime.date(2025, 8, 1),
        home_team="H",
        away_team="A",
    )
    g2 = models.GameResultDB(
        cpbl_game_id="G_HR2",
        game_date=datetime.date(2025, 8, 5),
        home_team="H",
        away_team="A",
    )
    g3 = models.GameResultDB(
        cpbl_game_id="G_HR3",
        game_date=datetime.date(2025, 8, 8),
        home_team="H",
        away_team="A",
    )
    db_session.add_all([g1, g2, g3])
    db_session.flush()
    s1 = models.PlayerGameSummaryDB(game_id=g1.id, player_name="轟炸基", at_bats=4)
    s2 = models.PlayerGameSummaryDB(game_id=g2.id, player_name="轟炸基", at_bats=5)
    s3 = models.PlayerGameSummaryDB(game_id=g3.id, player_name="轟炸基", at_bats=3)
    db_session.add_all([s1, s2, s3])
    db_session.flush()
    hr1 = models.AtBatDetailDB(
        player_game_summary_id=s1.id, game_id=g1.id, result_description_full="全壘打"
    )
    hr2 = models.AtBatDetailDB(
        player_game_summary_id=s2.id,
        game_id=g2.id,
        result_description_full="關鍵全壘打",
        opposing_pitcher_name="投手B",
    )
    db_session.add_all([hr1, hr2])
    db_session.commit()

    # [修正] patch 的目標應為 crud.analysis 中被匯入的 datetime 模組
    with patch("app.crud.analysis.datetime") as mock_datetime:
        # [修正] 設定 mock datetime 物件內部 date.today() 的回傳值
        mock_datetime.date.today.return_value = freezed_today
        response = client.get("/api/analysis/players/轟炸基/last-homerun")

    assert response.status_code == 200
    data = response.json()
    assert data["last_homerun"]["opposing_pitcher_name"] == "投手B"
    assert data["game_date"] == "2025-08-05"
    assert data["days_since"] == 5
    assert data["games_since"] == 2
    assert data["at_bats_since"] == 8


def test_get_situational_at_bats(client: TestClient, db_session: Session):
    """測試使用 Enum 查詢不同壘上情境的打席紀錄。"""
    game = models.GameResultDB(
        cpbl_game_id="G_SIT",
        game_date=datetime.date(2025, 8, 8),
        home_team="H",
        away_team="A",
    )
    db_session.add(game)
    db_session.flush()
    summary = models.PlayerGameSummaryDB(game_id=game.id, player_name="情境男")
    db_session.add(summary)
    db_session.flush()
    ab1 = models.AtBatDetailDB(
        player_game_summary_id=summary.id,
        game_id=game.id,
        runners_on_base_before="壘上無人",
        result_short="滾地",
    )
    ab2 = models.AtBatDetailDB(
        player_game_summary_id=summary.id,
        game_id=game.id,
        runners_on_base_before="一壘、二壘、三壘有人",
        result_short="滿貫砲",
    )
    ab3 = models.AtBatDetailDB(
        player_game_summary_id=summary.id,
        game_id=game.id,
        runners_on_base_before="二壘有人",
        result_short="安打",
    )
    db_session.add_all([ab1, ab2, ab3])
    db_session.commit()

    response_sp = client.get(
        "/api/analysis/players/情境男/situational-at-bats?situation=scoring_position&limit=1"
    )
    assert response_sp.status_code == 200
    data_sp = response_sp.json()
    assert len(data_sp) == 1
    assert data_sp[0]["result_short"] == "滿貫砲"  # 倒序，所以先拿到滿貫砲


def test_get_streaks_by_player_names(client: TestClient, setup_streak_test_data):
    """測試使用 player_names 參數查詢特定連續球員的連線。"""
    response = client.get(
        "/api/analysis/streaks?player_names=球員A&player_names=球員B&player_names=球員C"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    streak = data[0]
    assert streak["streak_length"] == 3
    assert streak["at_bats"][0]["player_name"] == "球員A"

    # 查詢一個不存在的連線
    response_none = client.get(
        "/api/analysis/streaks?player_names=球員A&player_names=球員C"
    )
    assert response_none.status_code == 200
    assert response_none.json() == []


def test_get_streaks_with_different_definition(
    client: TestClient, setup_streak_test_data
):
    """測試使用不同的連線定義。"""
    response = client.get(
        "/api/analysis/streaks?definition_name=consecutive_hits&min_length=2"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["streak_length"] == 2
    assert data[0]["at_bats"][0]["player_name"] == "球員E"


def test_get_ibb_impact_analysis_pagination(
    client: TestClient, setup_ibb_impact_test_data
):
    """測試 /api/analysis/players/{player_name}/ibb-impact 端點的分頁功能。"""
    response = client.get("/api/analysis/players/影響者B/ibb-impact?limit=1")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["inning"] == 2  # 倒序，拿到最新的
