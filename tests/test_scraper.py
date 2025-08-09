# tests/test_scraper.py

from unittest.mock import patch, MagicMock, call, ANY
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import scraper
from app.config import settings
from app.exceptions import ScraperError, RetryableScraperError


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
    為 scraper 中的函式模擬所有外部依賴。
    """
    mocks = {
        "fetcher": patch("app.scraper.fetcher").start(),
        "schedule_parser": patch("app.scraper.schedule").start(),
        "box_score_parser": patch("app.scraper.box_score").start(),
        "live_parser": patch("app.scraper.live").start(),
        "season_stats_parser": patch("app.scraper.season_stats").start(),
        "players": patch("app.scraper.players").start(),
        "games": patch("app.scraper.games").start(),
        "session": patch("app.scraper.SessionLocal").start(),
        "logger": patch("app.scraper.logger").start(),
        "datetime": patch("app.scraper.datetime").start(),
        "time": patch("app.scraper.time").start(),
    }
    yield mocks
    patch.stopall()


# --- 測試 scrape_and_store_season_stats ---


def test_scrape_season_stats_success(mock_scraper_dependencies):
    """測試球季數據抓取成功時的正常流程。"""
    mock_fetcher = mock_scraper_dependencies["fetcher"]
    mock_parser = mock_scraper_dependencies["season_stats_parser"]
    mock_players_crud = mock_scraper_dependencies["players"]
    mock_session_instance = mock_scraper_dependencies["session"].return_value

    mock_fetcher.get_dynamic_page_content.return_value = "<html>Stats Page</html>"
    mock_parser.parse_season_stats_page.return_value = [{"player_name": "Player A"}]

    scraper.scrape_and_store_season_stats()

    mock_fetcher.get_dynamic_page_content.assert_called_once()
    mock_parser.parse_season_stats_page.assert_called_once_with(
        "<html>Stats Page</html>"
    )
    mock_players_crud.store_player_season_stats_and_history.assert_called_once_with(
        mock_session_instance, [{"player_name": "Player A"}]
    )
    mock_session_instance.commit.assert_called_once()
    mock_session_instance.rollback.assert_not_called()


def test_scrape_season_stats_propagates_fetcher_error(mock_scraper_dependencies):
    """測試當 fetcher 拋出錯誤時，錯誤會被向上傳遞。"""
    mock_fetcher = mock_scraper_dependencies["fetcher"]
    mock_parser = mock_scraper_dependencies["season_stats_parser"]
    mock_players_crud = mock_scraper_dependencies["players"]

    mock_fetcher.get_dynamic_page_content.side_effect = RetryableScraperError(
        "Network Error"
    )

    with pytest.raises(RetryableScraperError, match="Network Error"):
        scraper.scrape_and_store_season_stats()

    mock_parser.parse_season_stats_page.assert_not_called()
    mock_players_crud.store_player_season_stats_and_history.assert_not_called()


def test_scrape_season_stats_propagates_db_error(mock_scraper_dependencies):
    """測試當資料庫操作拋出錯誤時，錯誤會被向上傳遞。"""
    mock_fetcher = mock_scraper_dependencies["fetcher"]
    mock_parser = mock_scraper_dependencies["season_stats_parser"]
    mock_players_crud = mock_scraper_dependencies["players"]
    mock_session_instance = mock_scraper_dependencies["session"].return_value

    mock_fetcher.get_dynamic_page_content.return_value = "<html>Stats Page</html>"
    mock_parser.parse_season_stats_page.return_value = [{"player_name": "Player A"}]
    mock_players_crud.store_player_season_stats_and_history.side_effect = (
        SQLAlchemyError("DB Connection Failed")
    )

    with pytest.raises(SQLAlchemyError, match="DB Connection Failed"):
        scraper.scrape_and_store_season_stats()

    mock_session_instance.commit.assert_not_called()


# --- 測試 _process_filtered_games ---


def test_process_filtered_games_commits_on_success(
    mock_scraper_dependencies, mock_playwright_page
):
    """【修改】測試 _process_filtered_games 的成功路徑，驗證冪等性操作。"""
    mock_session_class = mock_scraper_dependencies["session"]
    mock_games = mock_scraper_dependencies["games"]
    mock_box_score_parser = mock_scraper_dependencies["box_score_parser"]
    mock_live_parser = mock_scraper_dependencies["live_parser"]

    game_to_process = [
        {
            "home_team": settings.get_target_teams_as_list()[0],
            "away_team": "敵隊",
            "cpbl_game_id": "TEST01",
            "game_date": "2025-08-01",
            "box_score_url": "http://fake.url",
        }
    ]
    mock_games.create_game_and_get_id.return_value = 1
    mock_box_score_parser.parse_box_score_page.return_value = [
        {"summary": {"player_name": "王柏融"}, "at_bats_list": ["一安"]}
    ]
    mock_live_parser.parse_active_inning_details.return_value = []

    scraper._process_filtered_games(
        game_to_process, target_teams=settings.get_target_teams_as_list()
    )

    # 驗證冪等性操作
    session_instance_mock = mock_session_class.return_value
    # 【修正】使用 ANY 來比對被 mock 的 date 物件
    mock_games.delete_game_if_exists.assert_called_once_with(
        session_instance_mock, "TEST01", ANY
    )
    mock_games.create_game_and_get_id.assert_called_once_with(
        session_instance_mock, game_to_process[0]
    )

    # 驗證後續流程
    mock_box_score_parser.parse_box_score_page.assert_called_once_with(
        "<html></html>", target_teams=settings.get_target_teams_as_list()
    )
    session_instance_mock.commit.assert_called_once()
    session_instance_mock.rollback.assert_not_called()


def test_process_filtered_games_rolls_back_and_reraises_on_error(
    mock_scraper_dependencies, mock_playwright_page
):
    """【修正】測試 _process_filtered_games 在發生錯誤時會復原交易並重新拋出異常。"""
    mock_session_class = mock_scraper_dependencies["session"]
    mock_players = mock_scraper_dependencies["players"]
    mock_games = mock_scraper_dependencies["games"]
    mock_box_score_parser = mock_scraper_dependencies["box_score_parser"]

    mock_players.store_player_game_data.side_effect = ValueError("Invalid Data")
    mock_box_score_parser.parse_box_score_page.return_value = [
        {"summary": {"player_name": "王柏融"}, "at_bats_list": ["一安"]}
    ]

    game_to_process = [
        {
            "home_team": settings.get_target_teams_as_list()[0],
            "away_team": "敵隊",
            "cpbl_game_id": "TEST01",
            "game_date": "2025-08-01",
            "box_score_url": "http://fake.url",
        }
    ]
    mock_games.create_game_and_get_id.return_value = 1

    with pytest.raises(ValueError, match="Invalid Data"):
        scraper._process_filtered_games(
            game_to_process, target_teams=settings.get_target_teams_as_list()
        )

    session_instance_mock = mock_session_class.return_value
    session_instance_mock.commit.assert_not_called()
    session_instance_mock.rollback.assert_called_once()


def test_process_filtered_games_no_target_teams(
    mock_scraper_dependencies, mock_playwright_page
):
    """【修正】測試 _process_filtered_games 在 target_teams=None 時，會處理所有球隊。"""
    mock_box_score_parser = mock_scraper_dependencies["box_score_parser"]
    mock_games = mock_scraper_dependencies["games"]

    game_to_process = [
        {
            "home_team": "任何主隊",
            "away_team": "任何客隊",
            "cpbl_game_id": "TEST02",
            "game_date": "2025-08-01",
            "box_score_url": "http://fake.url",
        }
    ]
    mock_games.create_game_and_get_id.return_value = 1
    mock_box_score_parser.parse_box_score_page.return_value = []

    scraper._process_filtered_games(game_to_process, target_teams=None)

    # 【修正】使用 ANY 來比對被 mock 的 date 物件
    mock_games.delete_game_if_exists.assert_called_once_with(ANY, "TEST02", ANY)
    mock_games.create_game_and_get_id.assert_called_once()
    mock_box_score_parser.parse_box_score_page.assert_called_once_with(
        "<html></html>", target_teams=None
    )


# --- 測試 scrape_entire_year ---


def test_scrape_entire_year_skips_month_on_scraper_error(mock_scraper_dependencies):
    """測試 scrape_entire_year 在遇到 ScraperError 時會跳過該月份並繼續。"""
    mock_fetcher = mock_scraper_dependencies["fetcher"]
    mock_logger = mock_scraper_dependencies["logger"]
    mock_datetime = mock_scraper_dependencies["datetime"]
    mock_process_games = patch("app.scraper._process_filtered_games").start()

    mock_datetime.date.today.return_value = MagicMock(year=2025, month=5)
    mock_fetcher.fetch_schedule_page.side_effect = [
        "<html>March</html>",
        ScraperError("April schedule not found"),
        "<html>May</html>",
    ]

    scraper.scrape_entire_year(year_str="2025")

    assert mock_fetcher.fetch_schedule_page.call_count == 3
    mock_fetcher.fetch_schedule_page.assert_has_calls(
        [call(2025, 3), call(2025, 4), call(2025, 5)]
    )

    mock_logger.error.assert_called_once()
    assert "處理月份 2025-04 時發生爬蟲錯誤" in mock_logger.error.call_args[0][0]

    assert mock_process_games.call_count == 2
    patch.stopall()


# --- 測試 scrape_single_day ---


def test_scrape_single_day_flow(mock_scraper_dependencies):
    """【修改】測試 scrape_single_day 是否使用傳入的參數正確呼叫 _process_filtered_games。"""
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

    # 驗證傳入的 target_teams 是解析後的 Python list
    mock_process_games.assert_called_once_with(
        games_for_the_day, target_teams=settings.get_target_teams_as_list()
    )
    patch.stopall()
