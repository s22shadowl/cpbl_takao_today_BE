# tests/crud/test_crud_games.py

import datetime
from app import models
from app.crud import games


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

    game_id = games.store_game_and_get_id(db, game_info)
    db.commit()
    assert game_id is not None

    game_in_db = db.query(models.GameResultDB).filter_by(id=game_id).first()
    assert game_in_db is not None
    assert game_in_db.cpbl_game_id == "TEST01"

    game_id_again = games.store_game_and_get_id(db, game_info)
    assert game_id_again == game_id

    count = db.query(models.GameResultDB).count()
    assert count == 1


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

    games.update_game_schedules(db, initial_schedules)
    db.commit()

    schedules_from_db = games.get_all_schedules(db)
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

    games.update_game_schedules(db, updated_schedules)
    db.commit()

    schedules_from_db_updated = games.get_all_schedules(db)
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

    game_with_details = games.get_game_with_details(db, game.id)

    assert game_with_details is not None
    assert game_with_details.cpbl_game_id == "TEST_DETAIL"
    assert len(game_with_details.player_summaries) == 1
    player_summary = game_with_details.player_summaries[0]
    assert player_summary.player_name == "測試員D"
    assert len(player_summary.at_bat_details) == 2
    assert player_summary.at_bat_details[0].result_short == "全壘打"
    assert player_summary.at_bat_details[1].result_short == "保送"
