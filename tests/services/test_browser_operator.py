# tests/services/test_browser_operator.py

from unittest.mock import MagicMock, patch, ANY
import pytest

from app.services.browser_operator import BrowserOperator


@pytest.fixture(autouse=True)
def mock_browser_operator_dependencies(monkeypatch):
    """
    自動為此模組中的所有測試模擬外部依賴。
    - 模擬 `expect` 以避免對 mock 物件執行真實的 Playwright 斷言。
    - 模擬 `settings` 以隔離測試環境。
    """
    patch("app.services.browser_operator.expect").start()
    monkeypatch.setattr("app.services.browser_operator.settings", MagicMock())
    yield
    patch.stopall()


@pytest.fixture
def mock_page():
    """提供一個通用的 Playwright Page mock 物件。"""
    return MagicMock()


def test_navigate_and_get_box_score_content(mock_page):
    """測試導航至 Box Score 頁面並取得內容的流程。"""
    operator = BrowserOperator(mock_page)
    mock_page.content.return_value = "<html>Box Score</html>"

    content = operator.navigate_and_get_box_score_content("http://fake.url/box")

    mock_page.goto.assert_called_once_with("http://fake.url/box", timeout=ANY)
    mock_page.wait_for_selector.assert_called_once_with(
        "div.GameBoxDetail", state="visible", timeout=ANY
    )
    assert content == "<html>Box Score</html>"


def test_extract_live_events_html(mock_page):
    """測試從 Live 頁面提取所有半局 HTML 的複雜流程。"""
    # 1. 設定頁面元素的複雜 mock 結構
    mock_inning_button = MagicMock()
    mock_inning_buttons_locator = MagicMock()
    mock_inning_buttons_locator.all.return_value = [mock_inning_button]  # 1 局

    mock_top_section = MagicMock()
    mock_top_section.count.return_value = 1
    mock_top_section.inner_html.return_value = "<html>Top 1</html>"

    mock_bot_section = MagicMock()
    mock_bot_section.count.return_value = 0  # 模擬下半局不存在

    def active_content_locator_side_effect(selector):
        if selector == "section.top":
            return mock_top_section
        if selector == "section.bot":
            return mock_bot_section
        return MagicMock()

    mock_active_content = MagicMock()
    mock_active_content.locator.side_effect = active_content_locator_side_effect

    def page_locator_side_effect(selector):
        if "div.tabs > ul > li" in selector:
            return mock_inning_buttons_locator
        if "div.tab_cont.active" in selector:
            return mock_active_content
        return MagicMock()

    mock_page.locator.side_effect = page_locator_side_effect

    # 2. 執行被測試的函式
    operator = BrowserOperator(mock_page)
    with patch.object(operator, "_expand_all_events_in_half_inning") as mock_expand:
        results = operator.extract_live_events_html("http://fake.url/live")

    # 3. 驗證行為
    mock_page.goto.assert_called_once_with(
        "http://fake.url/live", wait_until="load", timeout=ANY
    )
    mock_page.add_style_tag.assert_called_once()
    mock_inning_button.click.assert_called_once()
    mock_expand.assert_called_once_with(mock_top_section)  # 只呼叫了上半局

    assert len(results) == 1
    assert results[0] == ("<html>Top 1</html>", 1, "section.top")


@patch("app.services.browser_operator.logger")
def test_extract_live_events_html_handles_timeout(mock_logger, mock_page):
    """測試在等待局數內容可見時超時，應記錄錯誤並繼續。"""
    mock_inning_button = MagicMock()
    mock_inning_buttons_locator = MagicMock()
    mock_inning_buttons_locator.all.return_value = [mock_inning_button]

    # 透過 autouse fixture，expect 已經被 mock。我們讓它在被呼叫時拋出異常。
    with patch("app.services.browser_operator.expect") as mock_expect:
        # 取得 to_be_visible 屬性並使其在被呼叫時拋出異常
        mock_expect.return_value.to_be_visible.side_effect = Exception("Timeout")
        mock_page.locator.return_value = mock_inning_buttons_locator

        operator = BrowserOperator(mock_page)
        results = operator.extract_live_events_html("http://fake.url/live")

    assert results == []
    mock_logger.error.assert_called_once()
