# app/api/games.py

from fastapi import APIRouter, Query
import datetime
from fastapi import Depends

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app import models, schemas
from app.crud import games
from app.db import get_db

# [修改] 導入新的例外類別
from app.exceptions import InvalidInputException, ResourceNotFoundException

router = APIRouter(
    prefix="/api/games",
    tags=["Games"],
)


@router.get("/{game_date}", response_model=List[schemas.GameResult])
def get_games_by_date(
    game_date: str,
    db: Session = Depends(get_db),
    team_name: Optional[str] = Query(None, description="依特定隊伍名稱篩選比賽"),
):
    """
    根據指定日期獲取比賽列表，可選擇性地依隊伍名稱篩選。
    """
    try:
        parsed_date = datetime.datetime.strptime(game_date, "%Y-%m-%d").date()
    except ValueError:
        # [修改] 改用自訂例外
        raise InvalidInputException(
            message="Invalid date format, please use YYYY-MM-DD."
        )

    query = db.query(models.GameResultDB).filter(
        models.GameResultDB.game_date == parsed_date
    )

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
    game = games.get_game_with_details(db, game_id)
    if not game:
        # [修改] 改用自訂例外
        raise ResourceNotFoundException(message=f"Game with ID {game_id} not found.")
    return game
