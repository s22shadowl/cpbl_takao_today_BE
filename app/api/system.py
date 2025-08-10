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

# ▼▼▼ 新增這個 import ▼▼▼
from app.tasks import task_run_daily_crawl

router = APIRouter(
    prefix="/api/system",
    tags=["System"],
    responses={404: {"description": "Not found"}},
)


@router.get("/health", status_code=status.HTTP_200_OK)
def health_check(db: Session = Depends(get_db)):
    """
    執行健康檢查。
    """
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception as e:
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
    """
    if not redis_client:
        logging.warning("Redis client 不可用，無法清除快取。")
        return {"message": "Redis client not available. Cache not cleared."}

    try:
        cache_key_pattern = "app.api.analysis:*"
        logging.info(f"準備清除快取，使用模式: {cache_key_pattern}")

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


# --- ▼▼▼ 新增這個 API 端點 ▼▼▼ ---
@router.post(
    "/trigger-daily-crawl",
    summary="觸發每日例行爬蟲任務",
    description="此端點設計給外部排程服務 (如 GitHub Actions) 呼叫，以啟動每日爬蟲的檢查與執行流程。",
    dependencies=[Depends(verify_api_key)],
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_daily_crawl_task():
    """
    將每日爬蟲的進入點任務 `task_run_daily_crawl` 發送到背景佇列。
    """
    try:
        task = task_run_daily_crawl.send()
        logging.info(f"Daily crawl task triggered with task ID: {task.id}")
        return {
            "message": "Daily crawl task successfully triggered.",
            "task_id": task.id,
        }
    except Exception as e:
        logging.error(f"Failed to trigger daily crawl task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enqueue daily crawl task.",
        )


# --- ▲▲▲ 新增這個 API 端點 ▲▲▲ ---
