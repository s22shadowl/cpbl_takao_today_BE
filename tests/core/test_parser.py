# tests/core/test_parser.py

import pytest
from pathlib import Path
from app.core import parser
from app.models import AtBatResultType  # 【新增】匯入 Enum

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# --- Fixtures ---


@pytest.fixture
def schedule_html_content():
    schedule_file = FIXTURES_DIR / "schedule_page.html"
    if not schedule_file.exists():
        pytest.skip("測試素材 schedule_page.html 不存在，跳過相關測試。")
    return schedule_file.read_text(encoding="utf-8")


@pytest.fixture
def team_score_html_content():
    teamscore_file = FIXTURES_DIR / "team_score_page.html"
    if not teamscore_file.exists():
        pytest.skip("測試素材 team_score_page.html 不存在，跳過相關測試。")
    return teamscore_file.read_text(encoding="utf-8")


@pytest.fixture
def box_score_html_content():
    box_score_file = FIXTURES_DIR / "box_score_page.html"
    if not box_score_file.exists():
        pytest.skip("測試素材 box_score_page.html 不存在，跳過相關測試。")
    return box_score_file.read_text(encoding="utf-8")


@pytest.fixture
def active_inning_html_content():
    return """
    <div class="InningPlaysGroup">
        <div class="tab_container">
            <div class="tab_cont active">
                <div class="cont">
                    <div class="InningPlays">
                        <section class="top">
                            <header class="title">測試局數</header>

                            <div class="item play">
                                <div class="player"><a href="#"><span>吳念庭</span></a></div>
                                <div class="info">
                                    <div class="desc">第3棒 3B 吳念庭： 擊出中外野方向飛球，二壘安打，帶有2分打點，得2分。</div>
                                    <div class="detail">
                                        <div class="detail_item pitcher">對戰投手： <a href="#">黃子鵬</a></div>
                                        <div class="detail_item pitch-1"><div class="pitch_num"><span>1</span></div><div class="call_desc">好球</div><div class="pitches_count">S:1 B:0</div></div>
                                    </div>
                                </div>
                            </div>

                            <div class="item play">
                                <div class="player"><a href="#"><span>林立</span></a></div>
                                <div class="info">
                                    <div class="desc">第1棒 2B 林立： 四壞球。</div>
                                </div>
                            </div>

                            <div class="no-pitch-action-remind">教練暫停</div>

                            <div class="item play">
                                <div class="player"><span></span></div>
                                <div class="info">
                                    <div class="desc">資訊不完整的打席</div>
                                    <div class="detail"></div>
                                </div>
                            </div>
                        </section>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """


# --- 測試案例 ---


def test_parse_schedule_page(schedule_html_content):
    result = parser.parse_schedule_page(schedule_html_content, year=2025)
    assert isinstance(result, list)
    assert len(result) > 0


def test_parse_season_stats_page(team_score_html_content):
    result = parser.parse_season_stats_page(team_score_html_content)
    assert isinstance(result, list)
    assert len(result) == 3


def test_parse_box_score_page(box_score_html_content):
    result = parser.parse_box_score_page(box_score_html_content)
    assert isinstance(result, list)
    assert len(result) == 3


def test_parse_active_inning_details(active_inning_html_content):
    """【修改】驗證 parse_active_inning_details 的完整解析邏輯，包含新欄位"""
    inning_number = 5
    events = parser.parse_active_inning_details(
        active_inning_html_content, inning=inning_number
    )

    # 應解析出兩個 at_bat 事件
    assert len(events) == 2

    # --- 驗證第一個事件 (吳念庭) ---
    event1 = events[0]
    assert event1["inning"] == inning_number
    assert event1["hitter_name"] == "吳念庭"
    assert event1["opposing_pitcher_name"] == "黃子鵬"
    # 【新增】驗證新欄位
    assert event1["runs_scored_on_play"] == 2
    assert event1["result_type"] == AtBatResultType.ON_BASE

    # --- 驗證第二個事件 (林立) ---
    event2 = events[1]
    assert event2["hitter_name"] == "林立"
    # 【新增】驗證新欄位
    assert event2["runs_scored_on_play"] == 0
    assert event2["result_type"] == AtBatResultType.ON_BASE


# 【新增】針對 _determine_result_details 輔助函式的參數化測試
@pytest.mark.parametrize(
    "description, expected_type, expected_runs",
    [
        ("擊出右外野方向陽春全壘打，帶有1分打點，得1分。", AtBatResultType.ON_BASE, 1),
        ("遭到三振，1出局。", AtBatResultType.OUT, 0),
        ("擊出游擊方向滾地球，形成雙殺，3出局。", AtBatResultType.OUT, 0),
        ("四壞球保送。", AtBatResultType.ON_BASE, 0),
        ("犧牲觸擊，跑者上二壘，2出局。", AtBatResultType.SACRIFICE, 0),
        ("投手暴投，跑者回本壘得分，得1分。", AtBatResultType.UNSPECIFIED, 1),
        ("因投手失誤上壘。", AtBatResultType.ERROR, 0),
        ("擊出投手前滾地球，經野手選擇上一壘。", AtBatResultType.FIELDERS_CHOICE, 0),
        ("這是一段沒有關鍵字的描述。", AtBatResultType.UNSPECIFIED, 0),
    ],
)
def test_determine_result_details(description, expected_type, expected_runs):
    """測試 _determine_result_details 函式能否正確解析各種文字描述。"""
    result = parser._determine_result_details(description)
    assert result["result_type"] == expected_type
    assert result["runs_scored_on_play"] == expected_runs
