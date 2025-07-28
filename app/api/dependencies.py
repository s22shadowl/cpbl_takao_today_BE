# app/api/dependencies.py

from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

from app.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_api_key(api_key: str = Security(api_key_header)):
    """
    API 金鑰驗證的依賴項。
    """
    if not api_key or api_key != settings.API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Could not validate credentials: Invalid API Key",
        )
    return api_key
