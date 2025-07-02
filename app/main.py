# app/main.py (Dramatiq 版 - 安全性強化)

import datetime
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from typing import List

# 【新】匯入 CORS 中介軟體和 API 金鑰相關模組
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

# SQLAlchemy 的 Session，用於型別提示
from sqlalchemy.orm import Session

# 匯入我們新的 SQLAlchemy 模型、設定、和資料庫連線函式
from app import models, scraper
from app.db import get_db, engine
# 【新】直接從 config 匯入 settings 實例
from app.config import settings
from app.tasks import task_update_schedule_and_reschedule

models.Base.metadata.create_all(bind=engine)


# --- FastAPI 應用程式設定 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("應用程式啟動中...")
    yield
    print("應用程式正在關閉...")

app = FastAPI(lifespan=lifespan)

# 【新】加入 CORS 中介軟體
# 這必須在所有路由註冊之前加入
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS, # 從設定檔讀取允許的來源
    allow_credentials=True,
    allow_methods=["*"], # 允許所有 HTTP 方法
    allow_headers=["*"], # 允許所有 HTTP 標頭
)

# 【新】API 金鑰驗證機制
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_api_key(api_key: str = Security(api_key_header)):
    """依賴函式，用於驗證傳入的 API 金鑰"""
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
        raise HTTPException(status_code=422, detail="日期格式錯誤，請使用YYYY-MM-DD 格式。")
    
    games = db.query(models.GameResultDB).filter(models.GameResultDB.game_date == parsed_date).all()
    
    if not games:
        raise HTTPException(status_code=404, detail=f"找不到日期 {game_date} 的比賽結果。")
    
    return games


# 【新】為此端點加上 API 金鑰保護
@app.post("/api/run_scraper", status_code=202, dependencies=[Depends(get_api_key)])
def run_scraper_manually(mode: str, date: str | None = None):
    if mode not in ["daily", "monthly", "yearly"]:
        raise HTTPException(status_code=400, detail="無效的模式。請使用 'daily', 'monthly', 或 'yearly'。")
    
    message = f"已接收到 {mode} 模式的爬蟲請求。任務佇列功能待實現。"
    
    headers = {"Content-Type": "application/json; charset=utf-8"}
    return JSONResponse(content={"message": message}, headers=headers, status_code=202)


# 【新】為此端點加上 API 金鑰保護
@app.post("/api/update_schedule", status_code=202, dependencies=[Depends(get_api_key)])
def update_schedule_manually():
    print("主程式：接收到更新請求，準備將任務發送到佇列...")
    task_update_schedule_and_reschedule.send()
    print("主程式：任務已成功發送，立即回傳 API 回應。")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    return JSONResponse(content={"message": "已成功將賽程更新任務發送到背景佇列。"}, headers=headers, status_code=202)