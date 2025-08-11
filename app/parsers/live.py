# app/parsers/live.py

import json
import logging
import re
from bs4 import BeautifulSoup
from app.models import AtBatResultType

# 【新增】導入用於解析的關鍵字常數
from app.core.constants import (
    PARSER_ON_BASE_KEYWORDS,
    PARSER_OUT_KEYWORDS,
    PARSER_SACRIFICE_KEYWORDS,
    PARSER_FC_KEYWORDS,
    PARSER_ERROR_KEYWORDS,
)


def _determine_result_details(description: str) -> dict:
    """
    根據打席的文字描述，解析出結構化的結果類型和得分。
    """
    result = {
        "result_type": AtBatResultType.UNSPECIFIED,
        "runs_scored_on_play": 0,
    }

    score_match = re.search(r"得(\d+)分", description)
    if score_match:
        result["runs_scored_on_play"] = int(score_match.group(1))

    # 【修改】使用從 constants.py 導入的常數進行判斷
    if any(k in description for k in PARSER_SACRIFICE_KEYWORDS):
        result["result_type"] = AtBatResultType.SACRIFICE
    elif any(k in description for k in PARSER_FC_KEYWORDS):
        result["result_type"] = AtBatResultType.FIELDERS_CHOICE
    elif any(k in description for k in PARSER_ERROR_KEYWORDS):
        result["result_type"] = AtBatResultType.ERROR
    elif any(k in description for k in PARSER_ON_BASE_KEYWORDS):
        result["result_type"] = AtBatResultType.ON_BASE
    elif any(k in description for k in PARSER_OUT_KEYWORDS):
        result["result_type"] = AtBatResultType.OUT

    return result


def parse_active_inning_details(inning_html_content, inning):
    """從單一局數的 HTML 內容中，解析出所有事件。"""
    if not inning_html_content:
        return []
    soup = BeautifulSoup(inning_html_content, "lxml")
    inning_events = []

    # [修改] 選擇器修正：只選擇打席的主容器，從根本上解決重複計算問題
    event_items = soup.select("div.item.play")
    for item in event_items:
        try:
            # [修改] 移除無用的 if/elif 結構，所有 item 都視為一個打席來處理
            event_data = {"inning": inning}
            event_data["type"] = "at_bat"  # 所有事件都從一個 at_bat 開始解析

            hitter_name_tag = item.select_one("div.player > a > span")
            desc_tag = item.select_one("div.info > div.desc")

            if not hitter_name_tag or not desc_tag:
                logging.warning("跳過一個缺少打者或描述的 item。")
                continue

            event_data["hitter_name"] = hitter_name_tag.text.strip()

            # 處理描述文字
            description_text = " ".join(desc_tag.stripped_strings)
            # 移除描述文字中固定的前綴，例如 "第4棒 DH 魔鷹："
            clean_desc = re.sub(
                r"^\s*第\d+棒\s+[A-Z0-9]+\s+[\w\s\.]+\s*：\s*",
                "",
                description_text,
            ).strip()
            event_data["description"] = clean_desc
            event_data["result_description_full"] = clean_desc

            # 根據描述判斷打席結果細節
            result_details = _determine_result_details(
                event_data["result_description_full"]
            )
            event_data.update(result_details)

            # 處理展開後的詳細投球數據
            pitch_detail_block = item.find("div", class_="detail")
            if pitch_detail_block:
                pitcher_name_tag = pitch_detail_block.select_one(
                    "div.detail_item.pitcher a"
                )
                if pitcher_name_tag:
                    event_data["opposing_pitcher_name"] = pitcher_name_tag.text.strip()

                pitch_sequence_tags = pitch_detail_block.select(
                    "div.detail_item[class*='pitch-'], div.detail_item.no-pitch"
                )
                pitch_list = []
                for tag in pitch_sequence_tags:
                    pitch_num_tag = tag.select_one("div.pitch_num span")
                    call_desc_tag = tag.select_one("div.call_desc")
                    pitches_count_tag = tag.select_one("div.pitches_count")
                    pitch_list.append(
                        {
                            "num": (
                                pitch_num_tag.text.strip() if pitch_num_tag else None
                            ),
                            "desc": (
                                call_desc_tag.text.strip() if call_desc_tag else None
                            ),
                            "count": (
                                pitches_count_tag.text.strip()
                                if pitches_count_tag
                                else None
                            ),
                        }
                    )
                if pitch_list:
                    event_data["pitch_sequence_details"] = json.dumps(
                        pitch_list, ensure_ascii=False
                    )

            inning_events.append(event_data)
        except Exception as e:
            logging.error(f"解析單一打席事件時出錯: {e}", exc_info=True)

    return inning_events
