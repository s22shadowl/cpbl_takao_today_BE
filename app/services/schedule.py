# app/services/schedule.py

import logging
from datetime import datetime
from typing import List, Dict, Optional

from bs4 import BeautifulSoup

from app.config import settings
from app.crud import games
from app.db import SessionLocal
from app.browser import get_page  # [重構] 使用統一的 browser manager

logger = logging.getLogger(__name__)


def scrape_cpbl_schedule(
    year: int, start_month: int, end_month: int, include_past_games: bool = False
) -> List[Dict[str, Optional[str]]]:
    """
    從中華職棒官網爬取指定年份和月份區間的賽程，並篩選目標球隊，最終存入資料庫。
    :param include_past_games: 若為 False (預設)，則只會儲存今天及未來的比賽。
    """
    schedule_page_url = "https://www.cpbl.com.tw/schedule"
    all_games: List[Dict[str, Optional[str]]] = []
    scraped_game_ids = set()

    # [重構] 使用統一的 browser manager
    with get_page(headless=True) as page:
        logger.info(f"正在啟動瀏覽器並前往 {schedule_page_url}...")
        page.goto(schedule_page_url, timeout=60000)

        try:
            page.wait_for_selector(".ScheduleSearch .month select", timeout=20000)
        except Exception as e:
            logger.error(f"錯誤：頁面載入超時或找不到關鍵元件。 {e}")
            return []

        logger.info("頁面載入完成。")

        for month in range(start_month, end_month + 1):
            try:
                logger.info(f"正在設定查詢條件： {year} 年 {month} 月")

                page.select_option(".ScheduleSearch .year select", value=str(year))
                page.select_option(
                    ".ScheduleSearch .month select", value=str(month - 1)
                )

                page.wait_for_selector(".blockUI", state="hidden", timeout=15000)
                logger.info(f"取得 {year} 年 {month} 月的資料成功。")

                html_content = page.content()
                soup = BeautifulSoup(html_content, "html.parser")

                schedule_table = soup.find("div", class_="ScheduleTableList")
                if not schedule_table:
                    logger.info(f"{year} 年 {month} 月沒有賽程資料。")
                    continue

                game_rows = schedule_table.find("tbody").find_all("tr")
                current_date = ""

                for row in game_rows:
                    date_cell = row.find("td", class_="date")
                    if date_cell and date_cell.get_text(strip=True):
                        current_date_text = (
                            date_cell.get_text(strip=True).split("(")[0].strip()
                        )
                        current_date = f"{year}-{current_date_text.replace('/', '-')}"

                    game_id_cell = row.find("td", class_="game_no")
                    team_cell = row.find("td", class_="team")
                    info_cell = row.find("td", class_="info")

                    if not all([game_id_cell, team_cell, info_cell]):
                        continue

                    game_id = game_id_cell.get_text(strip=True)
                    if game_id in scraped_game_ids:
                        continue

                    away_team = team_cell.find("div", class_="name away").get_text(
                        strip=True
                    )
                    home_team = team_cell.find("div", class_="name home").get_text(
                        strip=True
                    )

                    if settings.TARGET_TEAM_NAME not in [home_team, away_team]:
                        continue

                    start_time = ""
                    time_div = info_cell.find("div", class_="time")
                    if time_div:
                        time_span = time_div.find("span")
                        if time_span:
                            start_time = time_span.get_text(strip=True)

                    game_info = {
                        "date": current_date,
                        "game_id": game_id,
                        "matchup": f"{away_team} vs {home_team}",
                        "game_time": start_time,
                    }
                    all_games.append(game_info)
                    scraped_game_ids.add(game_id)

            except Exception as e:
                logger.error(
                    f"錯誤：處理 {year} 年 {month} 月資料時發生未知錯誤: {e}",
                    exc_info=True,
                )

    logger.info(f"\n爬取完成，總共取得 {len(all_games)} 場目標球隊的比賽。")

    games_to_save = all_games
    if not include_past_games:
        today = datetime.now().date()
        original_count = len(all_games)

        games_to_save = [
            game
            for game in all_games
            if datetime.strptime(game["date"], "%Y-%m-%d").date() >= today
        ]

        filtered_count = original_count - len(games_to_save)
        if filtered_count > 0:
            logger.info(f"已過濾掉 {filtered_count} 場過去的比賽，將只儲存未來賽程。")

    if games_to_save:
        db = SessionLocal()
        try:
            games.update_game_schedules(db, games_to_save)
            db.commit()
            logger.info(f"成功提交 {len(games_to_save)} 筆賽程到資料庫。")
        except Exception as e:
            logger.error(f"儲存賽程時發生錯誤，交易已復原: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()

    return games_to_save
