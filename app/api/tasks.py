# app/api/tasks.py

import logging
import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
from pydantic import BaseModel

from app.api.dependencies import get_api_key
from app.tasks import (
    task_update_schedule_and_reschedule,
    task_scrape_single_day,
    task_scrape_entire_month,
    task_scrape_entire_year,
)

from app.core import fetcher
from app.parsers import schedule

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Tasks"],
)


class ScraperRequest(BaseModel):
    mode: str
    date: Optional[str] = None


@router.post("/api/run_scraper", status_code=202, dependencies=[Depends(get_api_key)])
def run_scraper_manually(request_data: ScraperRequest):
    """手動觸發爬蟲任務。"""
    mode = request_data.mode
    date_str = request_data.date

    if mode not in ["daily", "monthly", "yearly"]:
        raise HTTPException(
            status_code=400,
            detail="無效的模式。請使用 'daily', 'monthly', 或 'yearly'。",
        )

    message = ""
    if mode == "daily":
        today = datetime.date.today()
        target_date_obj = (
            datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            if date_str
            else today
        )

        # 為了取得當天的賽程，我們需要抓取並解析該月份的賽程頁面
        html_content = fetcher.fetch_schedule_page(
            target_date_obj.year, target_date_obj.month
        )
        if not html_content:
            raise HTTPException(
                status_code=500,
                detail=f"無法獲取 {target_date_obj.strftime('%Y-%m')} 的賽程頁面。",
            )

        all_month_games = schedule.parse_schedule_page(
            html_content, target_date_obj.year
        )

        # 從月份的所有比賽中，篩選出目標日期的比賽
        games_for_day = [
            game
            for game in all_month_games
            if game["game_date"] == str(target_date_obj)
        ]

        task_scrape_single_day.send(str(target_date_obj), games_for_day)
        message = f"已將每日爬蟲任務 ({date_str or '今天'}) 發送到背景佇列。"

    elif mode == "monthly":
        task_scrape_entire_month.send(date_str)
        message = f"已將每月爬蟲任務 ({date_str or '本月'}) 發送到背景佇列。"
    elif mode == "yearly":
        task_scrape_entire_year.send(date_str)
        message = f"已將每年爬蟲任務 ({date_str or '今年'}) 發送到背景佇列。"

    headers = {"Content-Type": "application/json; charset=utf-8"}
    return JSONResponse(content={"message": message}, headers=headers, status_code=202)


@router.post(
    "/api/update_schedule", status_code=202, dependencies=[Depends(get_api_key)]
)
def update_schedule_manually():
    """手動觸發賽程更新任務。"""
    logger.info("主程式：接收到更新請求，準備將任務發送到佇列...")
    task_update_schedule_and_reschedule.send()
    logger.info("主程式：任務已成功發送，立即回傳 API 回應。")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    return JSONResponse(
        content={"message": "已成功將賽程更新任務發送到背景佇列。"},
        headers=headers,
        status_code=202,
    )
