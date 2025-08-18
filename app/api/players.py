# app/api/players.py

from collections import defaultdict
from fastapi import APIRouter, Query
from fastapi import Depends
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from app import models, schemas
from app.db import get_db
import datetime

from app.exceptions import PlayerNotFoundException


router = APIRouter(
    prefix="/api/players",
    tags=["Players"],
)


@router.get(
    "/stats/history",
    response_model=Dict[str, List[schemas.PlayerSeasonStatsHistory]],
)
def get_player_stats_history(
    db: Session = Depends(get_db),
    player_names: List[str] = Query(
        ...,
        alias="player_name",
        description="要查詢的一個或多個球員姓名",
        examples=["王柏融", "陳傑憲"],
    ),
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
):
    """
    獲取指定**一個或多個**球員的球季數據歷史紀錄，支援日期篩選。

    回傳格式為一個字典，key 為球員姓名，value 為該球員的數據歷史列表。
    """
    query = db.query(models.PlayerSeasonStatsHistoryDB).filter(
        models.PlayerSeasonStatsHistoryDB.player_name.in_(player_names)
    )

    if start_date:
        query = query.filter(models.PlayerSeasonStatsHistoryDB.created_at >= start_date)
    if end_date:
        query = query.filter(
            models.PlayerSeasonStatsHistoryDB.created_at
            < end_date + datetime.timedelta(days=1)
        )

    history_records = query.order_by(
        models.PlayerSeasonStatsHistoryDB.player_name,
        models.PlayerSeasonStatsHistoryDB.created_at,
    ).all()

    # 檢查是否有任何一位請求的球員完全不存在於資料庫中
    if not history_records:
        # 為了提供更精確的錯誤，可以檢查資料庫中是否存在這些球員的任何紀錄
        found_players_count = (
            db.query(models.PlayerSeasonStatsHistoryDB.id)
            .filter(models.PlayerSeasonStatsHistoryDB.player_name.in_(player_names))
            .limit(1)
            .count()
        )
        if found_players_count == 0:
            # [修正] 移除 'detail' 參數，直接拋出預定義的例外
            raise PlayerNotFoundException()

    # 將扁平的查詢結果按球員姓名分組
    grouped_results = defaultdict(list)
    for record in history_records:
        grouped_results[record.player_name].append(record)

    return grouped_results
