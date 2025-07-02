# tests/core/test_schedule_scraper.py

import pytest
from datetime import datetime
from unittest.mock import MagicMock

# 導入我們要測試的模組
from app.core import schedule_scraper

# --- 測試用的假資料 ---

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
    mock_playwright = mocker.patch("app.core.schedule_scraper.sync_playwright")
    mock_p_context = mock_playwright.return_value.__enter__.return_value
    mock_browser = mock_p_context.chromium.launch.return_value
    mock_page = mock_browser.new_page.return_value

    # 模擬資料庫相關操作
    mock_db_actions = mocker.patch("app.core.schedule_scraper.db_actions")
    mock_session_local = mocker.patch("app.core.schedule_scraper.SessionLocal")
    mock_session = MagicMock()
    mock_session_local.return_value = mock_session

    # 模擬 settings 物件
    mocker.patch("app.core.schedule_scraper.settings.TARGET_TEAM_NAME", "中信兄弟")

    # 模擬 datetime 模組以控制 "今天" 的日期
    mock_datetime = mocker.patch("app.core.schedule_scraper.datetime")

    return {
        "page": mock_page,
        "browser": mock_browser,
        "db_actions": mock_db_actions,
        "session": mock_session,
        "datetime": mock_datetime,
    }


# --- 測試案例 ---


def test_scrape_with_include_past_games_true(mock_dependencies):
    """測試當 include_past_games=True 時，會儲存所有爬取到的比賽。"""
    mock_page = mock_dependencies["page"]
    mock_db_actions = mock_dependencies["db_actions"]
    mock_session = mock_dependencies["session"]

    mock_page.content.return_value = SAMPLE_HTML_MULTIPLE_DATES

    expected_all_games = [
        {
            "date": "2025-06-30",
            "game_id": "180",
            "matchup": "中信兄弟 vs 味全龍",
            "game_time": "18:35",
        },
        {
            "date": "2025-07-01",
            "game_id": "181",
            "matchup": "樂天桃猿 vs 中信兄弟",
            "game_time": "18:35",
        },
        {
            "date": "2025-07-02",
            "game_id": "182",
            "matchup": "中信兄弟 vs 富邦悍將",
            "game_time": "17:05",
        },
    ]

    result = schedule_scraper.scrape_cpbl_schedule(2025, 6, 7, include_past_games=True)

    assert result == expected_all_games
    mock_db_actions.update_game_schedules.assert_called_once_with(
        mock_session, expected_all_games
    )
    mock_session.close.assert_called_once()


def test_scrape_with_default_filtering(mock_dependencies):
    """測試預設行為 (include_past_games=False)，只會儲存今天及未來的比賽。"""
    mock_page = mock_dependencies["page"]
    mock_db_actions = mock_dependencies["db_actions"]
    mock_datetime = mock_dependencies["datetime"]
    mock_session = mock_dependencies["session"]

    fake_today = datetime(2025, 7, 1).date()
    mock_datetime.now.return_value.date.return_value = fake_today
    mock_datetime.strptime = datetime.strptime

    mock_page.content.return_value = SAMPLE_HTML_MULTIPLE_DATES

    expected_future_games = [
        {
            "date": "2025-07-01",
            "game_id": "181",
            "matchup": "樂天桃猿 vs 中信兄弟",
            "game_time": "18:35",
        },
        {
            "date": "2025-07-02",
            "game_id": "182",
            "matchup": "中信兄弟 vs 富邦悍將",
            "game_time": "17:05",
        },
    ]

    result = schedule_scraper.scrape_cpbl_schedule(2025, 6, 7)

    assert result == expected_future_games
    mock_db_actions.update_game_schedules.assert_called_once_with(
        mock_session, expected_future_games
    )
    mock_session.close.assert_called_once()


def test_scrape_schedule_no_target_team_found(mock_dependencies):
    """測試當爬取到的賽程中不包含目標球隊時的行為。"""
    mock_page = mock_dependencies["page"]
    mock_db_actions = mock_dependencies["db_actions"]

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
    mock_db_actions.update_game_schedules.assert_not_called()


def test_scrape_schedule_page_load_timeout(mock_dependencies):
    """測試當頁面載入關鍵元件超時的錯誤處理。"""
    mock_page = mock_dependencies["page"]
    mock_browser = mock_dependencies["browser"]

    mock_page.wait_for_selector.side_effect = Exception("Test Timeout")

    result = schedule_scraper.scrape_cpbl_schedule(2025, 7, 7)

    assert result == []
    mock_browser.close.assert_called_once()


def test_scrape_schedule_db_error_handles_finally(mock_dependencies):
    """測試當資料庫寫入失敗時，是否能確保交易被復原且連線被關閉。"""
    mock_page = mock_dependencies["page"]
    mock_db_actions = mock_dependencies["db_actions"]
    mock_session = mock_dependencies["session"]

    mock_page.content.return_value = SAMPLE_HTML_MULTIPLE_DATES
    # 模擬 db_actions 在被呼叫時拋出錯誤
    mock_db_actions.update_game_schedules.side_effect = Exception("DB write error")

    # 執行函式，並預期它不會向外拋出錯誤 (因為已被 try/except 捕捉)
    schedule_scraper.scrape_cpbl_schedule(2025, 6, 7, include_past_games=True)

    # 斷言：db_actions 被呼叫，但 rollback 也被呼叫，最後連線被關閉
    mock_db_actions.update_game_schedules.assert_called_once()
    mock_session.rollback.assert_called_once()
    mock_session.commit.assert_not_called()  # 確保沒有提交
    mock_session.close.assert_called_once()
