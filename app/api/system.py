# app/api/system.py

import logging
from typing import Annotated

from fastapi.params import Header

from dramatiq.results.errors import ResultMissing
from app.broker_setup import broker

from app.cache import redis_client
from app.config import settings
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db
from app.workers import task_e2e_workflow_test, task_run_daily_crawl

# [修改] 導入新的例外類別
from app.exceptions import (
    InvalidCredentialsException,
    ServiceUnavailableException,
    ResultBackendNotConfiguredException,
)

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
    try:
        db.execute(text("SELECT 1"))
        results["database"] = "ok"
    except Exception as e:
        logging.error(f"Health check failed: Database connection error - {e}")
        raise ServiceUnavailableException(message=f"Database connection error: {e}")

    if redis_client:
        try:
            redis_client.ping()
            results["redis"] = "ok"
        except Exception as e:
            logging.error(f"Health check failed: Redis connection error - {e}")
            raise ServiceUnavailableException(message=f"Redis connection error: {e}")
    else:
        results["redis"] = "not configured"

    results["status"] = "ok"
    return results


async def verify_api_key(x_api_key: Annotated[str, Header()]):
    """Dependency to verify the API key."""
    if x_api_key != settings.API_KEY:
        raise InvalidCredentialsException(message="Invalid API Key")


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
        logging.warning("Redis client is not available, cannot clear cache.")
        return {"message": "Redis client not available. Cache not cleared."}

    # [新增] 增加 try/except 區塊以捕捉外部服務的錯誤
    try:
        cache_key_pattern = settings.REDIS_CACHE_KEY_PATTERN_ANALYSIS
        logging.info(f"Preparing to clear cache with pattern: {cache_key_pattern}")

        keys_to_delete = [
            key for key in redis_client.scan_iter(match=cache_key_pattern)
        ]

        if keys_to_delete:
            redis_client.delete(*keys_to_delete)
            logging.info(f"Successfully deleted {len(keys_to_delete)} cache keys.")
            return {
                "message": f"Successfully cleared {len(keys_to_delete)} cache keys."
            }
        else:
            logging.info("No matching cache keys found to clear.")
            return {"message": "No matching cache keys found to clear."}
    except Exception as e:
        logging.error(f"清除 Redis 快取時發生錯誤: {e}", exc_info=True)
        raise ServiceUnavailableException(message="Failed to communicate with Redis.")


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
    # [新增] 增加 try/except 區塊以捕捉外部服務的錯誤
    try:
        task = task_run_daily_crawl.send()
        logging.info(f"Daily crawl task triggered with task ID: {task.id}")
        return {
            "message": "Daily crawl task successfully triggered.",
            "task_id": task.id,
        }
    except Exception as e:
        logging.error(f"Failed to trigger daily crawl task: {e}", exc_info=True)
        raise ServiceUnavailableException(message="Failed to enqueue task.")


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
    可能的狀態: running, succeeded, failed
    """
    result_backend = broker.get_results_backend()
    if not result_backend:
        # [修正] 拋出特定的 HTTPException，讓 FastAPI 正確處理並回傳 501
        raise ResultBackendNotConfiguredException(message="Result backend 未設定")

    try:
        # 使用 message_id 查結果
        result = result_backend.get_result(task_id, block=False)

        # result 可能是 Exception 或真實結果
        if isinstance(result, Exception):
            return {"task_id": task_id, "status": "failed"}
        else:
            return {"task_id": task_id, "status": "succeeded"}
    except ResultMissing:
        logging.info(
            f"Task {task_id} result is missing. "
            f"Assuming it is still running, has never existed, or the result has expired."
        )
        return {"task_id": task_id, "status": "running"}
    except Exception:
        raise


@router.post(
    "/trigger-e2e-test-task",
    dependencies=[Depends(verify_api_key)],
    summary="Trigger E2E Workflow Test Task",
    description="[僅供 E2E 測試使用] 觸發一個快速完成的背景任務，用於驗證 GHA 工作流的健康度。",
)
def trigger_e2e_test_task():
    """
    觸發一個輕量級的 E2E 測試背景任務。
    """
    # 【修正】增加 try/except 區塊以捕捉 Broker 錯誤並回傳 503
    try:
        task = task_e2e_workflow_test.send()
        return {
            "message": "E2E workflow test task triggered.",
            "task_id": task.message_id,
        }
    except Exception as e:
        logging.error(f"Failed to trigger E2E test task: {e}", exc_info=True)
        raise ServiceUnavailableException(message="Failed to enqueue E2E test task.")
