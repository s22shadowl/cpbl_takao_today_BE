# app/crud/analysis.py

import datetime
import logging
from app import models, schemas
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session, joinedload, aliased
from sqlalchemy import func, or_, select, extract
from app.config import settings

from itertools import groupby
from operator import attrgetter
import sqlalchemy as sa

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


# [T31-4 修正] 擴充函式以整合打擊與守備數據
def get_position_analysis_by_year(db: Session, year: int, position: str) -> Dict:
    """
    查詢指定年度與守備位置的深入分析數據。

    Args:
        db: 資料庫 session。
        year: 查詢的年份。
        position: 查詢的守備位置 (例如: '2B')。

    Returns:
        一個包含 calendar_data 和 player_stats 的字典。
    """
    # 1. 查詢該年度、該守備位置相關的所有出場紀錄
    #    - position.like(f"%{position}%") 會同時抓取 '2B' 和 '(2B)'
    #    - 預先載入 game relationship 以避免 N+1 查詢
    summaries = (
        db.query(models.PlayerGameSummaryDB)
        .join(models.GameResultDB)
        .filter(extract("year", models.GameResultDB.game_date) == year)
        .filter(models.PlayerGameSummaryDB.position.like(f"%{position}%"))
        .options(sa.orm.joinedload(models.PlayerGameSummaryDB.game))
        .order_by(models.GameResultDB.game_date.asc())
        .all()
    )

    calendar_data = []
    # 2. 按 game_id 將紀錄分組
    #    - 需要先對 summaries 排序才能正確分組
    summaries.sort(key=attrgetter("game_id"))
    for game_id, group in groupby(summaries, key=attrgetter("game_id")):
        game_summaries = list(group)
        starter_summary = None
        substitute_player_names = []

        # 3. 在每場比賽中找出先發與替補
        for summary in game_summaries:
            # 先發定義：守備位置完全相符，且尚未找到先發
            if summary.position == position and not starter_summary:
                starter_summary = summary
            else:
                substitute_player_names.append(summary.player_name)

        # 4. 如果有找到先發球員，才建立日曆項目
        if starter_summary:
            # 從替補名單中移除先發球員自己
            final_substitutes = [
                name
                for name in substitute_player_names
                if name != starter_summary.player_name
            ]
            calendar_item = {
                "date": starter_summary.game.game_date,
                "starter_player_name": starter_summary.player_name,
                "substitute_player_names": final_substitutes,
                "starter_player_summary": starter_summary,
            }
            calendar_data.append(calendar_item)

    # 5. 整合 player_stats (打擊與守備數據)
    #    - 從已查詢的出場紀錄中，取得所有不重複的球員姓名
    player_names = {summary.player_name for summary in summaries}

    player_stats_combined = []
    if player_names:
        # 查詢所有相關球員的年度打擊數據
        batting_stats_list = (
            db.query(models.PlayerSeasonStatsDB)
            .filter(models.PlayerSeasonStatsDB.player_name.in_(player_names))
            .all()
        )
        batting_stats_map = {s.player_name: s for s in batting_stats_list}

        # 查詢所有相關球員在「指定守備位置」的年度守備數據
        # 由於爬蟲已統一格式，此處可直接查詢
        fielding_stats_list = (
            db.query(models.PlayerFieldingStatsDB)
            .filter(models.PlayerFieldingStatsDB.player_name.in_(player_names))
            .filter(models.PlayerFieldingStatsDB.position == position.upper())
            .all()
        )
        fielding_stats_map = {s.player_name: s for s in fielding_stats_list}

        # 組合打擊與守備數據
        for name in sorted(list(player_names)):
            batting_stats = batting_stats_map.get(name)
            # 守備數據可能不存在，所以用 .get()
            fielding_stats = fielding_stats_map.get(name)

            # 將守備數據放入一個列表中，以符合 Pydantic schema 的 `List` 預期
            fielding_stats_for_player = [fielding_stats] if fielding_stats else []

            player_stat_item = {
                "player_name": name,
                "batting_stats": batting_stats,
                "fielding_stats": fielding_stats_for_player,
            }
            player_stats_combined.append(player_stat_item)

    return {"calendar_data": calendar_data, "player_stats": player_stats_combined}


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
