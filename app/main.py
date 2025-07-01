# app/main.py (修改後)

import datetime
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from typing import List

# SQLAlchemy 的 Session，用於型別提示
from sqlalchemy.orm import Session

# 匯入我們新的 SQLAlchemy 模型、設定、和資料庫連線函式
from app import models, scraper
from app.db import get_db, engine
from app.core import schedule_scraper
from app.scheduler import setup_scheduler

# 為了讓 SQLAlchemy 在啟動時就能找到所有模型，我們需要在此處引用 models
# 雖然看似沒有直接使用，但這是必要的，以便 Base.metadata 能夠建立表格
models.Base.metadata.create_all(bind=engine)


# --- 背景任務的獨立工作函式 ---
# 這部分維持不變，但我們將透過 BackgroundTasks 呼叫它
def run_schedule_update_and_reschedule():
    """
    一個獨立的函式，用於在背景執行。
    它首先執行耗時的爬蟲任務（包含過去比賽），然後重新設定排程器。
    """
    print("背景任務：開始執行賽程更新...")
    # 注意：這裡的年份是寫死的，未來可以改為從 API 參數傳入
    schedule_scraper.scrape_cpbl_schedule(2025, 3, 10, include_past_games=True)
    print("背景任務：賽程更新完畢，開始重設排程器...")
    setup_scheduler()
    print("背景任務：排程重設完畢。")


# --- FastAPI 應用程式設定 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 應用程式啟動時執行的程式碼
    print("應用程式啟動中...")
    # 我們仍然可以在此處設定排程器，但記得部署到 Render 後要用外部 Cron Job
    setup_scheduler()
    yield
    # 應用程式關閉時執行的程式碼 (如果需要)
    print("應用程式正在關閉...")

app = FastAPI(lifespan=lifespan)


# --- API 端點 ---

# response_model 改用我們在 models.py 中定義的 Pydantic 模型
# 加入 db: Session = Depends(get_db) 來取得資料庫連線
@app.get("/api/games/{game_date}", response_model=List[models.GameResult])
def get_games_by_date(game_date: str, db: Session = Depends(get_db)):
    try:
        # 將日期字串轉換為 date 物件，以便與資料庫的 Date 型別比較
        parsed_date = datetime.datetime.strptime(game_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=422, detail="日期格式錯誤，請使用YYYY-MM-DD 格式。")
    
    # 使用 SQLAlchemy ORM 語法來查詢資料
    # 這等同於 SELECT * FROM game_results WHERE game_date = :game_date
    games = db.query(models.GameResultDB).filter(models.GameResultDB.game_date == parsed_date).all()
    
    if not games:
        raise HTTPException(status_code=404, detail=f"找不到日期 {game_date} 的比賽結果。")
    
    # SQLAlchemy 回傳的是 ORM 物件，FastAPI 會自動依據 response_model 將其轉換為 JSON
    return games


# 使用 BackgroundTasks 替代 multiprocessing.Process
@app.post("/api/run_scraper", status_code=202)
def run_scraper_manually(background_tasks: BackgroundTasks, mode: str, date: str | None = None):
    if mode not in ["daily", "monthly", "yearly"]:
        raise HTTPException(status_code=400, detail="無效的模式。請使用 'daily', 'monthly', 或 'yearly'。")
    
    target_func = None
    args_tuple = (date,)

    if mode == "daily":
        target_func = scraper.scrape_single_day
        message = f"已觸發每日爬蟲背景任務 ({date or '今天'})。"
    # ... 其他模式可以照樣加入
    # elif mode == "monthly": ...
    # elif mode == "yearly": ...
    
    if target_func:
        # 將爬蟲函式加入背景任務佇列
        background_tasks.add_task(target_func, *args_tuple)
    else:
        raise HTTPException(status_code=500, detail="無法匹配對應的爬蟲任務。")
        
    headers = {"Content-Type": "application/json; charset=utf-8"}
    return JSONResponse(content={"message": message}, headers=headers, status_code=202)


# 同樣使用 BackgroundTasks
@app.post("/api/update_schedule", status_code=202)
def update_schedule_manually(background_tasks: BackgroundTasks):
    """
    手動觸發賽程更新與排程重設的 API 端點。
    """
    print("主程式：接收到更新請求，將任務加入背景佇列...")
    background_tasks.add_task(run_schedule_update_and_reschedule)
    
    print("主程式：任務已排入，立即回傳 API 回應。")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    return JSONResponse(content={"message": "已觸發賽程更新與排程重設背景任務。"}, headers=headers, status_code=202)