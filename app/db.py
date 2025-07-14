# app/db.py

import os  # <--- 新增
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# from .config import settings # <--- 不再需要從 config 讀取

# --- 最終修正 ---
# 直接從環境變數讀取 DATABASE_URL
# 如果讀不到，就拋出明確的錯誤
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL 環境變數未設定，應用程式無法啟動。")

# 使用直接讀取到的 URL 建立資料庫引擎
engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
