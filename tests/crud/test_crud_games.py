# tests/crud/test_crud_games.py

import datetime
from app import models
from app.crud import games


def test_create_game_and_get_id(db_session):
    """【修改】測試 create_game_and_get_id 函式"""
    db = db_session

    game_info = {
        "cpbl_game_id": "TEST01",
        "game_date": "2025-06-21",
        "home_team": "測試主隊",
        "away_team": "測試客隊",
        "status": "已完成",
    }

    # 首次建立
    game_id = games.create_game_and_get_id(db, game_info)
    db.commit()
    assert game_id is not None

    game_in_db = db.query(models.GameResultDB).filter_by(id=game_id).first()
    assert game_in_db is not None
    assert game_in_db.cpbl_game_id == "TEST01"
    assert db.query(models.GameResultDB).count() == 1


def test_delete_game_if_exists(db_session):
    """【新增】測試 delete_game_if_exists 函式"""
    db = db_session

    # 準備一筆完整的比賽資料 (Game -> Summary -> AtBat)
    game = models.GameResultDB(
        cpbl_game_id="DEL01",
        game_date=datetime.date(2025, 8, 8),
        home_team="H",
        away_team="A",
    )
    db.add(game)
    db.flush()
    summary = models.PlayerGameSummaryDB(game_id=game.id, player_name="測試員")
    db.add(summary)
    db.flush()
    at_bat = models.AtBatDetailDB(
        player_game_summary_id=summary.id,
        game_id=game.id,
        result_short="一安",
    )
    db.add(at_bat)
    db.commit()

    assert db.query(models.GameResultDB).count() == 1
    assert db.query(models.PlayerGameSummaryDB).count() == 1
    assert db.query(models.AtBatDetailDB).count() == 1

    # 執行刪除
    games.delete_game_if_exists(db, "DEL01", datetime.date(2025, 8, 8))
    db.commit()

    # 驗證所有關聯資料都已被級聯刪除
    assert db.query(models.GameResultDB).count() == 0
    assert db.query(models.PlayerGameSummaryDB).count() == 0
    assert db.query(models.AtBatDetailDB).count() == 0

    # 測試刪除一個不存在的比賽，不應發生任何錯誤
    try:
        games.delete_game_if_exists(db, "NON_EXISTENT", datetime.date(2025, 8, 9))
        db.commit()
    except Exception as e:
        assert False, f"刪除不存在的比賽時不應拋出異常: {e}"


def test_idempotency_delete_then_create(db_session):
    """【新增】整合測試，驗證「先刪除後新增」的冪等性流程"""
    db = db_session

    # 第一次執行，建立初始資料
    initial_info = {
        "cpbl_game_id": "IDEMP01",
        "game_date": "2025-09-01",
        "home_team": "主隊",
        "away_team": "客隊",
        "status": "比賽中",
    }
    games.delete_game_if_exists(db, "IDEMP01", datetime.date(2025, 9, 1))
    games.create_game_and_get_id(db, initial_info)
    db.commit()

    assert db.query(models.GameResultDB).count() == 1
    game_v1 = db.query(models.GameResultDB).filter_by(cpbl_game_id="IDEMP01").first()
    assert game_v1.status == "比賽中"

    # 第二次執行，使用更新後的資料
    updated_info = {
        "cpbl_game_id": "IDEMP01",
        "game_date": "2025-09-01",
        "home_team": "主隊",
        "away_team": "客隊",
        "status": "已完成",  # 狀態已更新
    }
    games.delete_game_if_exists(db, "IDEMP01", datetime.date(2025, 9, 1))
    games.create_game_and_get_id(db, updated_info)
    db.commit()

    # 驗證資料庫中仍然只有一筆紀錄，且內容是更新後的
    assert db.query(models.GameResultDB).count() == 1
    game_v2 = db.query(models.GameResultDB).filter_by(cpbl_game_id="IDEMP01").first()
    assert game_v2 is not None
    assert game_v2.status == "已完成"


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


def test_get_games_by_date(db_session):
    """測試 get_games_by_date 函式"""
    db = db_session

    # 準備測試資料
    schedule1 = models.GameSchedule(
        game_id="DATE01",
        game_date=datetime.date(2025, 10, 10),
        game_time="17:05",
        matchup="A vs B",
    )
    schedule2 = models.GameSchedule(
        game_id="DATE02",
        game_date=datetime.date(2025, 10, 10),  # 同一天
        game_time="18:05",
        matchup="C vs D",
    )
    schedule3 = models.GameSchedule(
        game_id="DATE03",
        game_date=datetime.date(2025, 10, 11),  # 不同天
        game_time="17:05",
        matchup="E vs F",
    )
    db.add_all([schedule1, schedule2, schedule3])
    db.commit()

    # 執行函式
    results = games.get_games_by_date(db, datetime.date(2025, 10, 10))

    # 驗證結果
    assert len(results) == 2
    # 使用 set 比較可以忽略順序
    assert {s.game_id for s in results} == {"DATE01", "DATE02"}

    # 測試一個沒有比賽的日期
    no_game_results = games.get_games_by_date(db, datetime.date(2025, 1, 1))
    assert len(no_game_results) == 0


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
        player_game_summary_id=summary.id,
        game_id=game.id,  # 明確設定 game_id
        sequence_in_game=1,
        result_short="全壘打",
    )
    detail2 = models.AtBatDetailDB(
        player_game_summary_id=summary.id,
        game_id=game.id,  # 明確設定 game_id
        sequence_in_game=2,
        result_short="保送",
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


# === ▼▼▼ 新增 Dashboard CRUD Functions 的測試 ▼▼▼ ===


def test_get_completed_games_by_date(db_session):
    """測試 get_completed_games_by_date 是否只回傳指定日期的已完成比賽"""
    db = db_session
    target_date = datetime.date(2025, 8, 15)
    other_date = datetime.date(2025, 8, 16)

    # 準備測試資料
    # 1. 目標日期的已完成比賽 (應被回傳)
    game1 = models.GameResultDB(
        cpbl_game_id="DASH01",
        game_date=target_date,
        status="已完成",
        home_team="H1",
        away_team="A1",
    )
    # 2. 目標日期的未完成比賽 (不應被回傳)
    game2 = models.GameResultDB(
        cpbl_game_id="DASH02",
        game_date=target_date,
        status="Scheduled",
        home_team="H2",
        away_team="A2",
    )
    # 3. 其他日期的已完成比賽 (不應被回傳)
    game3 = models.GameResultDB(
        cpbl_game_id="DASH03",
        game_date=other_date,
        status="已完成",
        home_team="H3",
        away_team="A3",
    )
    db.add_all([game1, game2, game3])
    db.commit()

    # 執行函式
    results = games.get_completed_games_by_date(db, target_date)

    # 驗證結果
    assert len(results) == 1
    assert results[0].cpbl_game_id == "DASH01"
    assert results[0].status == "已完成"


def test_get_next_game_date_after(db_session):
    """測試 get_next_game_date_after 是否能找到正確的下一個比賽日"""
    db = db_session
    # 準備測試資料
    schedule_past = models.GameSchedule(
        game_id="SCHED_PAST", game_date=datetime.date(2025, 8, 14), matchup="G vs H"
    )
    schedule_today = models.GameSchedule(
        game_id="SCHED_CUR", game_date=datetime.date(2025, 8, 15), matchup="A vs B"
    )
    schedule_future_near = models.GameSchedule(
        game_id="SCHED_NEAR", game_date=datetime.date(2025, 8, 17), matchup="E vs F"
    )
    schedule_future_far = models.GameSchedule(
        game_id="SCHED_FAR", game_date=datetime.date(2025, 8, 20), matchup="C vs D"
    )
    db.add_all(
        [
            schedule_past,
            schedule_today,
            schedule_future_near,
            schedule_future_far,
        ]
    )
    db.commit()

    # --- 情境一: 從今天開始找，應找到今天 ---
    next_date_is_today = games.get_next_game_date_after(db, datetime.date(2025, 8, 15))
    assert next_date_is_today is not None
    assert next_date_is_today == datetime.date(2025, 8, 15)

    # --- 情境二: 從沒有比賽的明天開始找，應找到未來的最近一天 ---
    next_date_is_future = games.get_next_game_date_after(db, datetime.date(2025, 8, 16))
    assert next_date_is_future is not None
    assert next_date_is_future == datetime.date(2025, 8, 17)

    # --- 情境三: 測試沒有未來比賽的情況 ---
    no_future_date = games.get_next_game_date_after(db, datetime.date(2025, 8, 21))
    assert no_future_date is None


def test_get_last_completed_game_for_teams(db_session):
    """測試 get_last_completed_game_for_teams 能否找到正確的最後一場比賽"""
    db = db_session
    reference_date = datetime.date(2025, 8, 15)
    target_teams = ["目標A隊", "目標B隊"]

    # 準備測試資料
    # 1. 正確的目標比賽 (日期最近，隊伍正確，狀態正確)
    game1 = models.GameResultDB(
        cpbl_game_id="LAST01",
        game_date=datetime.date(2025, 8, 14),
        status="已完成",
        home_team="目標A隊",
        away_team="其他隊",
    )
    # 2. 較早的比賽
    game2 = models.GameResultDB(
        cpbl_game_id="LAST02",
        game_date=datetime.date(2025, 8, 13),
        status="已完成",
        home_team="其他隊",
        away_team="目標B隊",
    )
    # 3. 未完成的比賽 (修正: 變更 away_team 以避免 UNIQUE constraint 衝突)
    game3 = models.GameResultDB(
        cpbl_game_id="LAST03",
        game_date=datetime.date(2025, 8, 14),
        status="未開始",
        home_team="目標A隊",
        away_team="其他隊_v2",
    )
    # 4. 非目標隊伍的比賽
    game4 = models.GameResultDB(
        cpbl_game_id="LAST04",
        game_date=datetime.date(2025, 8, 14),
        status="已完成",
        home_team="其他隊C",
        away_team="其他隊D",
    )
    # 5. 未來的比賽
    game5 = models.GameResultDB(
        cpbl_game_id="LAST05",
        game_date=datetime.date(2025, 8, 16),
        status="已完成",
        home_team="目標A隊",
        away_team="其他隊",
    )
    db.add_all([game1, game2, game3, game4, game5])
    db.commit()

    # 執行函式
    result_game = games.get_last_completed_game_for_teams(
        db, target_teams, reference_date
    )

    # 驗證結果
    assert result_game is not None
    assert result_game.cpbl_game_id == "LAST01"

    # 測試找不到比賽的情況
    no_result_game = games.get_last_completed_game_for_teams(
        db, ["不存在的隊伍"], reference_date
    )
    assert no_result_game is None
