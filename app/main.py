# app/main.py

import datetime
import logging
from fastapi import FastAPI, HTTPException, Depends, Security, Query
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from typing import List, Optional

from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app import models, db_actions, schemas
from app.db import get_db
from app.config import settings
from app.logging_config import setup_logging
from app.tasks import (
    task_update_schedule_and_reschedule,
    task_scrape_single_day,
    task_scrape_entire_month,
    task_scrape_entire_year,
)

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

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_api_key(api_key: str = Security(api_key_header)):
    if not api_key or api_key != settings.API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Could not validate credentials: Invalid API Key",
        )
    return api_key


class ScraperRequest(BaseModel):
    mode: str
    date: Optional[str] = None


# --- API 端點 ---


@app.get("/api/games/{game_date}", response_model=List[schemas.GameResult])
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
    return games


@app.get("/api/games/details/{game_id}", response_model=schemas.GameResultWithDetails)
def get_game_details(game_id: int, db: Session = Depends(get_db)):
    game = db_actions.get_game_with_details(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail=f"找不到 ID 為 {game_id} 的比賽。")
    return game


@app.get(
    "/api/players/{player_name}/stats/history",
    response_model=List[schemas.PlayerSeasonStatsHistory],
)
def get_player_stats_history(player_name: str, db: Session = Depends(get_db)):
    history = (
        db.query(models.PlayerSeasonStatsHistoryDB)
        .filter(models.PlayerSeasonStatsHistoryDB.player_name == player_name)
        .order_by(models.PlayerSeasonStatsHistoryDB.created_at)
        .all()
    )
    if not history:
        raise HTTPException(
            status_code=404, detail=f"找不到球員 {player_name} 的歷史數據。"
        )
    return history


# --- 進階分析 API 端點 ---


@app.get("/api/analysis/games-with-players", response_model=List[schemas.GameResult])
def get_games_with_players(
    players: List[str] = Query(..., description="球員姓名列表"),
    db: Session = Depends(get_db),
):
    """查詢指定的所有球員同時出賽的比賽列表。"""
    games = db_actions.find_games_with_players(db, players)
    return games


@app.get(
    "/api/analysis/players/{player_name}/last-homerun",
    response_model=schemas.LastHomerunStats,
)
def get_last_homerun(player_name: str, db: Session = Depends(get_db)):
    """查詢指定球員的最後一轟，並回傳擴充後的統計數據。"""
    stats = db_actions.get_stats_since_last_homerun(db, player_name)
    if not stats:
        raise HTTPException(
            status_code=404, detail=f"找不到球員 {player_name} 的全壘打紀錄。"
        )
    return stats


@app.get(
    "/api/analysis/players/{player_name}/situational-at-bats",
    response_model=List[schemas.AtBatDetail],
)
def get_situational_at_bats(
    player_name: str, situation: models.RunnersSituation, db: Session = Depends(get_db)
):
    """根據指定的壘上情境，查詢球員的打席紀錄。"""
    at_bats = db_actions.find_at_bats_in_situation(db, player_name, situation)
    return at_bats


@app.get(
    "/api/analysis/positions/{position}", response_model=List[schemas.PlayerGameSummary]
)
def get_position_records(position: str, db: Session = Depends(get_db)):
    """查詢指定守備位置的所有球員出賽紀錄。"""
    summaries = db_actions.get_summaries_by_position(db, position)
    return summaries


@app.get(
    "/api/analysis/players/{player_name}/after-ibb",
    response_model=List[schemas.NextAtBatResult],
)
def get_next_at_bats_after_ibb(player_name: str, db: Session = Depends(get_db)):
    """查詢指定球員被故意四壞後，下一位打者的打席結果。"""
    results = db_actions.find_next_at_bats_after_ibb(db, player_name)
    return results


@app.get(
    "/api/analysis/streaks",
    response_model=List[schemas.OnBaseStreak],
    tags=["Analysis"],
    summary="查詢「連線」紀錄",
)
def get_on_base_streaks(
    db: Session = Depends(get_db),
    definition_name: str = Query("consecutive_on_base", description="要使用的連線定義"),
    min_length: int = Query(2, description="連線的最短長度", ge=2),
    player_names: Optional[List[str]] = Query(
        None, description="要查詢的連續球員姓名列表"
    ),
    lineup_positions: Optional[List[int]] = Query(
        None, description="要查詢的連續棒次列表"
    ),
):
    """
    查詢符合「連線」定義的打席序列。
    - 可依據不同的定義（連續安打、連續上壘）進行查詢。
    - 可指定查詢特定連續球員或特定連續棒次的連線紀錄。
    - 若未指定球員或棒次，則回傳所有長度達標的泛用連線。
    """
    if player_names and lineup_positions:
        raise HTTPException(
            status_code=400,
            detail="Cannot specify both player_names and lineup_positions at the same time.",
        )

    streaks = db_actions.find_on_base_streaks(
        db=db,
        definition_name=definition_name,
        min_length=min_length,
        player_names=player_names,
        lineup_positions=lineup_positions,
    )
    return streaks


@app.get(
    "/api/analysis/players/{player_name}/ibb-impact",
    response_model=List[schemas.IbbImpactResult],
    tags=["Analysis"],
    summary="【新增】分析故意四壞的失分影響",
)
def get_ibb_impact_analysis(player_name: str, db: Session = Depends(get_db)):
    """
    查詢指定球員被故意四壞後，該半局後續所有打席的紀錄與總失分。
    """
    results = db_actions.analyze_ibb_impact(db, player_name=player_name)
    return results


# --- 手動觸發任務的端點 ---


@app.post("/api/run_scraper", status_code=202, dependencies=[Depends(get_api_key)])
def run_scraper_manually(request_data: ScraperRequest):
    mode = request_data.mode
    date = request_data.date

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
