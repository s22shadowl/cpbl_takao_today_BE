# tests/parsers/test_schedule.py

import pytest
import logging
from pathlib import Path
from bs4 import BeautifulSoup

from app.parsers import schedule
from app.exceptions import FatalScraperError

# --- 測試素材設定 ---
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def schedule_html_content():
    """讀取真實的 fixture 檔案作為測試素材。"""
    schedule_file = FIXTURES_DIR / "schedule_page.html"
    if not schedule_file.exists():
        pytest.skip("測試素材 schedule_page.html 不存在，跳過相關測試。")
    return schedule_file.read_text(encoding="utf-8")


# --- 測試 parse_schedule_page 主函式 ---


def test_parse_schedule_page_success(schedule_html_content):
    """測試正常解析月曆檢視的賽程頁面，應只回傳「已完成」的比賽。"""
    # 執行解析
    games = schedule.parse_schedule_page(schedule_html_content, year=2025)

    # 驗證總數：根據提供的 HTML，共有 27 場比賽標記為 final
    assert len(games) == 27
    assert isinstance(games, list)

    # 驗證第一場比賽 (場次 134) 的內容是否正確
    first_game = games[0]
    assert first_game["game_date"] == "2025-06-01"
    assert first_game["cpbl_game_id"] == "134"
    assert first_game["status"] == "已完成"
    assert first_game["away_team"] == "富邦悍將"
    assert first_game["home_team"] == "台鋼雄鷹"
    assert first_game["away_score"] == 4
    assert first_game["home_score"] == 5
    assert first_game["venue"] == "澄清湖"
    assert (
        first_game["box_score_url"]
        == "https://www.cpbl.com.tw/box?year=2025&kindCode=A&gameSno=134"
    )


def test_parse_schedule_page_filters_non_final_games(schedule_html_content, caplog):
    """測試解析時會正確過濾掉非「已完成」狀態的比賽，並記錄日誌。"""
    # 【修正】設定 caplog 的等級，以確保能捕捉到 INFO 等級的日誌
    caplog.set_level(logging.INFO)
    # 執行解析
    schedule.parse_schedule_page(schedule_html_content, year=2025)

    # 驗證日誌中包含了因「延賽」和「保留」而被跳過的訊息
    assert "狀態為 '延賽'" in caplog.text
    assert "狀態為 '保留'" in caplog.text
    assert "狀態為 '未開始'" in caplog.text
    # 驗證日誌中不應包含錯誤訊息
    assert "解析單場比賽區塊時出錯" not in caplog.text


def test_parse_schedule_page_handles_malformed_game_block(
    schedule_html_content, caplog
):
    """測試當某個比賽區塊 HTML 結構錯誤時，能跳過該區塊並繼續解析。"""
    # 【修正】設定 caplog 的等級，以確保能捕捉到 ERROR 等級的日誌
    caplog.set_level(logging.ERROR)
    # 手動破壞一個比賽區塊的 HTML 結構 (移除隊伍資訊)
    soup = BeautifulSoup(schedule_html_content, "lxml")
    malformed_game = soup.find(
        "a", href=lambda href: href and "gameSno=134" in href
    ).find_parent("div", class_="game")
    if malformed_game and malformed_game.find("div", class_="vs_box"):
        malformed_game.find("div", class_="vs_box").decompose()
    malformed_html = str(soup)

    # 執行解析
    games = schedule.parse_schedule_page(malformed_html, year=2025)

    # 預期結果：原本 27 場成功，現在壞掉 1 場，剩下 26 場
    assert len(games) == 26
    # 驗證日誌中應包含解析錯誤的訊息
    assert "缺少隊伍資訊 (vs_box)" in caplog.text


@pytest.mark.parametrize(
    "missing_element_selector, error_message",
    [
        ("div.ScheduleTable > table > tbody", "找不到月曆表格"),
        ("div.date_selected > div.date", "無法從頁面中確定當前月份"),
    ],
)
def test_parse_schedule_page_raises_fatal_on_missing_main_element(
    schedule_html_content, missing_element_selector, error_message
):
    """測試當缺少關鍵 HTML 結構時，應拋出 FatalScraperError。"""
    # 破壞 HTML，移除指定的關鍵元素
    soup = BeautifulSoup(schedule_html_content, "lxml")
    # 也要移除備用的月份選擇器，以確保測試能觸發到目標錯誤
    month_selector_to_remove = soup.select_one(
        "div.item.month > select > option[selected]"
    )
    if month_selector_to_remove:
        month_selector_to_remove.decompose()

    element_to_remove = soup.select_one(missing_element_selector)
    if element_to_remove:
        element_to_remove.decompose()
    malformed_html = str(soup)

    # 驗證是否拋出致命錯誤
    with pytest.raises(FatalScraperError, match=error_message):
        schedule.parse_schedule_page(malformed_html, year=2025)


def test_parse_schedule_page_raises_fatal_on_empty_content():
    """測試當傳入的 HTML 內容為空時，應拋出 FatalScraperError。"""
    with pytest.raises(FatalScraperError, match="HTML 內容為空"):
        schedule.parse_schedule_page(None, year=2025)
    with pytest.raises(FatalScraperError, match="HTML 內容為空"):
        schedule.parse_schedule_page("", year=2025)
