# app/utils/parsing_helpers.py

# 【新增】此檔案用於存放通用的、無狀態的解析輔助函式。


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
