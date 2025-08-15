# app/api/dependencies.py

from typing import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session
from fastapi import Security
from fastapi.security import APIKeyHeader
from app.config import Settings, settings  # 1. 匯入 settings 實例
from app.db import SessionLocal
from app.exceptions import InvalidCredentialsException
from app.services.dashboard import DashboardService

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_settings() -> Settings:  # 2. 回傳型別使用 Settings class
    """
    Settings 的依賴項提供者，直接回傳全域設定實例。
    """
    return settings  # 3. 直接回傳匯入的 settings 實例


def get_db() -> Iterator[Session]:  # 4. 修正回傳型別提示
    """
    資料庫 Session 的依賴項提供者。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_dashboard_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DashboardService:
    """
    DashboardService 的依賴項提供者。
    """
    return DashboardService(db=db, settings=settings)


async def get_api_key(api_key: str = Security(api_key_header)):
    """
    API 金鑰驗證的依賴項。
    """
    if not api_key or api_key != settings.API_KEY:
        # [修改] 改用自訂例外
        raise InvalidCredentialsException(
            message="Could not validate credentials: Invalid API Key"
        )
    return api_key
