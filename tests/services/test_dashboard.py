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
    預期: 回傳 DashboardHasGamesResponse，包含當天比賽和下一場比賽狀態。
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
    # 3. 未來的比賽排程 (用於 next_game_status)
    next_schedule = models.GameSchedule(
        game_id="NEXT01",
        game_date=today + datetime.timedelta(days=2),  # 2025-08-17
        game_time="17:05",
        matchup="E vs F",
    )
    db.add_all([game1, game2, next_schedule])
    db.commit()

    # 準備 Service
    settings = Settings(TARGET_TEAMS=["any team"])
    service = DashboardService(db=db, settings=settings)

    # 執行
    result = service.get_today_dashboard_data()

    # 驗證
    assert isinstance(result, schemas.DashboardHasGamesResponse)
    assert result.status == "HAS_TODAY_GAMES"
    assert len(result.games) == 1
    assert result.games[0].cpbl_game_id == "G01"
    assert result.next_game_status is not None
    assert result.next_game_status.game_date == datetime.date(2025, 8, 17)
    assert result.next_game_status.matchup == "E vs F"


@freeze_time("2025-08-15")
def test_get_today_dashboard_data_no_games(db_session):
    """
    測試情境 B: 當天沒有已完成的比賽。
    預期: 回傳 DashboardNoGamesResponse，包含下一場比賽、目標球隊上一場比賽及近期戰況。
    """
    db = db_session
    today = datetime.date.today()  # 2025-08-15
    target_teams = ["目標A隊", "目標B隊"]

    # 準備資料
    # 1. 未來的比賽排程
    next_schedule_1 = models.GameSchedule(
        game_id="NEXT01",
        game_date=today + datetime.timedelta(days=2),  # 2025-08-17
        matchup="A vs B",
    )
    # 2. 目標球隊的歷史比賽
    last_game_target = (
        models.GameResultDB(  # 這是 get_last_completed_game_for_teams 的目標
            cpbl_game_id="LAST_TARGET",
            game_date=today - datetime.timedelta(days=1),  # 2025-08-14
            status="已完成",
            home_team="目標A隊",
            away_team="C",
            home_score=5,
            away_score=3,  # A隊勝
        )
    )
    # 3. 用於計算近期戰況的更多歷史比賽
    recent_game_1 = models.GameResultDB(  # A隊敗
        cpbl_game_id="RECENT_1",
        game_date=today - datetime.timedelta(days=2),  # 2025-08-13
        status="已完成",
        home_team="D",
        away_team="目標A隊",
        home_score=4,
        away_score=2,
    )
    recent_game_2 = models.GameResultDB(  # A隊勝 (更早)
        cpbl_game_id="RECENT_2",
        game_date=today - datetime.timedelta(days=4),  # 2025-08-11
        status="已完成",
        home_team="目標A隊",
        away_team="E",
        home_score=10,
        away_score=0,
    )
    other_team_game = models.GameResultDB(
        cpbl_game_id="LAST_OTHER",
        game_date=today - datetime.timedelta(days=1),
        status="已完成",
        home_team="其他隊",
        away_team="F",
    )
    db.add_all(
        [
            next_schedule_1,
            last_game_target,
            recent_game_1,
            recent_game_2,
            other_team_game,
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

    # 驗證下一場比賽狀態
    assert result.next_game_status is not None
    assert result.next_game_status.game_date == datetime.date(2025, 8, 17)

    # 驗證目標球隊的上一場比賽
    assert result.last_target_team_game is not None
    assert result.last_target_team_game.cpbl_game_id == "LAST_TARGET"

    # 驗證近期戰況 (目標A隊最近三場依序為 勝、敗、勝)
    assert result.target_team_status is not None
    assert result.target_team_status.team_name == "目標A隊"
    assert result.target_team_status.last_10_games_record == "2-1-0"
    assert result.target_team_status.current_streak_description == "1連勝"


@freeze_time("2025-08-15")
def test_get_today_dashboard_data_no_games_and_no_data(db_session):
    """
    測試情境 C (邊界條件): 當天無比賽，且資料庫無未來比賽也無目標球隊歷史比賽。
    預期: 回傳 DashboardNoGamesResponse，所有可選欄位均為 None。
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
    assert result.next_game_status is None
    assert result.last_target_team_game is None
    assert result.target_team_status is None
