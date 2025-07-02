# app/db.py

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings

# 根據 .env 中的 DATABASE_URL 建立資料庫引擎
engine = create_engine(settings.DATABASE_URL)

# 建立一個 SessionLocal 類別，它將作為資料庫會話的工廠
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 建立一個 Base 類別，我們的 ORM 模型將繼承它
Base = declarative_base()


# --- FastAPI 依賴注入 (Dependency Injection) ---
def get_db():
    """
    一個 FastAPI 的依賴函式。
    它會在每個 API 請求的生命週期中，建立並提供一個資料庫會話，
    並在請求結束後（無論成功或失敗）關閉它。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()