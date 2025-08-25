# app/crud/analysis.py

import datetime
import logging
from app import models, schemas
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session, joinedload, aliased
from sqlalchemy import func, or_, select
from app.config import settings

# --- 進階查詢函式 ---


def find_games_with_players(
    db: Session, player_names: List[str], skip: int = 0, limit: int = 100
) -> List[models.GameResultDB]:
    """查詢指定的所有球員同時出賽的比賽列表。"""
    if not player_names:
        return []

    subquery = (
        db.query(models.PlayerGameSummaryDB.game_id)
        .filter(models.PlayerGameSummaryDB.player_name.in_(player_names))
        .group_by(models.PlayerGameSummaryDB.game_id)
        .having(
            func.count(models.PlayerGameSummaryDB.player_name.distinct())
            == len(player_names)
        )
        .subquery()
    )

    games = (
        db.query(models.GameResultDB)
        .filter(models.GameResultDB.id.in_(subquery.select()))
        .options(joinedload(models.GameResultDB.player_summaries))
        .order_by(models.GameResultDB.game_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return games


def get_stats_since_last_homerun(
    db: Session, player_name: str
) -> Dict[str, Any] | None:
    """查詢指定球員的最後一發全壘打，並計算此後的相關數據及生涯數據。"""
    last_hr_at_bat = (
        db.query(models.AtBatDetailDB)
        .join(models.AtBatDetailDB.player_summary)
        .filter(models.PlayerGameSummaryDB.player_name == player_name)
        .filter(models.AtBatDetailDB.result_description_full.contains("全壘打"))
        .join(models.PlayerGameSummaryDB.game)
        .order_by(
            models.GameResultDB.game_date.desc(),
            models.AtBatDetailDB.sequence_in_game.desc(),
        )
        .first()
    )

    if not last_hr_at_bat:
        return None

    last_hr_game = last_hr_at_bat.player_summary.game
    last_hr_date = last_hr_game.game_date

    stats_since = (
        db.query(
            func.count(models.PlayerGameSummaryDB.game_id.distinct()).label(
                "games_since"
            ),
            func.sum(models.PlayerGameSummaryDB.at_bats).label("at_bats_since"),
        )
        .join(models.GameResultDB)
        .filter(
            models.PlayerGameSummaryDB.player_name == player_name,
            models.GameResultDB.game_date > last_hr_date,
        )
        .one()
    )

    career_stats_orm = (
        db.query(models.PlayerCareerStatsDB)
        .filter(models.PlayerCareerStatsDB.player_name == player_name)
        .first()
    )
    # [修正] 將 ORM 物件轉換為 Pydantic 模型以確保正確序列化
    career_stats_pydantic = (
        schemas.PlayerCareerStats.model_validate(career_stats_orm)
        if career_stats_orm
        else None
    )

    games_since_count = stats_since.games_since or 0
    at_bats_since_count = stats_since.at_bats_since or 0

    return {
        "last_homerun": last_hr_at_bat,
        "game_date": last_hr_date,
        "days_since": (datetime.date.today() - last_hr_date).days,
        "games_since": games_since_count,
        "at_bats_since": at_bats_since_count,
        "career_stats": career_stats_pydantic,
    }


def find_at_bats_in_situation(
    db: Session,
    player_name: str,
    situation: models.RunnersSituation,
    skip: int = 0,
    limit: int = 100,
) -> List[models.AtBatDetailDB]:
    """查詢指定球員在特定壘上情境下的所有打席紀錄。"""
    query = (
        db.query(models.AtBatDetailDB)
        .join(models.PlayerGameSummaryDB)
        .join(models.GameResultDB)
        .options(
            joinedload(models.AtBatDetailDB.player_summary).joinedload(
                models.PlayerGameSummaryDB.game
            )
        )
        .filter(models.PlayerGameSummaryDB.player_name == player_name)
    )

    if situation == models.RunnersSituation.BASES_LOADED:
        query = query.filter(
            models.AtBatDetailDB.runners_on_base_before == "一壘、二壘、三壘有人"
        )
    elif situation == models.RunnersSituation.SCORING_POSITION:
        query = query.filter(
            or_(
                models.AtBatDetailDB.runners_on_base_before.contains("二壘"),
                models.AtBatDetailDB.runners_on_base_before.contains("三壘"),
            )
        )
    elif situation == models.RunnersSituation.BASES_EMPTY:
        query = query.filter(models.AtBatDetailDB.runners_on_base_before == "壘上無人")

    at_bats = (
        query.order_by(
            models.GameResultDB.game_date.desc(),
            models.AtBatDetailDB.sequence_in_game.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )
    return at_bats


def get_summaries_by_position(
    db: Session, position: str, skip: int = 0, limit: int = 100
) -> List[models.PlayerGameSummaryDB]:
    """查詢指定守備位置的所有球員出賽紀錄。"""
    summaries = (
        db.query(models.PlayerGameSummaryDB)
        .filter(models.PlayerGameSummaryDB.position == position)
        .join(models.GameResultDB)
        .order_by(models.GameResultDB.game_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return summaries


def find_next_at_bats_after_ibb(
    db: Session, player_name: str, skip: int = 0, limit: int = 100
) -> List[Dict[str, Any]]:
    """使用 SQL 窗口函數 (LEAD) 高效查詢指定球員被故意四壞後，同一半局內下一位打者的打席結果。"""
    at_bat_with_next_subquery = (
        select(
            models.AtBatDetailDB.id.label("at_bat_id"),
            func.lead(models.AtBatDetailDB.id)
            .over(
                partition_by=(
                    models.PlayerGameSummaryDB.game_id,
                    models.AtBatDetailDB.inning,
                ),
                order_by=models.AtBatDetailDB.id,
            )
            .label("next_at_bat_id"),
        )
        .join(models.PlayerGameSummaryDB)
        .subquery()
    )

    ibb_at_bat = aliased(models.AtBatDetailDB)
    next_at_bat = aliased(models.AtBatDetailDB)

    results = (
        db.query(ibb_at_bat, next_at_bat)
        .join(
            at_bat_with_next_subquery,
            ibb_at_bat.id == at_bat_with_next_subquery.c.at_bat_id,
        )
        .join(
            models.PlayerGameSummaryDB,
            ibb_at_bat.player_game_summary_id == models.PlayerGameSummaryDB.id,
        )
        .outerjoin(
            next_at_bat,
            at_bat_with_next_subquery.c.next_at_bat_id == next_at_bat.id,
        )
        .filter(models.PlayerGameSummaryDB.player_name == player_name)
        .filter(ibb_at_bat.result_description_full.contains("故意四壞"))
        .order_by(ibb_at_bat.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return [
        {"intentional_walk": ibb, "next_at_bat": next_ab} for ibb, next_ab in results
    ]


def find_on_base_streaks(
    db: Session,
    definition_name: str,
    min_length: int,
    player_names: Optional[List[str]],
    lineup_positions: Optional[List[int]],
    skip: int = 0,
    limit: int = 100,
) -> List[schemas.OnBaseStreak]:
    """查詢符合「連線」定義的打席序列。"""
    valid_results = set(settings.STREAK_DEFINITIONS.get(definition_name, []))
    if not valid_results:
        logging.warning(f"無效的連線定義名稱: {definition_name}")
        return []

    query = (
        db.query(models.AtBatDetailDB)
        .join(models.PlayerGameSummaryDB)
        .options(
            joinedload(models.AtBatDetailDB.player_summary).joinedload(
                models.PlayerGameSummaryDB.game
            )
        )
    )

    if player_names:
        game_ids_subquery = (
            select(models.PlayerGameSummaryDB.game_id)
            .where(models.PlayerGameSummaryDB.player_name.in_(player_names))
            .distinct()
        )
        query = query.filter(models.AtBatDetailDB.game_id.in_(game_ids_subquery))

    final_query = query.order_by(
        models.AtBatDetailDB.game_id,
        models.AtBatDetailDB.inning,
        models.AtBatDetailDB.sequence_in_game,
    )

    all_at_bats = final_query.all()

    all_streaks = []
    if player_names or lineup_positions:
        target_list = player_names if player_names else lineup_positions
        target_len = len(target_list)
        if target_len < min_length:
            return []

        for i in range(len(all_at_bats) - target_len + 1):
            potential_streak = all_at_bats[i : i + target_len]
            first_ab = potential_streak[0]
            if not all(
                ab.game_id == first_ab.game_id and ab.inning == first_ab.inning
                for ab in potential_streak
            ):
                continue
            if not all(ab.result_short in valid_results for ab in potential_streak):
                continue

            is_match = False
            if player_names:
                streak_player_names = {
                    ab.player_summary.player_name for ab in potential_streak
                }
                if streak_player_names == set(player_names):
                    is_match = True
            elif lineup_positions:
                is_lineup_match = True
                for j, ab in enumerate(potential_streak):
                    try:
                        if int(ab.player_summary.batting_order) != lineup_positions[j]:
                            is_lineup_match = False
                            break
                    except (ValueError, TypeError):
                        is_lineup_match = False
                        break
                if is_lineup_match:
                    is_match = True

            if is_match:
                all_streaks.append(potential_streak)
    else:
        current_streak = []
        for i, at_bat in enumerate(all_at_bats):
            is_valid = at_bat.result_short in valid_results
            is_continuous = False
            if current_streak:
                prev_at_bat = current_streak[-1]
                if (
                    prev_at_bat.game_id == at_bat.game_id
                    and prev_at_bat.inning == at_bat.inning
                ):
                    is_continuous = True

            if is_valid and (not current_streak or is_continuous):
                current_streak.append(at_bat)
            else:
                if len(current_streak) >= min_length:
                    all_streaks.append(list(current_streak))
                current_streak = [at_bat] if is_valid else []

        if len(current_streak) >= min_length:
            all_streaks.append(list(current_streak))

    paginated_streaks = all_streaks[skip : skip + limit]
    result_models = []
    for streak in paginated_streaks:
        if not streak:
            continue
        game = streak[0].player_summary.game
        player_team = streak[0].player_summary.team_name
        opponent_team = (
            game.away_team if game.home_team == player_team else game.home_team
        )

        at_bat_models = [
            schemas.AtBatDetailForStreak(
                player_name=ab.player_summary.player_name,
                batting_order=ab.player_summary.batting_order,
                **ab.__dict__,
            )
            for ab in streak
        ]

        streak_model = schemas.OnBaseStreak(
            game_id=game.id,
            game_date=game.game_date,
            inning=streak[0].inning,
            streak_length=len(streak),
            opponent_team=opponent_team,
            runs_scored_during_streak=sum(ab.runs_scored_on_play for ab in streak),
            at_bats=at_bat_models,
        )
        result_models.append(streak_model)

    return result_models[::-1]


def analyze_ibb_impact(
    db: Session, player_name: str, skip: int = 0, limit: int = 100
) -> List[schemas.IbbImpactResult]:
    """分析指定球員被故意四壞後，對該半局總失分的影響。"""
    game_ids_subquery = (
        select(models.PlayerGameSummaryDB.game_id)
        .where(models.PlayerGameSummaryDB.player_name == player_name)
        .distinct()
    )

    all_related_at_bats = (
        db.query(models.AtBatDetailDB)
        .join(models.PlayerGameSummaryDB)
        .filter(models.PlayerGameSummaryDB.game_id.in_(game_ids_subquery))
        .options(
            joinedload(models.AtBatDetailDB.player_summary).joinedload(
                models.PlayerGameSummaryDB.game
            )
        )
        .order_by(
            models.PlayerGameSummaryDB.game_id,
            models.AtBatDetailDB.inning,
            models.AtBatDetailDB.id,
        )
        .all()
    )

    results = []
    for i, at_bat in enumerate(all_related_at_bats):
        is_ibb = (
            at_bat.result_description_full
            and "故意四壞" in at_bat.result_description_full
        )
        is_target_player = at_bat.player_summary.player_name == player_name

        if is_ibb and is_target_player:
            ibb_event = at_bat
            subsequent_at_bats = []
            runs_scored_after = 0

            for next_ab in all_related_at_bats[i + 1 :]:
                if (
                    next_ab.player_summary.game_id == ibb_event.player_summary.game_id
                    and next_ab.inning == ibb_event.inning
                ):
                    subsequent_at_bats.append(next_ab)
                    runs_scored_after += next_ab.runs_scored_on_play
                else:
                    break

            game = ibb_event.player_summary.game
            player_team = ibb_event.player_summary.team_name
            opponent_team = (
                game.away_team if game.home_team == player_team else game.home_team
            )

            ibb_model = schemas.AtBatDetailForStreak(
                player_name=ibb_event.player_summary.player_name,
                batting_order=ibb_event.player_summary.batting_order,
                **ibb_event.__dict__,
            )

            subsequent_models = [
                schemas.AtBatDetailForStreak(
                    player_name=ab.player_summary.player_name,
                    batting_order=ab.player_summary.batting_order,
                    **ab.__dict__,
                )
                for ab in subsequent_at_bats
            ]

            impact_result = schemas.IbbImpactResult(
                game_id=game.id,
                game_date=game.game_date,
                inning=ibb_event.inning,
                opponent_team=opponent_team,
                intentional_walk=ibb_model,
                subsequent_at_bats=subsequent_models,
                runs_scored_after_ibb=runs_scored_after,
            )
            results.append(impact_result)

    paginated_results = results[::-1][skip : skip + limit]
    return paginated_results
