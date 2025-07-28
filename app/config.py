# app/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional


class Settings(BaseSettings):
    # **新增**: 從 .env 讀取並驗證 PostgreSQL 的獨立設定變數
    # 這些變數主要由 docker-compose.yml 使用
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_DB: Optional[str] = None
    POSTGRES_PORT: Optional[int] = None

    # 應用程式主要使用的設定
    DATABASE_URL: str
    DRAMATIQ_BROKER_URL: str
    API_KEY: str

    # 其他應用程式設定
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://12-7.0.0.1:3000"]
    TARGET_TEAM_NAME: str = "台鋼雄鷹"
    TARGET_TEAMS: List[str] = ["台鋼雄鷹"]
    TARGET_PLAYER_NAMES: List[str] = ["王柏融", "魔鷹", "吳念庭"]
    BASE_URL: str = "https://www.cpbl.com.tw"
    SCHEDULE_URL: str = f"{BASE_URL}/schedule"
    TEAM_SCORE_URL: str = f"{BASE_URL}/team/teamscore"
    DEFAULT_REQUEST_TIMEOUT: int = 30
    PLAYWRIGHT_TIMEOUT: int = 60000
    FRIENDLY_SCRAPING_DELAY: int = 2

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # 【新增】E2E 測試模式開關
    E2E_TEST_MODE: bool = False


settings = Settings()

TEAM_CLUB_CODES = {
    "中信兄弟": "ACN",
    "統一7-ELEVEn獅": "ADD",
    "樂天桃猿": "AJL",
    "富邦悍將": "AEO",
    "味全龍": "AAA",
    "台鋼雄鷹": "AKP",
}
