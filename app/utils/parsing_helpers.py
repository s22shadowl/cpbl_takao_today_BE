# app/utils/parsing_helpers.py

# 【新增】此檔案用於存放通用的、無狀態的解析輔助函式。

from typing import Optional, List
from app.models import AtBatResultType  # 確保導入 Enum
from app.core.constants import (  # 導入 Box Score 結果分類
    HITS,
    WALKS,
    SACRIFICES,
    ALL_OUTS,
    FIELDERS_CHOICE,
    ERRORS,
)

from app.schemas import GameResult


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


def calculate_last_10_games_record(games: List[GameResult], team_name: str) -> str:
    """
    從最近的比賽列表中計算指定球隊的近十場戰績。

    :param games: GameResult 物件列表，需依比賽日期由新到舊排序。
    :param team_name: 要計算戰績的球隊名稱。
    :return: "勝-敗-和" 格式的字串，例如 "5-5-0"。
    """
    if not games:
        return "0-0-0"

    wins = 0
    losses = 0
    ties = 0

    games_to_consider = games[:10]

    for game in games_to_consider:
        if game.home_score is None or game.away_score is None:
            continue  # 跳過沒有分數、未完成的比賽

        is_home_team = game.home_team == team_name
        is_away_team = game.away_team == team_name

        # 如果比賽不包含該球隊，則跳過 (正常情況下不應發生)
        if not is_home_team and not is_away_team:
            continue

        if game.home_score == game.away_score:
            ties += 1
        elif (is_home_team and game.home_score > game.away_score) or (
            is_away_team and game.away_score > game.home_score
        ):
            wins += 1
        else:
            losses += 1

    return f"{wins}-{losses}-{ties}"


def calculate_current_streak(games: List[GameResult], team_name: str) -> str:
    """
    從最近的比賽列表中計算指定球隊的目前連勝/敗狀況。

    :param games: GameResult 物件列表，需依比賽日期由新到舊排序。
    :param team_name: 要計算近況的球隊名稱。
    :return: "X連勝" 或 "X連敗" 格式的字串。若上一場為和局則回傳 "中止"。
    """
    if not games:
        return "無"

    # 檢查最近一場比賽
    latest_game = games[0]
    if latest_game.home_score is None or latest_game.away_score is None:
        return "無"

    is_home_team = latest_game.home_team == team_name

    # 情況 1: 最近一場是和局，連勝/敗中止
    if latest_game.home_score == latest_game.away_score:
        return "中止"

    # 情況 2: 判斷最近一場是勝或敗，作為要計算的目標
    if (is_home_team and latest_game.home_score > latest_game.away_score) or (
        not is_home_team and latest_game.away_score > latest_game.home_score
    ):
        streak_type_to_track = "win"
    else:
        streak_type_to_track = "loss"

    streak_length = 0
    # 從最近的比賽開始往前追溯
    for game in games:
        if game.home_score is None or game.away_score is None:
            break  # 遇到未完成的比賽就停止計算

        is_home = game.home_team == team_name

        # 判斷當前這場比賽的結果
        current_game_result = ""
        if game.home_score == game.away_score:
            # 遇到和局，中斷計算
            break
        elif (is_home and game.home_score > game.away_score) or (
            not is_home and game.away_score > game.home_score
        ):
            current_game_result = "win"
        else:
            current_game_result = "loss"

        # 如果比賽結果與目標類型相符，計數器加一；否則中斷
        if current_game_result == streak_type_to_track:
            streak_length += 1
        else:
            break

    if streak_type_to_track == "win":
        return f"{streak_length}連勝"
    else:
        return f"{streak_length}連敗"
