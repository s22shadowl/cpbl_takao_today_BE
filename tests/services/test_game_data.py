# tests/services/test_game_data.py

from unittest.mock import patch, MagicMock, call, ANY
import pytest
from sqlalchemy.exc import SQLAlchemyError
import datetime

from app.config import settings
from app.exceptions import ScraperError
from app.services import game_data

# --- 測試用的模擬資料 ---

# 假設從 season_stats.parse_season_stats_page 解析器回傳的資料
MOCK_PARSED_PLAYERS = [
    {"player_name": "王柏融", "player_url": "http://example.com/wang"},
    {"player_name": "魔鷹", "player_url": "http://example.com/moya"},
    {"player_name": "吳念庭", "player_url": "http://example.com/wu"},
    {"player_name": "宋家豪", "player_url": "http://example.com/sung"},
    {"player_name": "路人甲", "player_url": "http://example.com/a"},
    {"player_name": "路人乙", "player_url": "http://example.com/b"},
]

# 假設 settings.TARGET_PLAYER_NAMES 的內容
TARGET_PLAYERS_IN_SETTINGS = ["王柏融", "魔鷹", "吳念庭"]


# --- Fixtures ---


@pytest.fixture
def mock_playwright_page(monkeypatch):
    """
    完整模擬 Playwright 的啟動過程，並回傳一個可控的假 page 物件。
    """
    # 最內層的事件容器
    mock_event_container = MagicMock()
    mock_event_container.count.return_value = 1  # 模擬找到 1 個事件容器
    mock_event_container.nth.return_value = (
        MagicMock()
    )  # .nth() 回傳一個可點擊的 mock 物件

    # 半局 section
    mock_half_inning_section = MagicMock()
    mock_half_inning_section.count.return_value = 1  # 模擬找到了 top/bot section
    mock_half_inning_section.locator.return_value = (
        mock_event_container  # 當它被 .locator() 時，回傳事件容器
    )

    # active tab 的內容
    mock_active_content = MagicMock()
    mock_active_content.inner_html.return_value = "<div>Mock Inning HTML</div>"
    mock_active_content.locator.return_value = (
        mock_half_inning_section  # 當它被 .locator() 時，回傳半局 section
    )

    # 局數按鈕
    mock_inning_button = MagicMock()
    mock_inning_buttons_locator = MagicMock()
    mock_inning_buttons_locator.all.return_value = [mock_inning_button]

    # page 物件本身
    mock_page = MagicMock()

    # 定義 side_effect 函式，根據選擇器回傳不同 mock 物件
    def locator_side_effect(selector):
        if "div.tabs > ul > li" in selector:
            return mock_inning_buttons_locator
        if "div.tab_cont.active" in selector:
            return mock_active_content
        return MagicMock()

    mock_page.locator.side_effect = locator_side_effect

    # 模擬 Playwright 的啟動過程
    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page
    mock_chromium = MagicMock()
    mock_chromium.launch.return_value = mock_browser
    mock_playwright = MagicMock()
    mock_playwright.chromium = mock_chromium
    mock_sync_playwright = MagicMock()
    mock_sync_playwright.__enter__.return_value = mock_playwright
    monkeypatch.setattr("app.browser.sync_playwright", lambda: mock_sync_playwright)

    return mock_page


@pytest.fixture
def mock_scraper_dependencies(monkeypatch):
    """
    為 scraper 中的函式模擬所有外部依賴。
    """
    test_settings = settings.model_copy()
    monkeypatch.setattr("app.services.game_data.settings", test_settings)

    mock_datetime = patch("app.services.game_data.datetime").start()
    mock_datetime.datetime.strptime.side_effect = datetime.datetime.strptime
    mock_datetime.date.today.return_value = datetime.date(2025, 8, 11)

    # 統一 mock fetcher.get_dynamic_page_content
    mock_fetcher = patch("app.services.game_data.fetcher").start()
    mock_fetcher.get_dynamic_page_content.return_value = "<html>Mock Page</html>"

    mocks = {
        "fetcher": mock_fetcher,
        "schedule_parser": patch("app.services.game_data.schedule").start(),
        "box_score_parser": patch("app.services.game_data.box_score").start(),
        "live_parser": patch("app.services.game_data.live").start(),
        "season_stats_parser": patch("app.services.game_data.season_stats").start(),
        "players_crud": patch("app.services.game_data.players").start(),
        "games_crud": patch("app.services.game_data.games").start(),
        "session": patch("app.services.game_data.SessionLocal").start(),
        "logger": patch("app.services.game_data.logger").start(),
        "time": patch("app.services.game_data.time").start(),
        "update_outs": patch("app.services.game_data._update_outs_count").start(),
        "update_runners": patch("app.services.game_data._update_runners_state").start(),
        "datetime": mock_datetime,
        "expect": patch("app.services.game_data.expect").start(),
    }
    yield mocks
    patch.stopall()


# --- 測試 scrape_and_store_season_stats ---


def test_scrape_and_store_season_stats_default_behavior(
    mock_scraper_dependencies, monkeypatch
):
    """
    測試預設行為 (update_career_stats_for_all=False)，
    應只為 settings.TARGET_PLAYER_NAMES 中的球員更新生涯數據。
    """
    # 1. 設定 Mocks
    monkeypatch.setattr(
        "app.config.settings.TARGET_PLAYER_NAMES", TARGET_PLAYERS_IN_SETTINGS
    )
    mock_parser = mock_scraper_dependencies["season_stats_parser"]
    mock_parser.parse_season_stats_page.return_value = MOCK_PARSED_PLAYERS

    with patch(
        "app.services.player.scrape_and_store_player_career_stats"
    ) as mock_scrape_career:
        # 2. 執行函式 (使用預設參數)
        game_data.scrape_and_store_season_stats()

        # 3. 驗證結果
        assert mock_scrape_career.call_count == len(TARGET_PLAYERS_IN_SETTINGS)
        mock_scrape_career.assert_any_call(
            player_name="王柏融", player_url="http://example.com/wang"
        )
        mock_scrape_career.assert_any_call(
            player_name="魔鷹", player_url="http://example.com/moya"
        )
        mock_scrape_career.assert_any_call(
            player_name="吳念庭", player_url="http://example.com/wu"
        )


def test_scrape_and_store_season_stats_update_all(mock_scraper_dependencies):
    """
    測試當 update_career_stats_for_all=True 時，
    應為所有從頁面解析出的球員更新生涯數據。
    """
    # 1. 設定 Mocks
    mock_parser = mock_scraper_dependencies["season_stats_parser"]
    mock_parser.parse_season_stats_page.return_value = MOCK_PARSED_PLAYERS

    with patch(
        "app.services.player.scrape_and_store_player_career_stats"
    ) as mock_scrape_career:
        # 2. 執行函式 (明確傳入 True)
        game_data.scrape_and_store_season_stats(update_career_stats_for_all=True)

        # 3. 驗證結果
        assert mock_scrape_career.call_count == len(MOCK_PARSED_PLAYERS)
        mock_scrape_career.assert_any_call(
            player_name="路人甲", player_url="http://example.com/a"
        )


def test_scrape_season_stats_propagates_db_error(mock_scraper_dependencies):
    """測試當資料庫操作拋出錯誤時，會正確關閉 session 且不 commit。"""
    mock_parser = mock_scraper_dependencies["season_stats_parser"]
    mock_players_crud = mock_scraper_dependencies["players_crud"]
    mock_session_instance = mock_scraper_dependencies["session"].return_value

    mock_parser.parse_season_stats_page.return_value = [{"player_name": "Player A"}]
    mock_players_crud.store_player_season_stats_and_history.side_effect = (
        SQLAlchemyError("DB Error")
    )

    # 驗證 SQLAlchemyError 是否被正確拋出
    with pytest.raises(SQLAlchemyError, match="DB Error"):
        game_data.scrape_and_store_season_stats()

    # 驗證資料庫操作
    mock_session_instance.commit.assert_not_called()
    mock_session_instance.rollback.assert_called_once()
    mock_session_instance.close.assert_called_once()


# --- 測試 _process_filtered_games ---


def test_process_filtered_games_happy_path_full_flow(
    mock_scraper_dependencies, mock_playwright_page
):
    """擴寫：測試 _process_filtered_games 的完整成功路徑，並專注於驗證合併邏輯。"""
    mock_session = mock_scraper_dependencies["session"].return_value
    mock_games_crud = mock_scraper_dependencies["games_crud"]
    mock_players_crud = mock_scraper_dependencies["players_crud"]
    mock_box_score_parser = mock_scraper_dependencies["box_score_parser"]
    mock_live_parser = mock_scraper_dependencies["live_parser"]
    mock_update_outs = mock_scraper_dependencies["update_outs"]
    mock_update_runners = mock_scraper_dependencies["update_runners"]

    game_to_process = [
        {
            "home_team": settings.TARGET_TEAM_NAME,
            "away_team": "中信兄弟",
            "cpbl_game_id": "TEST01",
            "game_date": "2025-08-11",
            "box_score_url": "http://fake.url/box?game_id=TEST01",
        }
    ]
    mock_games_crud.create_game_and_get_id.return_value = 1

    # [修正] 將 mock data 改回 game_data.py 預期的 at_bats_list 結構
    mock_box_score_parser.parse_box_score_page.return_value = [
        {
            "summary": {
                "player_name": "王柏融",
                "team_name": settings.TARGET_TEAM_NAME,
            },
            "at_bats_list": ["一安"],
            "at_bats_details": [],  # 原始 scraper 會清空並重建此列表
        }
    ]

    mock_live_parser.parse_active_inning_details.return_value = [
        {
            "inning": 1,
            "hitter_name": "王柏融",
            "description": "擊出一壘安打，帶有一分打點",
            "rbi": 1,
        }
    ]
    mock_update_outs.return_value = 0
    mock_update_runners.return_value = ["王柏融", None, None]

    game_data._process_filtered_games(
        game_to_process, target_teams=[settings.TARGET_TEAM_NAME]
    )

    mock_games_crud.delete_game_if_exists.assert_called_once()
    mock_games_crud.create_game_and_get_id.assert_called_once()

    mock_playwright_page.goto.assert_has_calls(
        [
            call("http://fake.url/box?game_id=TEST01", timeout=ANY),
            call(
                "http://fake.url/box/live?game_id=TEST01",
                wait_until="load",
                timeout=ANY,
            ),
        ]
    )

    mock_players_crud.store_player_game_data.assert_called_once()

    final_data_call = mock_players_crud.store_player_game_data.call_args
    # call_args.args[2] 是傳給 store_player_game_data 的第三個位置參數 (all_players_data)
    final_players_data_list = final_data_call.args[2]
    final_player_data = final_players_data_list[0]

    assert len(final_player_data["at_bats_details"]) == 1
    first_at_bat = final_player_data["at_bats_details"][0]

    assert first_at_bat["result_short"] == "一安"
    assert first_at_bat["sequence_in_game"] == 1
    assert first_at_bat["inning"] == 1
    assert "擊出一壘安打" in first_at_bat["description"]
    assert first_at_bat["rbi"] == 1
    assert "outs_before" in first_at_bat
    assert "runners_on_base_before" in first_at_bat

    mock_session.commit.assert_called_once()


def test_process_filtered_games_rolls_back_on_error(
    mock_scraper_dependencies, mock_playwright_page
):
    """測試 _process_filtered_games 在發生錯誤時會復原交易並重新拋出異常。"""
    mock_session = mock_scraper_dependencies["session"].return_value
    mock_players_crud = mock_scraper_dependencies["players_crud"]
    mock_box_score_parser = mock_scraper_dependencies["box_score_parser"]
    mock_games_crud = mock_scraper_dependencies["games_crud"]

    # 模擬儲存資料時發生錯誤
    mock_players_crud.store_player_game_data.side_effect = ValueError("Invalid Data")

    # [修正] 將 mock data 改回 game_data.py 預期的 at_bats_list 結構
    mock_box_score_parser.parse_box_score_page.return_value = [
        {
            "summary": {"player_name": "王柏融"},
            "at_bats_list": ["滾地"],
            "at_bats_details": [],
        }
    ]
    mock_games_crud.create_game_and_get_id.return_value = 1

    game_to_process = [
        {
            "home_team": settings.TARGET_TEAM_NAME,
            "box_score_url": "http://fake.url",
            "game_date": "2025-08-11",
            "cpbl_game_id": "ERR01",
        }
    ]

    with pytest.raises(ValueError, match="Invalid Data"):
        game_data._process_filtered_games(
            game_to_process, target_teams=[settings.TARGET_TEAM_NAME]
        )

    mock_session.commit.assert_not_called()
    mock_session.rollback.assert_called_once()


def test_process_filtered_games_e2e_mode(mock_scraper_dependencies, monkeypatch):
    """新增：測試當 E2E_TEST_MODE 為 True 時，是否跳過爬蟲直接寫入假資料。"""
    monkeypatch.setattr(game_data.settings, "E2E_TEST_MODE", True)
    mock_session = mock_scraper_dependencies["session"].return_value
    mock_games_crud = mock_scraper_dependencies["games_crud"]
    mock_players_crud = mock_scraper_dependencies["players_crud"]

    with patch("app.browser.sync_playwright") as mock_playwright_context:
        game_to_process = [
            {
                "home_team": settings.TARGET_TEAM_NAME,
                "game_date": "2025-08-11",
                "cpbl_game_id": "E2E01",
            }
        ]
        mock_games_crud.create_game_and_get_id.return_value = 99

        game_data._process_filtered_games(game_to_process)

        mock_playwright_context.assert_not_called()
        mock_players_crud.store_player_game_data.assert_called_once_with(
            mock_session, 99, ANY
        )
        mock_session.commit.assert_called_once()


# --- 測試 scrape_entire_year ---


def test_scrape_entire_year_skips_month_on_scraper_error(
    mock_scraper_dependencies, monkeypatch
):
    """測試 scrape_entire_year 在遇到 ScraperError 時會跳過該月份並繼續。"""
    mock_fetcher = mock_scraper_dependencies["fetcher"]
    mock_logger = mock_scraper_dependencies["logger"]
    mock_schedule_parser = mock_scraper_dependencies["schedule_parser"]
    mock_datetime = mock_scraper_dependencies["datetime"]

    with patch("app.services.game_data._process_filtered_games") as mock_process_games:
        mock_fetcher.fetch_schedule_page.side_effect = [
            "<html>March</html>",
            ScraperError("April schedule not found"),
            "<html>May</html>",
        ]
        mock_schedule_parser.parse_schedule_page.side_effect = [
            [{"game_date": "2025-03-15"}],
            [],
            [{"game_date": "2025-05-10"}],
        ]

        mock_datetime.date.today.return_value = datetime.date(2025, 5, 20)

        monkeypatch.setattr(settings, "CPBL_SEASON_START_MONTH", 3)
        monkeypatch.setattr(settings, "CPBL_SEASON_END_MONTH", 11)

        game_data.scrape_entire_year(year_str="2025")

        assert mock_fetcher.fetch_schedule_page.call_count == 3
        mock_logger.error.assert_called_once_with(
            "處理月份 2025-04 時發生爬蟲錯誤，已跳過此月份。", exc_info=True
        )
        assert mock_process_games.call_count == 2


# --- 測試 scrape_single_day ---


def test_scrape_single_day_flow(mock_scraper_dependencies):
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
