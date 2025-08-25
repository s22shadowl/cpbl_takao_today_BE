# tests/services/test_game_data.py

from unittest.mock import patch
import pytest
import datetime

from app.config import settings
from app.services import game_data
from app.exceptions import ScraperError

# --- 測試用的模擬資料 ---

MOCK_PARSED_PLAYERS = [
    {"player_name": "王柏融", "player_url": "http://example.com/wang"},
    {"player_name": "魔鷹", "player_url": "http://example.com/moya"},
    {"player_name": "吳念庭", "player_url": "http://example.com/wu"},
]

# --- Fixtures ---


@pytest.fixture
def mock_orchestration_dependencies(monkeypatch):
    """為 _process_filtered_games 模擬所有重構後的新服務依賴。"""
    mock_browser_operator_class = patch(
        "app.services.game_data.BrowserOperator"
    ).start()
    mock_game_state_machine_class = patch(
        "app.services.game_data.GameStateMachine"
    ).start()
    mock_data_persistence = patch("app.services.game_data.data_persistence").start()
    mock_box_score_parser = patch("app.services.game_data.box_score").start()
    mock_live_parser = patch("app.services.game_data.live").start()
    mock_session = patch("app.services.game_data.SessionLocal").start()
    patch("app.services.game_data.get_page").start()
    patch("app.utils.parsing_helpers.is_formal_pa", return_value=True).start()
    patch("app.utils.parsing_helpers.map_result_short_to_type").start()

    mocks = {
        "BrowserOperator": mock_browser_operator_class,
        "GameStateMachine": mock_game_state_machine_class,
        "data_persistence": mock_data_persistence,
        "box_score_parser": mock_box_score_parser,
        "live_parser": mock_live_parser,
        "session": mock_session,
    }
    yield mocks
    patch.stopall()


@pytest.fixture
def mock_high_level_dependencies(monkeypatch):
    """為高層級的協調函式 (如 scrape_entire_year) 模擬依賴。"""
    mock_fetcher = patch("app.services.game_data.fetcher").start()
    mock_schedule_parser = patch("app.services.game_data.schedule").start()
    mock_season_stats_parser = patch("app.services.game_data.season_stats").start()
    # [修正] 將 mock 路徑指向 app.services.game_data 內部使用的 crud 模組
    patch("app.services.game_data.data_persistence.players").start()
    mock_player_service = patch("app.services.game_data.player_service").start()
    mock_session = patch("app.services.game_data.SessionLocal").start()
    mock_logger = patch("app.services.game_data.logger").start()
    mock_time = patch("app.services.game_data.time").start()
    mock_datetime = patch("app.services.game_data.datetime").start()
    mock_datetime.datetime.strptime.side_effect = datetime.datetime.strptime
    mock_datetime.date.today.return_value = datetime.date(2025, 8, 11)

    mocks = {
        "fetcher": mock_fetcher,
        "schedule_parser": mock_schedule_parser,
        "season_stats_parser": mock_season_stats_parser,
        "player_service": mock_player_service,
        "session": mock_session,
        "logger": mock_logger,
        "time": mock_time,
        "datetime": mock_datetime,
    }
    yield mocks
    patch.stopall()


# --- 測試 scrape_and_store_season_stats ---


def test_scrape_and_store_season_stats_default_behavior(
    mock_high_level_dependencies, monkeypatch
):
    """測試 scrape_and_store_season_stats 在預設模式下只更新目標球員。"""
    monkeypatch.setattr("app.config.settings.TARGET_PLAYER_NAMES", ["王柏融", "魔鷹"])
    mock_parser = mock_high_level_dependencies["season_stats_parser"]
    mock_parser.parse_season_stats_page.return_value = MOCK_PARSED_PLAYERS
    mock_player_service = mock_high_level_dependencies["player_service"]

    # [修正] 由於 crud.players 已被 mock，這裡需要 mock 其底下的函式
    with patch("app.crud.players.store_player_season_stats_and_history"):
        game_data.scrape_and_store_season_stats()

    assert mock_player_service.scrape_and_store_player_career_stats.call_count == 2
    mock_player_service.scrape_and_store_player_career_stats.assert_any_call(
        player_name="王柏融", player_url="http://example.com/wang"
    )
    mock_player_service.scrape_and_store_player_career_stats.assert_any_call(
        player_name="魔鷹", player_url="http://example.com/moya"
    )


def test_scrape_and_store_season_stats_update_all(mock_high_level_dependencies):
    """測試 scrape_and_store_season_stats 在 update_career_stats_for_all=True 時更新所有球員。"""
    mock_parser = mock_high_level_dependencies["season_stats_parser"]
    mock_parser.parse_season_stats_page.return_value = MOCK_PARSED_PLAYERS
    mock_player_service = mock_high_level_dependencies["player_service"]

    with patch("app.crud.players.store_player_season_stats_and_history"):
        game_data.scrape_and_store_season_stats(update_career_stats_for_all=True)

    assert mock_player_service.scrape_and_store_player_career_stats.call_count == len(
        MOCK_PARSED_PLAYERS
    )
    mock_player_service.scrape_and_store_player_career_stats.assert_any_call(
        player_name="吳念庭", player_url="http://example.com/wu"
    )


# --- 測試 _process_filtered_games (重構後) ---


def test_process_filtered_games_orchestration(mock_orchestration_dependencies):
    """測試 _process_filtered_games 作為協調者的主要成功路徑。"""
    mock_dp = mock_orchestration_dependencies["data_persistence"]
    mock_browser_op_instance = mock_orchestration_dependencies[
        "BrowserOperator"
    ].return_value
    mock_state_machine_instance = mock_orchestration_dependencies[
        "GameStateMachine"
    ].return_value
    mock_box_parser = mock_orchestration_dependencies["box_score_parser"]
    mock_session_instance = mock_orchestration_dependencies["session"].return_value

    game_to_process = [
        {
            "home_team": "Team A",
            "away_team": "Team B",
            "cpbl_game_id": "G01",
            "game_date": "2025-08-12",
            "box_score_url": "http://fake.url/box",
        }
    ]
    mock_dp.prepare_game_storage.return_value = 123
    mock_browser_op_instance.navigate_and_get_box_score_content.return_value = (
        "<html>box</html>"
    )
    mock_box_parser.parse_box_score_page.return_value = [
        {"summary": {"player_name": "P1"}, "at_bats_list": ["安打"]}
    ]
    mock_browser_op_instance.extract_live_events_html.return_value = [
        ("<html>live</html>", 1, "section.top")
    ]
    mock_state_machine_instance.enrich_events_with_state.return_value = [
        {"hitter_name": "P1", "result_short": "安打"}
    ]

    game_data._process_filtered_games(game_to_process, target_teams=["Team A"])

    mock_dp.prepare_game_storage.assert_called_once()
    mock_browser_op_instance.navigate_and_get_box_score_content.assert_called_once()
    mock_browser_op_instance.extract_live_events_html.assert_called_once()
    mock_orchestration_dependencies["GameStateMachine"].assert_called_once()
    mock_state_machine_instance.enrich_events_with_state.assert_called_once()
    mock_dp.commit_player_game_data.assert_called_once()
    mock_session_instance.commit.assert_called_once()
    mock_session_instance.rollback.assert_not_called()


def test_process_filtered_games_rolls_back_on_error(mock_orchestration_dependencies):
    """測試當任何子服務拋出異常時，主流程會執行資料庫復原。"""
    mock_dp = mock_orchestration_dependencies["data_persistence"]
    mock_session_instance = mock_orchestration_dependencies["session"].return_value
    mock_dp.commit_player_game_data.side_effect = ValueError("DB Error")

    game_to_process = [
        {
            "home_team": "Team A",
            "away_team": "Team B",
            "cpbl_game_id": "G01",
            "game_date": "2025-08-12",
            "box_score_url": "http://fake.url/box",
        }
    ]

    with pytest.raises(ValueError, match="DB Error"):
        game_data._process_filtered_games(game_to_process, target_teams=["Team A"])

    mock_session_instance.commit.assert_not_called()
    mock_session_instance.rollback.assert_called_once()


# --- 測試高層級協調函式 ---


def test_scrape_entire_year_skips_month_on_scraper_error(
    mock_high_level_dependencies, monkeypatch
):
    """測試 scrape_entire_year 在遇到 ScraperError 時會跳過該月份並繼續。"""
    mock_fetcher = mock_high_level_dependencies["fetcher"]
    mock_logger = mock_high_level_dependencies["logger"]
    mock_schedule_parser = mock_high_level_dependencies["schedule_parser"]
    mock_datetime = mock_high_level_dependencies["datetime"]

    with patch("app.services.game_data._process_filtered_games") as mock_process_games:
        mock_fetcher.fetch_schedule_page.side_effect = [
            "<html>March</html>",
            ScraperError("April schedule not found"),
            "<html>May</html>",
        ]
        mock_schedule_parser.parse_schedule_page.side_effect = [
            [{"game_date": "2025-03-15"}],
            [{"game_date": "2025-05-10"}],
        ]
        mock_datetime.date.today.return_value = datetime.date(2025, 5, 20)
        monkeypatch.setattr(settings, "CPBL_SEASON_START_MONTH", 3)
        monkeypatch.setattr(settings, "CPBL_SEASON_END_MONTH", 5)

        game_data.scrape_entire_year(year_str="2025")

        assert mock_fetcher.fetch_schedule_page.call_count == 3
        mock_logger.error.assert_called_once_with(
            "處理月份 2025-04 時發生爬蟲錯誤，已跳過此月份。", exc_info=True
        )
        assert mock_process_games.call_count == 2


def test_scrape_single_day_flow(mock_high_level_dependencies):
    """測試 scrape_single_day 是否使用傳入的參數正確呼叫 _process_filtered_games。"""
    with (
        patch("app.services.game_data._process_filtered_games") as mock_process_games,
        patch(
            "app.services.game_data.scrape_and_store_season_stats"
        ) as mock_scrape_season_stats,
    ):
        target_date = "2025-06-25"
        games_for_the_day = [{"game_date": target_date, "cpbl_game_id": "G2"}]

        game_data.scrape_single_day(
            specific_date=target_date,
            games_for_day=games_for_the_day,
            update_season_stats=False,
        )

        mock_scrape_season_stats.assert_not_called()
        mock_process_games.assert_called_once_with(
            games_for_the_day, target_teams=settings.get_target_teams_as_list()
        )
