# app/api/games.py

from fastapi import APIRouter, Query
import datetime
from fastapi import HTTPException, Depends

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app import models, schemas
from app.crud import games
from app.db import get_db

router = APIRouter(
    prefix="/api/games",
    tags=["Games"],
)


@router.get("/{game_date}", response_model=List[schemas.GameResult])
def get_games_by_date(
    game_date: str,
    db: Session = Depends(get_db),
    # [新增] 增加 team_name 查詢參數以提供更彈性的過濾
    team_name: Optional[str] = Query(None, description="依特定隊伍名稱篩選比賽"),
):
    """
    根據指定日期獲取比賽列表，可選擇性地依隊伍名稱篩選。
    """
    try:
        parsed_date = datetime.datetime.strptime(game_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=422, detail="日期格式錯誤，請使用 YYYY-MM-DD 格式。"
        )

    query = db.query(models.GameResultDB).filter(
        models.GameResultDB.game_date == parsed_date
    )

    # [修改] 如果提供了 team_name，則增加過濾條件
    if team_name:
        query = query.filter(
            or_(
                models.GameResultDB.home_team == team_name,
                models.GameResultDB.away_team == team_name,
            )
        )

    return query.all()


@router.get("/details/{game_id}", response_model=schemas.GameResultWithDetails)
def get_game_details(game_id: int, db: Session = Depends(get_db)):
    """
    獲取單場比賽的完整細節，包含所有球員的摘要與逐打席紀錄。
    """
    # 此處調用的 crud 函式已使用 joinedload 進行效能優化，避免 N+1 查詢
    game = games.get_game_with_details(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail=f"找不到 ID 為 {game_id} 的比賽。")
    return game
