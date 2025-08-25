# app/services/browser_operator.py

import logging
from typing import List, Tuple
from playwright.sync_api import Page, expect, Locator

from app.config import settings

logger = logging.getLogger(__name__)


class BrowserOperator:
    """封裝所有 Playwright 瀏覽器互動邏輯的類別。"""

    def __init__(self, page: Page):
        """
        初始化 BrowserOperator。

        Args:
            page (Page): Playwright 的 Page 物件。
        """
        self.page = page

    def navigate_and_get_box_score_content(self, box_score_url: str) -> str:
        """導航至 Box Score 頁面並回傳其 HTML 內容。"""
        logger.info(f"導航至 Box Score 頁面: {box_score_url}")
        self.page.goto(box_score_url, timeout=settings.PLAYWRIGHT_TIMEOUT)
        self.page.wait_for_selector(
            "div.GameBoxDetail",
            state="visible",
            timeout=settings.PLAYWRIGHT_TIMEOUT,
        )
        return self.page.content()

    def extract_live_events_html(self, live_url: str) -> List[Tuple[str, int, str]]:
        """
        導航至 Live 頁面，遍歷所有半局，展開事件，並回傳每個半局的 HTML。

        Returns:
            List[Tuple[str, int, str]]: 一個元組列表，每個元組包含 (半局 HTML, 局數, 半局選擇器)。
        """
        logger.info(f"導航至 Live 頁面: {live_url}")
        self.page.goto(live_url, wait_until="load", timeout=settings.PLAYWRIGHT_TIMEOUT)
        self.page.wait_for_selector(
            "div.InningPlaysGroup", timeout=settings.PLAYWRIGHT_TIMEOUT
        )

        logger.info("注入 CSS 以隱藏所有 iframe...")
        try:
            self.page.add_style_tag(content="iframe { display: none !important; }")
        except Exception as e:
            logger.error(f"注入 CSS 時發生錯誤: {e}")

        inning_buttons = self.page.locator(
            "div.InningPlaysGroup div.tabs > ul > li"
        ).all()

        all_half_innings_html = []

        for i, inning_li in enumerate(inning_buttons):
            inning_num = i + 1
            logger.info(f"處理第 {inning_num} 局的瀏覽器互動...")

            inning_li.click()

            try:
                active_inning_content = self.page.locator(
                    "div.InningPlaysGroup div.tab_cont.active"
                )
                expect(active_inning_content).to_be_visible(timeout=5000)
            except Exception as e:
                logger.error(
                    f"等待第 {inning_num} 局內容可見時超時或失敗: {e}，將跳過此局的互動。"
                )
                continue

            for half_inning_selector in ["section.top", "section.bot"]:
                half_inning_section = active_inning_content.locator(
                    half_inning_selector
                )

                if half_inning_section.count() > 0:
                    self._expand_all_events_in_half_inning(half_inning_section)

                    # 展開所有事件後，擷取 HTML
                    inning_html = half_inning_section.inner_html()
                    all_half_innings_html.append(
                        (inning_html, inning_num, half_inning_selector)
                    )

        return all_half_innings_html

    def _expand_all_events_in_half_inning(self, half_inning_section: Locator):
        """展開指定半局區塊中的所有可點擊事件。"""
        event_containers = half_inning_section.locator("div.item.play")
        container_count = event_containers.count()

        if container_count > 0:
            logger.info(f"找到 {container_count} 個事件容器，準備展開...")

        for i in range(container_count):
            item_container = event_containers.nth(i)

            bell_button = item_container.locator("div.no-pitch-action-remind")
            event_button = item_container.locator("div.batter_event")
            event_anchor = event_button.locator("a")

            target_to_click = None
            try:
                anchor_text = (event_anchor.text_content(timeout=500) or "").strip()
                if anchor_text:
                    target_to_click = event_button
                elif bell_button.count() > 0:
                    target_to_click = bell_button
            except Exception:
                if bell_button.count() > 0:
                    target_to_click = bell_button

            if not target_to_click:
                continue

            # 重試點擊邏輯
            for attempt in range(2):
                try:
                    target_to_click.scroll_into_view_if_needed()
                    self.page.wait_for_timeout(100)
                    target_to_click.hover(force=True, timeout=3000)
                    self.page.wait_for_timeout(100)
                    target_to_click.click(force=True, timeout=2000)
                    break  # 成功點擊後跳出重試迴圈
                except Exception as e:
                    logger.warning(
                        f"點擊第 {i + 1} 個按鈕時失敗 (嘗試 {attempt + 1}): {e}",
                        exc_info=False,
                    )
                    if attempt == 1:
                        logger.error(f"重試多次後，點擊第 {i + 1} 個按鈕仍然失敗。")
