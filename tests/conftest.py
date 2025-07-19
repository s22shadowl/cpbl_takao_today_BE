# tests/conftest.py

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import logging.config

# **新增**: 匯入 StaticPool
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


# --- 資料庫 Fixture ---

# 使用記憶體中的 SQLite 資料庫進行測試
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

# **核心修正**: 建立 engine 時，指定使用 StaticPool，
# 這會強制所有操作都使用同一個底層資料庫連線。
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function", autouse=True)
def setup_database():
    """
    一個自動執行的 fixture，在每個測試函式執行前後，
    自動建立和銷毀所有資料庫資料表。
    """
    # 移除除錯用的 print 語句
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """
    提供一個資料庫 session 給需要直接操作資料庫的測試。
    它假設資料表已由 setup_database fixture 建立。
    """
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- FastAPI 應用程式 Fixture ---


@pytest.fixture(scope="function")
def client(monkeypatch):
    """
    提供一個 FastAPI TestClient。
    - 依賴自動執行的 setup_database 來確保資料庫已準備就緒。
    - 使用 monkeypatch 來禁用檔案日誌。
    """
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
