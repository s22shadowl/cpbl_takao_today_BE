# tests/test_canary.py

import json
from pathlib import Path
import pytest

# 匯入我們需要測試的解析函式
from app.parsers.box_score import parse_box_score_page

# --- 設定 ---
# 測試目標 URL
TARGET_URL = "https://www.cpbl.com.tw/box?year=2024&kindCode=A&gameSno=7"

# 黃金樣本的路徑
# Path(__file__).parent 會取得目前檔案所在的目錄 (tests/)
GOLDEN_SAMPLE_PATH = Path(__file__).parent / "fixtures/golden_sample.json"
# --- 設定結束 ---


@pytest.mark.canary
def test_cpbl_site_structure_unchanged(page):
    """
    金絲雀測試，用於偵測 CPBL Box Score 頁面結構是否發生破壞性變更。

    流程:
    1. 載入預先產生的 `golden_sample.json` 作為基準。
    2. 使用 pytest-playwright 提供的 `page` fixture 即時爬取目標 URL。
    3. 使用現有的解析器解析即時抓取的資料。
    4. 斷言即時解析的結果必須與黃金樣本完全一致。

    如果此測試失敗，極可能表示 CPBL 官網的 HTML 結構已變更，
    需要立即檢查並修復解析器 (`app/parsers/box_score.py`)。
    """
    # 1. 載入黃金樣本
    assert GOLDEN_SAMPLE_PATH.exists(), f"黃金樣本檔案不存在於: {GOLDEN_SAMPLE_PATH}"
    with open(GOLDEN_SAMPLE_PATH, "r", encoding="utf-8") as f:
        golden_data = json.load(f)

    # 2. 使用 pytest-playwright 的 page fixture 執行即時爬取
    page.goto(TARGET_URL, wait_until="networkidle")
    # 等待一些額外時間確保所有動態內容都載入完成
    page.wait_for_timeout(3000)
    html_content = page.content()

    # 3. 使用與建立樣本時完全相同的函式，解析即時抓取的資料
    live_data = parse_box_score_page(html_content=html_content)

    # 4. 斷言兩份資料必須完全相等
    assert live_data == golden_data, (
        "即時解析的資料與黃金樣本不符！CPBL 官網站點結構可能已發生變更。"
    )
