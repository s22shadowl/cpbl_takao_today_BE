# app/api/players.py

from fastapi import APIRouter
from fastapi import HTTPException, Depends
from typing import List
from sqlalchemy.orm import Session
from app import models, schemas
from app.db import get_db


router = APIRouter(
    prefix="/api/players",
    tags=["Players"],
)


@router.get(
    "/{player_name}/stats/history",
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
