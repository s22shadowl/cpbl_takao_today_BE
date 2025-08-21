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
    """驗證函式能解析出所有球員，並包含正確的 player_url。"""
    result = season_stats.parse_season_stats_page(team_score_html_content)
    assert isinstance(result, list)
    # 斷言解析出的球員數量應大於 0
    assert len(result) > 0

    # --- 驗證第一個球員的資料結構 ---
    first_player = result[0]
    assert "player_name" in first_player
    assert "player_url" in first_player
    assert isinstance(first_player["player_name"], str)
    assert isinstance(first_player["player_url"], str)

    # --- 驗證 player_url 是否為完整的絕對 URL ---
    assert first_player["player_url"].startswith("https://www.cpbl.com.tw")
    assert "team/person" in first_player["player_url"]

    # --- 維持原有的球員名稱驗證 ---
    parsed_player_names = {p["player_name"] for p in result}
    # 假設 settings.TARGET_PLAYER_NAMES 至少有一個目標球員
    if settings.TARGET_PLAYER_NAMES:
        assert set(settings.TARGET_PLAYER_NAMES).issubset(parsed_player_names)
