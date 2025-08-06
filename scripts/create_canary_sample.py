# scripts/create_canary_sample.py

import asyncio
import json
import logging
from pathlib import Path

from playwright.async_api import async_playwright

# 更新 import，直接引入函式
from app.parsers.box_score import parse_box_score_page

# --- 設定 ---
# 你提供的基準 URL
TARGET_URL = "https://www.cpbl.com.tw/box?year=2024&kindCode=A&gameSno=7"

# 黃金樣本的輸出路徑
OUTPUT_DIR = Path("tests/fixtures")
OUTPUT_FILE = OUTPUT_DIR / "golden_sample.json"
# --- 設定結束 ---

### 使用指令：python -m scripts.create_canary_sample


async def main():
    """
    主執行函式，抓取指定頁面、解析並儲存為黃金樣本。
    """
    # 你的 parser 使用了 logging 模組，做一個基本設定讓日誌可以顯示
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    print(f"目標 URL: {TARGET_URL}")

    # 確保輸出目錄存在
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"正在建立黃金樣本，將儲存至: {OUTPUT_FILE}")

    html_content = ""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            logging.info("正在啟動瀏覽器並前往目標頁面...")
            await page.goto(TARGET_URL, wait_until="networkidle")
            await page.wait_for_timeout(3000)

            html_content = await page.content()
            await browser.close()
            logging.info("頁面 HTML 內容已成功獲取。")

    except Exception as e:
        logging.error(f"抓取 HTML 時發生錯誤: {e}", exc_info=True)
        return

    if not html_content:
        logging.error("無法獲取 HTML 內容，腳本終止。")
        return

    # 使用你提供的 parse_box_score_page 函式進行解析
    try:
        logging.info("正在使用 parse_box_score_page 函式解析內容...")

        # 直接呼叫函式，傳入獲取的 html_content
        # 由於這是為了建立包含所有数据的黃金樣本，我們不傳入 target_teams
        parsed_data = parse_box_score_page(html_content=html_content)

        logging.info("內容解析成功。")

    except Exception as e:
        logging.error(f"解析 HTML 時發生錯誤: {e}", exc_info=True)
        return

    # 將解析後的資料寫入 JSON 檔案
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(parsed_data, f, ensure_ascii=False, indent=4)
        print("=" * 20)
        print("✅ 黃金樣本 golden_sample.json 已成功建立！")
        print("=" * 20)
    except Exception as e:
        logging.error(f"寫入 JSON 檔案時發生錯誤: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
