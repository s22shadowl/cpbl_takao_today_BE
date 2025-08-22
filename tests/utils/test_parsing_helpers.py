# tests/utils/test_parsing_helpers.py

import pytest
from app.utils.parsing_helpers import is_formal_pa

# 【新增 T19】為 is_formal_pa 建立獨立的、完整的測試案例


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
