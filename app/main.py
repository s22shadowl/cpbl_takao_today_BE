import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from typing import List
from multiprocessing import Process

from app import models, db_actions, scraper
from app.db import get_db_connection
from app.core import schedule_scraper
from app.scheduler import setup_scheduler

# --- 背景任務的獨立工作函式 ---
def run_schedule_update_and_reschedule():
    """
    一個獨立的函式，用於在新的行程中執行。
    它首先執行耗時的爬蟲任務（包含過去比賽），然後重新設定排程器。
    """
    print("背景行程：開始執行賽程更新...")
    schedule_scraper.scrape_cpbl_schedule(2025, 3, 10, include_past_games=True)
    print("背景行程：賽程更新完畢，開始重設排程器...")
    setup_scheduler()
    print("背景行程：排程重設完畢。")

# --- FastAPI 應用程式設定 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 應用程式啟動時執行的程式碼
    print("應用程式啟動中...")
    setup_scheduler()
    yield
    # 應用程式關閉時執行的程式碼 (如果需要)
    print("應用程式正在關閉...")

app = FastAPI(lifespan=lifespan)

# --- API 端點 ---

@app.get("/api/games/{game_date}", response_model=List[models.GameResult])
def get_games_by_date(game_date: str):
    try:
        datetime.datetime.strptime(game_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="日期格式錯誤，請使用YYYY-MM-DD 格式。")
    
    conn = get_db_connection()
    try:
        # 注意：此處的 get_games_by_date 函式尚未在 db_actions.py 中實作
        games = db_actions.get_games_by_date(conn, game_date)
        if not games:
            raise HTTPException(status_code=404, detail=f"找不到日期 {game_date} 的比賽結果。")
        return games
    finally:
        conn.close()

@app.post("/api/run_scraper", status_code=202)
def run_scraper_manually(mode: str, date: str | None = None):
    if mode not in ["daily", "monthly", "yearly"]:
        raise HTTPException(status_code=400, detail="無效的模式。請使用 'daily', 'monthly', 或 'yearly'。")
    
    message = ""
    target_func = None
    args_tuple = (date,)

    if mode == "daily":
        target_func = scraper.scrape_single_day
        message = f"已觸發每日爬蟲任務 ({date or '今天'})。"
    elif mode == "monthly":
        target_func = scraper.scrape_entire_month
        args_tuple = (date,)
        message = f"已觸發每月爬蟲任務 ({date or '本月'})。"
    elif mode == "yearly":
        target_func = scraper.scrape_entire_year
        args_tuple = (date,)
        message = f"已觸發每年爬蟲任務 ({date or '今年'})。"
    
    if target_func:
        process = Process(target=target_func, args=args_tuple)
        process.start()
    else:
        raise HTTPException(status_code=500, detail="無法匹配對應的爬蟲任務。")
        
    headers = {"Content-Type": "application/json; charset=utf-8"}
    return JSONResponse(content={"message": message}, headers=headers, status_code=202)


@app.post("/api/update_schedule", status_code=202)
def update_schedule_manually():
    """
    手動觸發賽程更新與排程重設的 API 端點。
    """
    print("主行程：接收到更新請求，準備啟動背景行程...")
    process = Process(target=run_schedule_update_and_reschedule)
    process.start()
    
    print("主行程：背景行程已啟動，立即回傳 API 回應。")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    return JSONResponse(content={"message": "已觸發賽程更新與排程重設任務。"}, headers=headers, status_code=202)
