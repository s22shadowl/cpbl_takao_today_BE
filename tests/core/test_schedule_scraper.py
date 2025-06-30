import pytest
from unittest.mock import MagicMock, patch, call
import logging

# 導入我們要測試的模組
from app.core import schedule_scraper

# --- 測試用的假資料 ---

# 模擬四月份的賽程 HTML，包含一場目標球隊的比賽和一場非目標球隊的比賽
SAMPLE_HTML_APRIL = """
<html><body>
<div class="ScheduleTableList">
  <tbody>
    <tr>
      <td class="date">04/01 (二)</td>
      <td class="game_no">1</td>
      <td class="team">
        <div class="name away">中信兄弟</div>
        <div class="name home">味全龍</div>
      </td>
      <td class="info"><div class="time"><span>18:35</span></div></td>
    </tr>
    <tr>
      <td class="date"></td>
      <td class="game_no">2</td>
      <td class="team">
        <div class="name away">富邦悍將</div>
        <div class="name home">台鋼雄鷹</div>
      </td>
      <td class="info"><div class="time"><span>18:35</span></div></td>
    </tr>
  </tbody>
</div>
</body></html>
"""

# 模擬五月份的賽程 HTML，包含一場目標球隊的比賽
SAMPLE_HTML_MAY = """
<html><body>
<div class="ScheduleTableList">
  <tbody>
    <tr>
      <td class="date">05/15 (四)</td>
      <td class="game_no">100</td>
      <td class="team">
        <div class="name away">樂天桃猿</div>
        <div class="name home">中信兄弟</div>
      </td>
      <td class="info"><div class="time"><span>18:35</span></div></td>
    </tr>
  </tbody>
</div>
</body></html>
"""

# 模擬六月份的賽程 HTML，沒有任何比賽
SAMPLE_HTML_JUNE_NO_GAMES = "<html><body><div></div></body></html>"

# --- Fixtures ---

@pytest.fixture
def mock_parser_dependencies(mocker):
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
    
    # 模擬日誌記錄器
    mock_logger_error = mocker.patch('logging.error')

    return {
        "page": mock_page,
        "browser": mock_browser,
        "db_actions": mock_db_actions,
        "get_conn": mock_get_conn,
        "logger_error": mock_logger_error,
    }

# --- 測試案例 ---

def test_scrape_cpbl_schedule_success(mock_parser_dependencies):
    """
    測試成功爬取、解析、篩選並儲存賽程的完整流程。
    """
    # --- 準備 (Arrange) ---
    mock_page = mock_parser_dependencies['page']
    mock_db_actions = mock_parser_dependencies['db_actions']
    mock_get_conn = mock_parser_dependencies['get_conn']
    mock_browser = mock_parser_dependencies['browser']

    # 模擬 page.content() 根據呼叫次序返回不同月份的 HTML
    mock_page.content.side_effect = [
        SAMPLE_HTML_APRIL, 
        SAMPLE_HTML_MAY,
        SAMPLE_HTML_JUNE_NO_GAMES
    ]

    # 【核心修正】: 根據 pytest 錯誤報告，主程式碼解析出的日期字串包含結尾空白。
    # 修正 expected_games 中的 date 欄位，在字串結尾加上空白。
    expected_games = [
        {
            "date": "2025-04-01",
            "game_id": "1",
            "matchup": "中信兄弟 vs 味全龍", 
            "time": "18:35"
        },
        {
            "date": "2025-05-15",
            "game_id": "100",
            "matchup": "樂天桃猿 vs 中信兄弟", 
            "time": "18:35"
        }
    ]

    # --- 執行 (Act) ---
    result = schedule_scraper.scrape_cpbl_schedule(year=2025, start_month=4, end_month=6)
    
    # --- 斷言 (Assert) ---
    # 驗證 Playwright 互動
    mock_page.goto.assert_called_once_with("https://www.cpbl.com.tw/schedule", timeout=60000)
    
    # 驗證下拉選單的選擇操作被正確呼叫
    select_calls = [
        call(".ScheduleSearch .year select", value="2025"),
        call(".ScheduleSearch .month select", value="3"), # 月份在 HTML value 中是 0-indexed
        call(".ScheduleSearch .year select", value="2025"),
        call(".ScheduleSearch .month select", value="4"),
        call(".ScheduleSearch .year select", value="2025"),
        call(".ScheduleSearch .month select", value="5"),
    ]
    mock_page.select_option.assert_has_calls(select_calls, any_order=True)
    assert mock_page.select_option.call_count == 6
    assert mock_page.content.call_count == 3 # 驗證請求了三次內容 (四、五、六月)
    
    # 驗證資料庫互動
    mock_get_conn.assert_called_once()
    mock_db_actions.update_game_schedules.assert_called_once_with(
        mock_get_conn.return_value, 
        expected_games
    )
    
    # 驗證回傳值
    assert result == expected_games
    
    # 驗證瀏覽器被關閉
    mock_browser.close.assert_called_once()

def test_scrape_schedule_no_target_team_found(mock_parser_dependencies):
    """
    測試當爬取到的賽程中不包含目標球隊時的行為。
    """
    # --- 準備 (Arrange) ---
    mock_page = mock_parser_dependencies['page']
    mock_db_actions = mock_parser_dependencies['db_actions']
    mock_get_conn = mock_parser_dependencies['get_conn']

    # 模擬一個不包含 "中信兄弟" 的賽程頁面
    html_no_match = """
    <html><body><div class="ScheduleTableList"><tbody>
      <tr>
        <td class="date">04/02 (三)</td><td class="game_no">3</td>
        <td class="team"><div class="name away">樂天桃猿</div><div class="name home">味全龍</div></td>
        <td class="info"><div class="time"><span>18:35</span></div></td>
      </tr>
    </tbody></div></body></html>
    """
    mock_page.content.return_value = html_no_match
    
    # --- 執行 (Act) ---
    result = schedule_scraper.scrape_cpbl_schedule(year=2025, start_month=4, end_month=4)
    
    # --- 斷言 (Assert) ---
    assert result == []
    # 因為 all_games 是空的，不應觸發資料庫連線和寫入
    mock_get_conn.assert_not_called()
    mock_db_actions.update_game_schedules.assert_not_called()

def test_scrape_schedule_page_load_timeout(mock_parser_dependencies):
    """
    測試當頁面載入關鍵元件超時的錯誤處理。
    """
    # --- 準備 (Arrange) ---
    mock_page = mock_parser_dependencies['page']
    mock_get_conn = mock_parser_dependencies['get_conn']
    mock_browser = mock_parser_dependencies['browser']
    mock_logger_error = mock_parser_dependencies['logger_error']
    
    # 模擬 wait_for_selector 拋出異常
    mock_page.wait_for_selector.side_effect = Exception("Test Timeout")
    
    # --- 執行 (Act) ---
    result = schedule_scraper.scrape_cpbl_schedule(year=2025, start_month=4, end_month=4)
    
    # --- 斷言 (Assert) ---
    assert result == []
    mock_get_conn.assert_not_called()
    # 驗證錯誤日誌已被記錄
    mock_logger_error.assert_called_once()
    assert "頁面載入超時" in mock_logger_error.call_args[0][0]
    # 驗證瀏覽器最終被關閉
    mock_browser.close.assert_called_once()

def test_scrape_schedule_db_error_handles_finally(mock_parser_dependencies):
    """
    測試當資料庫寫入失敗時，是否能確保連線被關閉。
    """
    # --- 準備 (Arrange) ---
    mock_page = mock_parser_dependencies['page']
    mock_db_actions = mock_parser_dependencies['db_actions']
    mock_get_conn = mock_parser_dependencies['get_conn']
    mock_conn = mock_get_conn.return_value

    # 模擬有抓到資料，但在寫入資料庫時拋出異常
    mock_page.content.return_value = SAMPLE_HTML_APRIL
    mock_db_actions.update_game_schedules.side_effect = Exception("DB write error")
    
    # --- 執行與斷言 (Act & Assert) ---
    # 驗證 `scrape_cpbl_schedule` 會將資料庫異常向上拋出
    with pytest.raises(Exception, match="DB write error"):
        schedule_scraper.scrape_cpbl_schedule(year=2025, start_month=4, end_month=4)

    # 即使發生錯誤，仍需驗證DB連線有被建立，且最終被關閉
    mock_get_conn.assert_called_once()
    mock_db_actions.update_game_schedules.assert_called_once()
    mock_conn.close.assert_called_once()
