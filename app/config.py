# app/config.py

import os
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    DATABASE_URL: str
    DRAMATIQ_BROKER_URL: str
    API_KEY: str
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    TARGET_TEAM_NAME: str = "台鋼雄鷹"
    TARGET_PLAYER_NAMES: List[str] = ["王柏融", "魔鷹", "吳念庭"]
    BASE_URL: str = "https://www.cpbl.com.tw"
    SCHEDULE_URL: str = f"{BASE_URL}/schedule"
    TEAM_SCORE_URL: str = f"{BASE_URL}/team/teamscore"
    DEFAULT_REQUEST_TIMEOUT: int = 30
    PLAYWRIGHT_TIMEOUT: int = 60000
    FRIENDLY_SCRAPING_DELAY: int = 2


settings = Settings(
    DATABASE_URL=os.getenv("DATABASE_URL"),
    DRAMATIQ_BROKER_URL=os.getenv("DRAMATIQ_BROKER_URL"),
    API_KEY=os.getenv("API_KEY"),
)

TEAM_CLUB_CODES = {
    "中信兄弟": "ACN",
    "統一7-ELEVEn獅": "ADD",
    "樂天桃猿": "AJL",
    "富邦悍將": "AEO",
    "味全龍": "AAA",
    "台鋼雄鷹": "AKP",
}
