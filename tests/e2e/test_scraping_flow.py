# tests/e2e/test_scraping_flow.py

import requests
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from tenacity import retry, stop_after_delay, wait_fixed

# **新增**: 匯入 Alembic 相關模組
from alembic.config import Config
from alembic import command

# 依賴 .env 檔案來取得連線資訊與 API 金鑰
from app.config import settings

# --- E2E 測試設定 ---
API_BASE_URL = "http://localhost:8000"
POLLING_TIMEOUT = 60
POLLING_INTERVAL = 1

# --- 資料庫連線設定 ---
DB_URL = str(settings.DATABASE_URL)
engine = create_engine(DB_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# --- Fixtures ---


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """
    一個 session 等級、自動執行的 fixture。
    在所有 E2E 測試開始前，執行 Alembic migrations 來建立資料表。
    在所有測試結束後，執行 downgrade 將資料庫還原為空。
    """
    print("\n[E2E Setup] 正在設定 E2E 測試資料庫...")
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", DB_URL)

    # 升級到最新版本
    command.upgrade(alembic_cfg, "head")
    print("[E2E Setup] 資料庫結構已建立。")

    yield

    # 降級回初始狀態
    print("\n[E2E Teardown] 正在清理 E2E 測試資料庫...")
    command.downgrade(alembic_cfg, "base")
    print("[E2E Teardown] 資料庫已還原。")


@pytest.fixture(scope="function")
def db_session():
    """提供一個直接連線到測試 PostgreSQL 資料庫的 session。"""
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

    # 前置清理：現在資料表已存在，我們可以安全地刪除資料
    # 順序很重要：先刪除子表，再刪除父表，以避免違反外鍵約束
    with engine.connect() as connection:
        connection.execute(text("DELETE FROM at_bat_details;"))
        connection.execute(text("DELETE FROM player_game_summary;"))
        connection.execute(text("DELETE FROM game_results;"))
        connection.commit()

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
        # 使用 tenacity 的 RetryError 可能會包裝原始的 AssertionError
        pytest.fail(f"E2E 測試失敗: {e}")
