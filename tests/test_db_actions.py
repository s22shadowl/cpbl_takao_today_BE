# tests/test_db_actions.py

import datetime

from app import db_actions, models


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
