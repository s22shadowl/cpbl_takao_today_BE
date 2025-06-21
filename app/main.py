# app/main.py

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from typing import List, Optional
import datetime
import logging
from contextlib import asynccontextmanager

from app import db, models, scraper, db_actions

# --- 排程器設定 ---
scheduler = BackgroundScheduler(timezone="Asia/Taipei")

def daily_scrape_job():
    """排程器要執行的任務：抓取昨天的比賽數據。"""
    yesterday_str = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    logging.info(f"排程任務啟動：開始抓取 {yesterday_str} 的數據...")
    try:
        scraper.scrape_single_day(specific_date=yesterday_str)
        logging.info(f"排程任務成功完成。")
    except Exception as e:
        logging.error(f"排程任務執行失敗: {e}", exc_info=True)

# --- FastAPI V2 生命週期事件處理器 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 應用程式啟動時執行的程式碼
    logging.info("應用程式啟動，設定每日排程任務...")
    scheduler.add_job(daily_scrape_job, 'cron', hour=4, minute=0, id="daily_scrape_job", replace_existing=True)
    scheduler.start()
    logging.info("排程器已啟動。每日爬取任務已設定在 04:00 執行。")
    yield
    # 應用程式關閉時執行的程式碼
    logging.info("應用程式準備關閉...")
    if scheduler.running:
        scheduler.shutdown()
        logging.info("排程器已安全關閉。")

# --- FastAPI 應用程式設定 ---
app = FastAPI(
    title="CPBL Stats API", 
    version="1.0.0",
    description="一個提供中華職棒數據查詢與爬蟲觸發的 API。",
    lifespan=lifespan # 註冊 lifespan 事件
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"], # 根據您的前端 React App 的位址調整
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API 端點 (Endpoints) ---
# --- 待依實際需求調整，先架骨架起來 ---

@app.get("/", response_model=models.Message, tags=["General"])
async def read_root():
    """API 根目錄，返回歡迎訊息。"""
    return {"message": "歡迎使用 CPBL Stats API"}

@app.get("/api/games", response_model=List[models.GameResult], tags=["Games"])
async def get_games_by_date(game_date: str):
    """根據指定日期獲取所有比賽的概要資訊。"""
    try:
        datetime.datetime.strptime(game_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="日期格式錯誤，請使用YYYY-MM-DD。")

    conn = db.get_db_connection()
    try:
        games = db_actions.get_games_by_date(conn, game_date)
        if not games:
            raise HTTPException(status_code=404, detail=f"找不到日期 {game_date} 的比賽結果。")
        return [dict(row) for row in games]
    finally:
        if conn:
            conn.close()

@app.get("/api/player/season_stats/{player_name}", response_model=models.PlayerSeasonStats, tags=["Players"])
async def get_season_stats(player_name: str):
    """獲取指定球員最新的球季累積數據。"""
    conn = db.get_db_connection()
    try:
        stats = db_actions.get_player_season_stats(conn, player_name)
        if not stats:
            raise HTTPException(status_code=404, detail=f"找不到球員 {player_name} 的球季數據。")
        return dict(stats)
    finally:
        if conn:
            conn.close()

@app.get("/api/player/game_stats/{player_name}", response_model=List[models.PlayerGameSummary], tags=["Players"])
async def get_game_stats(player_name: str, limit: int = Query(10, ge=1, le=50)):
    """獲取指定球員最近幾場比賽的表現總結。"""
    conn = db.get_db_connection()
    try:
        summaries = db_actions.get_player_game_summaries(conn, player_name, limit)
        if not summaries:
            raise HTTPException(status_code=404, detail=f"找不到球員 {player_name} 的任何比賽數據。")
        return [dict(row) for row in summaries]
    finally:
        if conn:
            conn.close()

@app.post("/api/run_scraper", response_model=models.Message, tags=["Scraper"])
async def trigger_scraper_manually(
    background_tasks: BackgroundTasks,
    mode: str = Query(..., description="執行模式: 'daily', 'monthly', 'yearly'"),
    date: Optional[str] = Query(None, description="日期 (YYYY-MM-DD), 月份 (YYYY-MM), 或年份 (YYYY)")
):
    """手動觸發爬蟲任務，任務將在背景執行。"""
    if mode == 'daily':
        background_tasks.add_task(scraper.scrape_single_day, specific_date=date)
        return {"message": f"已在背景觸發 [單日] 爬蟲任務，目標日期: {date or '今天'}。"}
    elif mode == 'monthly':
        background_tasks.add_task(scraper.scrape_entire_month, month_str=date)
        return {"message": f"已在背景觸發 [逐月] 爬蟲任務，目標月份: {date or '本月'}。"}
    elif mode == 'yearly':
        background_tasks.add_task(scraper.scrape_entire_year, year_str=date)
        return {"message": f"已在背景觸發 [逐年] 爬蟲任務，目標年份: {date or '本年'}。"}
    else:
        raise HTTPException(status_code=400, detail="無效的模式。請使用 'daily', 'monthly', 或 'yearly'。")