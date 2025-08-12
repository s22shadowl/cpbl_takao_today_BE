# app/config.py

import json
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional, Dict

# 【新增】從新建的常數模組導入打席結果分類
from .core.constants import HITS, ON_BASE_RESULTS, ADVANCEMENT_RESULTS


class Settings(BaseSettings):
    TEAM_CLUB_CODES: Dict[str, str] = {
        "中信兄弟": "ACN",
        "統一7-ELEVEn獅": "ADD",
        "樂天桃猿": "AJL",
        "富邦悍將": "AEO",
        "味全龍": "AAA",
        "台鋼雄鷹": "AKP",
    }

    # **新增**: 從 .env 讀取並驗證 PostgreSQL 的獨立設定變數
    # 這些變數主要由 docker-compose.yml 使用
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_DB: Optional[str] = None
    POSTGRES_PORT: Optional[int] = None

    # 應用程式主要使用的設定
    DATABASE_URL: str
    DRAMATIQ_BROKER_URL: str
    REDIS_CACHE_URL: str  # 【新增】專門用於應用層快取的 Redis URL
    API_KEY: str

    # [新增] 批次匯入腳本專用設定
    STAGING_DATABASE_URL: Optional[str] = None
    PRODUCTION_DATABASE_URL: Optional[str] = None
    BULK_IMPORT_DELAY_SECONDS: Optional[int] = 2

    # [修改] 將爬蟲目標設定的預設值移除，改為由環境變數強制定義
    TARGET_TEAM_NAME: str
    TARGET_TEAMS: List[str]
    TARGET_PLAYER_NAMES: List[str]

    # [新增] 將 tasks 和 scraper 的硬式編碼參數移至此處
    # Dramatiq 任務設定
    DRAMATIQ_MAX_RETRIES: int = 2
    DRAMATIQ_RETRY_BACKOFF: int = 300000  # in milliseconds

    # Playwright 操作設定
    PLAYWRIGHT_SLOW_MO: int = 300
    PLAYWRIGHT_TIMEOUT: int = 60000
    PLAYWRIGHT_STATIC_DELAY: int = 250

    # CPBL 賽季設定
    CPBL_SEASON_START_MONTH: int = 3
    CPBL_SEASON_END_MONTH: int = 11

    # 其他應用程式設定 (保留預設值)
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    BASE_URL: str = "https://www.cpbl.com.tw"
    SCHEDULE_URL: str = f"{BASE_URL}/schedule"
    TEAM_SCORE_URL: str = f"{BASE_URL}/team/teamscore"
    DEFAULT_REQUEST_TIMEOUT: int = 30
    FRIENDLY_SCRAPING_DELAY: int = 2

    # 【修改】「連線」功能定義，改為引用常數模組，並將 set 轉為 list
    STREAK_DEFINITIONS: Dict[str, List[str]] = {
        # 定義 A: 連續安打
        "consecutive_hits": list(HITS),
        # 定義 B: 連續上壘 (安打 + 保送/觸身)
        "consecutive_on_base": list(ON_BASE_RESULTS),
        # 定義 C: 連續推進 (上壘 + 犧牲打)
        "consecutive_advancements": list(ADVANCEMENT_RESULTS),
    }

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # 【新增】E2E 測試模式開關
    E2E_TEST_MODE: bool = False

    # --- 快取設定 ---
    # [新增] 用於清除分析 API 快取的 Redis 鍵名模式
    REDIS_CACHE_KEY_PATTERN_ANALYSIS: str = "app.api.analysis:*"

    def get_target_teams_as_list(self) -> List[str]:
        """【修正】處理 str 或 list 型別的輸入，使其更穩健"""
        if isinstance(self.TARGET_TEAMS, list):
            return self.TARGET_TEAMS
        return json.loads(self.TARGET_TEAMS)

    def get_target_players_as_list(self) -> List[str]:
        """【修正】處理 str 或 list 型別的輸入"""
        if isinstance(self.TARGET_PLAYER_NAMES, list):
            return self.TARGET_PLAYER_NAMES
        return json.loads(self.TARGET_PLAYER_NAMES)


settings = Settings()
