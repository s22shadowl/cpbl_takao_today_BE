# app/core/fetcher.py

import logging
import time
from playwright.sync_api import sync_playwright
import requests
# 修正：從 app.config 匯入 settings 物件
from app.config import settings

def get_static_page_content(url):
    """使用 requests 獲取靜態網頁內容"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        # 修正：透過 settings 物件存取設定值
        response = requests.get(url, headers=headers, timeout=settings.DEFAULT_REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        logging.error(f"請求 URL {url} 失敗: {e}")
        return None

def get_dynamic_page_content(url, wait_for_selector):
    """【通用版】使用 Playwright 獲取動態網頁內容，會等待特定元素出現。"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            logging.info(f"Playwright: 導航至 {url}")
            # 修正：透過 settings 物件存取設定值
            page.goto(url, timeout=settings.PLAYWRIGHT_TIMEOUT)
            
            logging.info(f"Playwright: 正在等待元素 '{wait_for_selector}' 變為可見")
            page.wait_for_selector(wait_for_selector, state='visible', timeout=30000)
            
            logging.info("Playwright: 頁面元素已載入，正在獲取內容。")
            content = page.content()
            browser.close()
            return content
    except Exception as e:
        logging.error(f"使用 Playwright 獲取 URL {url} 失敗: {e}", exc_info=True)
        return None

def fetch_schedule_page(year, month):
    """【賽程頁專用】抓取賽程頁面，並模擬選擇年份和月份，僅回傳 HTML 字串。"""
    # 修正：透過 settings 物件存取設定值
    logging.info(f"正在從 {settings.SCHEDULE_URL} 獲取 {year}-{month:02d} 的賽程頁面...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            # 修正：透過 settings 物件存取設定值
            page.goto(settings.SCHEDULE_URL, timeout=settings.PLAYWRIGHT_TIMEOUT)
            page.wait_for_selector('div.item.year > select', timeout=15000)
            
            logging.info(f"Playwright: 選擇年份 '{year}'")
            page.select_option('div.item.year > select', str(year))
            time.sleep(0.5)

            month_value = str(month - 1)
            logging.info(f"Playwright: 選擇月份 '{month}' (value: {month_value})")
            page.select_option('div.item.month > select', month_value)
            
            expected_header_text = f"{year} / {month:02d}"
            header_selector = "div.date_selected > div.date"
            logging.info(f"Playwright: 正在等待月份標題更新為 '{expected_header_text}'")
            page.wait_for_function(f"document.querySelector('{header_selector}').innerText.includes('{expected_header_text}')", timeout=10000)
            
            page.click('a[title="列表顯示"]')
            page.wait_for_selector('.ScheduleTableList', state='visible', timeout=10000)

            logging.info("Playwright: 賽程頁面元素已載入，正在獲取內容。")
            content = page.content()
            browser.close()
            return content
    except Exception as e:
        logging.error(f"使用 Playwright 獲取賽程頁面 {year}-{month:02d} 失敗: {e}", exc_info=True)
        return None