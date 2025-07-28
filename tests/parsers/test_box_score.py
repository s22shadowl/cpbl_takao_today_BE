# tests/parsers/test_box_score.py

from app.parsers import box_score
from app.config import settings
from pathlib import Path
import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def box_score_html_content():
    box_score_file = FIXTURES_DIR / "box_score_page.html"
    if not box_score_file.exists():
        pytest.skip("測試素材 box_score_page.html 不存在，跳過相關測試。")
    return box_score_file.read_text(encoding="utf-8")


def test_parse_box_score_page(box_score_html_content):
    """【修改】驗證函式能解析出所有球員，並可透過參數篩選"""
    # 案例一：不帶參數，應解析出所有球員
    result_all = box_score.parse_box_score_page(box_score_html_content)
    assert isinstance(result_all, list)
    assert len(result_all) > len(
        settings.TARGET_PLAYER_NAMES
    )  # 假定 fixture 中有更多球員

    # 案例二：帶入參數，只解析指定球隊的球員
    # 【修正】將目標球隊改為從 settings 動態讀取
    target_team = settings.TARGET_TEAMS[0]
    result_filtered = box_score.parse_box_score_page(
        box_score_html_content, target_teams=[target_team]
    )
    assert isinstance(result_filtered, list)
    assert len(result_filtered) > 0
    assert all(p["summary"]["team_name"] == target_team for p in result_filtered)
