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


# [新增] 通用的字串轉布林值工具函式
def to_boolean(value: any) -> bool:
    """
    一個穩健的工具函式，用於將各種輸入轉換為布林值。

    Python 的 `distutils.util.strtobool` 曾是處理此問題的常用工具，但它已被棄用。
    此自訂函式提供了一個無依賴、穩健的替代方案，可將各種常見的字串
    （如 'true', '1', 'yes'）轉換為布林值 True，其餘情況則為 False。
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "t", "y", "yes")
    # 對於其他情況 (例如整數 0 或 1)，標準的 bool() 轉換是安全的。
    return bool(value)


# [修改] 依賴項函式現在呼叫上面的工具函式，保持自身簡潔
def process_completed_only_param(
    # [核心修正] 將型別提示從 Any 改為 str，以明確告知 FastAPI 期望接收原始字串，
    # 從而繞過其內建的布林驗證，讓我們的 to_boolean 邏輯可以處理任意字串。
    completed_only: str = Query(
        default=False,
        description="是否只回傳已完成的比賽。接受 true/false, 1/0, t/f 等常見布林值表示法。",
    ),
) -> bool:
    """
    FastAPI 依賴項，呼叫 to_boolean 工具函式來處理查詢參數。
    """
    return to_boolean(completed_only)


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
    completed_only: bool = Depends(process_completed_only_param),
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
