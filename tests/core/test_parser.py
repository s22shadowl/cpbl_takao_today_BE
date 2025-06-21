# tests/core/test_parser.py

import pytest
from pathlib import Path
from app.core import parser

# 獲取測試素材檔案的路徑
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# --- 測試 parse_schedule_page ---

@pytest.fixture
def schedule_html_content():
    """一個 pytest fixture，用於讀取賽程頁面的 HTML 檔案內容。"""
    schedule_file = FIXTURES_DIR / "schedule_page.html"
    if not schedule_file.exists():
        pytest.skip("測試素材 schedule_page.html 不存在，跳過相關測試。")
    return schedule_file.read_text(encoding="utf-8")

def test_parse_schedule_page_returns_list(schedule_html_content):
    """測試 parse_schedule_page 函式是否總是回傳一個列表。"""
    # 測試正常情況
    result = parser.parse_schedule_page(schedule_html_content, year=2025)
    assert isinstance(result, list)
    
    # 測試傳入空內容的情況
    result_empty = parser.parse_schedule_page(None, year=2025)
    assert isinstance(result_empty, list)
    assert len(result_empty) == 0

def test_parse_schedule_page_finds_games(schedule_html_content):
    """測試 parse_schedule_page 是否能正確解析出比賽資訊。"""
    result = parser.parse_schedule_page(schedule_html_content, year=2025)
    
    # 根據您提供的 HTML，裡面有 62 場比賽
    assert len(result) > 0 # 簡單斷言有抓到比賽即可
    
    # 檢查第一筆資料的結構和內容是否符合預期
    first_game = result[0]
    assert isinstance(first_game, dict)
    assert 'game_date' in first_game
    assert 'cpbl_game_id' in first_game
    assert 'home_team' in first_game
    assert 'away_team' in first_game
    
    # 驗證具體值
    assert first_game['game_date'] == '2025-06-01'
    assert first_game['cpbl_game_id'] == '134'
    assert first_game['home_team'] == '台鋼雄鷹'


# --- 測試 parse_season_stats_page ---

@pytest.fixture
def team_score_html_content():
    """一個 pytest fixture，用於讀取球隊成績頁面的 HTML 檔案內容。"""
    teamscore_file = FIXTURES_DIR / "team_score_page.html"
    if not teamscore_file.exists():
        pytest.skip("測試素材 team_score_page.html 不存在，跳過相關測試。")
    return teamscore_file.read_text(encoding="utf-8")

def test_parse_season_stats_page(team_score_html_content):
    """測試 parse_season_stats_page 是否能正確解析出目標球員的累積數據。"""
    # config.py 中預設的目標球員是 ["王柏融", "魔鷹", "吳念庭"]
    result = parser.parse_season_stats_page(team_score_html_content)
    
    # 斷言回傳的是一個列表
    assert isinstance(result, list)
    # 斷言找到了我們設定的所有目標球員 (3位)
    assert len(result) == 3
    
    # 檢查王柏融的數據是否正確
    player_wang = next((p for p in result if p['player_name'] == '王柏融'), None)
    assert player_wang is not None
    assert isinstance(player_wang, dict)
    assert player_wang.get('games_played') == 48
    assert player_wang.get('avg') == 0.267
    assert player_wang.get('ops') == 0.714
    
# --- 測試 parse_box_score_page ---
@pytest.fixture
def box_score_html_content():
    """一個 pytest fixture，用於讀取 Box Score 頁面的 HTML 檔案內容。"""
    box_score_file = FIXTURES_DIR / "box_score_page.html"
    if not box_score_file.exists():
        pytest.skip("測試素材 box_score_page.html 不存在，跳過相關測試。")
    return box_score_file.read_text(encoding="utf-8")

def test_parse_box_score_page(box_score_html_content):
    """測試 parse_box_score_page 是否能正確解析出目標球員的單場數據。"""
    # config.py 中預設的目標球隊是 "台鋼雄鷹"
    # config.py 中預設的目標球員是 ["王柏融", "魔鷹", "吳念庭"]
    # 根據您提供的 HTML，這場比賽是 富邦 vs 台鋼，所以應該能抓到台鋼的球員
    result = parser.parse_box_score_page(box_score_html_content)
    
    assert isinstance(result, list)
    # 預期應該要找到 王柏融, 魔鷹, 吳念庭
    assert len(result) == 3
    
    # 檢查王柏融的單場數據
    player_wang_data = next((p for p in result if p['summary']['player_name'] == '王柏融'), None)
    assert player_wang_data is not None
    assert player_wang_data['summary']['at_bats'] == 3
    assert player_wang_data['summary']['hits'] == 0
    assert "左飛,左飛,一滾,死球" in player_wang_data['summary']['at_bat_results_summary']
    assert len(player_wang_data['at_bats_list']) == 4