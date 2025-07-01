# test/core/test_schedule_scraper.py

import pytest
from datetime import datetime

# 導入我們要測試的模組
from app.core import schedule_scraper

# --- 測試用的假資料 ---

# 模擬一個包含過去、今天、未來比賽的 HTML 內容
SAMPLE_HTML_MULTIPLE_DATES = """
<html><body>
<div class="ScheduleTableList">
  <tbody>
    <tr>
      <td class="date">06/30 (一)</td>
      <td class="game_no">180</td>
      <td class="team"><div class="name away">中信兄弟</div><div class="name home">味全龍</div></td>
      <td class="info"><div class="time"><span>18:35</span></div></td>
    </tr>
    <tr>
      <td class="date">07/01 (二)</td>
      <td class="game_no">181</td>
      <td class="team"><div class="name away">樂天桃猿</div><div class="name home">中信兄弟</div></td>
      <td class="info"><div class="time"><span>18:35</span></div></td>
    </tr>
    <tr>
      <td class="date">07/02 (三)</td>
      <td class="game_no">182</td>
      <td class="team"><div class="name away">中信兄弟</div><div class="name home">富邦悍將</div></td>
      <td class="info"><div class="time"><span>17:05</span></div></td>
    </tr>
  </tbody>
</div>
</body></html>
"""

# --- Fixtures ---

@pytest.fixture
def mock_dependencies(mocker):
    """一個 pytest fixture，用於模擬 schedule_scraper 模組的所有外部依賴。"""
    # 模擬 Playwright
    mock_playwright = mocker.patch('app.core.schedule_scraper.sync_playwright')
    mock_p_context = mock_playwright.return_value.__enter__.return_value
    mock_browser = mock_p_context.chromium.launch.return_value
    mock_page = mock_browser.new_page.return_value
    
    # 模擬資料庫相關操作
    mock_db_actions = mocker.patch('app.core.schedule_scraper.db_actions')
    mock_get_conn = mocker.patch('app.core.schedule_scraper.get_db_connection')
    
    # 模擬設定檔
    mocker.patch('app.core.schedule_scraper.config.TARGET_TEAM_NAME', '中信兄弟')
    
    # 模擬 datetime 模組以控制 "今天" 的日期
    mock_datetime = mocker.patch('app.core.schedule_scraper.datetime')
    
    return {
        "page": mock_page,
        "browser": mock_browser,
        "db_actions": mock_db_actions,
        "get_conn": mock_get_conn,
        "datetime": mock_datetime,
    }

# --- 測試案例 ---

def test_scrape_with_include_past_games_true(mock_dependencies):
    """【新增】測試當 include_past_games=True 時，會儲存所有爬取到的比賽。"""
    mock_page = mock_dependencies['page']
    mock_db_actions = mock_dependencies['db_actions']
    
    mock_page.content.return_value = SAMPLE_HTML_MULTIPLE_DATES
    
    expected_all_games = [
        {'date': '2025-06-30', 'game_id': '180', 'matchup': '中信兄弟 vs 味全龍', 'game_time': '18:35'},
        {'date': '2025-07-01', 'game_id': '181', 'matchup': '樂天桃猿 vs 中信兄弟', 'game_time': '18:35'},
        {'date': '2025-07-02', 'game_id': '182', 'matchup': '中信兄弟 vs 富邦悍將', 'game_time': '17:05'}
    ]

    # 執行，明確傳入 include_past_games=True
    result = schedule_scraper.scrape_cpbl_schedule(2025, 6, 7, include_past_games=True)
    
    # 斷言：回傳的結果應包含所有比賽
    assert result == expected_all_games
    # 斷言：存入資料庫的也是所有比賽
    mock_db_actions.update_game_schedules.assert_called_once_with(
        mock_dependencies['get_conn'].return_value,
        expected_all_games
    )

def test_scrape_with_default_filtering(mock_dependencies):
    """【新增】測試預設行為 (include_past_games=False)，只會儲存今天及未來的比賽。"""
    mock_page = mock_dependencies['page']
    mock_db_actions = mock_dependencies['db_actions']
    mock_datetime = mock_dependencies['datetime']

    # 模擬 "今天" 是 2025/7/1
    fake_today = datetime(2025, 7, 1).date()
    mock_datetime.now.return_value.date.return_value = fake_today
    # 確保 strptime 仍然可以使用
    mock_datetime.strptime = datetime.strptime

    mock_page.content.return_value = SAMPLE_HTML_MULTIPLE_DATES

    expected_future_games = [
        {'date': '2025-07-01', 'game_id': '181', 'matchup': '樂天桃猿 vs 中信兄弟', 'game_time': '18:35'},
        {'date': '2025-07-02', 'game_id': '182', 'matchup': '中信兄弟 vs 富邦悍將', 'game_time': '17:05'}
    ]

    # 執行，使用預設的 include_past_games=False
    result = schedule_scraper.scrape_cpbl_schedule(2025, 6, 7)

    # 斷言：回傳的結果只應包含今天及未來的比賽
    assert result == expected_future_games
    # 斷言：存入資料庫的也只應是今天及未來的比賽
    mock_db_actions.update_game_schedules.assert_called_once_with(
        mock_dependencies['get_conn'].return_value,
        expected_future_games
    )

def test_scrape_schedule_no_target_team_found(mock_dependencies):
    """測試當爬取到的賽程中不包含目標球隊時的行為。"""
    mock_page = mock_dependencies['page']
    mock_db_actions = mock_dependencies['db_actions']
    mock_get_conn = mock_dependencies['get_conn']

    html_no_match = """
    <html><body><div class="ScheduleTableList"><tbody>
      <tr>
        <td class="date">07/01 (二)</td><td class="game_no">181</td>
        <td class="team"><div class="name away">樂天桃猿</div><div class="name home">味全龍</div></td>
        <td class="info"><div class="time"><span>18:35</span></div></td>
      </tr>
    </tbody></div></body></html>
    """
    mock_page.content.return_value = html_no_match
    
    result = schedule_scraper.scrape_cpbl_schedule(2025, 7, 7)
    
    assert result == []
    mock_get_conn.assert_not_called()
    mock_db_actions.update_game_schedules.assert_not_called()

def test_scrape_schedule_page_load_timeout(mock_dependencies):
    """測試當頁面載入關鍵元件超時的錯誤處理。"""
    mock_page = mock_dependencies['page']
    mock_browser = mock_dependencies['browser']
    
    mock_page.wait_for_selector.side_effect = Exception("Test Timeout")
    
    result = schedule_scraper.scrape_cpbl_schedule(2025, 7, 7)
    
    assert result == []
    mock_browser.close.assert_called_once()

def test_scrape_schedule_db_error_handles_finally(mock_dependencies):
    """測試當資料庫寫入失敗時，是否能確保連線被關閉。"""
    mock_page = mock_dependencies['page']
    mock_db_actions = mock_dependencies['db_actions']
    mock_get_conn = mock_dependencies['get_conn']
    mock_conn = mock_get_conn.return_value

    mock_page.content.return_value = SAMPLE_HTML_MULTIPLE_DATES
    mock_db_actions.update_game_schedules.side_effect = Exception("DB write error")
    
    with pytest.raises(Exception, match="DB write error"):
        # 傳入 include_past_games=True 以確保有資料可以觸發儲存操作
        schedule_scraper.scrape_cpbl_schedule(2025, 6, 7, include_past_games=True)

    mock_get_conn.assert_called_once()
    mock_conn.close.assert_called_once()
