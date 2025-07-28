# app/parsers/schedule.py

import logging
import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from app.config import settings


def parse_schedule_page(html_content, year):
    """
    從賽程頁面的 HTML 中，解析出該月份「所有」的比賽基本資訊。
    """
    if settings.E2E_TEST_MODE:
        logging.info("E2E 模式啟用：正在產生假的比賽資料...")
        return [
            {
                "game_date": "2025-01-15",
                "cpbl_game_id": "E2E_20250115",
                "status": "已完成",
                "away_team": "E2E測試客隊",
                "home_team": settings.TARGET_TEAM_NAME,
                "away_score": 3,
                "home_score": 5,
                "venue": "E2E測試球場",
                "game_time": "18:35",
                "box_score_url": "http://fake-url.com/box",
            }
        ]

    if not html_content:
        logging.warning("傳入的賽程頁面 HTML 內容為空，無法進行解析。")
        return []

    logging.info(f"開始從 HTML 內容中解析年份為 {year} 的比賽...")
    soup = BeautifulSoup(html_content, "lxml")
    parsed_games = []

    list_view_container = soup.select_one("div.tab_cont.list")
    if not list_view_container:
        logging.warning("在賽程頁 HTML 中找不到 '列表顯示' 的區塊。")
        return []

    schedule_table = list_view_container.find("div", class_="ScheduleTableList")
    if not schedule_table:
        logging.warning("在 '列表顯示' 區塊中找不到賽程表格。")
        return []

    all_rows = schedule_table.find_all("tr")
    current_date_in_loop = None

    for row in all_rows:
        try:
            date_cell = row.find("td", class_="date")
            if date_cell:
                date_text = date_cell.text.strip().split("(")[0]
                month_str, day_str = date_text.split("/")
                current_date_in_loop = datetime.date(
                    int(year), int(month_str), int(day_str)
                )

            game_no_cell = row.find("td", class_="game_no")
            if not game_no_cell or not current_date_in_loop:
                continue

            game_data = {"game_date": current_date_in_loop.strftime("%Y-%m-%d")}
            box_link_tag = game_no_cell.find("a")
            if box_link_tag and box_link_tag.has_attr("href"):
                relative_url = box_link_tag["href"]
                game_data["box_score_url"] = (
                    f"{settings.BASE_URL}{relative_url}"
                    if relative_url.startswith("/")
                    else f"{settings.BASE_URL}/{relative_url}"
                )
                qs = parse_qs(urlparse(relative_url).query)
                game_data["cpbl_game_id"] = qs.get("gameSno", [None])[0]

            team_cell = row.find("td", class_="team")
            if team_cell:
                game_data["away_team"] = team_cell.find(
                    "div", class_="name away"
                ).text.strip()
                game_data["home_team"] = team_cell.find(
                    "div", class_="name home"
                ).text.strip()
                away_score_tag, home_score_tag = (
                    team_cell.find("div", class_="num away"),
                    team_cell.find("div", class_="num home"),
                )
                game_data["away_score"] = (
                    int(away_score_tag.text.strip())
                    if away_score_tag and away_score_tag.text.strip().isdigit()
                    else None
                )
                game_data["home_score"] = (
                    int(home_score_tag.text.strip())
                    if home_score_tag and home_score_tag.text.strip().isdigit()
                    else None
                )

            info_cell = row.find("td", class_="info")
            if info_cell:
                game_data["venue"] = (
                    info_cell.find("div", class_="place").span.text.strip()
                    if info_cell.find("div", class_="place")
                    and info_cell.find("div", class_="place").span
                    else None
                )
                game_data["game_time"] = (
                    info_cell.find("div", class_="time").span.text.strip()
                    if info_cell.find("div", class_="time")
                    and info_cell.find("div", class_="time").span
                    else None
                )

            remark_cell = row.find("td", class_="remark")
            if remark_cell:
                note_tag = remark_cell.find("div", class_="note")
                if note_tag:
                    game_data["status"] = note_tag.text.strip()
                elif game_data.get("home_score") is not None:
                    game_data["status"] = "已完成"
                else:
                    game_data["status"] = "未開始"
            else:
                if game_data.get("home_score") is not None:
                    game_data["status"] = "已完成"
                else:
                    game_data["status"] = "未開始"

            parsed_games.append(game_data)
        except Exception as e:
            logging.error(f"解析單場比賽概要時出錯，已跳過此行: {e}", exc_info=True)

    logging.info(f"從賽程頁面總共解析到 {len(parsed_games)} 場比賽。")
    return parsed_games
