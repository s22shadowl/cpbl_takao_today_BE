# app/utils/parsing_helpers.py

# 【新增】此檔案用於存放通用的、無狀態的解析輔助函式。

from typing import Optional
from app.models import AtBatResultType  # 確保導入 Enum
from app.core.constants import (  # 導入 Box Score 結果分類
    HITS,
    WALKS,
    SACRIFICES,
    ALL_OUTS,
    FIELDERS_CHOICE,
    ERRORS,
)


def is_formal_pa(event_description: str) -> bool:
    """
    【T19】根據事件描述判斷這是否為一個正式的打席 (PA)。
    一個啟發式的方法：如果描述中包含某些明確的非打席關鍵字，
    且不包含打擊結果的關鍵字，則判定為非正式打席。

    Args:
        event_description (str): 從 live text 解析出的事件描述文字。

    Returns:
        bool: 如果是正式打席則回傳 True，否則回傳 False。
    """
    if not event_description:
        return True  # 假設沒有描述就是一個常規打席

    non_pa_keywords = [
        "牽制",
        "盜壘",
        "暴投",
        "捕逸",
        "投手犯規",
        "更換投手",
        "更換代打",
        "更換代跑",
        "暫停",
    ]

    pa_keywords = [
        "安打",
        "全壘打",
        "三振",
        "保送",
        "飛球",
        "滾地",
        "犧牲",
        "妨礙",
        "失誤",
        "不死三振",
        "妨礙打擊",
        "觸身",
    ]

    # 如果描述包含非打席關鍵字，且不包含任何打席關鍵字，則判定為非打席事件
    if any(keyword in event_description for keyword in non_pa_keywords) and not any(
        keyword in event_description for keyword in pa_keywords
    ):
        return False

    return True


def map_result_short_to_type(result_short: str) -> Optional[AtBatResultType]:
    """
    [新增] 將 Box Score 的 result_short 字串映射到 AtBatResultType Enum。
    """
    if result_short in HITS or result_short in WALKS:
        return AtBatResultType.ON_BASE
    if result_short in ALL_OUTS:
        return AtBatResultType.OUT
    if result_short in SACRIFICES:
        return AtBatResultType.SACRIFICE
    if result_short in FIELDERS_CHOICE:
        return AtBatResultType.FIELDERS_CHOICE
    if result_short in ERRORS:
        return AtBatResultType.ERROR
    return None
