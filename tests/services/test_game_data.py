# tests/services/test_game_data.py

from app.services import game_data

# --- 測試用的模擬資料 ---

# 假設從 season_stats.parse_season_stats_page 解析器回傳的資料
MOCK_PARSED_PLAYERS = [
    {"player_name": "王柏融", "player_url": "http://example.com/wang"},
    {"player_name": "魔鷹", "player_url": "http://example.com/moya"},
    {"player_name": "吳念庭", "player_url": "http://example.com/wu"},
    {"player_name": "宋家豪", "player_url": "http://example.com/sung"},
    {"player_name": "路人甲", "player_url": "http://example.com/a"},
    {"player_name": "路人乙", "player_url": "http://example.com/b"},
]

# 假設 settings.TARGET_PLAYER_NAMES 的內容
# 注意：這應該與你的 .env.test 或設定檔中的值對應
TARGET_PLAYERS_IN_SETTINGS = ["王柏融", "魔鷹", "吳念庭"]


# --- 測試案例 ---


def test_scrape_and_store_season_stats_default_behavior(mocker):
    """
    測試預設行為 (update_career_stats_for_all=False)，
    應只為 settings.TARGET_PLAYER_NAMES 中的球員更新生涯數據。
    """
    # 1. 設定 Mocks
    mocker.patch("app.config.settings.TARGET_PLAYER_NAMES", TARGET_PLAYERS_IN_SETTINGS)
    mocker.patch(
        "app.core.fetcher.get_dynamic_page_content", return_value="<html></html>"
    )
    mocker.patch(
        "app.parsers.season_stats.parse_season_stats_page",
        return_value=MOCK_PARSED_PLAYERS,
    )
    mocker.patch("app.crud.players.store_player_season_stats_and_history")

    # 這是我們要監視的核心 mock
    mock_scrape_career = mocker.patch(
        "app.services.player.scrape_and_store_player_career_stats"
    )

    # 2. 執行函式 (使用預設參數)
    game_data.scrape_and_store_season_stats()

    # 3. 驗證結果
    # 斷言 scrape_and_store_player_career_stats 被呼叫的次數
    # 應該等於 MOCK_PARSED_PLAYERS 中，名字也存在於 TARGET_PLAYERS_IN_SETTINGS 的球員數量
    assert mock_scrape_career.call_count == len(TARGET_PLAYERS_IN_SETTINGS)

    mock_scrape_career.assert_any_call(
        player_name="王柏融", player_url="http://example.com/wang"
    )
    mock_scrape_career.assert_any_call(
        player_name="魔鷹", player_url="http://example.com/moya"
    )

    mock_scrape_career.assert_any_call(
        player_name="吳念庭", player_url="http://example.com/wu"
    )


def test_scrape_and_store_season_stats_update_all(mocker):
    """
    測試當 update_career_stats_for_all=True 時，
    應為所有從頁面解析出的球員更新生涯數據。
    """
    # 1. 設定 Mocks
    mocker.patch(
        "app.core.fetcher.get_dynamic_page_content", return_value="<html></html>"
    )
    mocker.patch(
        "app.parsers.season_stats.parse_season_stats_page",
        return_value=MOCK_PARSED_PLAYERS,
    )
    mocker.patch("app.crud.players.store_player_season_stats_and_history")

    mock_scrape_career = mocker.patch(
        "app.services.player.scrape_and_store_player_career_stats"
    )

    # 2. 執行函式 (明確傳入 True)
    game_data.scrape_and_store_season_stats(update_career_stats_for_all=True)

    # 3. 驗證結果
    # 斷言 scrape_and_store_player_career_stats 被呼叫的次數
    # 應該等於 MOCK_PARSED_PLAYERS 列表的總長度
    assert mock_scrape_career.call_count == len(MOCK_PARSED_PLAYERS)

    # 驗證它為 "路人甲" (一個非目標球員) 也被呼叫了
    mock_scrape_career.assert_any_call(
        player_name="路人甲", player_url="http://example.com/a"
    )
