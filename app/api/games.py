# app/api/games.py

from fastapi import APIRouter
import datetime
from fastapi import HTTPException, Depends

from typing import List
from sqlalchemy.orm import Session

from app import models, schemas
from app.crud import games
from app.db import get_db

router = APIRouter(
    prefix="/api/games",
    tags=["Games"],
)


@router.get("/{game_date}", response_model=List[schemas.GameResult])
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


@router.get("/details/{game_id}", response_model=schemas.GameResultWithDetails)
def get_game_details(game_id: int, db: Session = Depends(get_db)):
    game = games.get_game_with_details(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail=f"找不到 ID 為 {game_id} 的比賽。")
    return game
