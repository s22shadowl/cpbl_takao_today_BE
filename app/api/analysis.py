# app/api/analysis.py

from app.crud import analysis
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import List, Optional
from enum import Enum

from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db
from app.cache import cache


router = APIRouter(
    prefix="/api/analysis",
    tags=["Analysis"],
)


# [新增] 為連線定義建立 Enum
class StreakDefinition(str, Enum):
    consecutive_hits = "consecutive_hits"
    consecutive_on_base = "consecutive_on_base"
    consecutive_advancements = "consecutive_advancements"


# --- 進階分析 API 端點 ---


@router.get("/games-with-players", response_model=List[schemas.GameResult])
@cache()
def get_games_with_players(
    request: Request,
    players: List[str] = Query(..., description="球員姓名列表"),
    skip: int = Query(0, ge=0, description="要跳過的紀錄數量"),
    limit: int = Query(100, ge=1, le=200, description="每頁回傳的最大紀錄數量"),
    db: Session = Depends(get_db),
):
    """查詢指定的所有球員同時出賽的比賽列表。"""
    games = analysis.find_games_with_players(db, players, skip=skip, limit=limit)
    return games


@router.get(
    "/players/{player_name}/last-homerun",
    response_model=schemas.LastHomerunStats,
)
@cache()
def get_last_homerun(request: Request, player_name: str, db: Session = Depends(get_db)):
    """查詢指定球員的最後一轟，並回傳擴充後的統計數據。"""
    stats = analysis.get_stats_since_last_homerun(db, player_name)
    if not stats:
        raise HTTPException(
            status_code=404, detail=f"找不到球員 {player_name} 的全壘打紀錄。"
        )
    return stats


@router.get(
    "/players/{player_name}/situational-at-bats",
    response_model=List[schemas.AtBatDetail],
)
@cache()
def get_situational_at_bats(
    request: Request,
    player_name: str,
    situation: models.RunnersSituation,
    skip: int = Query(0, ge=0, description="要跳過的紀錄數量"),
    limit: int = Query(100, ge=1, le=200, description="每頁回傳的最大紀錄數量"),
    db: Session = Depends(get_db),
):
    """根據指定的壘上情境，查詢球員的打席紀錄。"""
    at_bats = analysis.find_at_bats_in_situation(
        db, player_name, situation, skip=skip, limit=limit
    )
    return at_bats


@router.get("/positions/{position}", response_model=List[schemas.PlayerGameSummary])
@cache()
def get_position_records(
    request: Request,
    position: str,
    skip: int = Query(0, ge=0, description="要跳過的紀錄數量"),
    limit: int = Query(100, ge=1, le=200, description="每頁回傳的最大紀錄數量"),
    db: Session = Depends(get_db),
):
    """查詢指定守備位置的所有球員出賽紀錄。"""
    summaries = analysis.get_summaries_by_position(db, position, skip=skip, limit=limit)
    return summaries


@router.get(
    "/players/{player_name}/after-ibb",
    response_model=List[schemas.NextAtBatResult],
)
@cache()  # [修改] 為此端點加上快取
def get_next_at_bats_after_ibb(
    request: Request,
    player_name: str,
    skip: int = Query(0, ge=0, description="要跳過的紀錄數量"),
    limit: int = Query(100, ge=1, le=200, description="每頁回傳的最大紀錄數量"),
    db: Session = Depends(get_db),
):
    """查詢指定球員被故意四壞後，下一位打者的打席結果。"""
    results = analysis.find_next_at_bats_after_ibb(
        db, player_name, skip=skip, limit=limit
    )
    return results


@router.get(
    "/streaks",
    response_model=List[schemas.OnBaseStreak],
    tags=["Analysis"],
    summary="查詢「連線」紀錄",
)
@cache()
def get_on_base_streaks(
    request: Request,
    db: Session = Depends(get_db),
    # [修改] 改用 Enum 作為參數型別
    definition_name: StreakDefinition = Query(
        StreakDefinition.consecutive_on_base, description="要使用的連線定義"
    ),
    min_length: int = Query(2, description="連線的最短長度", ge=2),
    player_names: Optional[List[str]] = Query(
        None, description="要查詢的連續球員姓名列表"
    ),
    lineup_positions: Optional[List[int]] = Query(
        None, description="要查詢的連續棒次列表"
    ),
    skip: int = Query(0, ge=0, description="要跳過的紀錄數量"),
    limit: int = Query(100, ge=1, le=200, description="每頁回傳的最大紀錄數量"),
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

    streaks = analysis.find_on_base_streaks(
        db=db,
        definition_name=definition_name.value,
        min_length=min_length,
        player_names=player_names,
        lineup_positions=lineup_positions,
        skip=skip,
        limit=limit,
    )
    return streaks


@router.get(
    "/players/{player_name}/ibb-impact",
    response_model=List[schemas.IbbImpactResult],
    tags=["Analysis"],
    summary="分析故意四壞的失分影響",
)
@cache()
def get_ibb_impact_analysis(
    request: Request,
    player_name: str,
    skip: int = Query(0, ge=0, description="要跳過的紀錄數量"),
    limit: int = Query(100, ge=1, le=200, description="每頁回傳的最大紀錄數量"),
    db: Session = Depends(get_db),
):
    """
    查詢指定球員被故意四壞後，該半局後續所有打席的紀錄與總失分。
    """
    results = analysis.analyze_ibb_impact(
        db, player_name=player_name, skip=skip, limit=limit
    )
    return results
