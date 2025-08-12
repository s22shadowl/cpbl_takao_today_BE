# app/api/players.py

from fastapi import APIRouter, Query
from fastapi import HTTPException, Depends
from typing import List, Optional
from sqlalchemy.orm import Session
from app import models, schemas
from app.db import get_db
import datetime


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
    # [新增] 日期篩選參數
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    # [新增] 分頁參數
    skip: int = Query(0, ge=0, description="要跳過的紀錄數量"),
    limit: int = Query(100, ge=1, le=200, description="每頁回傳的最大紀錄數量"),
):
    """
    獲取指定球員的球季數據歷史紀錄，支援日期篩選與分頁。
    """
    query = db.query(models.PlayerSeasonStatsHistoryDB).filter(
        models.PlayerSeasonStatsHistoryDB.player_name == player_name
    )

    # [修改] 應用日期篩選邏輯
    if start_date:
        query = query.filter(models.PlayerSeasonStatsHistoryDB.created_at >= start_date)
    if end_date:
        # 結束日期通常包含當天，所以篩選條件要到隔天為止
        query = query.filter(
            models.PlayerSeasonStatsHistoryDB.created_at
            < end_date + datetime.timedelta(days=1)
        )

    # [修改] 應用分頁與排序邏輯
    history = (
        query.order_by(models.PlayerSeasonStatsHistoryDB.created_at)
        .offset(skip)
        .limit(limit)
        .all()
    )

    # [修改] 優化 404 判斷邏輯
    # 只有當資料庫中完全不存在該球員的任何紀錄時，才回傳 404。
    # 如果只是篩選條件或分頁後沒有結果，則回傳空列表。
    if not history:
        total_count = (
            db.query(models.PlayerSeasonStatsHistoryDB.id)
            .filter(models.PlayerSeasonStatsHistoryDB.player_name == player_name)
            .count()
        )
        if total_count == 0:
            raise HTTPException(
                status_code=404, detail=f"找不到球員 {player_name} 的任何歷史數據。"
            )

    return history
