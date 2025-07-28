import pytest
import datetime
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app, get_api_key
from app import db_actions, models

# --- 輔助函式 (Overrides) ---


def override_get_api_key_success():
    """一個假的 get_api_key 函式，直接回傳成功。"""
    return "test-api-key"


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
                inning=1,
                sequence_in_game=1,
                result_short="一安",
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["B"].id,
                inning=1,
                sequence_in_game=2,
                result_short="四壞",
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["C"].id,
                inning=1,
                sequence_in_game=3,
                result_short="二安",
            ),
            # 中斷點
            models.AtBatDetailDB(
                player_game_summary_id=summaries["D"].id,
                inning=1,
                sequence_in_game=4,
                result_short="三振",
            ),
            # 半局二：球員E, F 連續安打
            models.AtBatDetailDB(
                player_game_summary_id=summaries["E"].id,
                inning=2,
                sequence_in_game=5,
                result_short="全打",
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["F"].id,
                inning=2,
                sequence_in_game=6,
                result_short="一安",
            ),
        ]
    )
    db_session.commit()
    return game


# --- 測試案例 ---


def test_get_games_by_date_success(client: TestClient, db_session: Session):
    """測試 /api/games/{game_date} 端點在成功獲取數據時的情況"""
    game_info_1 = {
        "cpbl_game_id": "TEST_MAIN_01",
        "game_date": "2025-06-21",
        "home_team": "測試主隊",
        "away_team": "測試客隊",
        "status": "已完成",
    }
    db_actions.store_game_and_get_id(db_session, game_info_1)
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
        player_game_summary_id=s1.id, result_description_full="全壘打"
    )
    hr2 = models.AtBatDetailDB(
        player_game_summary_id=s2.id,
        result_description_full="關鍵全壘打",
        opposing_pitcher_name="投手B",
    )
    db_session.add_all([hr1, hr2])
    db_session.commit()

    with patch("app.db_actions.datetime.date") as mock_date:
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
        runners_on_base_before="壘上無人",
        result_short="滾地",
    )
    ab2 = models.AtBatDetailDB(
        player_game_summary_id=summary.id,
        runners_on_base_before="一壘、二壘、三壘有人",
        result_short="滿貫砲",
    )
    ab3 = models.AtBatDetailDB(
        player_game_summary_id=summary.id,
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
        player_game_summary_id=s_A.id, inning=1, result_short="一安"
    )
    ab2_ibb = models.AtBatDetailDB(
        player_game_summary_id=s_B.id, inning=1, result_description_full="故意四壞"
    )
    ab3_next = models.AtBatDetailDB(
        player_game_summary_id=s_C.id, inning=1, result_short="三振"
    )
    ab4_new_inning = models.AtBatDetailDB(
        player_game_summary_id=s_A.id, inning=2, result_short="二安"
    )
    ab5_last_ibb = models.AtBatDetailDB(
        player_game_summary_id=s_B.id, inning=2, result_description_full="故意四壞"
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


# --- 手動觸發任務的端點 ---


@pytest.mark.parametrize(
    "mode, date_param, expected_task_str",
    [
        ("daily", "2025-06-21", "app.main.task_scrape_single_day"),
        ("monthly", "2025-06", "app.main.task_scrape_entire_month"),
        ("yearly", "2025", "app.main.task_scrape_entire_year"),
    ],
)
def test_run_scraper_manually(
    client: TestClient, mocker, mode, date_param, expected_task_str
):
    mock_task = mocker.patch(expected_task_str)
    app.dependency_overrides[get_api_key] = override_get_api_key_success
    headers = {"X-API-Key": "any-key-will-do"}
    request_payload = {"mode": mode, "date": date_param}
    response = client.post("/api/run_scraper", headers=headers, json=request_payload)
    del app.dependency_overrides[get_api_key]
    assert response.status_code == 202
    mock_task.send.assert_called_once_with(date_param)


def test_run_scraper_manually_invalid_mode(client: TestClient):
    app.dependency_overrides[get_api_key] = override_get_api_key_success
    headers = {"X-API-Key": "any-key-will-do"}
    request_payload = {"mode": "invalid_mode", "date": None}
    response = client.post("/api/run_scraper", headers=headers, json=request_payload)
    del app.dependency_overrides[get_api_key]
    assert response.status_code == 400


def test_update_schedule_manually(client: TestClient, mocker):
    mock_task = mocker.patch("app.main.task_update_schedule_and_reschedule")
    app.dependency_overrides[get_api_key] = override_get_api_key_success
    headers = {"X-API-Key": "any-key-will-do"}
    response = client.post("/api/update_schedule", headers=headers)
    del app.dependency_overrides[get_api_key]
    assert response.status_code == 202
    mock_task.send.assert_called_once()


# --- API 金鑰保護 ---


def test_post_endpoints_no_api_key(client: TestClient):
    response_run = client.post(
        "/api/run_scraper", json={"mode": "daily", "date": "2025-01-01"}
    )
    assert response_run.status_code == 403
    response_update = client.post("/api/update_schedule")
    assert response_update.status_code == 403


def test_post_endpoints_wrong_api_key(client: TestClient):
    headers = {"X-API-Key": "wrong-key"}
    response_run = client.post(
        "/api/run_scraper",
        headers=headers,
        json={"mode": "daily", "date": "2025-01-01"},
    )
    assert response_run.status_code == 403
    response_update = client.post("/api/update_schedule", headers=headers)
    assert response_update.status_code == 403
