# tests/core/test_parser.py

import pytest
import json
from pathlib import Path
from app.core import parser

# 獲取測試素材檔案的路徑
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# --- 通用的 HTML Fixtures ---


@pytest.fixture
def schedule_html_content():
    """一個 pytest fixture，用於讀取賽程頁面的 HTML 檔案內容。"""
    schedule_file = FIXTURES_DIR / "schedule_page.html"
    if not schedule_file.exists():
        pytest.skip("測試素材 schedule_page.html 不存在，跳過相關測試。")
    return schedule_file.read_text(encoding="utf-8")


@pytest.fixture
def team_score_html_content():
    """一個 pytest fixture，用於讀取球隊成績頁面的 HTML 檔案內容。"""
    teamscore_file = FIXTURES_DIR / "team_score_page.html"
    if not teamscore_file.exists():
        pytest.skip("測試素材 team_score_page.html 不存在，跳過相關測試。")
    return teamscore_file.read_text(encoding="utf-8")


@pytest.fixture
def box_score_html_content():
    """一個 pytest fixture，用於讀取 Box Score 頁面的 HTML 檔案內容。"""
    box_score_file = FIXTURES_DIR / "box_score_page.html"
    if not box_score_file.exists():
        pytest.skip("測試素材 box_score_page.html 不存在，跳過相關測試。")
    return box_score_file.read_text(encoding="utf-8")


@pytest.fixture
def active_inning_html_content():
    """
    【重新設計的 Fixture】
    此 HTML 包含多種情境，用於對 parse_active_inning_details 進行全面的單元測試。
    """
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
                                    <div class="desc">第3棒 3B 吳念庭： 擊出中外野方向飛球，出局。</div>
                                    <div class="detail">
                                        <div class="detail_item pitcher">對戰投手： <a href="#">黃子鵬</a></div>
                                        <div class="detail_item pitch-1">
                                            <div class="pitch_num"><span>1</span></div>
                                            <div class="call_desc">好球</div>
                                            <div class="pitches_count">S:1 B:0</div>
                                        </div>
                                        <div class="detail_item pitch-2">
                                            <div class="pitch_num"><span>2</span></div>
                                            <div class="call_desc">壞球</div>
                                            <div class="pitches_count">S:1 B:1</div>
                                        </div>
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
    """
    【重新設計的測試】
    對 parse_active_inning_details 進行全面的功能與邏輯驗證。
    """
    # 執行解析
    inning_number = 5
    events = parser.parse_active_inning_details(
        active_inning_html_content, inning=inning_number
    )

    # --- 1. 總體結構驗證 ---
    # 驗證回傳型別為列表
    assert isinstance(events, list)
    # 根據測試資料和函式邏輯，只有「案例1」會被解析，故列表長度應為 1
    assert len(events) == 1

    # --- 2. 詳細內容驗證 ---
    # 取得唯一的事件物件
    parsed_event = events[0]

    # 驗證字典的 Key 是否都存在
    expected_keys = [
        "inning",
        "type",
        "hitter_name",
        "description",
        "result_description_full",
        "opposing_pitcher_name",
        "pitch_sequence_details",
    ]
    for key in expected_keys:
        assert key in parsed_event

    # 驗證各欄位內容的正確性
    assert parsed_event["inning"] == inning_number
    assert parsed_event["type"] == "at_bat"
    assert parsed_event["hitter_name"] == "吳念庭"
    assert parsed_event["description"] == "擊出中外野方向飛球，出局。"
    assert parsed_event["opposing_pitcher_name"] == "黃子鵬"

    # --- 3. JSON 內容驗證 ---
    # 驗證 pitch_sequence_details 是一個 JSON 字串
    assert isinstance(parsed_event["pitch_sequence_details"], str)

    # 解析 JSON 字串以進行深度內容驗證
    pitch_sequence = json.loads(parsed_event["pitch_sequence_details"])

    # 驗證解析後的物件型別和長度
    assert isinstance(pitch_sequence, list)
    assert len(pitch_sequence) == 2

    # 驗證第一顆球的細節
    first_pitch = pitch_sequence[0]
    assert first_pitch["num"] == "1"
    assert first_pitch["desc"] == "好球"
    assert first_pitch["count"] == "S:1 B:0"

    # 驗證第二顆球的細節
    second_pitch = pitch_sequence[1]
    assert second_pitch["num"] == "2"
    assert second_pitch["desc"] == "壞球"
    assert second_pitch["count"] == "S:1 B:1"
