# app/parsers/box_score

import logging
from bs4 import BeautifulSoup
from typing import List, Optional


def parse_box_score_page(html_content, target_teams: Optional[List[str]] = None):
    """從 Box Score 頁面 HTML 中，解析出指定球隊的所有球員基本數據和簡易打席列表。"""
    if not html_content:
        return []
    soup = BeautifulSoup(html_content, "lxml")
    all_players_data = []

    team_stat_blocks = soup.select(
        "div.GameBoxDetail > div.tab_container > div.tab_cont"
    )
    if not team_stat_blocks:
        return []

    for block in team_stat_blocks:
        try:
            team_name_tag = block.select_one("th.player > a")
            if not team_name_tag:
                continue
            current_team_name = team_name_tag.text.strip()

            # 【修改】如果提供了 target_teams 列表，則只處理列表中的球隊
            if target_teams and current_team_name not in target_teams:
                continue

            logging.info(
                f"成功匹配到球隊 [{current_team_name}] 的數據區塊，開始解析球員..."
            )
            batting_stats_table = block.select_one(
                'div.DistTitle:has(h3:-soup-contains("打擊成績")) + div.RecordTableWrap table'
            )
            if not batting_stats_table:
                continue

            player_summary_rows = batting_stats_table.find("tbody").find_all(
                "tr", class_=lambda c: c != "total"
            )
            for player_row in player_summary_rows:
                try:
                    player_name_tag = player_row.find("span", class_="name")
                    if not player_name_tag:
                        continue
                    player_name = player_name_tag.text.strip()

                    logging.info(f"找到球員 [{player_name}] 的數據，準備提取...")
                    cells = player_row.find_all("td", class_="num")
                    col_map = [
                        "at_bats",
                        "runs_scored",
                        "hits",
                        "rbi",
                        "doubles",
                        "triples",
                        "homeruns",
                        "gidp",
                        "walks",
                        "intentional_walks",
                        "hit_by_pitch",
                        "strikeouts",
                        "sacrifice_hits",
                        "sacrifice_flies",
                        "stolen_bases",
                        "caught_stealing",
                        "errors",
                        "avg_cumulative",
                    ]
                    summary_data = {
                        "player_name": player_name,
                        "team_name": current_team_name,
                    }

                    order_pos_cell = player_row.find("td", class_="player")
                    if order_pos_cell:
                        summary_data["batting_order"] = order_pos_cell.find(
                            "span", class_="order"
                        ).text.strip()
                        summary_data["position"] = order_pos_cell.find(
                            "span", class_="position"
                        ).text.strip()

                    for i, field_name in enumerate(col_map):
                        if field_name == "intentional_walks":
                            ibb_text = cells[i - 1].text.strip()
                            summary_data[field_name] = (
                                int(ibb_text.split("（")[1].replace("）", ""))
                                if "（" in ibb_text
                                else 0
                            )
                            continue
                        if i < len(cells):
                            value_str = cells[i].text.strip()
                            if field_name.endswith("_cumulative"):
                                summary_data[field_name] = (
                                    float(value_str)
                                    if value_str and value_str != "."
                                    else 0.0
                                )
                            else:
                                summary_data[field_name] = (
                                    int(value_str) if value_str.isdigit() else 0
                                )

                    play_by_play_table = block.select_one(
                        'div.DistTitle:has(h3:-soup-contains("戰況表")) + div.RecordTableWrap table'
                    )
                    at_bat_summary_list = []
                    if play_by_play_table:
                        pbp_row = play_by_play_table.find(
                            "span", class_="name", string=player_name
                        )
                        if pbp_row:
                            pbp_row = pbp_row.find_parent("tr")
                            at_bat_cells = pbp_row.find_all("td")[1:-6]
                            for cell in at_bat_cells:
                                if cell.text.strip():
                                    at_bat_summary_list.append(cell.text.strip())
                    summary_data["at_bat_results_summary"] = ",".join(
                        at_bat_summary_list
                    )
                    summary_data["plate_appearances"] = sum(
                        [
                            summary_data.get(k, 0)
                            for k in [
                                "at_bats",
                                "walks",
                                "hit_by_pitch",
                                "sacrifice_hits",
                                "sacrifice_flies",
                            ]
                        ]
                    )

                    player_full_data = {
                        "summary": summary_data,
                        "at_bats_list": at_bat_summary_list,
                    }
                    all_players_data.append(player_full_data)
                except Exception as e:
                    logging.error(
                        f"解析球員 [{player_name or '未知'}] 的 Box Score 數據時發生錯誤，跳過此球員: {e}",
                        exc_info=True,
                    )
        except Exception as e:
            logging.error(f"解析球隊數據區塊時發生錯誤: {e}", exc_info=True)
    return all_players_data
