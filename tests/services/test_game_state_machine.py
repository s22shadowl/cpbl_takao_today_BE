# tests/services/test_game_state_machine.py

import pytest
from unittest.mock import patch

from app.services.game_state_machine import GameStateMachine

MOCK_BOX_SCORE_DATA = [
    {"summary": {"player_name": "打者A"}},
    {"summary": {"player_name": "打者B"}},
    {"summary": {"player_name": "打者C"}},
    {"summary": {"player_name": "打者D"}},
]


@pytest.fixture
def state_machine():
    """提供一個 GameStateMachine 實例，已使用模擬資料初始化。"""
    return GameStateMachine(MOCK_BOX_SCORE_DATA)


def test_initialization(state_machine):
    """測試狀態機初始化是否正確。"""
    assert state_machine.player_pa_counter == {
        "打者A": 0,
        "打者B": 0,
        "打者C": 0,
        "打者D": 0,
    }
    assert state_machine.inning_state == {}


def test_enrich_events_happy_path(state_machine):
    """測試狀態機處理正常事件流時，能否正確計算並注入狀態。"""
    events = [
        {"inning": 1, "hitter_name": "打者A", "description": "飛球出局"},
        {"inning": 1, "hitter_name": "打者B", "description": "一壘安打"},
    ]

    with (
        patch("app.services.game_state_machine._update_outs_count") as mock_update_outs,
        patch(
            "app.services.game_state_machine._update_runners_state"
        ) as mock_update_runners,
    ):
        mock_update_outs.side_effect = [1, 1]
        mock_update_runners.side_effect = [[None, None, None], ["打者B", None, None]]

        enriched = state_machine.enrich_events_with_state(events)

    assert len(enriched) == 2
    # 事件 1
    assert enriched[0]["outs_before"] == 0
    assert enriched[0]["runners_on_base_before"] == "壘上無人"
    assert enriched[0]["sequence_in_game"] == 1
    # 事件 2
    assert enriched[1]["outs_before"] == 1
    assert enriched[1]["runners_on_base_before"] == "壘上無人"
    assert enriched[1]["sequence_in_game"] == 1  # 打者B 的第一個打席

    # 檢查最終狀態
    assert state_machine.inning_state[1]["outs"] == 1
    assert state_machine.inning_state[1]["runners"] == ["打者B", None, None]
    assert state_machine.player_pa_counter["打者A"] == 1
    assert state_machine.player_pa_counter["打者B"] == 1


def test_enrich_events_resets_state_after_3_outs(state_machine):
    """測試在三人出局後，狀態機能否為下一個事件重設狀態。"""
    events = [
        {"inning": 1, "hitter_name": "打者A", "description": "飛球出局"},
        {"inning": 1, "hitter_name": "打者B", "description": "飛球出局"},
        {"inning": 1, "hitter_name": "打者C", "description": "飛球出局，三人出局"},
        {"inning": 1, "hitter_name": "打者D", "description": "一壘安打"},
    ]

    with (
        patch("app.services.game_state_machine._update_outs_count") as mock_update_outs,
        patch(
            "app.services.game_state_machine._update_runners_state"
        ) as mock_update_runners,
    ):
        mock_update_outs.side_effect = [1, 2, 3, 0]  # 模擬出局數計算與重設
        mock_update_runners.return_value = [None, None, None]

        enriched = state_machine.enrich_events_with_state(events)

    assert enriched[0]["outs_before"] == 0
    assert enriched[1]["outs_before"] == 1
    assert enriched[2]["outs_before"] == 2
    assert enriched[3]["outs_before"] == 0  # 驗證狀態已重設


def test_enrich_events_handles_unseen_player(state_machine):
    """測試當出現未在初始名單中的球員時，狀態機能否正確處理。"""
    events = [{"inning": 1, "hitter_name": "代打E", "description": "安打"}]

    with (
        patch("app.services.game_state_machine._update_outs_count", return_value=0),
        patch(
            "app.services.game_state_machine._update_runners_state",
            return_value=[None, None, None],
        ),
    ):
        enriched = state_machine.enrich_events_with_state(events)

    assert "代打E" in state_machine.player_pa_counter
    assert state_machine.player_pa_counter["代打E"] == 1
    assert enriched[0]["sequence_in_game"] == 1
