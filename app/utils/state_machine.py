import re


def _update_outs_count(description, current_outs):
    """規則 2: 根據文字描述更新出局數"""
    outs_match = re.search(r"(\d)人出局", description)
    if outs_match:
        return int(outs_match.group(1))
    return current_outs


def _update_runners_state(current_runners, hitter_name, description):
    """【最終版】規則 3: 根據文字描述更新跑者狀態，並分離跑者與打者的處理邏輯"""
    runners = list(current_runners)

    # --- 第一階段：只處理壘上跑者的移動 ---
    if runners[2] and re.search(r"三壘跑者.*?回本壘得分", description):
        runners[2] = None
    if runners[1]:
        if re.search(r"二壘跑者.*?上三壘", description):
            runners[2] = runners[1]
            runners[1] = None
        elif re.search(r"二壘跑者.*?回本壘得分", description):
            runners[1] = None
    if runners[0]:
        if re.search(r"一壘跑者.*?上三壘", description):
            runners[2] = runners[0]
            runners[0] = None
        elif re.search(r"一壘跑者.*?上二壘", description):
            runners[1] = runners[0]
            runners[0] = None
        elif re.search(r"一壘跑者.*?回本壘得分", description):
            runners[0] = None

    # --- 第二階段：只處理打者自己的上壘位置 ---
    if "失誤上" in description:
        if "上二壘" in description:
            runners[1] = hitter_name
        elif "上三壘" in description:
            runners[2] = hitter_name
        else:
            runners[0] = hitter_name
    elif any(
        keyword in description
        for keyword in ["一壘安打", "內野安打", "四壞球", "觸身死球"]
    ):
        runners[0] = hitter_name
    elif "二壘安打" in description:
        runners[1] = hitter_name
    elif "三壘安打" in description:
        runners[2] = hitter_name
    return runners
