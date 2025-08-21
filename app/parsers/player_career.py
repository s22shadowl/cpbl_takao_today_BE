# app/parsers/player_career.py

import logging
from datetime import datetime
from typing import Dict, Any, Optional

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


def _safe_to_int(value: Optional[str]) -> int:
    """
    安全地將字串轉換為整數，若失敗則回傳 0。
    【修正】增加對 '（31）' 這種格式的處理。
    """
    if value is None:
        return 0
    try:
        cleaned_value = value.strip()
        # 處理 '（31）' 這種格式
        if cleaned_value.startswith("（") and cleaned_value.endswith("）"):
            return int(cleaned_value.strip("（）"))
        # 處理 '281（31）' 這種格式，只取括號前的數字
        else:
            return int(cleaned_value.split("（")[0].strip())
    except (ValueError, TypeError):
        return 0


def _safe_to_float(value: Optional[str]) -> float:
    """安全地將字串轉換為浮點數，若失敗則回傳 0.0。"""
    if value is None:
        return 0.0
    try:
        if value.strip() in ["--", "."]:
            return 0.0
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def parse_player_career_page(html_content: str) -> Optional[Dict[str, Any]]:
    """
    從球員個人生涯頁面的 HTML 中，解析出指定的生涯數據。
    """
    if not html_content:
        return None

    logger.info("正在解析球員生涯數據頁面...")
    soup = BeautifulSoup(html_content, "lxml")
    parsed_data = {}

    try:
        # --- 1. 解析球員基本資訊 ---
        player_brief_div = soup.find("div", class_="PlayerBrief")
        if player_brief_div:
            # 解析初登場日期
            debut_dd = player_brief_div.find("dd", class_="debut")
            if debut_dd and isinstance(debut_dd.find("div", class_="desc"), Tag):
                debut_date_str = debut_dd.find("div", class_="desc").text.strip()
                try:
                    parsed_data["debut_date"] = datetime.strptime(
                        debut_date_str, "%Y/%m/%d"
                    ).date()
                except ValueError:
                    logger.warning(f"無法解析的初登場日期格式: '{debut_date_str}'")

            # 解析投打習慣
            handedness_dd = player_brief_div.find("dd", class_="b_t")
            if handedness_dd and isinstance(
                handedness_dd.find("div", class_="desc"), Tag
            ):
                parsed_data["handedness"] = handedness_dd.find(
                    "div", class_="desc"
                ).text.strip()

        # --- 2. 解析生涯數據表格 ---
        record_table_wrap = soup.find("div", class_="RecordTableWrap")
        if not record_table_wrap:
            logger.error("在頁面中找不到 'RecordTableWrap' 區塊。")
            return parsed_data if parsed_data else None

        table = record_table_wrap.find("table")
        if not table:
            logger.error("在 'RecordTableWrap' 中找不到 table。")
            return parsed_data if parsed_data else None

        # 建立表頭與索引的映射
        header_row = table.find("tbody").find("tr")
        header_cells = header_row.find_all("th")
        header_map = {cell.text.strip(): i for i, cell in enumerate(header_cells)}

        # 找到生涯總計列 (class="total")
        total_row = table.find("tr", class_="total")
        if not total_row:
            logger.error("在表格中找不到生涯總計列 (tr.total)。")
            return parsed_data if parsed_data else None

        db_col_map = {
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
            "四壞": "walks",
            "（故四）": "intentional_walks",
            "死球": "hit_by_pitch",
            "盜壘刺": "caught_stealing",
            "滾地出局": "ground_outs",
            "高飛出局": "fly_outs",
            "滾飛出局比": "go_ao_ratio",
            "盜壘率": "sb_percentage",
            "整體攻擊指數": "ops",
            "OPS+": "ops_plus",
            "K%": "k_percentage",
            "BB%": "bb_percentage",
            "BB/K": "bb_per_k",
            "BABIP": "babip",
            "BIP%": "bip_percentage",
        }

        total_cells = total_row.find_all("td")
        if not total_cells:
            logger.error("在生涯總計列中找不到任何數據儲存格 (td)。")
            return parsed_data if parsed_data else None

        # --- 3. 根據映射關係提取數據 ---
        for header_text, col_name in db_col_map.items():
            if header_text in header_map:
                cell_index = header_map[header_text]
                if cell_index < len(total_cells):
                    value_str = total_cells[cell_index].text.strip()
                    if col_name in [
                        "obp",
                        "slg",
                        "avg",
                        "go_ao_ratio",
                        "sb_percentage",
                        "ops",
                        "ops_plus",
                        "k_percentage",
                        "bb_percentage",
                        "bb_per_k",
                        "babip",
                        "bip_percentage",
                    ]:
                        parsed_data[col_name] = _safe_to_float(value_str)
                    else:
                        parsed_data[col_name] = _safe_to_int(value_str)

        logger.info(f"成功解析到球員生涯數據，共 {len(parsed_data)} 個欄位。")
        return parsed_data

    except Exception as e:
        logger.error(f"解析球員生涯數據頁面時發生未預期的錯誤: {e}", exc_info=True)
        return None
