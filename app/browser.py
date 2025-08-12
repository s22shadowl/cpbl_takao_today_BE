# app/browser.py

import logging
from contextlib import contextmanager
from typing import Generator
from playwright.sync_api import sync_playwright, Page

logger = logging.getLogger(__name__)


@contextmanager
def get_page(headless: bool = True) -> Generator[Page, None, None]:
    """
    一個 context manager，負責啟動 Playwright、建立瀏覽器頁面，並在結束時妥善關閉。

    :param headless: 是否以無頭模式執行瀏覽器。
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            slow_mo=0,
            # 確保在 Dramatiq worker 中能正常關閉
            handle_sigint=False,
            handle_sigterm=False,
            handle_sighup=False,
        )
        page = browser.new_page()
        try:
            yield page
        finally:
            logger.debug("Closing browser page and browser.")
            page.close()
            browser.close()
