# tests/api/test_api_analysis.py

import pytest
import datetime
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app import models
from app.config import settings  # 匯入 settings 以取得 API_KEY

# --- 測試資料設定 Fixture ---


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

    # 建立球員摘要
    summaries = {}
    players = [("A", "1"), ("B", "2"), ("C", "3"), ("D", "4"), ("E", "5"), ("F", "6")]
    for name, order in players:
        summary = models.PlayerGameSummaryDB(
            game_id=game.id,
            player_name=f"球員{name}",
            batting_order=order,
            team_name="測試隊",
        )
        db_session.add(summary)
        summaries[name] = summary
    db_session.flush()

    # 建立打席紀錄
    # 半局一：球員A, B, C 連續上壘 (一安, 四壞, 二安)
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
            # 中斷點
            models.AtBatDetailDB(
                player_game_summary_id=summaries["D"].id,
                game_id=game.id,
                inning=1,
                sequence_in_game=4,
                result_short="三振",
            ),
            # 半局二：球員E, F 連續安打
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
            batting_order=order,
            team_name="測試隊",
        )
        db_session.add(summary)
        summaries[name] = summary
    db_session.flush()

    # 建立打席紀錄
    db_session.add_all(
        [
            # 第 1 局: IBB 後續得 3 分
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
            # 第 2 局: IBB 後續得 0 分
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


def test_get_games_with_players_includes_non_starters(
    client: TestClient, db_session: Session
):
    """【擴充】測試查詢指定球員群組（包含非先發）是否同時出賽"""
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
    # G1 有 A (先發), B (代打)
    s1a = models.PlayerGameSummaryDB(game_id=g1.id, player_name="球員A", position="RF")
    s1b = models.PlayerGameSummaryDB(game_id=g1.id, player_name="球員B", position="PH")
    # G2 只有 A (先發)
    s2a = models.PlayerGameSummaryDB(game_id=g2.id, player_name="球員A", position="RF")
    db_session.add_all([s1a, s1b, s2a])
    db_session.commit()

    # 查詢 A, B -> 應回傳 G1
    response = client.get(
        "/api/analysis/games-with-players?players=球員A&players=球員B"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["cpbl_game_id"] == "G1"


def test_get_last_homerun_with_stats(client: TestClient, db_session: Session):
    """【修改】測試查詢球員的最後一轟，並驗證回傳的統計數據"""
    # 凍結時間以進行可預測的計算
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
    )  # 最後一轟的比賽
    g3 = models.GameResultDB(
        cpbl_game_id="G_HR3",
        game_date=datetime.date(2025, 8, 8),
        home_team="H",
        away_team="A",
    )  # 全壘打後的比賽
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

    with patch("app.crud.analysis.datetime.date") as mock_date:
        mock_date.today.return_value = freezed_today
        response = client.get("/api/analysis/players/轟炸基/last-homerun")

    assert response.status_code == 200
    data = response.json()

    assert data["last_homerun"]["opposing_pitcher_name"] == "投手B"
    assert data["game_date"] == "2025-08-05"
    assert data["days_since"] == 5  # 8/10 - 8/5
    assert data["games_since"] == 2  # 8/5 和 8/8 的比賽
    assert data["at_bats_since"] == 8  # 5 + 3


def test_get_situational_at_bats(client: TestClient, db_session: Session):
    """【修改】測試使用 Enum 查詢不同壘上情境的打席紀錄"""
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

    # 測試滿壘
    response_bl = client.get(
        "/api/analysis/players/情境男/situational-at-bats?situation=bases_loaded"
    )
    assert response_bl.status_code == 200
    data_bl = response_bl.json()
    assert len(data_bl) == 1
    assert data_bl[0]["result_short"] == "滿貫砲"

    # 測試得點圈有人
    response_sp = client.get(
        "/api/analysis/players/情境男/situational-at-bats?situation=scoring_position"
    )
    assert response_sp.status_code == 200
    data_sp = response_sp.json()
    assert len(data_sp) == 2  # 滿壘 + 二壘有人

    # 測試壘上無人
    response_be = client.get(
        "/api/analysis/players/情境男/situational-at-bats?situation=bases_empty"
    )
    assert response_be.status_code == 200
    data_be = response_be.json()
    assert len(data_be) == 1
    assert data_be[0]["result_short"] == "滾地"


def test_get_position_records(client: TestClient, db_session: Session):
    """測試查詢指定守備位置的紀錄"""
    game = models.GameResultDB(
        cpbl_game_id="G_POS",
        game_date=datetime.date(2025, 8, 9),
        home_team="H",
        away_team="A",
    )
    db_session.add(game)
    db_session.flush()
    s1 = models.PlayerGameSummaryDB(
        game_id=game.id, player_name="球員SS", position="游擊手"
    )
    s2 = models.PlayerGameSummaryDB(
        game_id=game.id, player_name="球員CF", position="中外野手"
    )
    db_session.add_all([s1, s2])
    db_session.commit()

    response = client.get("/api/analysis/positions/游擊手")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["player_name"] == "球員SS"


def test_get_next_at_bats_after_ibb(client: TestClient, db_session: Session):
    """【修改】測試查詢故意四壞後下一打席結果的 API 端點，並修正斷言邏輯"""
    game = models.GameResultDB(
        cpbl_game_id="G_IBB",
        game_date=datetime.date(2025, 8, 10),
        home_team="H",
        away_team="A",
    )
    db_session.add(game)
    db_session.flush()

    s_A = models.PlayerGameSummaryDB(game_id=game.id, player_name="球員A")
    s_B = models.PlayerGameSummaryDB(
        game_id=game.id, player_name="球員B"
    )  # 被 IBB 的目標
    s_C = models.PlayerGameSummaryDB(game_id=game.id, player_name="球員C")  # 下一棒
    db_session.add_all([s_A, s_B, s_C])
    db_session.flush()

    ab1 = models.AtBatDetailDB(
        player_game_summary_id=s_A.id, game_id=game.id, inning=1, result_short="一安"
    )
    ab2_ibb = models.AtBatDetailDB(
        player_game_summary_id=s_B.id,
        game_id=game.id,
        inning=1,
        result_description_full="故意四壞",
    )
    ab3_next = models.AtBatDetailDB(
        player_game_summary_id=s_C.id, game_id=game.id, inning=1, result_short="三振"
    )
    ab4_new_inning = models.AtBatDetailDB(
        player_game_summary_id=s_A.id, game_id=game.id, inning=2, result_short="二安"
    )
    ab5_last_ibb = models.AtBatDetailDB(
        player_game_summary_id=s_B.id,
        game_id=game.id,
        inning=2,
        result_description_full="故意四壞",
    )

    db_session.add_all([ab1, ab2_ibb, ab3_next, ab4_new_inning, ab5_last_ibb])
    db_session.commit()

    response = client.get("/api/analysis/players/球員B/after-ibb")
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 2

    # API 回傳結果按時間倒序，所以 data[0] 是最新的 IBB (第 2 局)
    result_latest = data[0]
    assert result_latest["intentional_walk"]["inning"] == 2
    # 驗證該局最後一打席的 IBB，其 next_at_bat 應為 None
    assert result_latest["next_at_bat"] is None

    # data[1] 是較早的 IBB (第 1 局)
    result_earlier = data[1]
    assert result_earlier["intentional_walk"]["inning"] == 1
    # 驗證其 next_at_bat 存在且結果正確
    assert result_earlier["next_at_bat"] is not None
    assert result_earlier["next_at_bat"]["result_short"] == "三振"


# --- 「連線」分析端點測試 ---


def test_get_streaks_generic_search(client: TestClient, setup_streak_test_data):
    """測試泛用查詢，不指定球員或棒次。"""
    # 測試 min_length=3，應只找到第一局的 3 人連線
    response = client.get("/api/analysis/streaks?min_length=3")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["streak_length"] == 3
    assert data[0]["at_bats"][0]["player_name"] == "球員A"

    # 測試 min_length=2，應找到第一局的 3 人連線和第二局的 2 人連線
    response = client.get("/api/analysis/streaks?min_length=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_get_streaks_by_player_names(client: TestClient, setup_streak_test_data):
    """測試使用 player_names 參數查詢特定連續球員的連線。"""
    # 查詢 球員A -> 球員B -> 球員C 的連線
    response = client.get(
        "/api/analysis/streaks?player_names=球員A&player_names=球員B&player_names=球員C"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    streak = data[0]
    assert streak["streak_length"] == 3
    assert streak["at_bats"][0]["player_name"] == "球員A"
    assert streak["at_bats"][1]["player_name"] == "球員B"
    assert streak["at_bats"][2]["player_name"] == "球員C"

    # --- FIX START ---
    # 清除快取以確保下一個斷言的獨立性
    # 必須提供 X-API-Key header 來通過端點的相依性檢查
    headers = {"X-API-Key": settings.API_KEY}
    clear_response = client.post("/api/system/clear-cache", headers=headers)
    # 端點成功時回傳包含 message 的 JSON，狀態碼為 200
    assert clear_response.status_code == 200
    # --- FIX END ---

    # 查詢一個不存在的連線
    response = client.get("/api/analysis/streaks?player_names=球員A&player_names=球員C")
    assert response.status_code == 200
    assert response.json() == []


def test_get_streaks_by_lineup_positions(client: TestClient, setup_streak_test_data):
    """測試使用 lineup_positions 參數查詢特定連續棒次的連線。"""
    # 查詢 1 -> 2 -> 3 棒的連線
    response = client.get(
        "/api/analysis/streaks?lineup_positions=1&lineup_positions=2&lineup_positions=3"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    streak = data[0]
    assert streak["streak_length"] == 3
    assert streak["at_bats"][0]["batting_order"] == "1"
    assert streak["at_bats"][1]["batting_order"] == "2"
    assert streak["at_bats"][2]["batting_order"] == "3"


def test_get_streaks_with_different_definition(
    client: TestClient, setup_streak_test_data
):
    """測試使用不同的連線定義。"""
    # 使用 consecutive_hits (連續安打) 定義，第一局的連線因包含「四壞」而應被排除
    response = client.get(
        "/api/analysis/streaks?definition_name=consecutive_hits&min_length=2"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    # 只有第二局的全打+一安符合連續安打
    assert data[0]["streak_length"] == 2
    assert data[0]["at_bats"][0]["player_name"] == "球員E"


def test_get_streaks_edge_cases(client: TestClient):
    """測試 API 的邊界條件與錯誤處理。"""
    # 同時提供 player_names 和 lineup_positions，應返回 400 錯誤
    response = client.get("/api/analysis/streaks?player_names=A&lineup_positions=1")
    assert response.status_code == 400

    # 提供無效的 definition_name，應返回空列表
    response = client.get("/api/analysis/streaks?definition_name=invalid_def")
    assert response.status_code == 200
    assert response.json() == []


# --- 【新增】「IBB 影響」分析端點測試 ---


def test_get_ibb_impact_analysis(client: TestClient, setup_ibb_impact_test_data):
    """測試 /api/analysis/players/{player_name}/ibb-impact 端點。"""
    response = client.get("/api/analysis/players/影響者B/ibb-impact")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # API 回傳結果是倒序的，所以 data[0] 是最新的事件 (第 2 局)
    result_inning2 = data[0]
    assert result_inning2["inning"] == 2
    assert result_inning2["intentional_walk"]["player_name"] == "影響者B"
    assert len(result_inning2["subsequent_at_bats"]) == 1
    assert result_inning2["subsequent_at_bats"][0]["player_name"] == "影響者C"
    assert result_inning2["runs_scored_after_ibb"] == 0

    # data[1] 是較早的事件 (第 1 局)
    result_inning1 = data[1]
    assert result_inning1["inning"] == 1
    assert result_inning1["intentional_walk"]["player_name"] == "影響者B"
    assert len(result_inning1["subsequent_at_bats"]) == 2
    assert result_inning1["subsequent_at_bats"][0]["player_name"] == "影響者C"
    assert result_inning1["subsequent_at_bats"][1]["player_name"] == "影響者D"
    assert result_inning1["runs_scored_after_ibb"] == 3
