# tests/test_scheduler.py

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, date

# 導入我們要測試的模組
from app import scheduler as app_scheduler
from app import models

# 導入要模擬的任務
from app.tasks import task_scrape_single_day

# --- Fixtures ---


@pytest.fixture
def mock_scheduler_and_deps(mocker):
    """
    一個 pytest fixture，用於模擬 scheduler 模組的所有外部依賴。
    我們直接模擬整個 scheduler 物件，並手動設定其屬性。
    """
    # 1. 在 mock 之前，先取得真實的 timezone
    real_timezone = app_scheduler.scheduler.timezone

    # 2. Mock 整個 scheduler 物件
    mock_scheduler = mocker.patch("app.scheduler.scheduler", autospec=True)

    # 3. 手動設定 mock 物件的屬性和方法的回傳值
    mock_scheduler.timezone = real_timezone
    # 使用 configure_mock 來一次性設定多個屬性
    mock_scheduler.configure_mock(
        running=False,
        state=0,  # 0 is STATE_STOPPED
        get_jobs=MagicMock(return_value=[]),
    )

    # 4. 模擬資料庫相關的依賴
    mocker.patch("app.scheduler.SessionLocal")
    mock_db_games = mocker.patch("app.scheduler.games")

    # 5. 回傳我們需要的 mock 物件
    return {"games": mock_db_games, "scheduler": mock_scheduler}


# --- 測試 _schedule_daily_scraper ---


@patch("app.scheduler.datetime")
def test_schedule_daily_scraper_with_valid_time(mock_datetime, mock_scheduler_and_deps):
    """測試 _schedule_daily_scraper 在有有效時間時，能正確設定排程。"""
    mock_scheduler = mock_scheduler_and_deps["scheduler"]

    fake_now = datetime(2025, 6, 25, 12, 0, 0, tzinfo=mock_scheduler.timezone)
    mock_datetime.now.return_value = fake_now
    mock_datetime.strptime = datetime.strptime

    game_date = "2025-07-10"
    game_time = "18:35"

    naive_game_dt = datetime.strptime(f"{game_date} {game_time}", "%Y-%m-%d %H:%M")
    aware_game_dt = naive_game_dt.astimezone(mock_scheduler.timezone)
    expected_run_date = aware_game_dt + timedelta(hours=3, minutes=30)

    app_scheduler._schedule_daily_scraper(game_date, game_time, "測試比賽")

    mock_scheduler.add_job.assert_called_once()
    call_args, call_kwargs = mock_scheduler.add_job.call_args
    assert call_args[0] == task_scrape_single_day.send
    assert call_kwargs["trigger"].run_date == expected_run_date


@patch("app.scheduler.datetime")
def test_schedule_daily_scraper_defaults_time(mock_datetime, mock_scheduler_and_deps):
    """測試 _schedule_daily_scraper 在時間為 None 或無效時，會使用預設時間 18:35。"""
    mock_scheduler = mock_scheduler_and_deps["scheduler"]

    fake_now = datetime(2025, 6, 25, 12, 0, 0, tzinfo=mock_scheduler.timezone)
    mock_datetime.now.return_value = fake_now
    mock_datetime.strptime = datetime.strptime

    game_date = "2025-07-10"

    app_scheduler._schedule_daily_scraper(game_date, None, "測試比賽1")
    mock_scheduler.add_job.assert_called_once()
    mock_scheduler.add_job.reset_mock()

    app_scheduler._schedule_daily_scraper(game_date, "", "測試比賽2")
    mock_scheduler.add_job.assert_called_once()


@patch("app.scheduler.datetime")
def test_schedule_daily_scraper_skips_past_run_date(
    mock_datetime, mock_scheduler_and_deps
):
    """測試 _schedule_daily_scraper 是否會正確跳過執行時間已過去的比賽。"""
    mock_scheduler = mock_scheduler_and_deps["scheduler"]

    fake_now = datetime(2025, 7, 1, 12, 0, 0, tzinfo=mock_scheduler.timezone)
    mock_datetime.now.return_value = fake_now
    mock_datetime.strptime = datetime.strptime

    past_game_date = "2025-06-30"
    past_game_time = "18:35"

    app_scheduler._schedule_daily_scraper(
        past_game_date, past_game_time, "已結束的比賽"
    )

    mock_scheduler.add_job.assert_not_called()


# --- 測試 setup_scheduler ---


@patch("app.scheduler._schedule_daily_scraper")
@patch("app.scheduler.datetime")
def test_setup_scheduler_default_behavior(
    mock_datetime, mock_schedule_func, mock_scheduler_and_deps
):
    """測試 setup_scheduler 預設行為 (只排程今天及未來的比賽)。"""
    mock_games = mock_scheduler_and_deps["games"]
    mock_scheduler = mock_scheduler_and_deps["scheduler"]

    mock_datetime.now.return_value = datetime(
        2025, 7, 1, 10, 0, 0, tzinfo=mock_scheduler.timezone
    )

    fake_schedules = [
        models.GameSchedule(
            game_date=date(2025, 6, 30), game_time="18:35", matchup="過去的比賽"
        ),
        models.GameSchedule(
            game_date=date(2025, 7, 1), game_time="18:35", matchup="今天的比賽"
        ),
        models.GameSchedule(
            game_date=date(2025, 7, 2), game_time="18:35", matchup="未來的比賽"
        ),
    ]
    mock_games.get_all_schedules.return_value = fake_schedules

    app_scheduler.setup_scheduler()

    assert mock_schedule_func.call_count == 2
    mock_schedule_func.assert_any_call("2025-07-01", "18:35", "今天的比賽")
    mock_schedule_func.assert_any_call("2025-07-02", "18:35", "未來的比賽")


@patch("app.scheduler._schedule_daily_scraper")
def test_setup_scheduler_scrape_all_season(mock_schedule_func, mock_scheduler_and_deps):
    """測試 setup_scheduler 在 scrape_all_season=True 時的行為。"""
    mock_games = mock_scheduler_and_deps["games"]

    fake_schedules = [
        models.GameSchedule(
            game_date=date(2025, 6, 30), game_time="18:35", matchup="過去的比賽"
        ),
        models.GameSchedule(
            game_date=date(2025, 7, 1), game_time="18:35", matchup="今天的比賽"
        ),
    ]
    mock_games.get_all_schedules.return_value = fake_schedules

    app_scheduler.setup_scheduler(scrape_all_season=True)

    assert mock_schedule_func.call_count == 2


def test_setup_scheduler_no_games(mock_scheduler_and_deps):
    """測試 setup_scheduler 在資料庫中沒有賽程時的行為。"""
    mock_games = mock_scheduler_and_deps["games"]
    mock_scheduler = mock_scheduler_and_deps["scheduler"]

    mock_games.get_all_schedules.return_value = []

    app_scheduler.setup_scheduler()

    mock_games.get_all_schedules.assert_called_once()
    mock_scheduler.add_job.assert_not_called()
    mock_scheduler.start.assert_called_once()
