# app/parsers/schedule.py

import logging
import datetime
import re
from bs4 import BeautifulSoup, Tag
from urllib.parse import urlparse, parse_qs, urljoin
from app.config import settings
from app.exceptions import FatalScraperError, GameNotFinalError


def _parse_single_game_block(game_block: Tag, game_date: datetime.date) -> dict | None:
    """從單一個比賽區塊 (div.game) 中解析出詳細資訊。"""
    game_data = {"game_date": game_date.strftime("%Y-%m-%d")}

    # --- 狀態判斷邏輯 ---
    status_text = "未開始"  # 預設狀態
    if "final" in game_block.get("class", []):
        status_text = "已完成"
    else:
        note_tag = game_block.select_one("div.remark > div.note")
        if note_tag and note_tag.text.strip():
            status_text = note_tag.text.strip()
    game_data["status"] = status_text

    # --- 基礎資訊解析 ---
    info_div = game_block.select_one("div.info")
    if info_div:
        venue_tag = info_div.select_one("div.place")
        game_data["venue"] = venue_tag.text.strip() if venue_tag else None

        game_no_tag = info_div.select_one("div.game_no")
        game_data["cpbl_game_id"] = game_no_tag.text.strip() if game_no_tag else None

    # 【核心修正】對於非「已完成」的比賽，它們可能沒有 info_div，但我們仍需從 a 標籤獲取 gameSno
    link_tag = game_block.find("a")
    if link_tag and link_tag.has_attr("href"):
        relative_url = link_tag["href"]
        game_data["box_score_url"] = urljoin(settings.BASE_URL, relative_url)
        qs = parse_qs(urlparse(relative_url).query)
        if "gameSno" in qs:
            game_data["cpbl_game_id"] = qs.get("gameSno", [None])[0]
    else:
        # 如果連 a 標籤都沒有，就無法取得比賽 ID，視為無效區塊
        return None

    # --- 隊伍與分數解析 ---
    vs_box = game_block.select_one("div.vs_box")
    if vs_box:
        away_team_tag = vs_box.select_one("div.team.away span")
        home_team_tag = vs_box.select_one("div.team.home span")
        game_data["away_team"] = away_team_tag.get("title") if away_team_tag else None
        game_data["home_team"] = home_team_tag.get("title") if home_team_tag else None

        away_score_tag = vs_box.select_one("div.score > div.num.away")
        home_score_tag = vs_box.select_one("div.score > div.num.home")
        game_data["away_score"] = (
            int(away_score_tag.text.strip()) if away_score_tag else None
        )
        game_data["home_score"] = (
            int(home_score_tag.text.strip()) if home_score_tag else None
        )
    elif status_text == "已完成":
        # 【核心修正】如果一場比賽已完成，但沒有隊伍資訊，這是一個嚴重的解析錯誤
        logging.error(
            f"已完成的比賽 {game_data.get('cpbl_game_id')} 缺少隊伍資訊 (vs_box)，將跳過此比賽。"
        )
        return None

    return game_data


def parse_schedule_page(html_content, year):
    """
    從賽程頁面的 HTML 中，解析出該月份「所有已完成」的比賽基本資訊。
    此函式現在解析的是「月曆檢視」的 HTML 結構。
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
        raise FatalScraperError("傳入的賽程頁面 HTML 內容為空，無法進行解析。")

    logging.info(f"開始從 HTML 內容中解析年份為 {year} 的比賽...")
    soup = BeautifulSoup(html_content, "lxml")
    parsed_games = []

    # 【核心修正】使用正確的 CSS 選擇器來定位月曆表格
    schedule_table = soup.select_one("div.ScheduleTable > table > tbody")
    if not schedule_table:
        raise FatalScraperError("在賽程頁 HTML 中找不到月曆表格 <tbody>。")

    all_days = schedule_table.find_all("td")

    # 從頁面內容中獲取當前月份，作為日期解析的基礎
    month_tag = soup.select_one("div.item.month > select > option[selected]")
    if not month_tag or not month_tag.has_attr("value"):
        date_header = soup.select_one("div.date_selected > div.date")
        if date_header:
            match = re.search(r"\d{4}\s+/\s+(\d{2})", date_header.text)
            if match:
                month = int(match.group(1))
            else:
                raise FatalScraperError("無法從頁面標題中確定當前月份。")
        else:
            raise FatalScraperError("無法從頁面中確定當前月份。")
    else:
        month = int(month_tag["value"]) + 1

    for day_cell in all_days:
        # 排除非本月份的日期格
        if "other_month" in day_cell.get("class", []):
            continue

        date_div = day_cell.find("div", class_="date")
        if not date_div or not date_div.text.strip().isdigit():
            continue

        day = int(date_div.text.strip())
        try:
            current_date_in_loop = datetime.date(year, month, day)
        except ValueError:
            logging.warning(
                f"解析到無效日期組合 (Y/M/D): {year}/{month}/{day}，跳過此日期格。"
            )
            continue

        game_blocks = day_cell.find_all("div", class_="game")
        for game_block in game_blocks:
            try:
                game_data = _parse_single_game_block(game_block, current_date_in_loop)
                if not game_data:
                    continue

                # 只有「已完成」的比賽會被加入列表，其餘狀態會被記錄並跳過
                if game_data.get("status") != "已完成":
                    raise GameNotFinalError(
                        f"比賽 {game_data.get('cpbl_game_id')} 狀態為 '{game_data.get('status')}'，應跳過。"
                    )

                parsed_games.append(game_data)
            except GameNotFinalError as e:
                logging.info(str(e))
                continue
            except Exception as e:
                logging.error(
                    f"解析單場比賽區塊時出錯，已跳過此比賽: {e}", exc_info=True
                )

    logging.info(f"從賽程頁面總共解析到 {len(parsed_games)} 場已完成的比賽。")
    return parsed_games
