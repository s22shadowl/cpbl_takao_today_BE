# app/services/game_state_machine.py

import logging
from typing import List, Dict

# 這些函式是核心的狀態轉換邏輯，從 utils 模組中引入
from app.utils.state_machine import _update_outs_count, _update_runners_state

logger = logging.getLogger(__name__)


class GameStateMachine:
    """
    封裝比賽狀態計算邏輯的狀態機。

    負責根據事件流，依序計算每個事件發生前的出局數、壘包狀態，
    並追蹤球員的打席順序。
    """

    def __init__(self, all_players_data: List[dict]):
        """
        初始化狀態機。

        Args:
            all_players_data (List[dict]): 從 Box Score 解析出的所有球員基本資料，
                                          用於初始化球員打席計數器。
        """
        self.inning_state: Dict[int, dict] = {}
        self.player_pa_counter: Dict[str, int] = {
            p["summary"]["player_name"]: 0 for p in all_players_data
        }

    def enrich_events_with_state(self, events: List[dict]) -> List[dict]:
        """
        接收原始事件列表，為每個事件注入計算後的狀態，並回傳豐富化後的列表。

        Args:
            events (List[dict]): 從 Live Text 解析出的原始事件列表。

        Returns:
            List[dict]: 每個事件都包含了 `outs_before`, `runners_on_base_before`,
                        和 `sequence_in_game` 的新列表。
        """
        enriched_events = []

        for event in events:
            inning = event.get("inning")
            if not inning:
                enriched_events.append(event)
                continue

            # 1. 取得或初始化當前半局的狀態
            if inning not in self.inning_state:
                self.inning_state[inning] = {"outs": 0, "runners": [None, None, None]}

            # 如果出局數滿了，重置半局狀態 (換邊)
            if self.inning_state[inning]["outs"] >= 3:
                self.inning_state[inning]["outs"] = 0
                self.inning_state[inning]["runners"] = [None, None, None]

            current_outs = self.inning_state[inning]["outs"]
            current_runners = self.inning_state[inning]["runners"]

            # 2. 為當前事件注入「發生前」的狀態
            event["outs_before"] = current_outs
            runners_str_list = [
                base
                for base, runner in zip(["一壘", "二壘", "三壘"], current_runners)
                if runner
            ]
            event["runners_on_base_before"] = (
                "、".join(runners_str_list) + "有人" if runners_str_list else "壘上無人"
            )

            # 3. 更新球員打席順序
            hitter = event.get("hitter_name")
            if hitter:
                if hitter not in self.player_pa_counter:
                    self.player_pa_counter[hitter] = 0
                self.player_pa_counter[hitter] += 1
                event["sequence_in_game"] = self.player_pa_counter[hitter]

            enriched_events.append(event)

            # 4. 根據事件描述，計算「發生後」的新狀態
            desc = event.get("description", "")
            new_outs = _update_outs_count(desc, current_outs)
            new_runners = _update_runners_state(current_runners, hitter, desc)

            # 5. 更新狀態機內部狀態，供下一個事件使用
            self.inning_state[inning]["outs"] = new_outs
            self.inning_state[inning]["runners"] = new_runners

        return enriched_events
