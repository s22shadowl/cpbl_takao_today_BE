# app/parsers/season_stats.py

import logging
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from app.config import settings


def parse_season_batting_stats_page(html_content):
    """
    從球隊成績頁面 HTML 中，解析出目標球員的球季累積數據，並包含球員個人頁面 URL。
    """
    if not html_content:
        return []
    logging.info("正在解析球季累積數據...")
    soup = BeautifulSoup(html_content, "lxml")
    parsed_stats = []
    batting_table = soup.find("div", class_="RecordTable")
    if not batting_table:
        return []
    tbody = batting_table.find("tbody")
    if not tbody:
        return []
    player_rows = tbody.find_all("tr")
    header_map = {
        "出賽數": "games_played",
        "打席": "plate_appearances",
        "打數": "at_bats",
        "打點": "rbi",
        "得分": "runs_scored",
        "安打": "hits",
        "一安": "singles",
        "二安": "doubles",
        "三安": "triples",
        "全壘打": "homeruns",
        "壘打數": "total_bases",
        "被三振": "strikeouts",
        "盜壘": "stolen_bases",
        "上壘率": "obp",
        "長打率": "slg",
        "打擊率": "avg",
        "雙殺打": "gidp",
        "犧短": "sacrifice_hits",
        "犧飛": "sacrifice_flies",
        "四壞球": "walks",
        "（故四）": "intentional_walks",
        "死球": "hit_by_pitch",
        "盜壘刺": "caught_stealing",
        "滾地出局": "ground_outs",
        "高飛出局": "fly_outs",
        "滾飛出局比": "go_ao_ratio",
        "盜壘率": "sb_percentage",
        "整體攻擊指數": "ops",
        "銀棒指數": "silver_slugger_index",
    }
    header_cells = [h.text.strip() for h in player_rows[0].find_all("th")]
    player_data_rows = player_rows[1:]

    for row in player_data_rows:
        player_name = ""
        try:
            cells = row.find_all("td")
            if not cells or len(cells) < 2:
                continue

            player_name_cell = cells[0].find("a")
            if not player_name_cell:
                continue

            player_name = player_name_cell.text.strip()
            relative_url = player_name_cell.get("href")

            # 將相對路徑轉換為絕對 URL
            full_url = (
                urljoin("https://www.cpbl.com.tw/", relative_url)
                if relative_url
                else None
            )

            stats_data = {
                "player_name": player_name,
                "player_url": full_url,  # 新增 player_url
                "team_name": settings.TARGET_TEAM_NAME,
            }
            for i, header_text in enumerate(header_cells):
                db_col_name = header_map.get(header_text)
                if db_col_name and (i < len(cells)):
                    value_str = cells[i].text.strip()
                    if db_col_name in [
                        "avg",
                        "obp",
                        "slg",
                        "ops",
                        "go_ao_ratio",
                        "sb_percentage",
                        "silver_slugger_index",
                    ]:
                        stats_data[db_col_name] = (
                            float(value_str) if value_str and value_str != "." else 0.0
                        )
                    else:
                        stats_data[db_col_name] = (
                            int(value_str) if value_str.isdigit() else 0
                        )
            parsed_stats.append(stats_data)
        except (IndexError, ValueError) as e:
            logging.error(
                f"解析球員 [{player_name or '未知'}] 的累積數據時出錯，跳過此行: {e}",
                exc_info=True,
            )

    logging.info(f"從球隊頁面解析到 {len(parsed_stats)} 名球員的累積數據。")
    return parsed_stats


# [長期方案] 建立中文到英文縮寫的對照表
POSITION_CH_TO_EN = {
    "投手": "P",
    "捕手": "C",
    "一壘手": "1B",
    "二壘手": "2B",
    "三壘手": "3B",
    "游擊手": "SS",
    "左外野手": "LF",
    "中外野手": "CF",
    "右外野手": "RF",
}


# [T31-3 新增] 解析球員年度守備數據的函式
def parse_season_fielding_stats_page(html_content):
    """
    從球隊成績頁面 HTML 中，解析出所有球員的球季累積守備數據。
    """
    if not html_content:
        return []
    logging.info("正在解析球季累積守備數據...")
    soup = BeautifulSoup(html_content, "lxml")
    parsed_stats = []
    fielding_table = soup.find("div", class_="RecordTable")
    if not fielding_table:
        return []
    tbody = fielding_table.find("tbody")
    if not tbody:
        return []
    player_rows = tbody.find_all("tr")

    # 建立表頭與 DB 欄位的映射
    header_map = {
        "出賽數": "games_played",
        "守備機會": "total_chances",
        "刺殺": "putouts",
        "助殺": "assists",
        "失誤": "errors",
        "雙殺": "double_plays",
        "三殺": "triple_plays",
        "捕逸": "passed_balls",
        "盜壘阻殺": "caught_stealing_catcher",
        "被盜成功": "stolen_bases_allowed_catcher",
        "守備率": "fielding_percentage",
    }
    # 實際的表頭順序從 HTML 中讀取
    header_cells = [th.text.strip() for th in player_rows[0].find_all("th")]
    player_data_rows = player_rows[1:]

    for row in player_data_rows:
        player_name = ""
        try:
            cells = row.find_all("td")
            if not cells or len(cells) < 2:
                continue

            player_name_cell = cells[0].find("a")
            if not player_name_cell:
                continue

            player_name = player_name_cell.text.strip()

            stats_data = {
                "player_name": player_name,
                "team_name": settings.TARGET_TEAM_NAME,
            }

            for i, header_text in enumerate(header_cells):
                # 跳過第一個 '球員' 欄位
                if i == 0:
                    continue

                # 第二個欄位是守備位置
                if header_text == "守備位置":
                    ch_pos = cells[i].text.strip()
                    # [長期方案] 在解析時直接轉換為英文縮寫
                    en_pos = POSITION_CH_TO_EN.get(ch_pos, ch_pos)  # 若找不到則保留原文
                    stats_data["position"] = en_pos
                    continue

                db_col_name = header_map.get(header_text)
                if db_col_name and (i < len(cells)):
                    value_str = cells[i].text.strip()
                    # 守備率是浮點數
                    if db_col_name == "fielding_percentage":
                        stats_data[db_col_name] = (
                            float(value_str) if value_str and value_str != "." else 0.0
                        )
                    else:
                        stats_data[db_col_name] = (
                            int(value_str) if value_str.isdigit() else 0
                        )

            # 確保解析到了守備位置
            if "position" in stats_data:
                parsed_stats.append(stats_data)

        except (IndexError, ValueError) as e:
            logging.error(
                f"解析球員 [{player_name or '未知'}] 的累積守備數據時出錯，跳過此行: {e}",
                exc_info=True,
            )

    logging.info(f"從球隊頁面解析到 {len(parsed_stats)} 筆球員守備數據。")
    return parsed_stats
