# tests/crud/test_crud_players.py

from app import models
from app.crud import games, players


def test_store_player_season_stats_and_history(db_session):
    """【修改】測試 store_player_season_stats_and_history 函式"""
    db = db_session

    stats_list_1 = [
        {"player_name": "測試員A", "team_name": "測試隊", "avg": 0.300},
        {"player_name": "測試員B", "team_name": "測試隊", "avg": 0.250, "homeruns": 5},
    ]

    # 第一次執行
    players.store_player_season_stats_and_history(db, stats_list_1)
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
    players.store_player_season_stats_and_history(db, stats_list_2)
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
    game_id = games.create_game_and_get_id(db, game_info)
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

    players.store_player_game_data(db, game_id, player_data_list)
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


def test_store_player_game_data_empty_list(db_session):
    """[新增] 測試當傳入空的 all_players_data 列表時，函式能優雅地處理。"""
    db = db_session
    game_info = {
        "cpbl_game_id": "TEST_EMPTY",
        "game_date": "2025-01-01",
        "home_team": "H",
        "away_team": "A",
    }
    game_id = games.create_game_and_get_id(db, game_info)
    db.commit()
    assert game_id is not None

    initial_summary_count = db.query(models.PlayerGameSummaryDB).count()
    initial_detail_count = db.query(models.AtBatDetailDB).count()

    # 執行函式
    players.store_player_game_data(db, game_id, [])
    db.commit()

    # 驗證資料庫沒有任何變動
    assert db.query(models.PlayerGameSummaryDB).count() == initial_summary_count
    assert db.query(models.AtBatDetailDB).count() == initial_detail_count
