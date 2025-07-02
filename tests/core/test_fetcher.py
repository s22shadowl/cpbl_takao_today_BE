# tests/core/test_fetcher.py

import pytest
import requests
from playwright.sync_api import Page, expect
from pathlib import Path

# 導入我們要測試的模組
from app.core import fetcher
from app.config import settings

# --- 測試 get_static_page_content ---


def test_get_static_page_content_success(mocker):
    """測試 get_static_page_content 成功獲取內容的情況"""
    fake_html = "<html><body><h1>Hello World</h1></body></html>"
    mock_get = mocker.patch("requests.get")
    mock_get.return_value.text = fake_html
    mock_get.return_value.raise_for_status.return_value = None
    result = fetcher.get_static_page_content("http://fakeurl.com")
    assert result == fake_html


def test_get_static_page_content_failure(mocker, caplog):
    """測試 get_static_page_content 在網路請求失敗時的情況"""
    mocker.patch(
        "requests.get",
        side_effect=requests.exceptions.RequestException("Network Error"),
    )
    result = fetcher.get_static_page_content("http://fakeurl.com")
    assert result is None
    assert "請求 URL http://fakeurl.com 失敗" in caplog.text


# --- 測試 Playwright 相關的函式 ---

# 獲取測試素材檔案的路徑
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_schedule_page_interaction(page: Page):
    """
    測試「賽程頁面」的互動邏輯。
    我們直接使用 pytest-playwright 提供的 page 物件來模擬操作，
    驗證我們在 fetch_schedule_page 中使用的選擇器和等待邏輯是正確的。
    """
    # 1. 準備：設定網路攔截
    schedule_html_path = FIXTURES_DIR / "schedule_page.html"
    if not schedule_html_path.exists():
        pytest.skip("測試素材 schedule_page.html 不存在，跳過此測試。")

    fake_html_content = schedule_html_path.read_text(encoding="utf-8")
    page.route(
        settings.SCHEDULE_URL,
        lambda route: route.fulfill(
            status=200, body=fake_html_content, content_type="text/html; charset=utf-8"
        ),
    )

    # 2. 執行：在 page 物件上模擬 fetch_schedule_page 函式中的操作
    page.goto(settings.SCHEDULE_URL)

    # 斷言：檢查頁面是否已載入我們的假 HTML
    expect(page.locator('a[title="列表顯示"]')).to_be_visible()

    # 模擬選擇年/月並斷言
    page.select_option("div.item.year > select", "2025")
    page.select_option("div.item.month > select", "5")  # 6月對應 value 5

    # 斷言日期標題是否被（模擬的）JS 更新
    expect(page.locator("div.date_selected > div.date")).to_contain_text("2025 / 06")

    # 模擬點擊並斷言
    page.click('a[title="列表顯示"]')
    expect(page.locator(".ScheduleTableList")).to_be_visible()


def test_dynamic_content_waits_correctly(page: Page):
    """
    測試「通用動態頁面」的等待邏輯。
    我們驗證 get_dynamic_page_content 中使用的 wait_for_selector 邏輯是有效的。
    """
    # 1. 準備
    fake_url = f"{settings.BASE_URL}/some_fake_path"
    fake_html = "<html><body><div id='my-data' style='display:none;'>目標內容</div></body></html>"
    page.route(
        fake_url,
        lambda route: route.fulfill(
            status=200, body=fake_html, content_type="text/html; charset=utf-8"
        ),
    )
    # 模擬一個讓元素延遲可見的 JS
    page.add_init_script(
        "setTimeout(() => { document.getElementById('my-data').style.display = 'block'; }, 100)"
    )

    # 2. 執行
    page.goto(fake_url)
    # 驗證核心邏輯：等待特定元素變為可見
    page.wait_for_selector("#my-data", state="visible")

    # 3. 斷言
    expect(page.locator("#my-data")).to_have_text("目標內容")
