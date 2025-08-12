# app/api/jobs.py

import logging
import datetime
from fastapi import APIRouter, Depends
from typing import Optional
from pydantic import BaseModel

from app.api.dependencies import get_api_key

# [修改] 導入新的例外類別
from app.exceptions import InvalidInputException

# [重構] 從新的 workers 模組匯入 actors
from app.workers import (
    task_update_schedule_and_reschedule,
    task_scrape_single_day,
    task_scrape_entire_month,
    task_scrape_entire_year,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Jobs & Tasks"],
    dependencies=[Depends(get_api_key)],
)


class ScraperRequest(BaseModel):
    mode: str
    date: Optional[str] = None


@router.post("/api/run_scraper", status_code=202)
def run_scraper_manually(request_data: ScraperRequest):
    """
    手動觸發爬蟲任務。此端點僅負責驗證輸入並分派任務至背景佇列。
    """
    mode = request_data.mode
    date_str = request_data.date

    if mode not in ["daily", "monthly", "yearly"]:
        # [修改] 改用自訂例外
        raise InvalidInputException(
            message="Invalid mode. Please use 'daily', 'monthly', or 'yearly'."
        )

    message = ""
    if mode == "daily":
        if date_str:
            try:
                datetime.datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                # [修改] 改用自訂例外
                raise InvalidInputException(
                    message="Invalid date format, please use YYYY-MM-DD."
                )
        task_scrape_single_day.send(date_str)
        message = f"Daily scraper task for ({date_str or 'today'}) has been sent to the queue."

    elif mode == "monthly":
        task_scrape_entire_month.send(date_str)
        message = f"Monthly scraper task for ({date_str or 'this month'}) has been sent to the queue."
    elif mode == "yearly":
        task_scrape_entire_year.send(date_str)
        message = f"Yearly scraper task for ({date_str or 'this year'}) has been sent to the queue."

    return {"message": message}


@router.post("/api/update_schedule", status_code=202)
def update_schedule_manually():
    """手動觸發賽程更新任務。"""
    logger.info("Main app: Received schedule update request, sending task to queue...")
    task_update_schedule_and_reschedule.send()
    logger.info("Main app: Task sent successfully, returning API response immediately.")
    return {"message": "Schedule update task has been successfully sent to the queue."}
