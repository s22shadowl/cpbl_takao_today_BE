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

    # 【修改】根據 scraper.py 的 import，只 mock 'players' 模組
    mock_players_crud = mocker.patch("app.scraper.players")

    mock_fetcher = mocker.patch("app.scraper.fetcher")

    # 【修改】mock scraper 中 import 的 parser 模組
    mock_season_stats_parser = mocker.patch("app.scraper.season_stats")
    mock_box_score_parser = mocker.patch("app.scraper.box_score")
    mock_schedule_parser = mocker.patch("app.scraper.schedule")
    mock_live_parser = mocker.patch("app.scraper.live")

    # 【修改】完整地模擬 Playwright 的呼叫鏈
    mock_sync_playwright = mocker.patch("app.scraper.sync_playwright")
    # 【新增】Mock expect 函式以避免 ValueError
    mocker.patch("app.scraper.expect")
    mock_page = MagicMock()
    mock_page.content.return_value = "<html></html>"

    # 【新增】為 locator 和 click 鏈式呼叫提供 mock
    mock_locator = MagicMock()
    # 【修正】明確設定 count() 的回傳值為整數，並處理鏈式呼叫
    mock_locator.count.return_value = 1
    mock_locator.locator.return_value = mock_locator  # 讓 locator().locator() 可以運作
    mock_page.locator.return_value = mock_locator
    mock_locator.all.return_value = [MagicMock()]  # 確保迴圈可以執行

    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page
    mock_playwright = MagicMock()
    mock_playwright.chromium.launch.return_value = mock_browser
    mock_sync_playwright.return_value.__enter__.return_value = mock_playwright

    # 【修改】將所有 mock 物件加入回傳的字典
    return {
        "session": mock_session,
        "players": mock_players_crud,
        "fetcher": mock_fetcher,
        "season_stats_parser": mock_season_stats_parser,
        "box_score_parser": mock_box_score_parser,
        "schedule_parser": mock_schedule_parser,
        "live_parser": mock_live_parser,
    }


# --- 測試案例 ---


def test_scrape_and_store_season_stats(mock_scraper_dependencies):
    """測試 scrape_and_store_season_stats 的正常流程。"""
    mock_fetcher = mock_scraper_dependencies["fetcher"]
    mock_players = mock_scraper_dependencies["players"]
    mock_session = mock_scraper_dependencies["session"]
    mock_season_stats_parser = mock_scraper_dependencies["season_stats_parser"]

    mock_fetcher.get_dynamic_page_content.return_value = "<html></html>"
    mock_season_stats_parser.parse_season_stats_page.return_value = [
        {"player_name": "王柏融"}
    ]

    scraper.scrape_and_store_season_stats()

    mock_fetcher.get_dynamic_page_content.assert_called_once()
    mock_season_stats_parser.parse_season_stats_page.assert_called_once()
    mock_players.store_player_season_stats_and_history.assert_called_once()
    mock_session.commit.assert_called_once()
    mock_session.close.assert_called_once()


def test_scrape_single_day_flow(mock_scraper_dependencies):
    """測試 scrape_single_day 的主要流程與過濾邏輯。"""
    mock_fetcher = mock_scraper_dependencies["fetcher"]
    mock_schedule_parser = mock_scraper_dependencies["schedule_parser"]
    mock_process_games = patch("app.scraper._process_filtered_games").start()

    target_date = "2025-06-25"
    all_games = [
        {"game_date": "2025-06-24", "cpbl_game_id": "G1"},
        {"game_date": target_date, "cpbl_game_id": "G2"},
        {"game_date": target_date, "cpbl_game_id": "G3"},
    ]
    mock_fetcher.fetch_schedule_page.return_value = "<html></html>"
    mock_schedule_parser.parse_schedule_page.return_value = all_games

    scraper.scrape_single_day(specific_date=target_date)

    mock_process_games.assert_called_once()

    call_args, call_kwargs = mock_process_games.call_args
    processed_games_list = call_args[0]

    assert len(processed_games_list) == 2
    assert processed_games_list[0]["cpbl_game_id"] == "G2"
    assert processed_games_list[1]["cpbl_game_id"] == "G3"
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
    mock_players = mock_scraper_dependencies["players"]
    mock_box_score_parser = mock_scraper_dependencies["box_score_parser"]
    mock_live_parser = mock_scraper_dependencies["live_parser"]

    game_to_process = [
        {
            "status": "已完成",
            "home_team": settings.TARGET_TEAMS[0],
            "away_team": "敵隊",
            "cpbl_game_id": "TEST01",
            "box_score_url": "http://fake.url",
        }
    ]
    mock_players.store_game_and_get_id.return_value = 1
    mock_box_score_parser.parse_box_score_page.return_value = [
        {"summary": {"player_name": "王柏融"}, "at_bats_list": ["一安"]}
    ]
    mock_live_parser.parse_active_inning_details.return_value = []

    scraper._process_filtered_games(game_to_process, target_teams=settings.TARGET_TEAMS)

    mock_box_score_parser.parse_box_score_page.assert_called_once_with(
        "<html></html>", target_teams=settings.TARGET_TEAMS
    )
    mock_session.commit.assert_called_once()
    mock_session.rollback.assert_not_called()
    mock_session.close.assert_called_once()


def test_process_filtered_games_rolls_back_on_error(mock_scraper_dependencies):
    """測試 _process_filtered_games 在發生錯誤時會復原交易。"""
    mock_session = mock_scraper_dependencies["session"]
    mock_players = mock_scraper_dependencies["players"]
    mock_box_score_parser = mock_scraper_dependencies["box_score_parser"]

    mock_players.store_player_game_data.side_effect = Exception("Database Error")
    mock_box_score_parser.parse_box_score_page.return_value = [
        {"summary": {"player_name": "王柏融"}, "at_bats_list": ["一安"]}
    ]

    game_to_process = [
        {
            "status": "已完成",
            "home_team": settings.TARGET_TEAMS[0],
            "away_team": "敵隊",
            "cpbl_game_id": "TEST01",
            "box_score_url": "http://fake.url",
        }
    ]
    mock_players.store_game_and_get_id.return_value = 1

    scraper._process_filtered_games(game_to_process, target_teams=settings.TARGET_TEAMS)

    mock_session.commit.assert_not_called()
    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()


def test_process_filtered_games_no_target_teams(mock_scraper_dependencies):
    """【新增】測試 _process_filtered_games 在 target_teams=None 時，會處理所有球隊。"""
    mock_box_score_parser = mock_scraper_dependencies["box_score_parser"]
    mock_players = mock_scraper_dependencies["players"]

    game_to_process = [
        {
            "status": "已完成",
            "home_team": "任何主隊",
            "away_team": "任何客隊",
            "cpbl_game_id": "TEST02",
            "box_score_url": "http://fake.url",
        }
    ]
    mock_players.store_game_and_get_id.return_value = 1
    mock_box_score_parser.parse_box_score_page.return_value = []

    scraper._process_filtered_games(game_to_process)

    mock_players.store_game_and_get_id.assert_called_once()
    mock_box_score_parser.parse_box_score_page.assert_called_once_with(
        "<html></html>", target_teams=None
    )


def test_process_filtered_games_skips_non_target_teams(mock_scraper_dependencies):
    """【新增】測試 _process_filtered_games 會跳過不包含目標球隊的比賽。"""
    mock_players = mock_scraper_dependencies["players"]

    game_to_process = [
        {
            "status": "已完成",
            "home_team": "非目標主隊",
            "away_team": "非目標客隊",
            "cpbl_game_id": "TEST03",
            "box_score_url": "http://fake.url",
        }
    ]

    scraper._process_filtered_games(
        game_to_process, target_teams=["味全龍", "中信兄弟"]
    )

    mock_players.store_game_and_get_id.assert_not_called()
