# tests/utils/test_parsing_helpers.py

import pytest
from datetime import date
from app.utils.parsing_helpers import (
    is_formal_pa,
    map_result_short_to_type,
    calculate_last_10_games_record,
    calculate_current_streak,
)
from app.models import AtBatResultType
from app.schemas import GameResult


# --- 測試 is_formal_pa ---


@pytest.mark.parametrize(
    "description, expected",
    [
        # --- 應判定為「正式打席」的案例 ---
        ("擊出右外野滾地球，二壘安打 。", True),
        ("遭到三振。", True),
        ("四壞球保送。", True),
        ("擊出中外野高飛球，打者-中外野手 飛球接殺出局。", True),
        ("擊出游擊方向滾地球，打者-游擊手 滾地傳一壘刺殺出局。", True),
        ("犧牲短打。犧牲觸擊。", True),
        ("擊出投手前滾地球，造成對手失誤。", True),
        ("", True),  # 空字串應視為正常打席
        ("觸身球保送", True),
        # --- 應判定為「非正式打席」的案例 ---
        ("二壘跑者王博玄出局-牽制 3人出局。", False),
    ],
)
def test_is_formal_pa(description, expected):
    """
    測試 is_formal_pa 函式是否能根據各種事件描述，正確判斷其是否為正式打席。
    """
    assert is_formal_pa(description) == expected


# --- 測試 map_result_short_to_type ---


@pytest.mark.parametrize(
    "result_short, expected_type",
    [
        # Hits and Walks -> ON_BASE
        ("一安", AtBatResultType.ON_BASE),
        ("全打", AtBatResultType.ON_BASE),
        ("四壞", AtBatResultType.ON_BASE),
        ("故四", AtBatResultType.ON_BASE),
        # Outs -> OUT
        ("三振", AtBatResultType.OUT),
        ("游滾", AtBatResultType.OUT),
        ("雙殺", AtBatResultType.OUT),
        # Sacrifices -> SACRIFICE
        ("犧短", AtBatResultType.SACRIFICE),
        ("犧飛", AtBatResultType.SACRIFICE),
        # Fielder's Choice -> FIELDERS_CHOICE
        ("野選", AtBatResultType.FIELDERS_CHOICE),
        # Errors -> ERROR
        ("一失", AtBatResultType.ERROR),
        ("犧飛誤", AtBatResultType.ERROR),
        # Unmapped cases
        ("未知", None),
        ("無", None),
        ("", None),
        ("妨礙打擊", None),  # 尚未對應的類型
    ],
)
def test_map_result_short_to_type(result_short, expected_type):
    """
    測試 map_result_short_to_type 函式能否將 result_short 字串正確映射到 AtBatResultType。
    """
    assert map_result_short_to_type(result_short) == expected_type


# --- 【新增】測試 calculate_last_10_games_record ---


# 輔助函式，用於建立 GameResult 假資料
def create_mock_game(
    home_team, away_team, home_score, away_score, game_date=date(2025, 1, 1)
):
    return GameResult(
        id=1,
        game_date=game_date,
        home_team=home_team,
        away_team=away_team,
        home_score=home_score,
        away_score=away_score,
    )


def test_calculate_last_10_games_record():
    team_name = "測試隊"

    # 情境 1: 基本案例 (2勝1敗1和)
    games1 = [
        create_mock_game(team_name, "B隊", 5, 3),  # 勝
        create_mock_game("C隊", team_name, 2, 1),  # 敗
        create_mock_game(team_name, "D隊", 4, 4),  # 和
        create_mock_game("E隊", team_name, 0, 8),  # 勝
    ]
    assert calculate_last_10_games_record(games1, team_name) == "2-1-1"

    # 情境 2: 空列表
    assert calculate_last_10_games_record([], team_name) == "0-0-0"

    # 情境 3: 超過10場比賽，只應計算最近10場 (5勝5敗)
    games3 = [create_mock_game(team_name, "X", 1, 0) for _ in range(5)] + [
        create_mock_game(team_name, "Y", 0, 1) for _ in range(7)
    ]  # 5勝7敗
    assert calculate_last_10_games_record(games3, team_name) == "5-5-0"

    # 情境 4: 包含未完成比賽 (應忽略)
    games4 = [
        create_mock_game(team_name, "B隊", 5, 3),  # 勝
        create_mock_game(team_name, "C隊", None, None),  # 忽略
        create_mock_game("D隊", team_name, 2, 1),  # 敗
    ]
    assert calculate_last_10_games_record(games4, team_name) == "1-1-0"


# --- 【新增】測試 calculate_current_streak ---


def test_calculate_current_streak():
    team_name = "測試隊"

    # 情境 1: 3連勝
    games1 = [
        create_mock_game(team_name, "A", 5, 3),  # W
        create_mock_game("B", team_name, 2, 4),  # W
        create_mock_game(team_name, "C", 1, 0),  # W
        create_mock_game(team_name, "D", 2, 5),  # L (中斷點)
    ]
    assert calculate_current_streak(games1, team_name) == "3連勝"

    # 情境 2: 2連敗
    games2 = [
        create_mock_game(team_name, "A", 3, 5),  # L
        create_mock_game("B", team_name, 4, 2),  # L
        create_mock_game(team_name, "C", 1, 0),  # W (中斷點)
    ]
    assert calculate_current_streak(games2, team_name) == "2連敗"

    # 情境 3: 最近一場是和局
    games3 = [
        create_mock_game(team_name, "A", 5, 5),  # T
        create_mock_game(team_name, "B", 1, 0),  # W
    ]
    assert calculate_current_streak(games3, team_name) == "中止"

    # 情境 4: 連勝被和局中斷
    games4 = [
        create_mock_game(team_name, "A", 5, 3),  # W
        create_mock_game(team_name, "B", 2, 0),  # W
        create_mock_game(team_name, "C", 4, 4),  # T (中斷點)
        create_mock_game(team_name, "D", 8, 1),  # W
    ]
    assert calculate_current_streak(games4, team_name) == "2連勝"

    # 情境 5: 空列表或最近一場未完成
    assert calculate_current_streak([], team_name) == "無"
    games5 = [create_mock_game(team_name, "A", None, None)]
    assert calculate_current_streak(games5, team_name) == "無"

    # 情境 6: 只有一場比賽
    games6_win = [create_mock_game(team_name, "A", 5, 3)]
    assert calculate_current_streak(games6_win, team_name) == "1連勝"
    games6_loss = [create_mock_game(team_name, "A", 3, 5)]
    assert calculate_current_streak(games6_loss, team_name) == "1連敗"
