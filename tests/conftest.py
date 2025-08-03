# tests/conftest.py

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import logging.config
from sqlalchemy.pool import StaticPool


# 核心修正 1: 使用 pytest hook 自動為 e2e 測試加上標記
def pytest_collection_modifyitems(config, items):
    """
    在 pytest 收集完所有測試項目後，自動為位於 'e2e' 目錄下的測試
    加上 'e2e' 標記。
    """
    for item in items:
        # 檢查測試項目的路徑是否包含 'e2e' 這個目錄名稱
        if "e2e" in item.path.parts:
            item.add_marker(pytest.mark.e2e)


# 核心修正 2: 簡化 fixture，使其只處理非 E2E 測試的環境設定
@pytest.fixture(scope="function", autouse=True)
def apply_test_settings(monkeypatch, request):
    """
    為每個測試函式設定必要的環境變數。
    此 fixture 會檢查測試是否有 'e2e' 標記。
    - 如果有，它會直接跳過，不執行任何操作，以避免污染由 Docker 管理的 E2E 環境。
    - 如果沒有，它才會設定單元測試所需的環境 (如記憶體資料庫)。
    """
    if "e2e" in request.node.keywords:
        # 對於 E2E 測試，此 fixture 不執行任何操作。
        # E2E 測試的環境應由 Docker Compose 和 .env 檔案完全控制。
        yield
        return
    else:
        # 為單元/整合測試設定環境變數
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
        monkeypatch.setenv("DRAMATIQ_BROKER_URL", "redis://localhost:6379/1")
        monkeypatch.setenv("API_KEY", "test-api-key-for-pytest")
        yield


# 將 engine 的建立延遲到 fixture 中。
# scope 設為 "session" 以確保整個測試過程只建立一次 engine，提升效率。
@pytest.fixture(scope="session")
def engine():
    """建立並提供一個 session-scope 的 SQLAlchemy engine，指向記憶體中的 SQLite。"""
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture(scope="session")
def TestingSessionLocal(engine):
    """根據測試 engine 建立 sessionmaker。"""
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


# --- 資料庫 Fixture ---


@pytest.fixture(scope="function")
def setup_database(engine):
    """
    在每個測試函式執行前後，自動建立和銷毀所有資料庫資料表。
    """
    # 將模組匯入移至 fixture 內部，確保在 monkeypatch 之後執行。
    from app.db import Base

    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(TestingSessionLocal, setup_database):
    """
    提供一個資料庫 session 給需要直接操作資料庫的測試。
    它依賴 setup_database fixture 來確保資料表已存在。
    """
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- FastAPI 應用程式 Fixture ---


@pytest.fixture(scope="function")
def client(monkeypatch, TestingSessionLocal, setup_database):
    """
    提供一個 FastAPI TestClient。
    - 依賴 setup_database 來確保資料庫已準備就緒。
    - 使用 monkeypatch 來禁用檔案日誌。
    """
    # 將 app 相關的匯入移至 fixture 內部。
    from app.main import app
    from app.db import get_db

    # 禁用日誌檔案寫入
    monkeypatch.setattr(logging.config, "dictConfig", lambda *args, **kwargs: None)

    def override_get_db():
        """
        為 API 端點提供一個獨立的資料庫 session。
        """
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    # 將 app 中的 get_db 依賴替換為我們的測試版本
    app.dependency_overrides[get_db] = override_get_db

    # 建立 TestClient
    with TestClient(app) as c:
        yield c

    # 測試結束後，清除依賴覆寫
    app.dependency_overrides.clear()
