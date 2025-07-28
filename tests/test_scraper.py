# tests/test_scraper.py

import pytest
import datetime
from unittest.mock import MagicMock, patch

from app import scraper
from app.config import settings

# --- Fixtures ---


@pytest.fixture
def mock_scraper_dependencies(mocker):
    """一個 fixture，用於模擬 scraper 模組的所有外部依賴。"""
    mock_session_local = mocker.patch("app.scraper.SessionLocal")
    mock_session = MagicMock()
    mock_session_local.return_value = mock_session
    mock_db_actions = mocker.patch("app.scraper.db_actions")
    mock_fetcher = mocker.patch("app.scraper.fetcher")
    mock_parser = mocker.patch("app.scraper.html_parser")

    # 【修改】完整地模擬 Playwright 的呼叫鏈
    mock_sync_playwright = mocker.patch("app.scraper.sync_playwright")

    # 建立一個 mock page 物件，並設定其 content() 方法的回傳值
    mock_page = MagicMock()
    mock_page.content.return_value = "<html></html>"

    # 建立 mock browser 並設定其 new_page() 方法回傳我們建立的 mock page
    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page

    # 建立 mock playwright 實例並設定其 launch() 方法回傳 mock browser
    mock_playwright = MagicMock()
    mock_playwright.chromium.launch.return_value = mock_browser

    # 確保當 sync_playwright 作為上下文管理器被進入時，回傳的是我們設定好的 mock playwright 實例
    mock_sync_playwright.return_value.__enter__.return_value = mock_playwright

    return {
        "session": mock_session,
        "db_actions": mock_db_actions,
        "fetcher": mock_fetcher,
        "parser": mock_parser,
    }


# --- 測試案例 ---


def test_scrape_and_store_season_stats(mock_scraper_dependencies):
    """測試 scrape_and_store_season_stats 的正常流程。"""
    mock_fetcher = mock_scraper_dependencies["fetcher"]
    mock_parser = mock_scraper_dependencies["parser"]
    mock_db_actions = mock_scraper_dependencies["db_actions"]
    mock_session = mock_scraper_dependencies["session"]

    mock_fetcher.get_dynamic_page_content.return_value = "<html></html>"
    mock_parser.parse_season_stats_page.return_value = [{"player_name": "王柏融"}]

    scraper.scrape_and_store_season_stats()

    mock_fetcher.get_dynamic_page_content.assert_called_once()
    mock_parser.parse_season_stats_page.assert_called_once()
    mock_db_actions.store_player_season_stats_and_history.assert_called_once()
    mock_session.commit.assert_called_once()
    mock_session.close.assert_called_once()


def test_scrape_single_day_flow(mock_scraper_dependencies):
    """測試 scrape_single_day 的主要流程與過濾邏輯。"""
    mock_fetcher = mock_scraper_dependencies["fetcher"]
    mock_parser = mock_scraper_dependencies["parser"]
    mock_process_games = patch("app.scraper._process_filtered_games").start()

    target_date = "2025-06-25"
    all_games = [
        {"game_date": "2025-06-24", "cpbl_game_id": "G1"},
        {"game_date": target_date, "cpbl_game_id": "G2"},
        {"game_date": target_date, "cpbl_game_id": "G3"},
    ]
    mock_fetcher.fetch_schedule_page.return_value = "<html></html>"
    mock_parser.parse_schedule_page.return_value = all_games

    scraper.scrape_single_day(specific_date=target_date)

    mock_process_games.assert_called_once()

    # 驗證傳遞給 _process_filtered_games 的參數是正確過濾後的結果
    call_args, call_kwargs = mock_process_games.call_args
    processed_games_list = call_args[0]

    assert len(processed_games_list) == 2
    assert processed_games_list[0]["cpbl_game_id"] == "G2"
    assert processed_games_list[1]["cpbl_game_id"] == "G3"
    # 【新增】驗證 target_teams 參數被正確傳遞
    assert call_kwargs == {"target_teams": settings.TARGET_TEAMS}

    patch.stopall()


def test_scrape_single_day_aborts_for_future_date(mock_scraper_dependencies):
    """測試當目標日期為未來時，scrape_single_day 是否會中止。"""
    mock_fetcher = mock_scraper_dependencies["fetcher"]

    future_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )

    scraper.scrape_single_day(specific_date=future_date)

    mock_fetcher.fetch_schedule_page.assert_not_called()


def test_process_filtered_games_commits_on_success(mock_scraper_dependencies):
    """【修改】測試 _process_filtered_games 在成功時會提交交易，並驗證參數傳遞"""
    mock_session = mock_scraper_dependencies["session"]
    mock_db_actions = mock_scraper_dependencies["db_actions"]
    mock_parser = mock_scraper_dependencies["parser"]

    game_to_process = [
        {
            "status": "已完成",
            "home_team": settings.TARGET_TEAMS[0],  # 使用 settings 中的球隊列表
            "away_team": "敵隊",
            "cpbl_game_id": "TEST01",
            "box_score_url": "http://fake.url",
        }
    ]
    mock_db_actions.store_game_and_get_id.return_value = 1
    mock_parser.parse_box_score_page.return_value = [
        {"summary": {"player_name": "王柏融"}, "at_bats_list": ["一安"]}
    ]
    mock_parser.parse_active_inning_details.return_value = []

    # 執行，並傳入 target_teams 參數
    scraper._process_filtered_games(game_to_process, target_teams=settings.TARGET_TEAMS)

    # 斷言
    # 驗證 parse_box_score_page 被呼叫時，收到了正確的 target_teams 參數
    mock_parser.parse_box_score_page.assert_called_once_with(
        "<html></html>", target_teams=settings.TARGET_TEAMS
    )
    mock_session.commit.assert_called_once()
    mock_session.rollback.assert_not_called()
    mock_session.close.assert_called_once()


def test_process_filtered_games_rolls_back_on_error(mock_scraper_dependencies):
    """測試 _process_filtered_games 在發生錯誤時會復原交易。"""
    mock_session = mock_scraper_dependencies["session"]
    mock_db_actions = mock_scraper_dependencies["db_actions"]

    mock_db_actions.store_player_game_data.side_effect = Exception("Database Error")

    game_to_process = [
        {
            "status": "已完成",
            "home_team": settings.TARGET_TEAMS[0],
            "away_team": "敵隊",
            "cpbl_game_id": "TEST01",
            "box_score_url": "http://fake.url",
        }
    ]
    mock_db_actions.store_game_and_get_id.return_value = 1

    # 執行
    scraper._process_filtered_games(game_to_process, target_teams=settings.TARGET_TEAMS)

    # 斷言
    mock_session.commit.assert_not_called()
    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()


def test_process_filtered_games_no_target_teams(mock_scraper_dependencies):
    """【新增】測試 _process_filtered_games 在 target_teams=None 時，會處理所有球隊。"""
    mock_parser = mock_scraper_dependencies["parser"]
    mock_db_actions = mock_scraper_dependencies["db_actions"]

    game_to_process = [
        {
            "status": "已完成",
            "home_team": "任何主隊",
            "away_team": "任何客隊",
            "cpbl_game_id": "TEST02",
            "box_score_url": "http://fake.url",
        }
    ]
    mock_db_actions.store_game_and_get_id.return_value = 1

    # 執行，不傳入 target_teams 參數 (預設為 None)
    scraper._process_filtered_games(game_to_process)

    # 斷言 store_game_and_get_id 被呼叫，表示函式沒有因為球隊不符而被跳過
    mock_db_actions.store_game_and_get_id.assert_called_once()
    # 斷言 parse_box_score_page 被呼叫時，target_teams 參數為 None
    mock_parser.parse_box_score_page.assert_called_once_with(
        "<html></html>", target_teams=None
    )


def test_process_filtered_games_skips_non_target_teams(mock_scraper_dependencies):
    """【新增】測試 _process_filtered_games 會跳過不包含目標球隊的比賽。"""
    mock_db_actions = mock_scraper_dependencies["db_actions"]

    game_to_process = [
        {
            "status": "已完成",
            "home_team": "非目標主隊",
            "away_team": "非目標客隊",
            "cpbl_game_id": "TEST03",
            "box_score_url": "http://fake.url",
        }
    ]

    # 執行，並傳入一個包含目標球隊的列表
    scraper._process_filtered_games(
        game_to_process, target_teams=["味全龍", "中信兄弟"]
    )

    # 斷言核心的資料庫操作函式從未被呼叫，因為比賽被篩選掉了
    mock_db_actions.store_game_and_get_id.assert_not_called()
