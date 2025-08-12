# app/api/tasks.py

import logging
import datetime
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from pydantic import BaseModel

from app.api.dependencies import get_api_key
from app.tasks import (
    task_update_schedule_and_reschedule,
    task_scrape_single_day,
    task_scrape_entire_month,
    task_scrape_entire_year,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Tasks"],
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
        raise HTTPException(
            status_code=400,
            detail="無效的模式。請使用 'daily', 'monthly', 或 'yearly'。",
        )

    message = ""
    if mode == "daily":
        if date_str:
            try:
                datetime.datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(
                    status_code=422, detail="日期格式錯誤，請使用 YYYY-MM-DD 格式。"
                )
        task_scrape_single_day.send(date_str)
        message = f"已將每日爬蟲任務 ({date_str or '今天'}) 發送到背景佇列。"

    elif mode == "monthly":
        task_scrape_entire_month.send(date_str)
        message = f"已將每月爬蟲任務 ({date_str or '本月'}) 發送到背景佇列。"
    elif mode == "yearly":
        task_scrape_entire_year.send(date_str)
        message = f"已將每年爬蟲任務 ({date_str or '今年'}) 發送到背景佇列。"

    return {"message": message}


@router.post("/api/update_schedule", status_code=202)
def update_schedule_manually():
    """手動觸發賽程更新任務。"""
    logger.info("主程式：接收到更新請求，準備將任務發送到佇列...")
    task_update_schedule_and_reschedule.send()
    logger.info("主程式：任務已成功發送，立即回傳 API 回應。")
    return {"message": "已成功將賽程更新任務發送到背景佇列。"}
