# tests/conftest.py

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
import logging.config
from sqlalchemy.pool import StaticPool


def pytest_collection_modifyitems(config, items):
    """
    在 pytest 收集完所有測試項目後，自動為位於 'e2e' 目錄下的測試
    加上 'e2e' 標記。
    """
    for item in items:
        if "e2e" in item.path.parts:
            item.add_marker(pytest.mark.e2e)


@pytest.fixture(scope="function", autouse=True)
def apply_test_settings(monkeypatch, request):
    """
    為每個測試函式設定必要的環境變數。
    此 fixture 會檢查測試是否有 'e2e' 標記。
    - 如果有，它會直接跳過，不執行任何操作。
    - 如果沒有，它才會設定單元測試所需的環境。
    """
    if "e2e" in request.node.keywords:
        yield
        return
    else:
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
        monkeypatch.setenv("DRAMATIQ_BROKER_URL", "redis://localhost:6379/1")
        monkeypatch.setenv("API_KEY", "test-api-key-for-pytest")
        yield


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
    """
    根據測試 engine 建立 sessionmaker。
    為了讓未重構的測試通過，暫時還原事件監聽器。
    """
    from app.models import AtBatDetailDB, PlayerGameSummaryDB

    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def before_flush_listener(session, flush_context, instances):
        """
        在 session flush 到資料庫前，自動為新的 AtBatDetailDB 物件
        回填 denormalized 的 game_id，以修復因模型變更導致的單元測試失效。
        """
        for instance in session.new:
            if isinstance(instance, AtBatDetailDB) and not instance.game_id:
                if instance.player_summary:
                    instance.game_id = instance.player_summary.game_id
                elif instance.player_game_summary_id:
                    summary = session.get(
                        PlayerGameSummaryDB, instance.player_game_summary_id
                    )
                    if summary:
                        instance.game_id = summary.game_id

    event.listen(Session, "before_flush", before_flush_listener)
    return Session


@pytest.fixture
def factories(db_session):
    """
    【新增】提供一個已設定好資料庫 session 的工廠模組。
    測試函式應明確請求此 fixture 來使用 factory-boy。
    """
    from tests import factories as factories_module

    factories_module.BaseFactory._meta.sqlalchemy_session = db_session
    yield factories_module
    factories_module.BaseFactory._meta.sqlalchemy_session = None


# --- 資料庫 Fixture ---


@pytest.fixture(scope="function")
def setup_database(engine):
    """
    在每個測試函式執行前後，自動建立和銷毀所有資料庫資料表。
    """
    from app.db import Base

    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(TestingSessionLocal, setup_database):
    """
    提供一個資料庫 session 給需要直接操作資料庫的測試。
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
    """
    from app.main import app
    from app.db import get_db

    monkeypatch.setattr(logging.config, "dictConfig", lambda *args, **kwargs: None)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
