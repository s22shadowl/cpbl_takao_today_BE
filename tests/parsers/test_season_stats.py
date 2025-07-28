# tests/parsers/test_season_stats.py

from app.parsers import season_stats
from app.config import settings
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# --- Fixtures ---


@pytest.fixture
def team_score_html_content():
    teamscore_file = FIXTURES_DIR / "team_score_page.html"
    if not teamscore_file.exists():
        pytest.skip("測試素材 team_score_page.html 不存在，跳過相關測試。")
    return teamscore_file.read_text(encoding="utf-8")


def test_parse_season_stats_page(team_score_html_content):
    """【修改】驗證函式能解析出所有球員，而不只是特定目標球員"""
    result = season_stats.parse_season_stats_page(team_score_html_content)
    assert isinstance(result, list)
    # 斷言解析出的球員數量應大於等於我們已知的目標球員數量
    assert len(result) >= len(settings.TARGET_PLAYER_NAMES)

    # 驗證所有已知的目標球員都包含在解析結果中
    parsed_player_names = {p["player_name"] for p in result}
    assert set(settings.TARGET_PLAYER_NAMES).issubset(parsed_player_names)
