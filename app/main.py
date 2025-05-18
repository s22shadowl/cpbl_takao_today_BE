from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware # 處理跨域請求
from apscheduler.schedulers.background import BackgroundScheduler
from typing import List, Optional
import datetime
import atexit # 用於程式結束時關閉排程器
import logging

from . import db # 從同目錄的 db.py 匯入
from . import models # 從同目錄的 models.py 匯入
from .scraper import run_scraper_tasks # 從同目錄的 scraper.py 匯入

# 設定日誌 (與 scraper.py 分開設定，或共用一個全域設定)
api_logger = logging.getLogger("api")
api_logger.setLevel(logging.INFO)
# stream_handler = logging.StreamHandler()
# stream_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# stream_handler.setFormatter(stream_formatter)
# api_logger.addHandler(stream_handler)
# (如果 scraper.py 中已經有 StreamHandler，這裡可以不用重複加，避免重複輸出)

app = FastAPI(title="CPBL Stats API", version="0.1.0")

# --- CORS 中間件設定 ---
# 允許所有來源 (在開發時方便，生產環境應更嚴格)
origins = [
    "http://localhost",       # React 開發伺服器預設
    "http://localhost:3000",  # React 開發伺服器常見埠號
    "http://localhost:5173",  # Vite React 開發伺服器常見埠號
    # 你部署前端的實際網域
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # 允許所有 HTTP 方法
    allow_headers=["*"], # 允許所有 HTTP 標頭
)

# --- 排程器設定 ---
scheduler = BackgroundScheduler(timezone="Asia/Taipei") # 設定時區

def scheduled_job():
    """排程執行的任務"""
    api_logger.info("排程任務開始：執行爬蟲...")
    try:
        run_scraper_tasks()
        api_logger.info("排程任務：爬蟲執行完畢。")
    except Exception as e:
        api_logger.error(f"排程任務執行爬蟲時發生錯誤: {e}", exc_info=True)

# 應用啟動時執行的事件
@app.on_event("startup")
async def startup_event():
    api_logger.info("應用程式啟動...")
    # 每天凌晨 03:00 執行爬蟲 (你可以根據需求調整時間)
    scheduler.add_job(scheduled_job, 'cron', hour=3, minute=0, misfire_grace_time=900)
    # scheduler.add_job(scheduled_job, 'interval', minutes=60) # DEBUG: 每60分鐘執行一次
    if not scheduler.running:
        scheduler.start()
        api_logger.info("排程器已啟動。")
    
    # (可選) 應用啟動時先執行一次爬蟲
    # import asyncio
    # asyncio.create_task(run_scraper_tasks_async_wrapper()) # 如果 run_scraper_tasks 是同步的
    api_logger.info("執行一次啟動爬蟲任務...")
    try:
        scheduled_job() # 首次啟動時同步執行一次 (或者異步執行)
    except Exception as e:
        api_logger.error(f"啟動時執行爬蟲失敗: {e}", exc_info=True)


# 應用關閉時執行的事件
@app.on_event("shutdown")
async def shutdown_event():
    if scheduler.running:
        scheduler.shutdown()
        api_logger.info("排程器已關閉。")
    api_logger.info("應用程式關閉。")

# 確保程式退出時能正常關閉排程器 (對於 uvicorn --reload 可能不完全有效)
atexit.register(lambda: scheduler.shutdown() if scheduler.running else None)


# --- API 端點 ---
@app.get("/", response_model=models.Message)
async def read_root():
    return {"message": "歡迎使用 CPBL Stats API"}

@app.get("/api/games", response_model=List[models.GameResult])
async def get_games_by_date(
    game_date: Optional[str] = Query(None, description="比賽日期 (YYYY-MM-DD)。預設為今天。")
):
    if game_date is None:
        game_date = datetime.date.today().strftime("%Y-%m-%d")
    else:
        try:
            datetime.datetime.strptime(game_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式錯誤，請使用 YYYY-MM-DD。")

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM game_results WHERE game_date = ? ORDER BY game_time", (game_date,))
    games = cursor.fetchall()
    conn.close()
    if not games:
        # raise HTTPException(status_code=404, detail=f"找不到 {game_date} 的比賽結果。")
        api_logger.info(f"API: 找不到 {game_date} 的比賽結果。")
        return [] # 返回空列表而非 404，前端較好處理
    return games

@app.get("/api/player_stats/{player_name}", response_model=List[models.PlayerDailyStat])
async def get_player_stats_history(
    player_name: str,
    limit: int = Query(30, ge=1, le=100, description="返回最近的幾筆資料")
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM player_daily_stats WHERE player_name = ? ORDER BY game_date DESC LIMIT ?",
        (player_name, limit)
    )
    stats = cursor.fetchall()
    conn.close()
    if not stats:
        # raise HTTPException(status_code=404, detail=f"找不到球員 {player_name} 的數據。")
        api_logger.info(f"API: 找不到球員 {player_name} 的數據。")
        return []
    return stats

@app.get("/api/player_stats_by_date", response_model=List[models.PlayerDailyStat])
async def get_player_stats_for_date(
    game_date: str = Query(..., description="比賽日期 (YYYY-MM-DD)"),
    team_name: Optional[str] = Query(None, description="球隊名稱 (可選)")
):
    try:
        datetime.datetime.strptime(game_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式錯誤，請使用 YYYY-MM-DD。")

    conn = db.get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM player_daily_stats WHERE game_date = ?"
    params = [game_date]

    if team_name:
        query += " AND team = ?"
        params.append(team_name)
    
    query += " ORDER BY player_name"
    cursor.execute(query, tuple(params))
    stats = cursor.fetchall()
    conn.close()
    if not stats:
        # raise HTTPException(status_code=404, detail=f"找不到 {game_date} {team_name or ''} 的球員數據。")
        api_logger.info(f"API: 找不到 {game_date} {team_name or ''} 的球員數據。")
        return []
    return stats

@app.post("/api/run_scraper_manually", response_model=models.Message)
async def trigger_scraper_manually():
    """手動觸發一次爬蟲任務 (主要用於測試)"""
    api_logger.info("手動觸發爬蟲任務...")
    try:
        # 由於 run_scraper_tasks 是同步阻塞的，在 FastAPI 中直接呼叫會阻塞事件循環
        # 理想情況下，長時間運行的任務應該在背景執行緒或任務隊列中執行
        # 此處為簡化，直接呼叫，但要知道這在生產環境中可能影響 API 回應性
        # from concurrent.futures import ThreadPoolExecutor
        # loop = asyncio.get_event_loop()
        # with ThreadPoolExecutor() as pool:
        #     await loop.run_in_executor(pool, run_scraper_tasks)

        # 簡單的同步執行 (用於測試)
        run_scraper_tasks()
        api_logger.info("手動爬蟲任務執行完畢。")
        return {"message": "爬蟲任務已手動觸發並執行完畢。"}
    except Exception as e:
        api_logger.error(f"手動執行爬蟲時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"手動執行爬蟲失敗: {str(e)}")

# --- 靜態檔案 (可選，如果你的 FastAPI 也想服務前端打包後的檔案) ---
# from fastapi.staticfiles import StaticFiles
# app.mount("/static", StaticFiles(directory="path_to_your_static_files"), name="static")
# @app.get("/")
# async def serve_spa(request: Request):
#     return FileResponse(os.path.join("path_to_your_static_files", "index.html"))