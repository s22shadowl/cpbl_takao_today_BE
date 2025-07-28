# tests/test_db_actions.py

import datetime
from unittest.mock import patch
import pytest
from sqlalchemy.orm import Session

from app import db_actions, models

# --- Fixtures ---
# conftest.py 全域提供 db_session


# --- 測試案例 ---


def test_store_game_and_get_id(db_session):
    """測試 store_game_and_get_id 函式"""
    db = db_session

    game_info = {
        "cpbl_game_id": "TEST01",
        "game_date": "2025-06-21",
        "home_team": "測試主隊",
        "away_team": "測試客隊",
        "status": "已完成",
    }

    game_id = db_actions.store_game_and_get_id(db, game_info)
    db.commit()
    assert game_id is not None

    game_in_db = db.query(models.GameResultDB).filter_by(id=game_id).first()
    assert game_in_db is not None
    assert game_in_db.cpbl_game_id == "TEST01"

    game_id_again = db_actions.store_game_and_get_id(db, game_info)
    assert game_id_again == game_id

    count = db.query(models.GameResultDB).count()
    assert count == 1


def test_store_player_season_stats_and_history(db_session):
    """【修改】測試 store_player_season_stats_and_history 函式"""
    db = db_session

    stats_list_1 = [
        {"player_name": "測試員A", "team_name": "測試隊", "avg": 0.300},
        {"player_name": "測試員B", "team_name": "測試隊", "avg": 0.250, "homeruns": 5},
    ]

    # 第一次執行
    db_actions.store_player_season_stats_and_history(db, stats_list_1)
    db.commit()

    # 驗證 PlayerSeasonStatsDB (最新狀態)
    player_a_latest = (
        db.query(models.PlayerSeasonStatsDB).filter_by(player_name="測試員A").first()
    )
    assert player_a_latest is not None
    assert player_a_latest.avg == 0.300
    assert db.query(models.PlayerSeasonStatsDB).count() == 2

    # 驗證 PlayerSeasonStatsHistoryDB (歷史紀錄)
    history_records = db.query(models.PlayerSeasonStatsHistoryDB).all()
    assert len(history_records) == 2
    assert history_records[0].player_name == "測試員A"

    # 第二次執行，更新球員 A 的數據
    stats_list_2 = [
        {"player_name": "測試員A", "team_name": "測試隊", "avg": 0.305, "hits": 10},
    ]
    db_actions.store_player_season_stats_and_history(db, stats_list_2)
    db.commit()

    # 再次驗證 PlayerSeasonStatsDB (最新狀態)
    player_a_updated = (
        db.query(models.PlayerSeasonStatsDB).filter_by(player_name="測試員A").first()
    )
    assert player_a_updated.avg == 0.305
    assert player_a_updated.hits == 10
    # 總數應不變，因為球員 B 的資料未被更新
    assert db.query(models.PlayerSeasonStatsDB).count() == 2

    # 再次驗證 PlayerSeasonStatsHistoryDB (歷史紀錄應增加)
    history_records_updated = (
        db.query(models.PlayerSeasonStatsHistoryDB)
        .order_by(models.PlayerSeasonStatsHistoryDB.id)
        .all()
    )
    assert len(history_records_updated) == 3  # 2 (初次) + 1 (更新) = 3
    assert history_records_updated[2].player_name == "測試員A"
    assert history_records_updated[2].avg == 0.305


def test_store_player_game_data_with_details(db_session):
    """測試 store_player_game_data 函式，包含詳細打席資訊"""
    db = db_session

    game_info = {
        "cpbl_game_id": "TEST02",
        "game_date": "2025-06-21",
        "home_team": "H",
        "away_team": "A",
    }
    game_id = db_actions.store_game_and_get_id(db, game_info)
    db.commit()
    assert game_id is not None

    player_data_list = [
        {
            "summary": {"player_name": "測試員C", "team_name": "測試隊"},
            "at_bats_details": [
                {"sequence_in_game": 1, "result_short": "一安", "inning": 1},
                {"sequence_in_game": 2, "result_short": "三振", "inning": 3},
            ],
        }
    ]

    db_actions.store_player_game_data(db, game_id, player_data_list)
    db.commit()

    summary = (
        db.query(models.PlayerGameSummaryDB).filter_by(player_name="測試員C").first()
    )
    assert summary is not None

    details = (
        db.query(models.AtBatDetailDB)
        .filter_by(player_game_summary_id=summary.id)
        .all()
    )
    assert len(details) == 2
    assert details[0].result_short == "一安"
    assert details[1].inning == 3


def test_update_and_get_game_schedules(db_session):
    """測試 update_game_schedules 和 get_all_schedules 函式"""
    db = db_session

    initial_schedules = [
        {
            "game_id": "176",
            "date": "2025-06-21",
            "game_time": "17:05",
            "matchup": "台鋼雄鷹 vs 樂天桃猿",
        },
        {
            "game_id": "179",
            "date": "2025-06-22",
            "game_time": "17:05",
            "matchup": "台鋼雄鷹 vs 樂天桃猿",
        },
    ]

    db_actions.update_game_schedules(db, initial_schedules)
    db.commit()

    schedules_from_db = db_actions.get_all_schedules(db)
    assert len(schedules_from_db) == 2
    assert schedules_from_db[0].game_id == "176"

    updated_schedules = [
        {
            "game_id": "180",
            "date": "2025-06-22",
            "game_time": "18:35",
            "matchup": "統一獅 vs 味全龍",
        },
    ]

    db_actions.update_game_schedules(db, updated_schedules)
    db.commit()

    schedules_from_db_updated = db_actions.get_all_schedules(db)
    assert len(schedules_from_db_updated) == 1
    assert schedules_from_db_updated[0].game_id == "180"


def test_get_game_with_details(db_session):
    """測試 get_game_with_details 是否能正確地預先載入所有關聯資料"""
    db = db_session

    game = models.GameResultDB(
        cpbl_game_id="TEST_DETAIL",
        game_date=datetime.date(2025, 7, 21),
        home_team="H",
        away_team="A",
    )
    db.add(game)
    db.flush()

    summary = models.PlayerGameSummaryDB(
        game_id=game.id, player_name="測試員D", team_name="測試隊"
    )
    db.add(summary)
    db.flush()

    detail1 = models.AtBatDetailDB(
        player_game_summary_id=summary.id, sequence_in_game=1, result_short="全壘打"
    )
    detail2 = models.AtBatDetailDB(
        player_game_summary_id=summary.id, sequence_in_game=2, result_short="保送"
    )
    db.add_all([detail1, detail2])
    db.commit()

    game_with_details = db_actions.get_game_with_details(db, game.id)

    assert game_with_details is not None
    assert game_with_details.cpbl_game_id == "TEST_DETAIL"
    assert len(game_with_details.player_summaries) == 1
    player_summary = game_with_details.player_summaries[0]
    assert player_summary.player_name == "測試員D"
    assert len(player_summary.at_bat_details) == 2
    assert player_summary.at_bat_details[0].result_short == "全壘打"
    assert player_summary.at_bat_details[1].result_short == "保送"


def test_find_games_with_players(db_session):
    """【新增】測試 find_games_with_players 函式"""
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
    s2c = models.PlayerGameSummaryDB(game_id=g2.id, player_name="球員C", position="LF")
    db_session.add_all([s1a, s1b, s2a, s2c])
    db_session.commit()

    # 查詢 A, B -> 應回傳 G1
    games1 = db_actions.find_games_with_players(db_session, ["球員A", "球員B"])
    assert len(games1) == 1
    assert games1[0].cpbl_game_id == "G1"

    # 查詢 A, B, C -> 應回傳空列表
    games2 = db_actions.find_games_with_players(db_session, ["球員A", "球員B", "球員C"])
    assert len(games2) == 0


def test_get_stats_since_last_homerun(db_session):
    """【新增】測試 get_stats_since_last_homerun 函式"""
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
        player_game_summary_id=s1.id, result_description_full="全壘打"
    )
    hr2 = models.AtBatDetailDB(
        player_game_summary_id=s2.id, result_description_full="關鍵全壘打"
    )
    db_session.add_all([hr1, hr2])
    db_session.commit()

    with patch("app.db_actions.datetime.date") as mock_date:
        mock_date.today.return_value = freezed_today
        stats = db_actions.get_stats_since_last_homerun(db_session, "轟炸基")

    assert stats is not None
    assert stats["game_date"] == datetime.date(2025, 8, 5)
    assert stats["days_since"] == 5
    assert stats["games_since"] == 2
    assert stats["at_bats_since"] == 8


def test_find_at_bats_in_situation(db_session):
    """【新增】測試 find_at_bats_in_situation 函式"""
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
        player_game_summary_id=summary.id, runners_on_base_before="壘上無人"
    )
    ab2 = models.AtBatDetailDB(
        player_game_summary_id=summary.id, runners_on_base_before="一壘、二壘、三壘有人"
    )
    ab3 = models.AtBatDetailDB(
        player_game_summary_id=summary.id, runners_on_base_before="二壘有人"
    )
    db_session.add_all([ab1, ab2, ab3])
    db_session.commit()

    # 測試滿壘
    results_bl = db_actions.find_at_bats_in_situation(
        db_session, "情境男", models.RunnersSituation.BASES_LOADED
    )
    assert len(results_bl) == 1
    assert results_bl[0].runners_on_base_before == "一壘、二壘、三壘有人"

    # 測試得點圈
    results_sp = db_actions.find_at_bats_in_situation(
        db_session, "情境男", models.RunnersSituation.SCORING_POSITION
    )
    assert len(results_sp) == 2


def test_get_summaries_by_position(db_session):
    """【新增】測試 get_summaries_by_position 函式"""
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

    summaries = db_actions.get_summaries_by_position(db_session, "游擊手")
    assert len(summaries) == 1
    assert summaries[0].player_name == "球員SS"


def test_find_next_at_bats_after_ibb(db_session):
    """【新增】測試 find_next_at_bats_after_ibb 的 v2 (同半局) 查詢邏輯"""
    db = db_session
    game = models.GameResultDB(
        cpbl_game_id="G_IBB",
        game_date=datetime.date(2025, 8, 10),
        home_team="H",
        away_team="A",
    )
    db.add(game)
    db.flush()

    s_A = models.PlayerGameSummaryDB(game_id=game.id, player_name="球員A")
    s_B = models.PlayerGameSummaryDB(game_id=game.id, player_name="球員B")
    s_C = models.PlayerGameSummaryDB(game_id=game.id, player_name="球員C")
    db.add_all([s_A, s_B, s_C])
    db.flush()

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

    db.add_all([ab1, ab2_ibb, ab3_next, ab4_new_inning, ab5_last_ibb])
    db.commit()

    results = db_actions.find_next_at_bats_after_ibb(db, "球員B")

    assert len(results) == 2

    # API 回傳結果按時間倒序，所以 results[0] 是最新的 IBB (第 2 局)
    result_latest = results[0]
    assert result_latest["intentional_walk"].inning == 2
    assert result_latest["next_at_bat"] is None

    # results[1] 是較早的 IBB (第 1 局)
    result_earlier = results[1]
    assert result_earlier["intentional_walk"].inning == 1
    assert result_earlier["next_at_bat"] is not None
    assert result_earlier["next_at_bat"].player_summary.player_name == "球員C"
    assert result_earlier["next_at_bat"].result_short == "三振"


# --- 「連線」功能 db_actions 函式測試 ---


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


def test_find_on_base_streaks_generic(db_session: Session, setup_streak_test_data):
    """直接測試 db_actions 的泛用查詢功能。"""
    # 測試 min_length=3，應只找到第一局的 3 人連線
    streaks = db_actions.find_on_base_streaks(
        db=db_session,
        definition_name="consecutive_on_base",
        min_length=3,
        player_names=None,
        lineup_positions=None,
    )
    assert len(streaks) == 1
    assert streaks[0].streak_length == 3
    assert streaks[0].at_bats[0].player_name == "球員A"

    # 測試 min_length=2，應找到第一局的 3 人連線和第二局的 2 人連線
    streaks = db_actions.find_on_base_streaks(
        db=db_session,
        definition_name="consecutive_on_base",
        min_length=2,
        player_names=None,
        lineup_positions=None,
    )
    assert len(streaks) == 2


def test_find_on_base_streaks_by_player_names(
    db_session: Session, setup_streak_test_data
):
    """直接測試 db_actions 的指定球員序列查詢功能。"""
    # 查詢 球員A -> 球員B -> 球員C 的連線
    streaks = db_actions.find_on_base_streaks(
        db=db_session,
        definition_name="consecutive_on_base",
        min_length=3,
        player_names=["球員A", "球員B", "球員C"],
        lineup_positions=None,
    )
    assert len(streaks) == 1
    streak = streaks[0]
    assert streak.streak_length == 3
    assert streak.at_bats[0].player_name == "球員A"
    assert streak.at_bats[1].player_name == "球員B"
    assert streak.at_bats[2].player_name == "球員C"

    # 查詢一個不存在的序列 (球員A -> 球員C)
    streaks = db_actions.find_on_base_streaks(
        db=db_session,
        definition_name="consecutive_on_base",
        min_length=2,
        player_names=["球員A", "球員C"],
        lineup_positions=None,
    )
    assert len(streaks) == 0


def test_find_on_base_streaks_by_lineup_positions(
    db_session: Session, setup_streak_test_data
):
    """直接測試 db_actions 的指定棒次序列查詢功能。"""
    streaks = db_actions.find_on_base_streaks(
        db=db_session,
        definition_name="consecutive_on_base",
        min_length=3,
        player_names=None,
        lineup_positions=[1, 2, 3],
    )
    assert len(streaks) == 1
    streak = streaks[0]
    assert streak.streak_length == 3
    assert streak.at_bats[0].batting_order == "1"
    assert streak.at_bats[1].batting_order == "2"
    assert streak.at_bats[2].batting_order == "3"


def test_find_on_base_streaks_with_different_definition(
    db_session: Session, setup_streak_test_data
):
    """直接測試 db_actions 使用不同連線定義的功能。"""
    # 使用 consecutive_hits (連續安打) 定義，第一局的連線因包含「四壞」而應被排除
    streaks = db_actions.find_on_base_streaks(
        db=db_session,
        definition_name="consecutive_hits",
        min_length=2,
        player_names=None,
        lineup_positions=None,
    )
    assert len(streaks) == 1
    # 只有第二局的全打+一安符合連續安打
    assert streaks[0].streak_length == 2
    assert streaks[0].at_bats[0].player_name == "球員E"
    assert streaks[0].at_bats[1].player_name == "球員F"


def test_find_on_base_streaks_no_result(db_session: Session, setup_streak_test_data):
    """測試各種應返回空列表的情境。"""
    # 查詢一個不可能的長連線
    streaks = db_actions.find_on_base_streaks(
        db=db_session,
        definition_name="consecutive_on_base",
        min_length=10,
        player_names=None,
        lineup_positions=None,
    )
    assert len(streaks) == 0

    # 查詢一個不存在的 definition_name
    streaks = db_actions.find_on_base_streaks(
        db=db_session,
        definition_name="invalid_definition",
        min_length=2,
        player_names=None,
        lineup_positions=None,
    )
    assert len(streaks) == 0


# --- 【新增】「IBB 影響」功能 db_actions 函式測試 ---


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
                inning=1,
                result_short="一安",
                runs_scored_on_play=0,
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["B"].id,
                inning=1,
                result_description_full="故意四壞",
                runs_scored_on_play=0,
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["C"].id,
                inning=1,
                result_short="二安",
                runs_scored_on_play=1,
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["D"].id,
                inning=1,
                result_short="全打",
                runs_scored_on_play=2,
            ),
            # 第 2 局: IBB 後續得 0 分
            models.AtBatDetailDB(
                player_game_summary_id=summaries["A"].id, inning=2, result_short="滾地"
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["B"].id,
                inning=2,
                result_description_full="故意四壞",
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["C"].id, inning=2, result_short="三振"
            ),
        ]
    )
    db_session.commit()
    return game


def test_analyze_ibb_impact(db_session: Session, setup_ibb_impact_test_data):
    """直接測試 db_actions 的 analyze_ibb_impact 函式。"""
    results = db_actions.analyze_ibb_impact(db=db_session, player_name="影響者B")

    assert len(results) == 2

    # API 回傳結果是倒序的，所以 results[0] 是最新的事件 (第 2 局)
    result_inning2 = results[0]
    assert result_inning2.inning == 2
    assert result_inning2.intentional_walk.player_name == "影響者B"
    assert len(result_inning2.subsequent_at_bats) == 1
    assert result_inning2.subsequent_at_bats[0].player_name == "影響者C"
    assert result_inning2.runs_scored_after_ibb == 0

    # results[1] 是較早的事件 (第 1 局)
    result_inning1 = results[1]
    assert result_inning1.inning == 1
    assert result_inning1.intentional_walk.player_name == "影響者B"
    assert len(result_inning1.subsequent_at_bats) == 2
    assert result_inning1.subsequent_at_bats[0].player_name == "影響者C"
    assert result_inning1.subsequent_at_bats[1].player_name == "影響者D"
    assert result_inning1.runs_scored_after_ibb == 3  # 1 (二安) + 2 (全打)
