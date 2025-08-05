# tests/core/test_fetcher.py

import pytest
import requests
from playwright.sync_api import (
    Page,
    expect,
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
)
from pathlib import Path

from app.core import fetcher
from app.config import settings
from app.exceptions import RetryableScraperError, FatalScraperError

# --- 測試 get_static_page_content ---


def test_get_static_page_content_success(mocker):
    """測試 get_static_page_content 成功獲取內容。"""
    fake_html = "<html><body>Success</body></html>"
    mock_response = mocker.Mock()
    mock_response.text = fake_html
    mock_response.raise_for_status.return_value = None

    mocker.patch("requests.get", return_value=mock_response)

    result = fetcher.get_static_page_content("http://fakeurl.com")
    assert result == fake_html


@pytest.mark.parametrize("status_code", [500, 503, 504])
def test_get_static_page_content_raises_retryable_on_5xx(mocker, status_code):
    """測試 get_static_page_content 在遇到 5xx 錯誤時拋出 RetryableScraperError。"""
    mock_response = mocker.Mock()
    mock_response.status_code = status_code
    http_error = requests.exceptions.HTTPError(response=mock_response)

    mocker.patch("requests.get", side_effect=http_error)

    with pytest.raises(RetryableScraperError, match=f"伺服器錯誤.*{status_code}"):
        fetcher.get_static_page_content("http://fakeurl.com")


@pytest.mark.parametrize("status_code", [400, 404, 429])
def test_get_static_page_content_raises_fatal_on_4xx(mocker, status_code):
    """測試 get_static_page_content 在遇到 4xx 錯誤時拋出 FatalScraperError。"""
    mock_response = mocker.Mock()
    mock_response.status_code = status_code
    http_error = requests.exceptions.HTTPError(response=mock_response)

    mocker.patch("requests.get", side_effect=http_error)

    with pytest.raises(FatalScraperError, match=f"客戶端錯誤.*{status_code}"):
        fetcher.get_static_page_content("http://fakeurl.com")


def test_get_static_page_content_raises_retryable_on_request_exception(mocker):
    """測試 get_static_page_content 在遇到通用請求錯誤時拋出 RetryableScraperError。"""
    mocker.patch(
        "requests.get", side_effect=requests.exceptions.Timeout("Connection timed out")
    )

    with pytest.raises(RetryableScraperError, match="Connection timed out"):
        fetcher.get_static_page_content("http://fakeurl.com")


# --- Unit Tests for Playwright functions ---


def test_get_dynamic_page_content_raises_retryable_on_timeout(mocker):
    """測試 get_dynamic_page_content 在遇到 Playwright 超時錯誤時拋出 RetryableScraperError。"""
    mock_playwright_context = mocker.patch("app.core.fetcher.sync_playwright")
    mock_page = mock_playwright_context.return_value.__enter__.return_value.chromium.launch.return_value.new_page.return_value
    mock_page.goto.side_effect = PlaywrightTimeoutError("Page load timed out")

    with pytest.raises(RetryableScraperError, match="發生超時"):
        fetcher.get_dynamic_page_content("http://fakeurl.com", "#selector")


def test_fetch_schedule_page_raises_fatal_on_playwright_error(mocker):
    """測試 fetch_schedule_page 在遇到 Playwright 嚴重錯誤時拋出 FatalScraperError。"""
    mock_playwright_context = mocker.patch("app.core.fetcher.sync_playwright")
    mock_playwright_context.return_value.__enter__.return_value.chromium.launch.side_effect = PlaywrightError(
        "Browser could not be started"
    )

    with pytest.raises(FatalScraperError, match="發生嚴重錯誤"):
        fetcher.fetch_schedule_page(2025, 5)


# --- E2E-style Tests (Kept from original for interaction validation) ---

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_schedule_page_interaction(page: Page):
    """
    測試「賽程頁面」的互動邏輯。
    我們直接使用 pytest-playwright 提供的 page 物件來模擬操作，
    驗證我們在 fetch_schedule_page 中使用的選擇器和等待邏輯是正確的。
    """
    schedule_html_path = FIXTURES_DIR / "schedule_page.html"
    if not schedule_html_path.exists():
        pytest.skip("測試素材 schedule_page.html 不存在，跳過此測試。")

    fake_html_content = schedule_html_path.read_text(encoding="utf-8")

    def handle_route(route):
        if route.request.url == settings.SCHEDULE_URL:
            route.fulfill(
                status=200,
                body=fake_html_content,
                content_type="text/html; charset=utf-8",
            )
        else:
            route.abort()

    page.route("**/*", handle_route)
    page.goto(settings.SCHEDULE_URL, wait_until="domcontentloaded")

    expect(page.locator('a[title="列表顯示"]')).to_be_visible()

    page.select_option("div.item.year > select", "2025")
    page.select_option("div.item.month > select", "5")  # 6月對應 value 5

    expect(page.locator("div.date_selected > div.date")).to_contain_text("2025 / 06")

    page.click('a[title="列表顯示"]')
    expect(page.locator(".ScheduleTableList")).to_be_visible()


def test_dynamic_content_waits_correctly(page: Page):
    """
    測試「通用動態頁面」的等待邏輯。
    我們驗證 get_dynamic_page_content 中使用的 wait_for_selector 邏輯是有效的。
    """
    fake_url = f"{settings.BASE_URL}/some_fake_path"
    fake_html = "<html><body><div id='my-data' style='display:none;'>目標內容</div></body></html>"

    def handle_route(route):
        if route.request.url == fake_url:
            route.fulfill(
                status=200, body=fake_html, content_type="text/html; charset=utf-8"
            )
        else:
            route.abort()

    page.route("**/*", handle_route)
    page.add_init_script(
        "setTimeout(() => { document.getElementById('my-data').style.display = 'block'; }, 100)"
    )

    page.goto(fake_url, wait_until="domcontentloaded")
    page.wait_for_selector("#my-data", state="visible")

    expect(page.locator("#my-data")).to_have_text("目標內容")
