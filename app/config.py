# app/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    # --- 資料庫設定 ---
    # DATABASE_URL 會從 .env 檔案中讀取
    DATABASE_URL: str

    # --- 目標設定 ---
    TARGET_TEAM_NAME: str = "台鋼雄鷹"
    TARGET_PLAYER_NAMES: List[str] = ["王柏融", "魔鷹", "吳念庭"]

    # --- 網站與 URL 設定 ---
    BASE_URL: str = "https://www.cpbl.com.tw"
    SCHEDULE_URL: str = f"{BASE_URL}/schedule"
    TEAM_SCORE_URL: str = f"{BASE_URL}/team/teamscore"
    
    # --- 爬蟲相關設定 ---
    DEFAULT_REQUEST_TIMEOUT: int = 30
    PLAYWRIGHT_TIMEOUT: int = 60000
    FRIENDLY_SCRAPING_DELAY: int = 2

    # --- 安全性與 CORS 設定 (未來部署用) ---
    # API_KEY: str = "your_secret_api_key" # 建議取消註解並在 .env 中設定
    # FRONTEND_URL: str = "http://localhost:3000"

    # 指定讀取 .env 檔案
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8')

# 建立一個全域可用的 settings 實例
settings = Settings()

# 註：舊的 TEAM_CLUB_CODES 字典若其他地方還需使用，可保留在此處
TEAM_CLUB_CODES = {
    "中信兄弟": "ACN",
    "統一7-ELEVEn獅": "ADD",
    "樂天桃猿": "AJL",
    "富邦悍將": "AEO",
    "味全龍": "AAA",
    "台鋼雄鷹": "AKP"
}