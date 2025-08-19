# tests/services/test_dashboard.py

import datetime

from freezegun import freeze_time

from app import models, schemas
from app.config import Settings
from app.services.dashboard import DashboardService


@freeze_time("2025-08-15")
def test_get_today_dashboard_data_with_games(db_session):
    """
    測試情境 A: 當天有已完成的比賽。
    預期: 回傳 DashboardHasGamesResponse，且只包含當天的已完成比賽。
    """
    db = db_session
    today = datetime.date.today()  # 2025-08-15

    # 準備資料
    # 1. 當天已完成的比賽 (應回傳)
    game1 = models.GameResultDB(
        cpbl_game_id="G01",
        game_date=today,
        status="已完成",
        home_team="A",
        away_team="B",
    )
    # 2. 當天未完成的比賽 (應忽略)
    game2 = models.GameResultDB(
        cpbl_game_id="G02",
        game_date=today,
        status="Scheduled",
        home_team="C",
        away_team="D",
    )
    # 3. 其他日期的比賽 (應忽略)
    game3 = models.GameResultDB(
        cpbl_game_id="G03",
        game_date=today - datetime.timedelta(days=1),
        status="已完成",
        home_team="E",
        away_team="F",
    )
    db.add_all([game1, game2, game3])
    db.commit()

    # 準備 Service
    # 在此情境下，TARGET_TEAMS 不影響結果
    settings = Settings(TARGET_TEAMS=["any team"])
    service = DashboardService(db=db, settings=settings)

    # 執行
    result = service.get_today_dashboard_data()

    # 驗證
    assert isinstance(result, schemas.DashboardHasGamesResponse)
    assert result.status == "HAS_TODAY_GAMES"
    assert len(result.games) == 1
    assert result.games[0].cpbl_game_id == "G01"


@freeze_time("2025-08-15")
def test_get_today_dashboard_data_no_games(db_session):
    """
    測試情境 B: 當天沒有已完成的比賽。
    預期: 回傳 DashboardNoGamesResponse，包含正確的下一場比賽日期和目標球隊的上一場比賽。
    """
    db = db_session
    today = datetime.date.today()  # 2025-08-15
    target_teams = ["目標A隊", "目標B隊"]

    # 準備資料
    # 【修正】 1. 未來的比賽應建立在 GameSchedule 表格
    next_schedule_1 = models.GameSchedule(
        game_id="NEXT01",
        game_date=today + datetime.timedelta(days=2),  # 2025-08-17
        matchup="A vs B",
    )
    next_schedule_2 = models.GameSchedule(
        game_id="NEXT02",
        game_date=today + datetime.timedelta(days=5),  # 2025-08-20
        matchup="C vs D",
    )
    # 2. 過去的比賽 (應找到目標A隊 8/14 這場)，維持在 GameResultDB
    last_game_target = models.GameResultDB(
        cpbl_game_id="LAST_TARGET",
        game_date=today - datetime.timedelta(days=1),  # 2025-08-14
        status="已完成",
        home_team="目標A隊",
        away_team="C",
    )
    last_game_older = models.GameResultDB(
        cpbl_game_id="LAST_OLDER",
        game_date=today - datetime.timedelta(days=3),  # 2025-08-12
        status="已完成",
        home_team="目標B隊",
        away_team="D",
    )
    last_game_other_team = models.GameResultDB(
        cpbl_game_id="LAST_OTHER",
        game_date=today - datetime.timedelta(days=1),  # 2025-08-14
        status="已完成",
        home_team="其他隊",
        away_team="E",
    )
    db.add_all(
        [
            next_schedule_1,
            next_schedule_2,
            last_game_target,
            last_game_older,
            last_game_other_team,
        ]
    )
    db.commit()

    # 準備 Service
    settings = Settings(TARGET_TEAMS=target_teams)
    service = DashboardService(db=db, settings=settings)

    # 執行
    result = service.get_today_dashboard_data()

    # 驗證
    assert isinstance(result, schemas.DashboardNoGamesResponse)
    assert result.status == "NO_TODAY_GAMES"
    assert result.next_game_date == datetime.date(2025, 8, 17)
    assert result.last_target_team_game is not None
    assert result.last_target_team_game.cpbl_game_id == "LAST_TARGET"


@freeze_time("2025-08-15")
def test_get_today_dashboard_data_no_games_and_no_data(db_session):
    """
    測試情境 C (邊界條件): 當天無比賽，且資料庫無未來比賽也無目標球隊歷史比賽。
    預期: 回傳 DashboardNoGamesResponse，但 next_game_date 和 last_target_team_game 均為 None。
    """
    db = db_session

    # 資料庫中只有一場無關的舊比賽
    other_game = models.GameResultDB(
        cpbl_game_id="OTHER",
        game_date=datetime.date(2025, 8, 1),
        status="已完成",
        home_team="其他隊",
        away_team="無關隊",
    )
    db.add(other_game)
    db.commit()

    # 準備 Service
    settings = Settings(TARGET_TEAMS=["目標A隊"])
    service = DashboardService(db=db, settings=settings)

    # 執行
    result = service.get_today_dashboard_data()

    # 驗證
    assert isinstance(result, schemas.DashboardNoGamesResponse)
    assert result.status == "NO_TODAY_GAMES"
    assert result.next_game_date is None
    assert result.last_target_team_game is None
