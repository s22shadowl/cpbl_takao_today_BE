# app/main.py

import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging_config import setup_logging
from app.api import games, players, analysis, system, tasks

logger = logging.getLogger(__name__)


# --- FastAPI 應用程式設定 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("應用程式啟動中...")
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

# --- 掛載所有 API 路由 ---
app.include_router(games.router)
app.include_router(players.router)
app.include_router(analysis.router)
app.include_router(tasks.router)
app.include_router(system.router)
