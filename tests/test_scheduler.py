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

    real_timezone = app_scheduler.scheduler.timezone
    mock_apscheduler = mocker.patch('app.scheduler.scheduler')
    mock_apscheduler.timezone = real_timezone
    mock_apscheduler.running = False
    
    return {
        "db_actions": mock_db_actions,
        "scheduler": mock_apscheduler
    }


# --- 測試案例 ---

@patch('app.scheduler.datetime') # 使用 patch 來模擬整個 datetime 模組
def test_schedule_daily_scraper(mock_datetime, mock_scheduler_dependencies):
    """
    單元測試 _schedule_daily_scraper 函式，驗證其排程邏輯。
    """
    mock_scheduler = mock_scheduler_dependencies["scheduler"]
    
    # 準備：設定一個固定的 "現在" 時間，並確保它是帶有時區的 "aware" 物件
    fake_now = datetime(2025, 6, 25, 12, 0, 0, tzinfo=mock_scheduler.timezone)
    mock_datetime.now.return_value = fake_now
    # 確保 strptime 仍然使用真實的 datetime 類別來建立物件
    mock_datetime.strptime = datetime.strptime

    # 1. 準備一個未來的比賽時間
    future_game_dt = fake_now + timedelta(hours=5)
    game_date = future_game_dt.strftime("%Y-%m-%d")
    game_time = future_game_dt.strftime("%H:%M")
    
    # 預期觸發時間
    naive_game_dt = datetime.strptime(f"{game_date} {game_time}", "%Y-%m-%d %H:%M")
    
    # 【核心修正】:
    # 修正 AttributeError: 'zoneinfo.ZoneInfo' object has no attribute 'localize'
    # 為了與 app/scheduler.py 中的邏輯完全保持一致，此處也使用 .astimezone() 
    # 來計算期望值，以確保測試斷言能夠通過。
    aware_game_dt = naive_game_dt.astimezone(mock_scheduler.timezone)
    expected_run_date = aware_game_dt + timedelta(hours=3, minutes=30)
    
    # 2. 執行
    app_scheduler._schedule_daily_scraper(game_date, game_time, "測試客隊 vs 測試主隊")
    
    # 3. 斷言
    mock_scheduler.add_job.assert_called_once()
    _, call_kwargs = mock_scheduler.add_job.call_args
    assert call_kwargs['trigger'].run_date == expected_run_date

@patch('app.scheduler.datetime')
def test_schedule_daily_scraper_skips_past_games(mock_datetime, mock_scheduler_dependencies):
    """
    測試 _schedule_daily_scraper 是否會正確跳過已過去的比賽。
    """
    mock_scheduler = mock_scheduler_dependencies["scheduler"]

    fake_now = datetime.now(mock_scheduler.timezone)
    mock_datetime.now.return_value = fake_now
    mock_datetime.strptime = datetime.strptime

    past_trigger_dt = fake_now - timedelta(days=1)
    game_date = past_trigger_dt.strftime("%Y-%m-%d")
    game_time = past_trigger_dt.strftime("%H:%M")
    
    app_scheduler._schedule_daily_scraper(game_date, game_time, "已結束的比賽")
    
    mock_scheduler.add_job.assert_not_called()

@patch('app.scheduler._schedule_daily_scraper') # 直接模擬內部的排程函式
def test_setup_scheduler_with_games(mock_schedule_func, mock_scheduler_dependencies):
    """
    測試 setup_scheduler 在資料庫中有賽程時的完整流程。
    """
    mock_db_actions = mock_scheduler_dependencies["db_actions"]
    mock_scheduler = mock_scheduler_dependencies["scheduler"]

    fake_schedules = [
        {'game_date': '2025-07-01', 'game_time': '18:35', 'matchup': 'A vs B'},
        {'game_date': '2025-07-02', 'game_time': '18:35', 'matchup': 'C vs D'},
    ]
    mock_db_actions.get_all_schedules.return_value = fake_schedules
    
    mock_job1 = MagicMock()
    mock_job1.next_run_time = datetime(2025, 7, 1, 22, 5, 0)
    mock_job2 = MagicMock()
    mock_job2.next_run_time = datetime(2025, 7, 2, 22, 5, 0)
    mock_scheduler.get_jobs.return_value = [mock_job1, mock_job2]
    
    # 執行
    app_scheduler.setup_scheduler()

    # 斷言
    mock_db_actions.get_all_schedules.assert_called_once()
    # 確認 _schedule_daily_scraper 被呼叫了兩次
    assert mock_schedule_func.call_count == 2
    mock_scheduler.start.assert_called_once()


def test_setup_scheduler_no_games(mock_scheduler_dependencies):
    """
    測試 setup_scheduler 在資料庫中沒有賽程時的行為。
    """
    mock_db_actions = mock_scheduler_dependencies["db_actions"]
    mock_scheduler = mock_scheduler_dependencies["scheduler"]

    mock_db_actions.get_all_schedules.return_value = []
    
    mock_scheduler.get_jobs.return_value = []
    
    app_scheduler.setup_scheduler()

    mock_db_actions.get_all_schedules.assert_called_once()
    mock_scheduler.add_job.assert_not_called()
    mock_scheduler.start.assert_called_once()