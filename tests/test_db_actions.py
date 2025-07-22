# tests/test_db_actions.py

# 【新增】匯入 datetime 模組
import datetime

# 導入我們要測試的資料庫操作函式和 ORM 模型
from app import db_actions, models

# --- Fixtures ---
# 此處的 test_db_session fixture 已被移除，它現在由 tests/conftest.py 全域提供


# --- 測試案例 ---


# 函式簽章從 (test_db_session) 改為 (db_session)
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

    # 第一次儲存，應該會新增並回傳 ID
    game_id = db_actions.store_game_and_get_id(db, game_info)
    db.commit()  # 手動提交交易
    assert game_id is not None

    # 驗證資料已寫入
    game_in_db = db.query(models.GameResultDB).filter_by(id=game_id).first()
    assert game_in_db is not None
    assert game_in_db.cpbl_game_id == "TEST01"

    # 第二次儲存相同的比賽，應該直接回傳已存在的 ID
    game_id_again = db_actions.store_game_and_get_id(db, game_info)
    assert game_id_again == game_id

    # 驗證資料庫中仍然只有一筆記錄
    count = db.query(models.GameResultDB).count()
    assert count == 1


# 函式簽章從 (test_db_session) 改為 (db_session)
def test_update_player_season_stats(db_session):
    """測試 update_player_season_stats 函式"""
    db = db_session

    stats_list = [
        {"player_name": "測試員A", "team_name": "測試隊", "avg": 0.300},
        {"player_name": "測試員B", "team_name": "測試隊", "avg": 0.250, "homeruns": 5},
    ]

    db_actions.update_player_season_stats(db, stats_list)
    db.commit()

    player_a = (
        db.query(models.PlayerSeasonStatsDB).filter_by(player_name="測試員A").first()
    )
    assert player_a is not None
    assert player_a.avg == 0.300

    updated_stats_list = [
        {"player_name": "測試員A", "team_name": "測試隊", "avg": 0.305, "hits": 10},
    ]
    db_actions.update_player_season_stats(db, updated_stats_list)
    db.commit()

    player_a_updated = (
        db.query(models.PlayerSeasonStatsDB).filter_by(player_name="測試員A").first()
    )
    assert player_a_updated.avg == 0.305
    assert player_a_updated.hits == 10

    count = db.query(models.PlayerSeasonStatsDB).count()
    assert count == 2


# 函式簽章從 (test_db_session) 改為 (db_session)
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
    db.commit()  # 先提交比賽資訊
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


# 函式簽章從 (test_db_session) 改為 (db_session)
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


# 【新增】測試 get_game_with_details 函式
def test_get_game_with_details(db_session):
    """測試 get_game_with_details 是否能正確地預先載入所有關聯資料"""
    db = db_session

    # 1. 建立測試資料
    # 建立比賽
    # 【修改】將 game_date 的值從字串改為 datetime.date 物件
    game = models.GameResultDB(
        cpbl_game_id="TEST_DETAIL",
        game_date=datetime.date(2025, 7, 21),
        home_team="H",
        away_team="A",
    )
    db.add(game)
    db.flush()

    # 建立球員表現摘要
    summary = models.PlayerGameSummaryDB(
        game_id=game.id, player_name="測試員D", team_name="測試隊"
    )
    db.add(summary)
    db.flush()

    # 建立逐打席紀錄
    detail1 = models.AtBatDetailDB(
        player_game_summary_id=summary.id, sequence_in_game=1, result_short="全壘打"
    )
    detail2 = models.AtBatDetailDB(
        player_game_summary_id=summary.id, sequence_in_game=2, result_short="保送"
    )
    db.add_all([detail1, detail2])
    db.commit()

    # 2. 執行被測試的函式
    game_with_details = db_actions.get_game_with_details(db, game.id)

    # 3. 驗證結果
    assert game_with_details is not None
    assert game_with_details.cpbl_game_id == "TEST_DETAIL"

    # 驗證 player_summaries 是否已載入
    assert len(game_with_details.player_summaries) == 1
    player_summary = game_with_details.player_summaries[0]
    assert player_summary.player_name == "測試員D"

    # 驗證 at_bat_details 是否已從 summary 中載入
    assert len(player_summary.at_bat_details) == 2
    assert player_summary.at_bat_details[0].result_short == "全壘打"
    assert player_summary.at_bat_details[1].result_short == "保送"
