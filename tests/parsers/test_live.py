# tests/parsers/test_live.py

import pytest
import json
from app.parsers import live
from app.models import AtBatResultType


@pytest.fixture
def active_inning_html_content():
    """
    提供一個更全面的 HTML fixture，涵蓋多種情境：
    1. 完整的打席，包含投球細節和一個非投球事件（投手牽制）。
    2. 只有基本結果的打席。
    3. 使用 'DH' 稱謂的打者，以測試更新後的正規表示式。
    4. [新增] 測試第二層得分邏輯的案例。
    5. 應被忽略的非打席事件（教練暫停）。
    6. 應被忽略的資訊不完整項目。
    """
    return """
    <div class="InningPlaysGroup">
        <div class="tab_container">
            <div class="tab_cont active">
                <div class="cont">
                    <div class="InningPlays">
                        <section class="top">
                            <header class="title">測試局數</header>

                            <!-- 案例 1: 完整打席，包含詳細投球過程與非投球事件 -->
                            <div class="item play">
                                <div class="player"><a href="#"><span>吳念庭</span></a></div>
                                <div class="info">
                                    <div class="desc">第3棒 3B 吳念庭： 擊出中外野方向飛球，二壘安打，帶有2分打點。</div>
                                    <div class="detail">
                                        <div class="detail_item pitcher">對戰投手： <a href="#">黃子鵬</a></div>
                                        <div class="detail_item pitch-1"><div class="pitch_num"><span>1</span></div><div class="call_desc">好球</div><div class="pitches_count">S:1 B:0</div></div>
                                        <div class="detail_item no-pitch"><div class="call_desc">投手牽制</div></div>
                                        <div class="detail_item pitch-2"><div class="pitch_num"><span>2</span></div><div class="call_desc">壞球</div><div class="pitches_count">S:1 B:1</div></div>
                                    </div>
                                </div>
                            </div>

                            <!-- 案例 2: 基本打席，無詳細投球過程 -->
                            <div class="item play">
                                <div class="player"><a href="#"><span>林立</span></a></div>
                                <div class="info">
                                    <div class="desc">第1棒 2B 林立： 四壞球。</div>
                                </div>
                            </div>

                            <!-- 案例 3: 測試正規表示式，打者描述包含 'DH' -->
                            <div class="item play">
                                <div class="player"><a href="#"><span>魔鷹</span></a></div>
                                <div class="info">
                                    <div class="desc">第4棒 DH 魔鷹： 擊出右外野方向陽春全壘打，帶有1分打點。</div>
                                </div>
                            </div>

                            <!-- 案例 4 (新增): 測試第二層得分邏輯 -->
                            <div class="item play">
                                <div class="player"><a href="#"><span>孔念恩</span></a></div>
                                <div class="info">
                                    <div class="desc">第9棒 SS 孔念恩： 因三壘手失誤上壘，二壘跑者回本壘得分。</div>
                                </div>
                            </div>

                            <!-- 案例 5: 非打席事件，應被忽略 -->
                            <div class="no-pitch-action-remind">教練暫停</div>

                            <!-- 案例 6: 資訊不完整的項目，應被忽略 -->
                            <div class="item play">
                                <div class="player"><a href="#"></a></div>
                                <div class="info">
                                    <div class="desc">資訊不完整的打席</div>
                                </div>
                            </div>
                        </section>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """


def test_parse_active_inning_details(active_inning_html_content):
    """
    【修改】驗證 parse_active_inning_details 的完整解析邏輯。
    - 確保只解析 'div.item.play'。
    - 驗證所有欄位，包括 is_score_from_description。
    - 確保能處理複雜的打者描述前綴。
    """
    inning_number = 5
    events = live.parse_active_inning_details(
        active_inning_html_content, inning=inning_number
    )

    # 應解析出 4 個打席事件
    assert len(events) == 4

    # --- 驗證第一個事件 (吳念庭) ---
    event1 = events[0]
    assert event1["inning"] == inning_number
    assert event1["type"] == "at_bat"
    assert event1["hitter_name"] == "吳念庭"
    assert event1["description"] == "擊出中外野方向飛球，二壘安打，帶有2分打點。"
    assert event1["opposing_pitcher_name"] == "黃子鵬"
    assert event1["runs_scored_on_play"] == 2
    assert event1["is_score_from_description"] is False
    assert event1["result_type"] == AtBatResultType.ON_BASE

    assert "pitch_sequence_details" in event1
    pitch_details = json.loads(event1["pitch_sequence_details"])
    assert len(pitch_details) == 3
    assert pitch_details[0] == {"num": "1", "desc": "好球", "count": "S:1 B:0"}
    assert pitch_details[1] == {"num": None, "desc": "投手牽制", "count": None}
    assert pitch_details[2] == {"num": "2", "desc": "壞球", "count": "S:1 B:1"}

    # --- 驗證第二個事件 (林立) ---
    event2 = events[1]
    assert event2["hitter_name"] == "林立"
    assert event2["description"] == "四壞球。"
    assert event2["runs_scored_on_play"] == 0
    assert event2["is_score_from_description"] is False
    assert event2["result_type"] == AtBatResultType.ON_BASE
    assert "opposing_pitcher_name" not in event2
    assert "pitch_sequence_details" not in event2

    # --- 驗證第三個事件 (魔鷹) ---
    event3 = events[2]
    assert event3["hitter_name"] == "魔鷹"
    assert event3["description"] == "擊出右外野方向陽春全壘打，帶有1分打點。"
    assert event3["runs_scored_on_play"] == 1
    assert event3["is_score_from_description"] is False
    assert event3["result_type"] == AtBatResultType.ON_BASE

    # --- 驗證第四個事件 (孔念恩) ---
    event4 = events[3]
    assert event4["hitter_name"] == "孔念恩"
    assert event4["description"] == "因三壘手失誤上壘，二壘跑者回本壘得分。"
    assert event4["runs_scored_on_play"] == 1
    assert event4["is_score_from_description"] is True
    assert event4["result_type"] == AtBatResultType.ERROR


def test_parse_active_inning_details_empty_input():
    assert live.parse_active_inning_details(None, 1) == []
    assert live.parse_active_inning_details("", 1) == []


@pytest.mark.parametrize(
    "description, expected_type, expected_runs, expected_is_from_desc",
    [
        # Layer 1: 帶有「打點」的案例
        ("擊出右外野方向陽春全壘打，帶有1分打點。", AtBatResultType.ON_BASE, 1, False),
        (
            "擊出中外野方向飛球，二壘安打，帶有2分打點。",
            AtBatResultType.ON_BASE,
            2,
            False,
        ),
        (
            "擊出高飛犧牲打，三壘跑者回本壘得分，帶有1分打點。",
            AtBatResultType.SACRIFICE,
            1,
            False,
        ),
        # Layer 2: 帶有「回本壘得分」的案例
        ("三壘跑者因游擊手失誤回本壘得分。", AtBatResultType.ERROR, 1, True),
        (
            "投手暴投，二壘跑者王柏融回本壘得分、三壘跑者魔鷹回本壘得分。",  # [修正] 測試案例文字
            AtBatResultType.UNSPECIFIED,
            2,
            True,
        ),
        ("犧牲觸擊，跑者回本壘得分，2出局。", AtBatResultType.SACRIFICE, 1, True),
        # 其他案例
        ("遭到三振，1出局。", AtBatResultType.OUT, 0, False),
        ("擊出游擊方向滾地球，形成雙殺，3出局。", AtBatResultType.OUT, 0, False),
        ("四壞球保送。", AtBatResultType.ON_BASE, 0, False),
        ("因投手失誤上壘。", AtBatResultType.ERROR, 0, False),
        (
            "擊出投手前滾地球，經野手選擇上一壘。",
            AtBatResultType.FIELDERS_CHOICE,
            0,
            False,
        ),
        ("這是一段沒有關鍵字的描述。", AtBatResultType.UNSPECIFIED, 0, False),
    ],
)
def test_determine_result_details(
    description, expected_type, expected_runs, expected_is_from_desc
):
    """【修改】測試 _determine_result_details 函式能否正確解析並標記得分來源。"""
    result = live._determine_result_details(description)
    assert result["result_type"] == expected_type
    assert result["runs_scored_on_play"] == expected_runs
    assert result["is_score_from_description"] == expected_is_from_desc
