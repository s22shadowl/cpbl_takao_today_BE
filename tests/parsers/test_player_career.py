# tests/parsers/test_player_career.py

import pytest
from pathlib import Path
import datetime

from app.parsers import player_career

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# --- Fixtures ---


@pytest.fixture
def player_career_html_content():
    """讀取球員生涯頁面的 HTML 測試素材。"""
    career_page_file = FIXTURES_DIR / "player_career_page.html"
    if not career_page_file.exists():
        pytest.skip("測試素材 player_career_page.html 不存在，跳過相關測試。")
    return career_page_file.read_text(encoding="utf-8")


@pytest.fixture
def player_career_html_content_minimal():
    """提供一個僅包含基本資訊，但沒有 CAREER STATS 表格的 HTML。"""
    return """
    <div class="PlayerBrief">
        <dd class="debut">
            <div class="desc">2015/09/02</div>
        </dd>
    </div>
    """


# --- 測試案例 ---


def test_parse_player_career_page_with_full_data(player_career_html_content):
    """測試解析包含完整資料的 HTML 頁面。"""
    result = player_career.parse_player_career_page(player_career_html_content)

    assert result is not None
    assert isinstance(result, dict)

    # 驗證基本資訊
    assert result["debut_date"] == datetime.date(2015, 9, 2)
    assert result["handedness"] == "右投左打"

    # 驗證生涯總計數據 (抽樣)
    assert result["games_played"] == 568
    assert result["plate_appearances"] == 2524
    assert result["homeruns"] == 95
    assert result["avg"] == 0.350
    assert result["ops"] == 0.993
    assert result["ops_plus"] == 159.59
    assert result["intentional_walks"] == 31  # 驗證 '（故四）' 欄位能正確解析


def test_parse_player_career_page_with_empty_html():
    """測試當傳入空字串時，函式應回傳 None。"""
    result = player_career.parse_player_career_page("")
    assert result is None


def test_parse_player_career_page_with_invalid_html():
    """測試當傳入無效 HTML 時，函式應回傳 None。"""
    result = player_career.parse_player_career_page("<div><p>invalid</div>")
    assert result is None


def test_parse_player_career_page_with_minimal_data(player_career_html_content_minimal):
    """測試當 HTML 缺少 CAREER STATS 表格時，仍能解析出基本資訊。"""
    result = player_career.parse_player_career_page(player_career_html_content_minimal)
    assert result is not None
    assert result["debut_date"] == datetime.date(2015, 9, 2)
    # 應不包含 handedness 因為 fixture 中沒有
    assert "handedness" not in result
    # 應不包含任何表格數據
    assert "games_played" not in result
