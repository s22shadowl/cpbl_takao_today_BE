# test/test_scheduler.py

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

# 導入我們要測試的模組
from app import scheduler as app_scheduler
from app import scraper

# --- Fixtures ---

@pytest.fixture
def mock_scheduler_dependencies(mocker):
    """一個 pytest fixture，用於模擬 scheduler 模組的所有外部依賴。"""
    mock_db_actions = mocker.patch('app.scheduler.db_actions')
    mock_get_conn = mocker.patch('app.scheduler.get_db_connection')
    mock_get_conn.return_value = MagicMock()
    mocker.patch('app.scheduler.scraper')

    # 【核心修正】: 先取得真實的時區物件，再進行 patch
    real_timezone = app_scheduler.scheduler.timezone

    # 模擬 APScheduler 的核心物件
    mock_apscheduler = mocker.patch('app.scheduler.scheduler')
    
    # 將真實的時區物件賦予給模擬物件的屬性
    mock_apscheduler.timezone = real_timezone
    mock_apscheduler.running = False
    mock_apscheduler.state = 0 # 0 is STATE_STOPPED

    return {
        "db_actions": mock_db_actions,
        "scheduler": mock_apscheduler
    }


# --- 測試 _schedule_daily_scraper ---

@patch('app.scheduler.datetime')
def test_schedule_daily_scraper_with_valid_time(mock_datetime, mock_scheduler_dependencies):
    """測試 _schedule_daily_scraper 在有有效時間時，能正確設定排程。"""
    mock_scheduler = mock_scheduler_dependencies["scheduler"]
    
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
    _, call_kwargs = mock_scheduler.add_job.call_args
    assert call_kwargs['trigger'].run_date == expected_run_date

@patch('app.scheduler.datetime')
def test_schedule_daily_scraper_defaults_time(mock_datetime, mock_scheduler_dependencies):
    """【新增】測試 _schedule_daily_scraper 在時間為 None 或無效時，會使用預設時間 18:35。"""
    mock_scheduler = mock_scheduler_dependencies["scheduler"]
    
    fake_now = datetime(2025, 6, 25, 12, 0, 0, tzinfo=mock_scheduler.timezone)
    mock_datetime.now.return_value = fake_now
    mock_datetime.strptime = datetime.strptime

    game_date = "2025-07-10"
    default_game_time = "18:35" # 主程式碼中的預設時間
    
    # 預期觸發時間應基於預設時間計算
    naive_game_dt = datetime.strptime(f"{game_date} {default_game_time}", "%Y-%m-%d %H:%M")
    aware_game_dt = naive_game_dt.astimezone(mock_scheduler.timezone)
    expected_run_date = aware_game_dt + timedelta(hours=3, minutes=30)
    
    # 測試 game_time 為 None 的情況
    app_scheduler._schedule_daily_scraper(game_date, None, "測試比賽1")
    
    # 斷言
    mock_scheduler.add_job.assert_called_once()
    _, call_kwargs = mock_scheduler.add_job.call_args
    assert call_kwargs['trigger'].run_date == expected_run_date
    mock_scheduler.add_job.reset_mock()

    # 測試 game_time 為空字串的情況
    app_scheduler._schedule_daily_scraper(game_date, "", "測試比賽2")
    mock_scheduler.add_job.assert_called_once()
    _, call_kwargs = mock_scheduler.add_job.call_args
    assert call_kwargs['trigger'].run_date == expected_run_date

@patch('app.scheduler.datetime')
def test_schedule_daily_scraper_skips_past_run_date(mock_datetime, mock_scheduler_dependencies):
    """測試 _schedule_daily_scraper 是否會正確跳過執行時間已過去的比賽。"""
    mock_scheduler = mock_scheduler_dependencies["scheduler"]

    fake_now = datetime(2025, 7, 1, 12, 0, 0, tzinfo=mock_scheduler.timezone)
    mock_datetime.now.return_value = fake_now
    mock_datetime.strptime = datetime.strptime

    # 一個過去的比賽，其觸發時間 (賽後3.5小時) 也已經過去
    past_game_date = "2025-06-30"
    past_game_time = "18:35"
    
    app_scheduler._schedule_daily_scraper(past_game_date, past_game_time, "已結束的比賽")
    
    mock_scheduler.add_job.assert_not_called()

# --- 測試 setup_scheduler ---

@patch('app.scheduler._schedule_daily_scraper')
@patch('app.scheduler.datetime')
def test_setup_scheduler_default_behavior(mock_datetime, mock_schedule_func, mock_scheduler_dependencies):
    """【新增】測試 setup_scheduler 預設行為 (只排程今天及未來的比賽)。"""
    mock_db_actions = mock_scheduler_dependencies["db_actions"]
    
    # 設定一個固定的 "今天"
    # 【核心修正】: 直接使用真實的時區物件
    fake_today = datetime(2025, 7, 1, 10, 0, 0, tzinfo=app_scheduler.scheduler.timezone).date()
    mock_datetime.now.return_value.date.return_value = fake_today
    mock_datetime.strptime = datetime.strptime

    fake_schedules = [
        {'game_date': '2025-06-30', 'game_time': '18:35', 'matchup': '過去的比賽'},
        {'game_date': '2025-07-01', 'game_time': '18:35', 'matchup': '今天的比賽'},
        {'game_date': '2025-07-02', 'game_time': '18:35', 'matchup': '未來的比賽'},
    ]
    mock_db_actions.get_all_schedules.return_value = fake_schedules
    
    app_scheduler.setup_scheduler() # 預設 scrape_all_season=False

    assert mock_schedule_func.call_count == 2
    mock_schedule_func.assert_any_call('2025-07-01', '18:35', '今天的比賽')
    mock_schedule_func.assert_any_call('2025-07-02', '18:35', '未來的比賽')

@patch('app.scheduler._schedule_daily_scraper')
@patch('app.scheduler.datetime')
def test_setup_scheduler_scrape_all_season(mock_datetime, mock_schedule_func, mock_scheduler_dependencies):
    """【新增】測試 setup_scheduler 在 scrape_all_season=True 時的行為。"""
    mock_db_actions = mock_scheduler_dependencies["db_actions"]

    # 【核心修正】: 直接使用真實的時區物件
    fake_today = datetime(2025, 7, 1, 10, 0, 0, tzinfo=app_scheduler.scheduler.timezone).date()
    mock_datetime.now.return_value.date.return_value = fake_today
    mock_datetime.strptime = datetime.strptime

    fake_schedules = [
        {'game_date': '2025-06-30', 'game_time': '18:35', 'matchup': '過去的比賽'},
        {'game_date': '2025-07-01', 'game_time': '18:35', 'matchup': '今天的比賽'},
        {'game_date': '2025-07-02', 'game_time': '18:35', 'matchup': '未來的比賽'},
    ]
    mock_db_actions.get_all_schedules.return_value = fake_schedules
    
    app_scheduler.setup_scheduler(scrape_all_season=True)

    # 斷言所有比賽都被排程
    assert mock_schedule_func.call_count == 3

def test_setup_scheduler_no_games(mock_scheduler_dependencies):
    """測試 setup_scheduler 在資料庫中沒有賽程時的行為。"""
    mock_db_actions = mock_scheduler_dependencies["db_actions"]
    mock_scheduler = mock_scheduler_dependencies["scheduler"]

    mock_db_actions.get_all_schedules.return_value = []
    
    app_scheduler.setup_scheduler()

    mock_db_actions.get_all_schedules.assert_called_once()
    # 驗證 add_job 從未被呼叫
    mock_scheduler.add_job.assert_not_called()
    # 驗證 scheduler 仍然會啟動
    mock_scheduler.start.assert_called_once()
