import pytest
from app.utils.state_machine import _update_outs_count, _update_runners_state


# --- 測試 _update_outs_count 函式 ---
@pytest.mark.parametrize(
    "description, current_outs, expected",
    [
        ("擊出右外野高飛球， 打者-右外野手 飛球接殺出局。 1人出局。", 0, 1),
        ("擊出內野滾地球，... 2人出局。", 1, 2),
        ("三振。 3人出局。", 2, 3),
    ],
    ids=[
        "1_out_from_0",
        "2_outs_from_1",
        "3_outs_from_2",
    ],
)
def test_update_outs_count(description, current_outs, expected):
    """測試根據文字描述更新出局數的各種情境。"""
    assert _update_outs_count(description, current_outs) == expected


# --- 測試 _update_runners_state 函式 ---
@pytest.mark.parametrize(
    "runners_before, hitter, description, expected_runners_after",
    [
        # --- 基本安打與保送 ---
        (
            [None, None, None],
            "打者A",
            "擊出右外野滾地球，一壘安打 。",
            ["打者A", None, None],
        ),
        (
            [None, None, None],
            "打者A",
            "擊出左外野平飛球，二壘安打 。",
            [None, "打者A", None],
        ),
        (
            [None, None, None],
            "打者A",
            "擊出中外野深遠飛球，三壘安打 。",
            [None, None, "打者A"],
        ),
        ([None, None, None], "打者A", "獲得一個四壞球保送", ["打者A", None, None]),
        # --- 跑者推進 & 打者上壘 ---
        (
            ["跑者B", None, None],
            "打者A",
            "擊出一壘安打，一壘跑者跑者B上二壘。",
            ["打者A", "跑者B", None],
        ),
        # --- 僅有「安打」不算是正規關鍵字 ---
        (
            ["跑者B", "跑者C", None],
            "打者A",
            "擊出安打。二壘跑者跑者C 上三壘。一壘跑者跑者B 上二壘。",
            [None, "跑者B", "跑者C"],
        ),
        # --- 【新增】失誤優先級測試 ---
        # 只有失誤
        ([None, None, None], "打者A", "因投手傳球失誤上一壘", ["打者A", None, None]),
        # 同時有安打和失誤，應以失誤結果為準
        (
            ["跑者B", None, None],
            "打者A",
            "擊出一壘安打，但因外野手失誤，打者上二壘；一壘跑者跑者B上三壘。",
            ["打者A", None, "跑者B"],
        ),
    ],
    ids=[
        # --- 原有案例 ---
        "hitter_to_1B_bases_empty",
        "hitter_to_2B_bases_empty",
        "hitter_to_3B_bases_empty",
        "walk_bases_empty",
        "hit_runner_from_1st_to_2nd",
        "hit_runners_from_1st2nd_to_2nd3rd",
        # --- 新增案例 ---
        "error_hitter_to_1B",
        "hit_plus_error_hitter_to_2nd",
    ],
)
def test_update_runners_state(
    runners_before, hitter, description, expected_runners_after
):
    """測試根據文字描述更新跑者狀態的各種情境。"""
    assert (
        _update_runners_state(runners_before, hitter, description)
        == expected_runners_after
    )
