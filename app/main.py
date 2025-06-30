# app/main.py

import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks
from contextlib import asynccontextmanager
from typing import List

from app import models, db_actions, scraper
from app.db import get_db_connection
from app.core import schedule_scraper
from app.scheduler import setup_scheduler # 【修改】導入排程器設定函式

# 使用 lifespan 事件來在應用程式啟動時執行排程設定
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 應用程式啟動時執行的程式碼
    print("應用程式啟動中...")
    setup_scheduler() # 【修改】呼叫排程器設定
    yield
    # 應用程式關閉時執行的程式碼 (如果需要)
    print("應用程式正在關閉...")

app = FastAPI(lifespan=lifespan)

# --- API 端點 ---

@app.get("/api/games/{game_date}", response_model=List[models.GameResult])
def get_games_by_date(game_date: str):
    # (此端點不變)
    try:
        datetime.datetime.strptime(game_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="日期格式錯誤，請使用 YYYY-MM-DD 格式。")
    
    conn = get_db_connection()
    try:
        games = db_actions.get_games_by_date(conn, game_date)
        if not games:
            raise HTTPException(status_code=404, detail=f"找不到日期 {game_date} 的比賽結果。")
        return games
    finally:
        conn.close()

@app.post("/api/run_scraper", status_code=202)
def run_scraper_manually(background_tasks: BackgroundTasks, mode: str, date: str | None = None):
    # (此端點不變)
    if mode not in ["daily", "monthly", "yearly"]:
        raise HTTPException(status_code=400, detail="無效的模式。請使用 'daily', 'monthly', 或 'yearly'。")
    
    if mode == "daily":
        background_tasks.add_task(scraper.scrape_single_day, specific_date=date)
        return {"message": f"已觸發每日爬蟲任務 ({date or '今天'})。"}
    elif mode == "monthly":
        background_tasks.add_task(scraper.scrape_entire_month, month_str=date)
        return {"message": f"已觸發每月爬蟲任務 ({date or '本月'})。"}
    elif mode == "yearly":
        background_tasks.add_task(scraper.scrape_entire_year, year_str=date)
        return {"message": f"已觸發每年爬蟲任務 ({date or '今年'})。"}

@app.post("/api/update_schedule", status_code=202)
def update_schedule_manually(background_tasks: BackgroundTasks):
    """
    【全新】手動觸發賽程更新與排程重設的 API 端點。
    """
    # 為了不阻塞 API 回應，我們將爬取任務放在背景執行
    background_tasks.add_task(schedule_scraper.scrape_cpbl_schedule, 2025, 3, 10)
    # 在爬取完成後，重新設定排程
    background_tasks.add_task(setup_scheduler)

    return {"message": "已觸發賽程更新與排程重設任務。"}