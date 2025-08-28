# app/api/games.py

from fastapi import APIRouter, Query, Depends, HTTPException, Request
import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app import models, schemas
from app.crud import games
from app.db import get_db
from app.config import settings
from app.cache import cache

# [修改] 導入新的例外類別
from app.exceptions import InvalidInputException, ResourceNotFoundException

router = APIRouter(
    prefix="/api/games",
    tags=["Games"],
)


# [T29 修正] 調整路由順序
# 將更具體的 /schedule 路由移至通用路由 /{game_date} 之前
@router.get(
    "/season",
    response_model=List[schemas.SeasonGame],
    summary="取得年度賽果",
    description="根據年份取得指定球隊的全年度賽果，可用於日曆圖表的底圖。",
)
@cache(expire=60 * 60 * 24)  # 快取 24 小時
def get_season_games(
    *,
    request: Request,  # [修正] 加入 request 參數供 cache 裝飾器使用
    db: Session = Depends(get_db),
    year: int = Query(
        default_factory=lambda: datetime.datetime.now().year,
        description="查詢的年份，預設為今年。",
    ),
    completed_only: bool = Query(
        default=False,
        description="是否只回傳已完成的比賽。",
    ),
):
    """
    提供前端日曆圖表所需的全域賽果資料。
    """
    # 從設定檔中取得目標球隊名稱
    if not settings.TARGET_TEAMS:
        raise HTTPException(
            status_code=500, detail="Target team is not configured in settings."
        )
    target_team = settings.TARGET_TEAMS[0]

    schedule_data = games.get_games_by_year_and_team(
        db, year=year, team_name=target_team, completed_only=completed_only
    )
    # GameResultDB 的 id 欄位才是 game_id
    # 手動轉換以符合 SeasonGame 模型
    return [
        schemas.SeasonGame(
            game_date=game.game_date,
            game_id=game.id,
            home_team=game.home_team,
            away_team=game.away_team,
        )
        for game in schedule_data
    ]


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
