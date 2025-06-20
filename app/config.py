# app/config.py

# --- 目標設定 ---
TARGET_TEAM_NAME = "台鋼雄鷹"
TARGET_PLAYER_NAMES = ["王柏融", "魔鷹", "吳念庭"]

# --- 網站與 URL 設定 ---
BASE_URL = "https://www.cpbl.com.tw"
SCHEDULE_URL = f"{BASE_URL}/schedule"
TEAM_SCORE_URL = f"{BASE_URL}/team/teamscore"

# 球隊代碼對應
TEAM_CLUB_CODES = {
    "中信兄弟": "ACN",
    "統一7-ELEVEn獅": "ADD",
    "樂天桃猿": "AJL",
    "富邦悍將": "AEO",
    "味全龍": "AAA",
    "台鋼雄鷹": "AKP"
}

# --- 爬蟲相關設定 ---
DEFAULT_REQUEST_TIMEOUT = 30
PLAYWRIGHT_TIMEOUT = 60000
FRIENDLY_SCRAPING_DELAY = 2 # 秒