# tests/crud/test_crud_analysis.py

import datetime
from unittest.mock import patch
import pytest
from sqlalchemy.orm import Session

from app import models
from app.crud import analysis


# --- 測試資料設定 Fixture ---


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
            batting_order=order,
            team_name="台鋼雄鷹",
        )
        db_session.add(summary)
        summaries[name] = summary
    db_session.flush()

    # [修正] 補上球員 E 和 F 的打席紀錄
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
            batting_order=order,
            team_name="味全龍",
        )
        db_session.add(summary)
        summaries[name] = summary
    db_session.flush()

    # [修正] 補上第 2 局的 IBB 事件，使其與 API 測試資料一致
    db_session.add_all(
        [
            models.AtBatDetailDB(
                player_game_summary_id=summaries["A"].id,
                game_id=game.id,
                inning=1,
                result_short="一安",
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["B"].id,
                game_id=game.id,
                inning=1,
                result_description_full="故意四壞",
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["C"].id,
                game_id=game.id,
                inning=1,
                result_short="二安",
            ),
            models.AtBatDetailDB(
                player_game_summary_id=summaries["D"].id,
                game_id=game.id,
                inning=1,
                result_short="全打",
                runs_scored_on_play=3,
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


# --- CRUD 函式單元測試 ---


def test_find_games_with_players(db_session: Session):
    """測試 find_games_with_players 函式。"""
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

    games1 = analysis.find_games_with_players(db_session, ["球員A", "球員B"])
    assert len(games1) == 1
    assert games1[0].cpbl_game_id == "G1"

    games2 = analysis.find_games_with_players(db_session, ["球員A", "球員B", "球員C"])
    assert len(games2) == 0


def test_get_stats_since_last_homerun(db_session: Session):
    """測試 get_stats_since_last_homerun 函式。"""
    freezed_today = datetime.date(2025, 8, 10)
    g1 = models.GameResultDB(
        cpbl_game_id="G_HR1",
        game_date=datetime.date(2025, 8, 1),
        home_team="H",
        away_team="A",
    )
    # 這個是最後一轟
    g2_hr = models.GameResultDB(
        cpbl_game_id="G_HR2",
        game_date=datetime.date(2025, 8, 5),
        home_team="H",
        away_team="A",
    )
    # 全壘打之後的比賽
    g3_after = models.GameResultDB(
        cpbl_game_id="G_HR3",
        game_date=datetime.date(2025, 8, 8),
        home_team="H",
        away_team="A",
    )
    db_session.add_all([g1, g2_hr, g3_after])
    db_session.flush()
    s1 = models.PlayerGameSummaryDB(game_id=g1.id, player_name="轟炸基", at_bats=4)
    s2_hr = models.PlayerGameSummaryDB(
        game_id=g2_hr.id, player_name="轟炸基", at_bats=5
    )
    s3_after = models.PlayerGameSummaryDB(
        game_id=g3_after.id, player_name="轟炸基", at_bats=3
    )
    db_session.add_all([s1, s2_hr, s3_after])
    db_session.flush()
    hr1 = models.AtBatDetailDB(
        player_game_summary_id=s1.id, game_id=g1.id, result_description_full="全壘打"
    )
    hr2 = models.AtBatDetailDB(
        player_game_summary_id=s2_hr.id,
        game_id=g2_hr.id,
        result_description_full="關鍵全壘打",
    )
    db_session.add_all([hr1, hr2])
    db_session.commit()

    with patch("app.crud.analysis.datetime.date") as mock_date:
        mock_date.today.return_value = freezed_today
        stats = analysis.get_stats_since_last_homerun(db_session, "轟炸基")

    assert stats is not None
    # 驗證找到的是 8/5 的全壘打
    assert stats["game_date"] == datetime.date(2025, 8, 5)
    assert stats["days_since"] == 5
    # 驗證只計算 8/8 的比賽
    assert stats["games_since"] == 1
    assert stats["at_bats_since"] == 3


def test_get_last_homerun_multiple_in_same_game(db_session: Session):
    """【新增】測試當天多發全壘打時，是否能正確找到最後一發。"""
    player_name = "單場雙響砲"
    game_date = datetime.date(2025, 8, 20)

    # 準備資料
    game = models.GameResultDB(
        cpbl_game_id="MULTI_HR_GAME",
        game_date=game_date,
        home_team="H",
        away_team="A",
    )
    db_session.add(game)
    db_session.flush()

    summary = models.PlayerGameSummaryDB(game_id=game.id, player_name=player_name)
    db_session.add(summary)
    db_session.flush()

    # 同場比賽的三個打席
    ab1_hr = models.AtBatDetailDB(
        player_game_summary_id=summary.id,
        game_id=game.id,
        sequence_in_game=1,
        result_description_full="陽春全壘打",
    )
    ab2_out = models.AtBatDetailDB(
        player_game_summary_id=summary.id,
        game_id=game.id,
        sequence_in_game=2,
        result_description_full="飛球出局",
    )
    ab3_hr_last = models.AtBatDetailDB(
        player_game_summary_id=summary.id,
        game_id=game.id,
        sequence_in_game=3,
        result_description_full="再見全壘打",
    )
    db_session.add_all([ab1_hr, ab2_out, ab3_hr_last])
    db_session.commit()

    # 執行查詢
    stats = analysis.get_stats_since_last_homerun(db_session, player_name)

    # 驗證結果
    assert stats is not None
    # 驗證 last_homerun 物件本身是正確的
    assert stats["last_homerun"].result_description_full == "再見全壘打"
    assert stats["last_homerun"].sequence_in_game == 3
    # 驗證回傳的 game_date 也是正確的
    assert stats["game_date"] == game_date


def test_get_last_homerun_no_data(db_session: Session):
    """
    重現 bug 的測試案例：
    1. 建立有全壘打的球員 A 和沒有全壘打的球員 B。
    2. 查詢球員 B 時，應回傳 None，而不是球員 A 的全壘打。
    """
    # 準備資料
    game = models.GameResultDB(
        cpbl_game_id="BUG_REPRO",
        game_date=datetime.date(2025, 8, 1),
        home_team="H",
        away_team="A",
    )
    db_session.add(game)
    db_session.flush()

    # 球員 A (Homerun King)
    summary_a = models.PlayerGameSummaryDB(game_id=game.id, player_name="Homerun King")
    db_session.add(summary_a)
    db_session.flush()
    db_session.add(
        models.AtBatDetailDB(
            player_game_summary_id=summary_a.id,
            game_id=game.id,
            result_description_full="石破天驚的滿貫全壘打",
        )
    )

    # 球員 B (No Homerun Guy)
    summary_b = models.PlayerGameSummaryDB(
        game_id=game.id, player_name="No Homerun Guy"
    )
    db_session.add(summary_b)
    db_session.flush()
    db_session.add(
        models.AtBatDetailDB(
            player_game_summary_id=summary_b.id,
            game_id=game.id,
            result_description_full="一個平凡的滾地球",
        )
    )
    db_session.commit()

    # 執行查詢
    # 驗證查詢 Homerun King 能正確找到資料
    stats_a = analysis.get_stats_since_last_homerun(db_session, "Homerun King")
    assert stats_a is not None
    assert stats_a["last_homerun"].player_summary.player_name == "Homerun King"

    # 驗證查詢 No Homerun Guy 時，應回傳 None
    stats_b = analysis.get_stats_since_last_homerun(db_session, "No Homerun Guy")
    assert stats_b is None


def test_find_at_bats_in_situation(db_session: Session):
    """測試 find_at_bats_in_situation 函式。"""
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
    )
    ab2 = models.AtBatDetailDB(
        player_game_summary_id=summary.id,
        game_id=game.id,
        runners_on_base_before="一壘、二壘、三壘有人",
    )
    ab3 = models.AtBatDetailDB(
        player_game_summary_id=summary.id,
        game_id=game.id,
        runners_on_base_before="二壘有人",
    )
    db_session.add_all([ab1, ab2, ab3])
    db_session.commit()

    results_bl = analysis.find_at_bats_in_situation(
        db_session, "情境男", models.RunnersSituation.BASES_LOADED
    )
    assert len(results_bl) == 1
    assert results_bl[0].runners_on_base_before == "一壘、二壘、三壘有人"

    results_sp = analysis.find_at_bats_in_situation(
        db_session, "情境男", models.RunnersSituation.SCORING_POSITION
    )
    assert len(results_sp) == 2


def test_find_next_at_bats_after_ibb(db_session: Session):
    """測試 find_next_at_bats_after_ibb 的 v2 (同半局) 查詢邏輯。"""
    game = models.GameResultDB(
        cpbl_game_id="G_IBB",
        game_date=datetime.date(2025, 8, 10),
        home_team="H",
        away_team="A",
    )
    db_session.add(game)
    db_session.flush()
    s_A = models.PlayerGameSummaryDB(game_id=game.id, player_name="球員A")
    s_B = models.PlayerGameSummaryDB(game_id=game.id, player_name="球員B")
    s_C = models.PlayerGameSummaryDB(game_id=game.id, player_name="球員C")
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

    results = analysis.find_next_at_bats_after_ibb(db_session, "球員B")
    assert len(results) == 2

    result_latest = results[0]
    assert result_latest["intentional_walk"].inning == 2
    assert result_latest["next_at_bat"] is None

    result_earlier = results[1]
    assert result_earlier["intentional_walk"].inning == 1
    assert result_earlier["next_at_bat"] is not None
    assert result_earlier["next_at_bat"].player_summary.player_name == "球員C"


def test_find_on_base_streaks_by_player_names(
    db_session: Session, setup_streak_test_data
):
    """測試 find_on_base_streaks 的指定球員序列查詢功能。"""
    streaks = analysis.find_on_base_streaks(
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

    streaks = analysis.find_on_base_streaks(
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
    """測試 find_on_base_streaks 的指定棒次序列查詢功能。"""
    streaks = analysis.find_on_base_streaks(
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


def test_find_games_with_players_eager_loads_summaries(db_session: Session):
    """[修改] 測試 find_games_with_players 是否預先載入了 summaries。"""
    g1 = models.GameResultDB(
        cpbl_game_id="G1",
        game_date=datetime.date(2025, 8, 1),
        home_team="H",
        away_team="A",
    )
    db_session.add(g1)
    db_session.flush()
    s1a = models.PlayerGameSummaryDB(game_id=g1.id, player_name="球員A")
    s1b = models.PlayerGameSummaryDB(game_id=g1.id, player_name="球員B")
    db_session.add_all([s1a, s1b])
    db_session.commit()

    games = analysis.find_games_with_players(db_session, ["球員A", "球員B"])
    assert len(games) == 1
    from sqlalchemy.orm.attributes import instance_state

    # [修正] 斷言邏輯：預先載入後，'player_summaries' 不應在 unloaded 集合中
    assert "player_summaries" not in instance_state(games[0]).unloaded


def test_get_stats_since_last_homerun_includes_career_stats(db_session: Session):
    """[修改] 測試 get_stats_since_last_homerun 是否包含生涯數據。"""
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
    career = models.PlayerCareerStatsDB(player_name="轟炸基", homeruns=100, avg=0.300)
    db_session.add(career)
    db_session.commit()

    stats = analysis.get_stats_since_last_homerun(db_session, "轟炸基")

    assert stats is not None
    assert "career_stats" in stats
    assert stats["career_stats"].player_name == "轟炸基"
    assert stats["career_stats"].homeruns == 100


def test_find_on_base_streaks_includes_opponent_team(
    db_session: Session, setup_streak_test_data
):
    """[修改] 測試 find_on_base_streaks 的結果是否包含 opponent_team。"""
    streaks = analysis.find_on_base_streaks(
        db=db_session,
        definition_name="consecutive_on_base",
        min_length=3,
        player_names=None,
        lineup_positions=None,
    )
    assert len(streaks) == 1
    assert streaks[0].opponent_team == "樂天桃猿"


def test_find_on_base_streaks_by_player_names_order_agnostic(
    db_session: Session, setup_streak_test_data
):
    """[新增] 測試使用 player_names 查詢時，順序不影響結果。"""
    streaks = analysis.find_on_base_streaks(
        db=db_session,
        definition_name="consecutive_on_base",
        min_length=3,
        player_names=["球員C", "球員A", "球員B"],  # 順序打亂
        lineup_positions=None,
    )
    assert len(streaks) == 1
    streak = streaks[0]
    assert streak.streak_length == 3
    # 驗證回傳的打席順序仍然是 A -> B -> C
    assert streak.at_bats[0].player_name == "球員A"
    assert streak.at_bats[1].player_name == "球員B"
    assert streak.at_bats[2].player_name == "球員C"


def test_find_on_base_streaks_generic(db_session: Session, setup_streak_test_data):
    """測試 find_on_base_streaks 的泛用查詢功能。"""
    streaks_len3 = analysis.find_on_base_streaks(
        db=db_session,
        definition_name="consecutive_on_base",
        min_length=3,
        player_names=None,
        lineup_positions=None,
    )
    assert len(streaks_len3) == 1
    assert streaks_len3[0].streak_length == 3
    assert streaks_len3[0].at_bats[0].player_name == "球員A"

    streaks_len2 = analysis.find_on_base_streaks(
        db=db_session,
        definition_name="consecutive_on_base",
        min_length=2,
        player_names=None,
        lineup_positions=None,
    )
    # [修正] 預期結果應為 2 (A-B-C 和 E-F)
    assert len(streaks_len2) == 2


def test_find_on_base_streaks_with_different_definition(
    db_session: Session, setup_streak_test_data
):
    """測試 find_on_base_streaks 使用不同連線定義的功能。"""
    streaks = analysis.find_on_base_streaks(
        db=db_session,
        definition_name="consecutive_hits",
        min_length=2,
        player_names=None,
        lineup_positions=None,
    )
    # [修正] 預期結果應為 1 (E-F)
    assert len(streaks) == 1
    assert streaks[0].streak_length == 2
    assert streaks[0].at_bats[0].player_name == "球員E"


def test_analyze_ibb_impact(db_session: Session, setup_ibb_impact_test_data):
    """測試 analyze_ibb_impact 函式。"""
    results = analysis.analyze_ibb_impact(db=db_session, player_name="影響者B")
    # [修正] 預期結果應為 2
    assert len(results) == 2
    assert results[0].inning == 2
    assert results[1].inning == 1


def test_analyze_ibb_impact_includes_opponent_team(
    db_session: Session, setup_ibb_impact_test_data
):
    """[修改] 測試 analyze_ibb_impact 的結果是否包含 opponent_team。"""
    results = analysis.analyze_ibb_impact(db=db_session, player_name="影響者B")
    assert len(results) > 0
    assert results[0].opponent_team == "中信兄弟"
