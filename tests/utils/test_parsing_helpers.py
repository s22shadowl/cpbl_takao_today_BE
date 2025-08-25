# tests/utils/test_parsing_helpers.py

import pytest
from app.utils.parsing_helpers import is_formal_pa, map_result_short_to_type
from app.models import AtBatResultType

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


# --- [新增] 測試 map_result_short_to_type ---


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
