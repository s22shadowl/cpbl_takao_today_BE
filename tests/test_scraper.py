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
    mocker.patch("app.scraper.sync_playwright")

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
    # 【修改】斷言新的函式被呼叫
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

    call_args, _ = mock_process_games.call_args
    processed_games_list = call_args[0]

    assert len(processed_games_list) == 2
    assert processed_games_list[0]["cpbl_game_id"] == "G2"
    assert processed_games_list[1]["cpbl_game_id"] == "G3"

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
    """測試 _process_filtered_games 在成功時會提交交易。"""
    mock_session = mock_scraper_dependencies["session"]
    mock_db_actions = mock_scraper_dependencies["db_actions"]
    mock_fetcher = mock_scraper_dependencies["fetcher"]
    mock_parser = mock_scraper_dependencies["parser"]

    game_to_process = [
        {
            "status": "已完成",
            "home_team": settings.TARGET_TEAM_NAME,
            "away_team": "敵隊",
            "cpbl_game_id": "TEST01",
            "box_score_url": "http://fake.url",
        }
    ]
    mock_db_actions.store_game_and_get_id.return_value = 1
    mock_fetcher.get_dynamic_page_content.return_value = "<html></html>"
    mock_parser.parse_box_score_page.return_value = [
        {"summary": {"player_name": "王柏融"}, "at_bats_list": ["一安"]}
    ]
    mock_parser.parse_active_inning_details.return_value = []

    scraper._process_filtered_games(game_to_process)

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
            "home_team": settings.TARGET_TEAM_NAME,
            "away_team": "敵隊",
            "cpbl_game_id": "TEST01",
            "box_score_url": "http://fake.url",
        }
    ]
    mock_db_actions.store_game_and_get_id.return_value = 1

    scraper._process_filtered_games(game_to_process)

    mock_session.commit.assert_not_called()
    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()
