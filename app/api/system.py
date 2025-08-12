# app/api/system.py

import logging
from typing import Annotated

from fastapi.params import Header

import dramatiq
from dramatiq.results.errors import ResultMissing

from app.cache import redis_client
from app.config import settings
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db
from app.workers import task_run_daily_crawl

router = APIRouter(
    prefix="/api/system",
    tags=["System"],
    responses={404: {"description": "Not found"}},
)


@router.get("/health", status_code=status.HTTP_200_OK)
def health_check(db: Session = Depends(get_db)):
    """
    執行健康檢查，包含對資料庫與 Redis 的連線測試。
    """
    results = {}
    # 檢查資料庫連線
    try:
        db.execute(text("SELECT 1"))
        results["database"] = "ok"
    except Exception as e:
        logging.error(f"健康檢查失敗：資料庫連線錯誤 - {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection error: {e}",
        )

    # [修改] 增加 Redis 連線檢查
    if redis_client:
        try:
            redis_client.ping()
            results["redis"] = "ok"
        except Exception as e:
            logging.error(f"健康檢查失敗：Redis 連線錯誤 - {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Redis connection error: {e}",
            )
    else:
        results["redis"] = "not configured"

    results["status"] = "ok"
    return results


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
        # [修改] 從 config 讀取鍵名模式，以降低模組間的耦合
        cache_key_pattern = settings.REDIS_CACHE_KEY_PATTERN_ANALYSIS
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


@router.get(
    "/task-status/{task_id}",
    summary="查詢背景任務的執行狀態",
    description="根據任務 ID 查詢 Dramatiq 任務的狀態。",
    dependencies=[Depends(verify_api_key)],
    status_code=status.HTTP_200_OK,
)
def get_task_status(task_id: str):
    """
    查詢指定 task_id 的執行狀態。
    可能的狀態: running, succeeded, failed, unknown
    """
    broker = dramatiq.get_broker()
    result_backend = broker.get_result_backend()
    if not result_backend:
        raise HTTPException(
            status_code=501, detail="Result backend is not configured for the broker."
        )

    try:
        # Dramatiq 的 result backend 需要一個 Message 物件來查詢結果。
        # 由於此處我們只有 task_id，因此我們建立一個 dummy message。
        # 這是目前在不知道 actor name 的情況下查詢任意任務狀態的標準作法。
        message = dramatiq.Message(
            queue_name="default",
            actor_name="unknown",
            args=(),
            kwargs={},
            options={},
            message_id=task_id,
        )
        stored_result = result_backend.get_result(message, block=False)

        if isinstance(stored_result, Exception):
            logging.warning(f"Task {task_id} failed with exception: {stored_result}")
            return {"task_id": task_id, "status": "failed"}

        return {"task_id": task_id, "status": "succeeded"}
    except ResultMissing:
        # [修改] 增加日誌清晰度，說明此狀態的模糊性
        logging.info(
            f"Task {task_id} result is missing. "
            f"Assuming it is still running, has never existed, or the result has expired."
        )
        return {"task_id": task_id, "status": "running"}
    except Exception as e:
        logging.error(f"查詢任務狀態時發生未知錯誤 (ID: {task_id}): {e}", exc_info=True)
        return {"task_id": task_id, "status": "unknown"}
