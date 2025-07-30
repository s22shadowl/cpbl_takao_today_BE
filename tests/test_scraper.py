# tests/test_scraper.py

from unittest.mock import patch, MagicMock
import pytest

from app import scraper
from app.config import settings


@pytest.fixture
def mock_playwright_page(monkeypatch):
    """
    完整模擬 Playwright 的啟動過程，並回傳一個可控的假 page 物件。
    """
    mock_page = MagicMock()
    mock_page.content.return_value = "<html></html>"
    mock_page.locator.return_value.all.return_value = []

    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page

    mock_chromium = MagicMock()
    mock_chromium.launch.return_value = mock_browser

    mock_playwright = MagicMock()
    mock_playwright.chromium = mock_chromium

    mock_sync_playwright = MagicMock()
    mock_sync_playwright.__enter__.return_value = mock_playwright

    monkeypatch.setattr("app.scraper.sync_playwright", lambda: mock_sync_playwright)

    return mock_page


@pytest.fixture
def mock_scraper_dependencies(monkeypatch):
    """
    【修改】為 scraper 中的函式模擬所有外部依賴。
    SessionLocal 不再回傳真實 db_session，而是回傳一個 MagicMock 實例。
    """
    mocks = {
        "fetcher": patch("app.scraper.fetcher").start(),
        "schedule_parser": patch("app.scraper.schedule").start(),
        "box_score_parser": patch("app.scraper.box_score").start(),
        "live_parser": patch("app.scraper.live").start(),
        "season_stats_parser": patch("app.scraper.season_stats").start(),
        "players": patch("app.scraper.players").start(),
        "games": patch("app.scraper.games").start(),
        "session": patch("app.scraper.SessionLocal").start(),  # <--- 核心修改點
    }
    yield mocks
    patch.stopall()


def test_scrape_single_day_flow(mock_scraper_dependencies):
    """
    測試 scrape_single_day 是否使用傳入的參數正確呼叫 _process_filtered_games。
    """
    mock_process_games = patch("app.scraper._process_filtered_games").start()
    target_date = "2025-06-25"
    games_for_the_day = [{"game_date": target_date, "cpbl_game_id": "G2"}]

    scraper.scrape_single_day(
        specific_date=target_date,
        games_for_day=games_for_the_day,
        update_season_stats=False,
    )

    mock_scraper_dependencies[
        "season_stats_parser"
    ].parse_season_stats_page.assert_not_called()
    mock_process_games.assert_called_once_with(
        games_for_the_day, target_teams=settings.TARGET_TEAMS
    )


def test_process_filtered_games_commits_on_success(
    mock_scraper_dependencies, mock_playwright_page
):
    """
    【修改】測試 _process_filtered_games 在成功時會提交交易。
    """
    mock_session_class = mock_scraper_dependencies["session"]
    mock_games = mock_scraper_dependencies["games"]
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
    mock_games.store_game_and_get_id.return_value = 1
    mock_box_score_parser.parse_box_score_page.return_value = [
        {"summary": {"player_name": "王柏融"}, "at_bats_list": ["一安"]}
    ]
    mock_live_parser.parse_active_inning_details.return_value = []

    scraper._process_filtered_games(game_to_process, target_teams=settings.TARGET_TEAMS)

    mock_box_score_parser.parse_box_score_page.assert_called_once_with(
        "<html></html>", target_teams=settings.TARGET_TEAMS
    )

    # 【修改】驗證由 SessionLocal 類別建立出來的「實例」的 commit 方法被呼叫
    session_instance_mock = mock_session_class.return_value
    session_instance_mock.commit.assert_called_once()
    session_instance_mock.rollback.assert_not_called()


def test_process_filtered_games_rolls_back_on_error(
    mock_scraper_dependencies, mock_playwright_page
):
    """
    【修改】測試 _process_filtered_games 在發生錯誤時會復原交易。
    """
    mock_session_class = mock_scraper_dependencies["session"]
    mock_players = mock_scraper_dependencies["players"]
    mock_games = mock_scraper_dependencies["games"]
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
    mock_games.store_game_and_get_id.return_value = 1

    scraper._process_filtered_games(game_to_process, target_teams=settings.TARGET_TEAMS)

    # 【修改】驗證由 SessionLocal 類別建立出來的「實例」的 rollback 方法被呼叫
    session_instance_mock = mock_session_class.return_value
    session_instance_mock.commit.assert_not_called()
    session_instance_mock.rollback.assert_called_once()


def test_process_filtered_games_no_target_teams(
    mock_scraper_dependencies, mock_playwright_page
):
    """
    測試 _process_filtered_games 在 target_teams=None 時，會處理所有球隊。
    """
    mock_box_score_parser = mock_scraper_dependencies["box_score_parser"]
    mock_games = mock_scraper_dependencies["games"]

    game_to_process = [
        {
            "status": "已完成",
            "home_team": "任何主隊",
            "away_team": "任何客隊",
            "cpbl_game_id": "TEST02",
            "box_score_url": "http://fake.url",
        }
    ]
    mock_games.store_game_and_get_id.return_value = 1
    mock_box_score_parser.parse_box_score_page.return_value = []

    scraper._process_filtered_games(game_to_process)

    mock_games.store_game_and_get_id.assert_called_once()
