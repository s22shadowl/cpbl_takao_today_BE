# app/parsers/season_stats.py

import logging
from bs4 import BeautifulSoup
from app.config import settings


def parse_season_stats_page(html_content):
    """從球隊成績頁面 HTML 中，解析出目標球員的球季累積數據。"""
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
        try:
            cells = row.find_all("td")
            if not cells or len(cells) < 2:
                continue
            player_name_cell = cells[0].find("a")
            player_name = (
                player_name_cell.text.strip()
                if player_name_cell
                else cells[0].text.strip()
            )
            # 【修改】移除對特定球員的篩選
            # if player_name in settings.TARGET_PLAYER_NAMES:
            stats_data = {
                "player_name": player_name,
                "team_name": settings.TARGET_TEAM_NAME,  # 這部分邏輯可能需要後續調整
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
