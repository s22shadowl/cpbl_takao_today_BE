# tests/test_scraper.py

import pytest
from unittest.mock import MagicMock
import datetime # <--- 修正二：加入了缺少的 import

from app import scraper, config

@pytest.fixture
def mock_modules(mocker):
    """一個 pytest fixture，用於模擬所有外部依賴模組。"""
    # 模擬整個模組，這樣 scraper.py 內部對這些模組的任何呼叫都會被攔截
    mock_fetcher = mocker.patch('app.scraper.fetcher')
    mock_parser = mocker.patch('app.scraper.html_parser') # 注意：要 patch scraper 裡面的 html_parser
    mock_db_actions = mocker.patch('app.scraper.db_actions')
    mock_get_conn = mocker.patch('app.scraper.get_db_connection')
    
    mock_conn = MagicMock()
    mock_get_conn.return_value = mock_conn

    # 將 mocker 也回傳，方便其他測試使用
    return {
        "fetcher": mock_fetcher,
        "parser": mock_parser,
        "db_actions": mock_db_actions,
        "conn": mock_conn,
        "mocker": mocker  
    }

def test_scrape_single_day_flow(mock_modules):
    """測試 scrape_single_day 的主要流程是否正確。"""
    # 1. 準備 (Arrange)
    fake_games_list = [
        {'game_date': '2025-06-21', 'cpbl_game_id': 'DUMMY01', 'home_team': config.TARGET_TEAM_NAME, 'status': '已完成', 'box_score_url': 'http://fake.box.url/1'},
    ]
    fake_player_data = [{"summary": {"player_name": "王柏融"}, "at_bats_list": []}]
    
    # 【修正一】設定所有會被呼叫的 fetcher 函式的回傳值
    mock_modules["fetcher"].get_dynamic_page_content.return_value = "<html></html>"
    mock_modules["fetcher"].fetch_schedule_page.return_value = "<html></html>"
    mock_modules["parser"].parse_season_stats_page.return_value = [] # 假設回傳空，避免進入 db
    mock_modules["parser"].parse_schedule_page.return_value = fake_games_list
    mock_modules["parser"].parse_box_score_page.return_value = fake_player_data
    mock_modules["db_actions"].store_game_and_get_id.return_value = 1

    # 2. 執行 (Act)
    scraper.scrape_single_day(specific_date='2025-06-21')

    # 3. 斷言 (Assert)
    # 驗證抓取球季數據的函式被呼叫
    mock_modules["fetcher"].get_dynamic_page_content.assert_any_call(
        f"{config.TEAM_SCORE_URL}?ClubNo={config.TEAM_CLUB_CODES[config.TARGET_TEAM_NAME]}", 
        wait_for_selector="div.RecordTable"
    )
    # 驗證抓取賽程頁的函式被呼叫
    mock_modules["fetcher"].fetch_schedule_page.assert_called_once_with(2025, 6)
    # 驗證抓取 Box Score 的函式被呼叫
    mock_modules["fetcher"].get_dynamic_page_content.assert_called_with(
        'http://fake.box.url/1', 
        wait_for_selector="div.GameBoxDetail"
    )
    # 驗證儲存球員數據的函式被呼叫
    mock_modules["db_actions"].store_player_game_data.assert_called_once_with(mock_modules["conn"], 1, fake_player_data)

def test_scrape_entire_year_skips_future(mock_modules):
    """測試 scrape_entire_year 在目標是未來年份時，是否會提前中止。"""
    future_year = str(datetime.date.today().year + 1)
    scraper.scrape_entire_year(year_str=future_year)
    mock_modules["fetcher"].fetch_schedule_page.assert_not_called()

def test_scrape_single_day_calls_season_stats(mock_modules):
    """測試 scrape_single_day 是否會呼叫 scrape_and_store_season_stats。"""
    mock_modules["fetcher"].fetch_schedule_page.return_value = "<html></html>"
    mock_modules["parser"].parse_schedule_page.return_value = []
    
    # 【修正三】直接從 mocker fixture 獲取 spy，而不是從我們自訂的 fixture
    mocker = mock_modules["mocker"]
    spy_season_stats = mocker.spy(scraper, 'scrape_and_store_season_stats')
    
    scraper.scrape_single_day(specific_date='2025-01-01')
    
    spy_season_stats.assert_called_once()