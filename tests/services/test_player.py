# tests/services/test_player.py

from sqlalchemy.orm import Session
from app.services import player as player_service
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

# --- 測試用的模擬資料 ---

MOCK_PLAYER_NAME = "測試球員"
MOCK_PLAYER_URL = "http://fake.url/player"
MOCK_HTML_CONTENT = "<html><body>Mock HTML</body></html>"
MOCK_PARSED_STATS = {
    "debut_date": "2020-01-01",
    "games_played": 100,
    "homeruns": 10,
}

# --- 測試案例 ---


def test_scrape_and_store_player_career_stats_success(mocker):
    """
    [修改] 測試成功抓取、解析並儲存的完整流程 (使用 Page 物件)。
    """
    # 1. Arrange (設定 Mocks)
    # [修改] 模擬 Playwright Page 物件及其方法
    mock_page = mocker.MagicMock(spec=Page)
    mock_page.content.return_value = MOCK_HTML_CONTENT

    mock_parser = mocker.patch(
        "app.parsers.player_career.parse_player_career_page",
        return_value=MOCK_PARSED_STATS,
    )
    mock_crud = mocker.patch("app.crud.players.create_or_update_player_career_stats")

    # 模擬資料庫 session
    mock_session = mocker.MagicMock(spec=Session)
    mocker.patch("app.services.player.SessionLocal", return_value=mock_session)

    # 2. Act (執行函式)
    player_service.scrape_and_store_player_career_stats(
        page=mock_page, player_name=MOCK_PLAYER_NAME, player_url=MOCK_PLAYER_URL
    )

    # 3. Assert (驗證結果)
    # [修改] 驗證 Page 物件的方法被正確呼叫
    mock_page.goto.assert_called_once_with(MOCK_PLAYER_URL, wait_until="networkidle")
    mock_page.wait_for_selector.assert_called_once_with(
        "div.RecordTableWrap", timeout=15000
    )
    mock_parser.assert_called_once_with(MOCK_HTML_CONTENT)

    # 驗證傳遞給 CRUD 的資料是正確的
    expected_stats_to_store = MOCK_PARSED_STATS.copy()
    expected_stats_to_store["player_name"] = MOCK_PLAYER_NAME
    mock_crud.assert_called_once_with(mock_session, expected_stats_to_store)

    # 驗證資料庫交易
    mock_session.commit.assert_called_once()
    mock_session.rollback.assert_not_called()
    mock_session.close.assert_called_once()


def test_scrape_and_store_player_career_stats_no_url(mocker):
    """
    測試當 player_url 為 None 或空時，函式應直接返回且不執行任何操作。
    """
    # [修改] 移除 fetcher mock，建立 mock_page
    mock_page = mocker.MagicMock(spec=Page)
    mock_parser = mocker.patch("app.parsers.player_career.parse_player_career_page")
    mock_crud = mocker.patch("app.crud.players.create_or_update_player_career_stats")

    player_service.scrape_and_store_player_career_stats(
        page=mock_page, player_name=MOCK_PLAYER_NAME, player_url=None
    )

    # [修改] 驗證 page 物件的方法未被呼叫
    mock_page.goto.assert_not_called()
    mock_parser.assert_not_called()
    mock_crud.assert_not_called()


def test_scrape_and_store_player_career_stats_parser_fails(mocker):
    """
    測試當解析器回傳 None (解析失敗) 時，不應呼叫 CRUD 函式。
    """
    # [修改] 移除 fetcher mock，改用 page mock
    mock_page = mocker.MagicMock(spec=Page)
    mock_page.content.return_value = MOCK_HTML_CONTENT

    # 模擬解析失敗
    mock_parser = mocker.patch(
        "app.parsers.player_career.parse_player_career_page", return_value=None
    )
    mock_crud = mocker.patch("app.crud.players.create_or_update_player_career_stats")
    mock_session_local = mocker.patch("app.services.player.SessionLocal")

    player_service.scrape_and_store_player_career_stats(
        page=mock_page, player_name=MOCK_PLAYER_NAME, player_url=MOCK_PLAYER_URL
    )

    mock_page.goto.assert_called_once()
    mock_parser.assert_called_once()
    # 核心驗證：CRUD 和資料庫 session 都不應該被觸發
    mock_crud.assert_not_called()
    mock_session_local.assert_not_called()


def test_scrape_and_store_player_career_stats_db_error(mocker):
    """
    測試當資料庫操作 (CRUD) 拋出例外時，應呼叫 session.rollback()。
    """
    # [修改] 移除 fetcher mock，改用 page mock
    mock_page = mocker.MagicMock(spec=Page)
    mock_page.content.return_value = MOCK_HTML_CONTENT

    mock_parser = mocker.patch(  # noqa: F841
        "app.parsers.player_career.parse_player_career_page",
        return_value=MOCK_PARSED_STATS,
    )
    # 模擬資料庫寫入失敗
    mock_crud = mocker.patch(
        "app.crud.players.create_or_update_player_career_stats",
        side_effect=Exception("DB Error"),
    )

    mock_session = mocker.MagicMock(spec=Session)
    mocker.patch("app.services.player.SessionLocal", return_value=mock_session)

    # 執行函式
    player_service.scrape_and_store_player_career_stats(
        page=mock_page, player_name=MOCK_PLAYER_NAME, player_url=MOCK_PLAYER_URL
    )

    # 驗證資料庫交易
    mock_crud.assert_called_once()
    mock_session.commit.assert_not_called()
    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()


def test_scrape_and_store_player_career_stats_playwright_timeout(mocker):
    """
    [新增] 測試當 Playwright 頁面載入超時，函式應正確處理錯誤。
    """
    # 1. Arrange
    mock_page = mocker.MagicMock(spec=Page)
    mock_page.wait_for_selector.side_effect = PlaywrightTimeoutError("Timeout")

    mock_parser = mocker.patch("app.parsers.player_career.parse_player_career_page")
    mock_crud = mocker.patch("app.crud.players.create_or_update_player_career_stats")
    mock_session_local = mocker.patch("app.services.player.SessionLocal")

    # 2. Act
    player_service.scrape_and_store_player_career_stats(
        page=mock_page, player_name=MOCK_PLAYER_NAME, player_url=MOCK_PLAYER_URL
    )

    # 3. Assert
    mock_page.goto.assert_called_once()
    mock_page.wait_for_selector.assert_called_once()
    mock_parser.assert_not_called()
    mock_crud.assert_not_called()
    mock_session_local.assert_not_called()
