# app/main.py

import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging_config import setup_logging
from app.api import games, jobs, players, analysis, system

# 導入新的 middleware 與 exceptions
from app.middleware import RequestContextMiddleware
from app.exceptions import APIException, api_exception_handler

logger = logging.getLogger(__name__)


# --- FastAPI 應用程式設定 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("應用程式啟動中...")
    yield
    logger.info("應用程式正在關閉...")


app = FastAPI(lifespan=lifespan)

# --- 掛載所有 Middleware ---
# 將 RequestContextMiddleware 加在最前面，以確保所有後續處理都能取用到 request_id
app.add_middleware(RequestContextMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 掛載全域例外處理器 ---
# [新增] 註冊自訂的例外處理器
app.add_exception_handler(APIException, api_exception_handler)


# --- 掛載所有 API 路由 ---
app.include_router(games.router)
app.include_router(players.router)
app.include_router(analysis.router)
app.include_router(jobs.router)
app.include_router(system.router)
