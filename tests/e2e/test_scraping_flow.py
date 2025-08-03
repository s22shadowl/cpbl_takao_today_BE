# tests/e2e/test_scraping_flow.py

import requests
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from tenacity import retry, stop_after_delay, wait_fixed

# 確保在呼叫 Base.metadata 前，所有模型都已載入
from app import models  # noqa: F401
from app.db import Base
from app.config import settings

# --- E2E 測試設定 ---
API_BASE_URL = "http://localhost:8000"
POLLING_TIMEOUT = 60
POLLING_INTERVAL = 1


# --- Fixtures ---


# 核心修正 1: 建立一個 session scope 的 fixture 來集中管理 engine。
# 這能確保所有測試函式共享同一個 engine 實例，避免多個 engine 實例造成衝突。
@pytest.fixture(scope="session")
def e2e_engine():
    """建立並提供一個 session-scope 的 SQLAlchemy engine。"""
    engine = create_engine(str(settings.DATABASE_URL))
    yield engine
    # 在所有測試結束後，關閉 engine 的連線池
    engine.dispose()


# 核心修正 2: 將 fixture 的 scope 改為 "function"，並接收 e2e_engine。
# 這能確保每個測試函式執行前，資料庫都會使用同一個 engine 被完整地重置。
@pytest.fixture(scope="function", autouse=True)
def setup_e2e_database(e2e_engine):
    """
    一個 function 等級、自動執行的 fixture。
    在每個 E2E 測試函式開始前，使用共享的 engine 刪除並重建所有資料表。
    """
    print("\n[E2E Setup] 正在為測試函式設定資料庫...")
    print("[E2E Setup] 正在刪除所有舊資料表...")
    Base.metadata.drop_all(bind=e2e_engine)
    print("[E2E Setup] 正在建立所有新資料表...")
    Base.metadata.create_all(bind=e2e_engine)
    print("[E2E Setup] 資料庫結構已建立。")


# 核心修正 3: 修改 db_session fixture，使其也依賴 e2e_engine。
@pytest.fixture(scope="function")
def db_session(e2e_engine):
    """
    提供一個直接連線到測試 PostgreSQL 資料庫的 session。
    此 session 是從一個與 e2e_engine 綁定的 sessionmaker 建立的。
    """
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=e2e_engine
    )
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- 測試案例 ---


def test_scrape_daily_job_flow(db_session):
    """
    測試從觸發每日爬蟲 API 到資料寫入資料庫的完整端到端流程。
    """
    # 1. 準備 (Arrange)
    target_date = "2025-01-15"
    expected_cpbl_game_id = f"E2E_{target_date.replace('-', '')}"
    api_key = settings.API_KEY
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    payload = {"mode": "daily", "date": target_date}

    # 2. 執行 (Act)
    response = requests.post(
        f"{API_BASE_URL}/api/run_scraper", headers=headers, json=payload
    )
    assert response.status_code == 202, f"API 呼叫失敗: {response.text}"
    print(
        f"\n[E2E] 已成功觸發 API，任務已送出。等待 Worker 處理 (最多 {POLLING_TIMEOUT} 秒)..."
    )

    # 3. 驗證 (Assert)
    @retry(stop=stop_after_delay(POLLING_TIMEOUT), wait=wait_fixed(POLLING_INTERVAL))
    def _check_for_data_in_db():
        print(f"[E2E] 正在輪詢資料庫，檢查 ID: {expected_cpbl_game_id}...")
        # 確保每次輪詢都使用最新的 session 狀態
        db_session.expire_all()
        game = db_session.execute(
            text(
                f"SELECT * FROM game_results WHERE cpbl_game_id = '{expected_cpbl_game_id}'"
            )
        ).first()

        assert game is not None, "在超時範圍內，資料未寫入 game_results 表。"
        return game

    try:
        created_game = _check_for_data_in_db()
        print("[E2E] 成功在資料庫中找到資料！")

        assert created_game.home_team == settings.TARGET_TEAM_NAME
        assert created_game.away_team == "E2E測試客隊"
        assert created_game.status == "已完成"

    except Exception as e:
        pytest.fail(f"E2E 測試失敗: {e}")
