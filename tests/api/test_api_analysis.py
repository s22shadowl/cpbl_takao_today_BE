# tests/api/test_api_analysis.py

import pytest
import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app import models
from app.cache import redis_client

# --- 測試資料設定 Fixture ---


@pytest.fixture(scope="function", autouse=True)
def auto_clear_cache():
    """自動使用的 fixture，在每個測試函式執行後自動清除所有快取。"""
    yield
    if redis_client:
        redis_client.flushdb()


@pytest.fixture(scope="function")
def setup_streak_test_data(db_session: Session):
    """建立一個用於測試「連線」功能的比賽場景。"""
    game = models.GameResultDB(
        cpbl_game_id="STREAK_TEST_GAME",
        game_date=datetime.date(2025, 8, 15),
        home_team="台鋼雄鷹",
        away_team="樂天桃猿",
    )
    db_session.add(game)
    db_session.flush()

    summaries = {}
    players = [("A", "1"), ("B", "2"), ("C", "3"), ("D", "4"), ("E", "5"), ("F", "6")]
    for name, order in players:
        summary = models.PlayerGameSummaryDB(
            game_id=game.id,
            player_name=f"球員{name}",
            batting_order=int(order),
            team_name="台鋼雄鷹",
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
        home_team="味全龍",
        away_team="中信兄弟",
    )
    db_session.add(game)
    db_session.flush()

    summaries = {}
    players = [("A", "1"), ("B", "2"), ("C", "3"), ("D", "4")]
    for name, order in players:
        summary = models.PlayerGameSummaryDB(
            game_id=game.id,
            player_name=f"影響者{name}",
            batting_order=int(order),
            team_name="味全龍",
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


def test_get_games_with_players_includes_summaries(
    client: TestClient, db_session: Session
):
    """[修改] 測試 /games-with-players 是否能正確回傳 player_summaries。"""
    g1 = models.GameResultDB(
        cpbl_game_id="G1",
        game_date=datetime.date(2025, 8, 1),
        home_team="H",
        away_team="A",
    )
    db_session.add(g1)
    db_session.flush()
    s1a = models.PlayerGameSummaryDB(game_id=g1.id, player_name="球員A", position="RF")
    s1b = models.PlayerGameSummaryDB(game_id=g1.id, player_name="球員B", position="PH")
    db_session.add_all([s1a, s1b])
    db_session.commit()

    response = client.get(
        "/api/analysis/games-with-players?players=球員A&players=球員B"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["cpbl_game_id"] == "G1"
    assert "player_summaries" in data[0]
    assert len(data[0]["player_summaries"]) == 2
    assert data[0]["player_summaries"][0]["player_name"] == "球員A"


def test_get_last_homerun_includes_career_stats(
    client: TestClient, db_session: Session
):
    """[修改] 測試 /last-homerun 是否能正確回傳 career_stats。"""
    g1 = models.GameResultDB(
        cpbl_game_id="G_HR1",
        game_date=datetime.date(2025, 8, 1),
        home_team="H",
        away_team="A",
    )
    db_session.add(g1)
    db_session.flush()
    s1 = models.PlayerGameSummaryDB(game_id=g1.id, player_name="轟炸基", at_bats=4)
    db_session.add(s1)
    db_session.flush()
    hr1 = models.AtBatDetailDB(
        player_game_summary_id=s1.id, game_id=g1.id, result_description_full="全壘打"
    )
    db_session.add(hr1)
    # [新增] 加入生涯數據
    career = models.PlayerCareerStatsDB(player_name="轟炸基", homeruns=100, avg=0.300)
    db_session.add(career)
    db_session.commit()

    response = client.get("/api/analysis/players/轟炸基/last-homerun")

    assert response.status_code == 200
    data = response.json()
    assert data["last_homerun"]["id"] == hr1.id
    assert "career_stats" in data
    assert data["career_stats"]["player_name"] == "轟炸基"
    assert data["career_stats"]["homeruns"] == 100
    assert data["career_stats"]["avg"] == 0.3


def test_get_streaks_includes_opponent_team(client: TestClient, setup_streak_test_data):
    """[修改] 測試 /streaks 的回應是否包含 opponent_team。"""
    response = client.get("/api/analysis/streaks?min_length=3")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    streak = data[0]
    assert streak["opponent_team"] == "樂天桃猿"


def test_get_streaks_by_player_names_order_agnostic(
    client: TestClient, setup_streak_test_data
):
    """[新增] 測試使用 player_names 參數查詢時，順序不影響結果。"""
    # 順序 C -> B -> A
    response = client.get(
        "/api/analysis/streaks?player_names=球員C&player_names=球員B&player_names=球員A"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    streak = data[0]
    assert streak["streak_length"] == 3
    # 回傳的打席順序仍然是 A -> B -> C
    assert streak["at_bats"][0]["player_name"] == "球員A"
    assert streak["at_bats"][1]["player_name"] == "球員B"
    assert streak["at_bats"][2]["player_name"] == "球員C"


def test_get_ibb_impact_analysis_includes_opponent_team(
    client: TestClient, setup_ibb_impact_test_data
):
    """[修改] 測試 /ibb-impact 的回應是否包含 opponent_team。"""
    response = client.get("/api/analysis/players/影響者B/ibb-impact")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert data[0]["opponent_team"] == "中信兄弟"
