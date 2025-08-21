# app/services/player.py

import logging
from typing import Optional

from app.core import fetcher
from app.parsers import player_career
from app.db import SessionLocal
from app.crud import players
from app.exceptions import FatalScraperError

logger = logging.getLogger(__name__)


def scrape_and_store_player_career_stats(player_name: str, player_url: Optional[str]):
    """
    抓取並儲存單一球員的生涯數據。

    Args:
        player_name: 球員姓名。
        player_url: 球員在 CPBL 官網上的個人頁面完整 URL。
    """
    if not player_url:
        logger.warning(f"球員 [{player_name}] 缺少個人頁面 URL，無法抓取生涯數據。")
        return

    logger.info(f"--- 開始抓取球員 [{player_name}] 的生涯數據，URL: {player_url} ---")

    try:
        # 使用 Playwright 抓取動態頁面內容
        # 根據實際頁面結構，等待關鍵的 .RecordTableWrap 元素出現
        html_content = fetcher.get_dynamic_page_content(
            player_url, wait_for_selector="div.RecordTableWrap"
        )
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

    except Exception as e:
        logger.error(
            f"抓取與儲存球員 [{player_name}] 生涯數據的過程中發生錯誤: {e}",
            exc_info=True,
        )
        # 在 service 層決定是否要 re-raise 異常
