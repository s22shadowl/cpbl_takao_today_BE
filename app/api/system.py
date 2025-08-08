# app/api/system.py

import logging
from typing import Annotated

from fastapi.params import Header

from app.cache import redis_client
from app.config import settings
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db

router = APIRouter(
    prefix="/api/system",
    tags=["System"],
    responses={404: {"description": "Not found"}},
)


@router.get("/health", status_code=status.HTTP_200_OK)
def health_check(db: Session = Depends(get_db)):
    """
    執行健康檢查。

    這個端點會嘗試連接資料庫並執行一個簡單的查詢，以確認服務本身
    及其關鍵依賴（資料庫）是否都正常運作。

    - **成功**: 回傳 HTTP 200 OK，表示服務健康。
    - **失敗**: 回傳 HTTP 503 Service Unavailable，表示服務的依賴項（資料庫）出現問題。
    """
    try:
        # 執行一個最簡單、成本最低的查詢來驗證資料庫連線
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception as e:
        # 如果資料庫連線失敗，拋出 503 錯誤
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection error: {e}",
        )


async def verify_api_key(x_api_key: Annotated[str, Header()]):
    """Dependency to verify the API key."""
    if x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")


@router.post(
    "/clear-cache",
    summary="清除所有分析相關的 Redis 快取",
    dependencies=[Depends(verify_api_key)],
    status_code=status.HTTP_200_OK,
)
def clear_analysis_cache():
    """
    清除所有由 app.cache 模組產生的快取。
    此端點應在每日爬蟲任務成功完成後由 Worker 呼叫。
    """
    # 檢查 redis_client 是否可用
    if not redis_client:
        logging.warning("Redis client 不可用，無法清除快取。")
        # 即使 Redis 不可用，也回傳成功，因為這不是一個致命錯誤
        return {"message": "Redis client not available. Cache not cleared."}

    try:
        # 我們將清除所有以 "app.api.analysis" 開頭的快取鍵
        cache_key_pattern = "app.api.analysis:*"
        logging.info(f"準備清除快取，使用模式: {cache_key_pattern}")

        # 使用 SCAN 迭代器安全地找出所有匹配的鍵
        keys_to_delete = [
            key for key in redis_client.scan_iter(match=cache_key_pattern)
        ]

        if keys_to_delete:
            redis_client.delete(*keys_to_delete)
            logging.info(f"成功刪除 {len(keys_to_delete)} 個快取鍵。")
            return {
                "message": f"Successfully cleared {len(keys_to_delete)} cache keys."
            }
        else:
            logging.info("找不到符合模式的快取鍵，無需清除。")
            return {"message": "No matching cache keys found to clear."}

    except Exception as e:
        logging.error(f"清除 Redis 快取時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to clear cache.")
