# app/main.py (生命週期修正)

import datetime
import logging
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from sqlalchemy.orm import Session

from app import models
from app.db import get_db, engine
from app.config import settings
from app.logging_config import setup_logging
from app.tasks import (
    task_update_schedule_and_reschedule,
    task_scrape_single_day,
    task_scrape_entire_month,
    task_scrape_entire_year,
)

setup_logging()
logger = logging.getLogger(__name__)

# 【核心修正】: 不在模組載入時建立表格


# --- FastAPI 應用程式設定 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("應用程式啟動中...")
    # 【核心修正】: 將表格建立的邏輯移至此處
    # 這確保了只有在應用程式真正啟動時，才會嘗試連接資料庫並建立表格
    logger.info("正在檢查並建立資料庫表格...")
    models.Base.metadata.create_all(bind=engine)
    logger.info("資料庫表格檢查完畢。")
    yield
    logger.info("應用程式正在關閉...")


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_api_key(api_key: str = Security(api_key_header)):
    if not api_key or api_key != settings.API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Could not validate credentials: Invalid API Key",
        )
    return api_key


# --- API 端點 ---


@app.get("/api/games/{game_date}", response_model=List[models.GameResult])
def get_games_by_date(game_date: str, db: Session = Depends(get_db)):
    try:
        parsed_date = datetime.datetime.strptime(game_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=422, detail="日期格式錯誤，請使用YYYY-MM-DD 格式。"
        )

    games = (
        db.query(models.GameResultDB)
        .filter(models.GameResultDB.game_date == parsed_date)
        .all()
    )

    if not games:
        raise HTTPException(
            status_code=404, detail=f"找不到日期 {game_date} 的比賽結果。"
        )

    return games


@app.post("/api/run_scraper", status_code=202, dependencies=[Depends(get_api_key)])
def run_scraper_manually(mode: str, date: Optional[str] = None):
    if mode not in ["daily", "monthly", "yearly"]:
        raise HTTPException(
            status_code=400,
            detail="無效的模式。請使用 'daily', 'monthly', 或 'yearly'。",
        )

    message = ""
    if mode == "daily":
        task_scrape_single_day.send(date)
        message = f"已將每日爬蟲任務 ({date or '今天'}) 發送到背景佇列。"
    elif mode == "monthly":
        task_scrape_entire_month.send(date)
        message = f"已將每月爬蟲任務 ({date or '本月'}) 發送到背景佇列。"
    elif mode == "yearly":
        task_scrape_entire_year.send(date)
        message = f"已將每年爬蟲任務 ({date or '今年'}) 發送到背景佇列。"

    headers = {"Content-Type": "application/json; charset=utf-8"}
    return JSONResponse(content={"message": message}, headers=headers, status_code=202)


@app.post("/api/update_schedule", status_code=202, dependencies=[Depends(get_api_key)])
def update_schedule_manually():
    logger.info("主程式：接收到更新請求，準備將任務發送到佇列...")
    task_update_schedule_and_reschedule.send()
    logger.info("主程式：任務已成功發送，立即回傳 API 回應。")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    return JSONResponse(
        content={"message": "已成功將賽程更新任務發送到背景佇列。"},
        headers=headers,
        status_code=202,
    )
