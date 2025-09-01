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


@pytest.fixture
def team_fielding_html_content():
    """[新增] 提供一個模擬的球隊守備數據 HTML 內容 fixture。"""
    return """
    <div class="RecordTable">
        <table>
            <tbody>
                <tr>
                    <th>球員</th>
                    <th>守備位置</th>
                    <th>出賽數</th>
                    <th>失誤</th>
                    <th>捕逸</th>
                    <th>盜壘阻殺</th>
                    <th>守備率</th>
                </tr>
                <tr>
                    <td><a href="/web/index.php?p=person&id=1">守備大師</a></td>
                    <td>游擊手</td>
                    <td>120</td>
                    <td>5</td>
                    <td>0</td>
                    <td>0</td>
                    <td>.987</td>
                </tr>
                <tr>
                    <td><a href="/web/index.php?p=person&id=2">鐵捕</a></td>
                    <td>捕手</td>
                    <td>100</td>
                    <td>2</td>
                    <td>1</td>
                    <td>10</td>
                    <td>.995</td>
                </tr>
                <tr>
                    <td><a href="/web/index.php?p=person&id=3">無名氏</a></td>
                    <td>指定打擊</td>
                    <td>80</td>
                    <td>0</td>
                    <td>0</td>
                    <td>0</td>
                    <td>.000</td>
                </tr>
            </tbody>
        </table>
    </div>
    """


def test_parse_season_batting_stats_page(team_score_html_content):
    """[修改] 驗證函式能解析出所有球員，並包含正確的 player_url。"""
    result = season_stats.parse_season_batting_stats_page(team_score_html_content)
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


def test_parse_season_fielding_stats_page(team_fielding_html_content):
    """[新增] 測試 parse_season_fielding_stats_page 函式的正確性。"""
    result = season_stats.parse_season_fielding_stats_page(team_fielding_html_content)
    assert isinstance(result, list)
    # 應解析到 3 位球員的守備數據
    assert len(result) == 3

    # 驗證「守備大師」的資料
    stats_master = next(p for p in result if p["player_name"] == "守備大師")
    assert stats_master is not None
    # 驗證守備位置是否正確從中文轉換為英文縮寫
    assert stats_master["position"] == "SS"
    assert stats_master["games_played"] == 120
    assert stats_master["errors"] == 5
    # 驗證浮點數的轉換
    assert stats_master["fielding_percentage"] == 0.987

    # 驗證「鐵捕」的資料
    stats_catcher = next(p for p in result if p["player_name"] == "鐵捕")
    assert stats_catcher is not None
    assert stats_catcher["position"] == "C"
    assert stats_catcher["passed_balls"] == 1
    assert stats_catcher["caught_stealing_catcher"] == 10

    # 驗證「無名氏」的資料 (測試未在轉換表中的守備位置)
    stats_dh = next(p for p in result if p["player_name"] == "無名氏")
    assert stats_dh is not None
    assert stats_dh["position"] == "指定打擊"  # 應保留原文
