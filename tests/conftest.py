# tests/conftest.py

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import logging.config
from sqlalchemy.pool import StaticPool


# **核心修正 1**: 將 apply_test_settings 的 scope 改為 "function"，
# 以匹配它所依賴的 monkeypatch fixture 的 scope。
# autouse=True 確保它依然會在每個測試函式前自動執行。
@pytest.fixture(scope="function", autouse=True)
def apply_test_settings(monkeypatch):
    """為每個測試函式設定必要的環境變數，以滿足 Pydantic 的驗證。"""
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")
    monkeypatch.setenv("POSTGRES_DB", "test_db")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("DRAMATIQ_BROKER_URL", "redis://localhost:6379/1")
    monkeypatch.setenv("API_KEY", "test-api-key-for-pytest")


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
