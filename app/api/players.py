# app/api/players.py

from fastapi import APIRouter, Query
from fastapi import Depends
from typing import List, Optional
from sqlalchemy.orm import Session
from app import models, schemas
from app.db import get_db
import datetime

# [修改] 導入新的例外類別
from app.exceptions import PlayerNotFoundException


router = APIRouter(
    prefix="/api/players",
    tags=["Players"],
)


@router.get(
    "/{player_name}/stats/history",
    response_model=List[schemas.PlayerSeasonStatsHistory],
)
def get_player_stats_history(
    player_name: str,
    db: Session = Depends(get_db),
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    skip: int = Query(0, ge=0, description="要跳過的紀錄數量"),
    limit: int = Query(100, ge=1, le=200, description="每頁回傳的最大紀錄數量"),
):
    """
    獲取指定球員的球季數據歷史紀錄，支援日期篩選與分頁。
    """
    query = db.query(models.PlayerSeasonStatsHistoryDB).filter(
        models.PlayerSeasonStatsHistoryDB.player_name == player_name
    )

    if start_date:
        query = query.filter(models.PlayerSeasonStatsHistoryDB.created_at >= start_date)
    if end_date:
        query = query.filter(
            models.PlayerSeasonStatsHistoryDB.created_at
            < end_date + datetime.timedelta(days=1)
        )

    history = (
        query.order_by(models.PlayerSeasonStatsHistoryDB.created_at)
        .offset(skip)
        .limit(limit)
        .all()
    )

    if not history:
        total_count = (
            db.query(models.PlayerSeasonStatsHistoryDB.id)
            .filter(models.PlayerSeasonStatsHistoryDB.player_name == player_name)
            .count()
        )
        if total_count == 0:
            # [修改] 改用自訂例外
            raise PlayerNotFoundException()

    return history
