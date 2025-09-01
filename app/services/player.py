# app/services/player.py

import logging
from typing import Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from app.db import SessionLocal
from app.crud import players
from app.parsers import player_career
from app.exceptions import FatalScraperError

logger = logging.getLogger(__name__)


def scrape_and_store_player_career_stats(
    page: Page, player_name: str, player_url: Optional[str]
):
    """
    [重構] 抓取並儲存單一球員的生涯數據，重複使用已存在的瀏覽器頁面 (Page)。

    Args:
        page: Playwright 的 Page 物件。
        player_name: 球員姓名。
        player_url: 球員在 CPBL 官網上的個人頁面完整 URL。
    """
    if not player_url:
        logger.warning(f"球員 [{player_name}] 缺少個人頁面 URL，無法抓取生涯數據。")
        return

    logger.info(f"--- 開始抓取球員 [{player_name}] 的生涯數據，URL: {player_url} ---")

    try:
        # 使用傳入的 page 物件進行操作，而不是建立新的 fetcher
        page.goto(player_url, wait_until="networkidle")
        page.wait_for_selector("div.RecordTableWrap", timeout=15000)
        html_content = page.content()

        if not html_content:
            raise FatalScraperError(f"無法從 {player_url} 獲取 HTML 內容。")

        # 解析生涯數據
        career_stats = player_career.parse_player_career_page(html_content)
        if not career_stats:
            logger.warning(f"無法為球員 [{player_name}] 解析到任何生涯數據。")
            return

        # 準備寫入資料庫
        db = SessionLocal()
        try:
            career_stats["player_name"] = player_name
            players.create_or_update_player_career_stats(db, career_stats)
            db.commit()
            logger.info(f"成功儲存球員 [{player_name}] 的生涯數據。")
        except Exception:
            db.rollback()
            logger.error(
                f"儲存球員 [{player_name}] 生涯數據時發生資料庫錯誤。", exc_info=True
            )
            raise
        finally:
            db.close()

    except PlaywrightTimeoutError as e:
        # 捕獲更具體的 Playwright 錯誤
        logger.error(
            f"抓取球員 [{player_name}] 生涯數據時頁面載入超時: {e}",
            exc_info=True,
        )
    except Exception as e:
        logger.error(
            f"抓取與儲存球員 [{player_name}] 生涯數據的過程中發生錯誤: {e}",
            exc_info=True,
        )
        # 在 service 層決定是否要 re-raise 異常
