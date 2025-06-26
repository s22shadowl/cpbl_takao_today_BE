import pytest
import datetime
from unittest.mock import MagicMock, call, patch

from app import scraper, config

@pytest.fixture
def mock_modules_with_playwright(mocker):
    """
    一個擴充版的 fixture，除了模擬基本模組外，還深度模擬了 Playwright 的操作鏈。
    """
    # 模擬基本模組
    mock_db_actions = mocker.patch('app.scraper.db_actions')
    mock_get_conn = mocker.patch('app.scraper.get_db_connection')
    mock_conn = MagicMock()
    mock_get_conn.return_value = mock_conn
    
    # 深度模擬 Playwright
    mock_sync_playwright = mocker.patch('app.scraper.sync_playwright')
    mock_p = MagicMock()
    mock_browser = MagicMock()
    mock_page = MagicMock()

    mock_sync_playwright.return_value.__enter__.return_value = mock_p
    mock_p.chromium.launch.return_value = mock_browser
    mock_browser.new_page.return_value = mock_page

    # 【修正】將 scraper 中使用的 expect 函式也模擬掉，避免 ValueError
    mocker.patch('app.scraper.expect')

    # 模擬狀態機函式，讓它們使用真實邏輯
    mocker.patch('app.scraper._update_outs_count', side_effect=scraper._update_outs_count)
    mocker.patch('app.scraper._update_runners_state', side_effect=scraper._update_runners_state)

    return {
        "db_actions": mock_db_actions,
        "conn": mock_conn,
        "page": mock_page,
        "mocker": mocker,
        "parser": mocker.patch('app.scraper.html_parser'),
        "fetcher": mocker.patch('app.scraper.fetcher')
    }

def test_process_filtered_games_e2e_flow(mock_modules_with_playwright):
    """
    端到端測試 _process_filtered_games 的完整流程，
    包含 Playwright 互動、狀態機計算與最終資料合併邏輯。
    """
    # 1. 準備 (Arrange)
    mock_page = mock_modules_with_playwright["page"]
    mock_parser = mock_modules_with_playwright["parser"]
    mock_db_actions = mock_modules_with_playwright["db_actions"]
    
    mock_parser.parse_box_score_page.return_value = [
        {"summary": {"player_name": "吳念庭"}, "at_bats_list": ["一安", "左飛"]},
        {"summary": {"player_name": "魔鷹"}, "at_bats_list": ["二安"]},
    ]

    # --- 建立更精確的 Playwright 模擬 ---
    mock_inning1_li, mock_inning2_li = MagicMock(), MagicMock()
    mock_inning1_content_locator, mock_inning2_content_locator = MagicMock(), MagicMock()
    mock_inning1_half_section, mock_inning2_half_section = MagicMock(), MagicMock()

    # 設定 page.locator 的回傳行為
    mock_page.locator.side_effect = [
        MagicMock(all=MagicMock(return_value=[mock_inning1_li, mock_inning2_li])), # for inning_buttons
        mock_inning1_content_locator,
        mock_inning2_content_locator
    ]
    
    # 設定每一局內容區塊的內部 locator 行為
    mock_inning1_content_locator.locator.return_value = mock_inning1_half_section
    mock_inning1_half_section.count.return_value = 1
    mock_inning1_half_section.locator.return_value.all.return_value = [MagicMock()]
    mock_inning1_content_locator.inner_html.return_value = "<html>inning 1 content</html>"

    mock_inning2_content_locator.locator.return_value = mock_inning2_half_section
    mock_inning2_half_section.count.return_value = 1
    mock_inning2_half_section.locator.return_value.all.return_value = [MagicMock()]
    mock_inning2_content_locator.inner_html.return_value = "<html>inning 2 content</html>"
    
    # 模擬 parser 回傳值
    mock_parser.parse_active_inning_details.side_effect = [
        [
            {'inning': 1, 'type': 'at_bat', 'hitter_name': '路人甲', 'description': '造成1人出局'},
            {'inning': 1, 'type': 'at_bat', 'hitter_name': '吳念庭', 'description': '一壘安打', 'opposing_pitcher_name': '黃子鵬'},
        ],
        [
            {'inning': 2, 'type': 'at_bat', 'hitter_name': '魔鷹', 'description': '二壘安打。1人出局', 'opposing_pitcher_name': '陳冠宇'},
            {'inning': 2, 'type': 'at_bat', 'hitter_name': '吳念庭', 'description': '左外野飛球出局。2人出局', 'opposing_pitcher_name': '陳冠宇'},
        ]
    ]

    mock_db_actions.store_game_and_get_id.return_value = 99

    # 2. 執行 (Act)
    scraper._process_filtered_games([{
        'status': '已完成', 'home_team': config.TARGET_TEAM_NAME, 'away_team': '敵隊',
        'cpbl_game_id': 'TEST99', 'box_score_url': 'http://fake.url'
    }])

    # 3. 斷言 (Assert)
    assert mock_db_actions.store_player_game_data.call_count == 1
    call_args, _ = mock_db_actions.store_player_game_data.call_args
    
    _, final_game_id, final_player_data = call_args
    assert final_game_id == 99
    assert len(final_player_data) == 2

    wu_data = next(p for p in final_player_data if p['summary']['player_name'] == '吳念庭')
    assert len(wu_data['at_bats_details']) == 2
    
    wu_pa1 = wu_data['at_bats_details'][0]
    assert wu_pa1['result_short'] == '一安'
    assert wu_pa1['inning'] == 1
    assert wu_pa1['outs_before'] == 1
    assert wu_pa1['runners_on_base_before'] == '壘上無人'
    assert wu_pa1['opposing_pitcher_name'] == '黃子鵬'

    wu_pa2 = wu_data['at_bats_details'][1]
    assert wu_pa2['result_short'] == '左飛'
    assert wu_pa2['inning'] == 2
    assert wu_pa2['outs_before'] == 1
    assert wu_pa2['runners_on_base_before'] == '二壘有人'
    assert wu_pa2['opposing_pitcher_name'] == '陳冠宇'


def test_scrape_single_day_filters_correctly(mocker):
    """【新增】測試 scrape_single_day 是否能正確過濾出指定日期的比賽"""
    target_date = "2025-06-25"
    all_games = [
        {'game_date': "2025-06-24", 'cpbl_game_id': 'G1'},
        {'game_date': target_date, 'cpbl_game_id': 'G2'},
        {'game_date': target_date, 'cpbl_game_id': 'G3'},
        {'game_date': "2025-06-26", 'cpbl_game_id': 'G4'},
    ]
    mocker.patch('app.scraper.scrape_and_store_season_stats')
    mocker.patch('app.scraper.fetcher.fetch_schedule_page', return_value="<html></html>")
    mock_parse_schedule = mocker.patch('app.scraper.html_parser.parse_schedule_page', return_value=all_games)
    mock_process_games = mocker.patch('app.scraper._process_filtered_games')

    scraper.scrape_single_day(specific_date=target_date)

    mock_parse_schedule.assert_called_once()
    mock_process_games.assert_called_once()
    
    call_args, _ = mock_process_games.call_args
    processed_games_list = call_args[0]
    
    assert len(processed_games_list) == 2
    assert processed_games_list[0]['cpbl_game_id'] == 'G2'
    assert processed_games_list[1]['cpbl_game_id'] == 'G3'

def test_scrape_single_day_aborts_for_future_date(mocker):
    """【新增】測試當目標日期為未來時，scrape_single_day 是否會中止"""
    future_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    mock_season_scrape = mocker.patch('app.scraper.scrape_and_store_season_stats')
    mock_fetch = mocker.patch('app.scraper.fetcher.fetch_schedule_page')
    
    scraper.scrape_single_day(specific_date=future_date)

    mock_season_scrape.assert_not_called()
    mock_fetch.assert_not_called()