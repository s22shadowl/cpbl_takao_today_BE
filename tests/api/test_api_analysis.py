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


@pytest.fixture(scope="function")
def setup_situational_at_bats_data(db_session: Session):
    """[新增] 建立用於測試情境打席的資料"""
    game = models.GameResultDB(
        cpbl_game_id="SITUATION_TEST_GAME",
        game_date=datetime.date(2025, 8, 17),
        home_team="富邦悍將",
        away_team="統一7-ELEVEn獅",
    )
    db_session.add(game)
    db_session.flush()

    summary = models.PlayerGameSummaryDB(
        game_id=game.id, player_name="情境打者", team_name="富邦悍將"
    )
    db_session.add(summary)
    db_session.flush()

    db_session.add_all(
        [
            models.AtBatDetailDB(
                player_game_summary_id=summary.id,
                game_id=game.id,
                inning=1,
                runners_on_base_before="一壘、三壘有人",
                result_short="一安",  # 符合
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summary.id,
                game_id=game.id,
                inning=3,
                runners_on_base_before="壘上無人",
                result_short="三振",  # 不符合
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summary.id,
                game_id=game.id,
                inning=5,
                runners_on_base_before="一壘、三壘有人",
                result_short="高犧",  # 符合
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summary.id,
                game_id=game.id,
                inning=7,
                runners_on_base_before="二壘有人",
                result_short="滾地",  # 符合 (得點圈)
            ),
        ]
    )
    db_session.commit()


@pytest.fixture(scope="function")
def setup_position_analysis_data(db_session: Session):
    """[新增] 建立用於測試年度守備位置分析的資料"""
    game1 = models.GameResultDB(
        cpbl_game_id="POS_TEST_2024_1",
        game_date=datetime.date(2024, 4, 1),
        home_team="中信兄弟",
        away_team="味全龍",
    )
    game2 = models.GameResultDB(
        cpbl_game_id="POS_TEST_2024_2",
        game_date=datetime.date(2024, 5, 10),
        home_team="中信兄弟",
        away_team="樂天桃猿",
    )
    game_other_year = models.GameResultDB(
        cpbl_game_id="POS_TEST_2025_1",
        game_date=datetime.date(2025, 4, 1),
        home_team="中信兄弟",
        away_team="味全龍",
    )
    db_session.add_all([game1, game2, game_other_year])
    db_session.flush()

    db_session.add_all(
        [
            # 2024 年 SS 的相關紀錄
            models.PlayerGameSummaryDB(
                game_id=game1.id,
                player_name="游擊大師",
                team_name="中信兄弟",
                position="SS",
                at_bats=4,
                hits=2,
            ),
            models.PlayerGameSummaryDB(
                game_id=game1.id,
                player_name="工具人",
                team_name="中信兄弟",
                position="2B,SS",
                at_bats=3,
                hits=1,
            ),
            models.PlayerGameSummaryDB(
                game_id=game2.id,
                player_name="游擊大師",
                team_name="中信兄弟",
                position="SS",
                at_bats=5,
                hits=1,
            ),
            # 應被忽略的紀錄 (不同年份)
            models.PlayerGameSummaryDB(
                game_id=game_other_year.id,
                player_name="游擊大師",
                team_name="中信兄弟",
                position="SS",
                at_bats=3,
                hits=3,
            ),
            # 應被忽略的紀錄 (不同位置)
            models.PlayerGameSummaryDB(
                game_id=game1.id,
                player_name="角落砲",
                team_name="中信兄弟",
                position="LF",
                at_bats=4,
                hits=1,
            ),
        ]
    )

    # [修正] 新增球員年度數據，以供 API 查詢
    db_session.add_all(
        [
            models.PlayerSeasonStatsDB(
                player_name="游擊大師", at_bats=9, hits=3, avg=(3 / 9)
            ),
            models.PlayerSeasonStatsDB(
                player_name="工具人", at_bats=3, hits=1, avg=(1 / 3)
            ),
        ]
    )
    db_session.commit()


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


def test_get_situational_at_bats(client: TestClient, setup_situational_at_bats_data):
    """[新增] 測試 /situational-at-bats 端點能根據壘上情境正確篩選並回傳擴充資訊。"""
    # [修正] 使用有效的 Enum 值 "scoring_position"
    response = client.get(
        "/api/analysis/players/情境打者/situational-at-bats?situation=scoring_position"
    )
    assert response.status_code == 200
    data = response.json()

    # [修正] 驗證所有符合 "scoring_position" 的打席都被回傳 (B1,B3 and B2)
    assert len(data) == 3
    results_short = {d["result_short"] for d in data}
    assert results_short == {"一安", "高犧", "滾地"}

    # 驗證回應已正確擴充比賽資訊
    assert data[0]["game_date"] == "2025-08-17"
    assert data[0]["opponent_team"] == "統一7-ELEVEn獅"


def test_get_position_records(client: TestClient, setup_position_analysis_data):
    """[新增] 測試 /positions/{year}/{position} 端點能回傳正確的年度守位分析。"""
    response = client.get("/api/analysis/positions/2024/SS")
    assert response.status_code == 200
    data = response.json()

    # 驗證基本結構
    assert "calendar_data" in data
    assert "player_stats" in data

    # 驗證 calendarData
    assert len(data["calendar_data"]) == 2  # 2024 年有兩天比賽有 SS
    dates = {c["date"] for c in data["calendar_data"]}
    assert dates == {"2024-04-01", "2024-05-10"}

    # 驗證 playerStats (球員賽季數據彙總)
    assert len(data["player_stats"]) == 2  # 游擊大師、工具人
    player_stats_map = {p["player_name"]: p for p in data["player_stats"]}
    assert "游擊大師" in player_stats_map
    assert "工具人" in player_stats_map

    # [修正] 從 "batting_stats" 子物件中取得數據
    stats_master = player_stats_map["游擊大師"]["batting_stats"]
    assert stats_master["at_bats"] == 9
    assert stats_master["hits"] == 3
    assert stats_master["avg"] == pytest.approx(3 / 9)

    # [修正] 從 "batting_stats" 子物件中取得數據
    stats_utility = player_stats_map["工具人"]["batting_stats"]
    assert stats_utility["at_bats"] == 3
    assert stats_utility["hits"] == 1
