# app/db_actions.py

import logging
import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session, joinedload, aliased
from sqlalchemy.inspection import inspect
from sqlalchemy import func, or_, select

from . import models
from .config import settings


def store_game_and_get_id(db: Session, game_info: Dict[str, Any]) -> int | None:
    """
    【ORM版】準備單場比賽概要資訊以供儲存。
    如果比賽記錄已存在，則不進行任何操作。
    :return: 該筆比賽記錄在資料庫中的 id (int)，如果失敗則返回 None
    """
    try:
        cpbl_game_id = game_info.get("cpbl_game_id")
        if not cpbl_game_id:
            return None

        existing_game = (
            db.query(models.GameResultDB)
            .filter(models.GameResultDB.cpbl_game_id == cpbl_game_id)
            .first()
        )

        if existing_game:
            return existing_game.id
        else:
            game_data_for_db = {
                "cpbl_game_id": game_info.get("cpbl_game_id"),
                "game_date": datetime.datetime.strptime(
                    game_info["game_date"], "%Y-%m-%d"
                ).date(),
                "game_time": game_info.get("game_time"),
                "home_team": game_info.get("home_team"),
                "away_team": game_info.get("away_team"),
                "home_score": game_info.get("home_score"),
                "away_score": game_info.get("away_score"),
                "venue": game_info.get("venue"),
                "status": game_info.get("status"),
            }
            new_game = models.GameResultDB(**game_data_for_db)
            db.add(new_game)
            db.flush()
            logging.info(f"準備新增比賽結果到資料庫: {new_game.cpbl_game_id}")
            return new_game.id

    except Exception as e:
        logging.error(f"準備儲存比賽結果時出錯: {e}", exc_info=True)
        raise


def store_player_season_stats_and_history(
    db: Session, season_stats_list: List[Dict[str, Any]]
):
    """
    【修改】儲存最新的球員球季數據，並同時在歷史紀錄表中新增一筆快照。
    """
    if not season_stats_list:
        return

    logging.info(
        f"準備批次更新 {len(season_stats_list)} 位球員的球季累積數據，並寫入歷史紀錄..."
    )
    player_names_to_update = [stats["player_name"] for stats in season_stats_list]

    try:
        # 1. 更新 PlayerSeasonStatsDB (覆蓋式)
        db.query(models.PlayerSeasonStatsDB).filter(
            models.PlayerSeasonStatsDB.player_name.in_(player_names_to_update)
        ).delete(synchronize_session=False)

        new_stats_objects = []
        for stats in season_stats_list:
            stats["data_retrieved_date"] = datetime.date.today().strftime("%Y-%m-%d")
            new_stats_objects.append(models.PlayerSeasonStatsDB(**stats))
        db.add_all(new_stats_objects)

        # 2. 新增至 PlayerSeasonStatsHistoryDB (日誌式)
        history_stats_objects = []
        for stats in season_stats_list:
            # 移除 'updated_at' 欄位，因為 history 表沒有這個欄位
            stats_copy = stats.copy()
            stats_copy.pop("updated_at", None)
            history_stats_objects.append(
                models.PlayerSeasonStatsHistoryDB(**stats_copy)
            )
        db.add_all(history_stats_objects)

        logging.info(
            f"已準備 {len(new_stats_objects)} 筆球員球季數據與 {len(history_stats_objects)} 筆歷史數據待提交。"
        )
    except Exception as e:
        logging.error(f"準備更新球員球季數據時出錯: {e}", exc_info=True)
        raise


def store_player_game_data(
    db: Session, game_id: int, all_players_data: List[Dict[str, Any]]
):
    """【ORM版】準備多位球員的單場總結與完整的逐打席記錄以供儲存。"""
    if not all_players_data:
        return

    summary_cols = {c.key for c in inspect(models.PlayerGameSummaryDB).column_attrs}
    detail_cols = {c.key for c in inspect(models.AtBatDetailDB).column_attrs}

    for player_data in all_players_data:
        summary_dict = player_data.get("summary", {})
        at_bats_details_list = player_data.get("at_bats_details", [])
        if not summary_dict:
            continue

        player_name = summary_dict.get("player_name")

        try:
            summary_dict["game_id"] = game_id

            filtered_summary = {
                k: v for k, v in summary_dict.items() if k in summary_cols
            }

            existing_summary = (
                db.query(models.PlayerGameSummaryDB)
                .filter_by(game_id=game_id, player_name=player_name)
                .first()
            )

            if existing_summary:
                for key, value in filtered_summary.items():
                    setattr(existing_summary, key, value)
                summary_orm_object = existing_summary
            else:
                summary_orm_object = models.PlayerGameSummaryDB(**filtered_summary)
                db.add(summary_orm_object)

            db.flush()

            player_game_summary_id = summary_orm_object.id
            if not player_game_summary_id:
                logging.warning(
                    f"無法取得球員 {player_name} 在比賽 {game_id} 的 summary_id。"
                )
                continue

            for detail_dict in at_bats_details_list:
                detail_dict["player_game_summary_id"] = player_game_summary_id

                filtered_detail = {
                    k: v for k, v in detail_dict.items() if k in detail_cols
                }

                existing_detail = (
                    db.query(models.AtBatDetailDB)
                    .filter_by(
                        player_game_summary_id=player_game_summary_id,
                        sequence_in_game=detail_dict.get("sequence_in_game"),
                    )
                    .first()
                )

                if existing_detail:
                    for key, value in filtered_detail.items():
                        setattr(existing_detail, key, value)
                else:
                    db.add(models.AtBatDetailDB(**filtered_detail))

            logging.info(
                f"已準備球員 [{player_name}] 的 {len(at_bats_details_list)} 筆逐打席記錄待提交。"
            )

        except Exception as e:
            logging.error(
                f"準備儲存球員 [{player_name}] 的單場比賽數據時出錯: {e}", exc_info=True
            )
            raise


def update_game_schedules(db: Session, games_list: List[Dict[str, Any]]):
    """【ORM版】準備比賽排程表以供更新。"""
    if not games_list:
        logging.info("沒有新的比賽排程需要更新。")
        return

    logging.info(f"準備更新資料庫中的比賽排程，共 {len(games_list)} 場...")

    try:
        num_deleted = db.query(models.GameSchedule).delete()
        logging.info(f"已準備清空舊的比賽排程 ({num_deleted} 筆)。")

        data_to_insert = []
        for game in games_list:
            data_to_insert.append(
                models.GameSchedule(
                    game_id=game.get("game_id"),
                    game_date=datetime.datetime.strptime(
                        game["date"], "%Y-%m-%d"
                    ).date(),
                    game_time=game.get("game_time"),
                    matchup=game.get("matchup"),
                )
            )

        db.add_all(data_to_insert)
        logging.info(f"已準備寫入 {len(data_to_insert)} 筆新的比賽排程。")
    except Exception as e:
        logging.error(f"準備更新比賽排程時發生錯誤: {e}", exc_info=True)
        raise


def get_all_schedules(db: Session) -> List[models.GameSchedule]:
    """【ORM版】從資料庫獲取所有已儲存的比賽排程。"""
    try:
        schedules = (
            db.query(models.GameSchedule)
            .order_by(models.GameSchedule.game_date, models.GameSchedule.game_time)
            .all()
        )
        return schedules
    except Exception as e:
        logging.error(f"獲取比賽排程時發生錯誤: {e}", exc_info=True)
        return []


def get_game_with_details(db: Session, game_id: int) -> models.GameResultDB | None:
    """
    使用 joinedload 預先載入關聯資料，獲取單場比賽的完整細節。
    """
    try:
        game = (
            db.query(models.GameResultDB)
            .options(
                joinedload(models.GameResultDB.player_summaries).options(
                    joinedload(models.PlayerGameSummaryDB.at_bat_details)
                )
            )
            .filter(models.GameResultDB.id == game_id)
            .first()
        )
        return game
    except Exception as e:
        logging.error(
            f"獲取比賽詳細資料時發生錯誤 (game_id: {game_id}): {e}", exc_info=True
        )
        return None


# --- 進階查詢函式 ---


def find_games_with_players(
    db: Session, player_names: List[str]
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
        .order_by(models.GameResultDB.game_date.desc())
        .all()
    )
    return games


def get_stats_since_last_homerun(
    db: Session, player_name: str
) -> Dict[str, Any] | None:
    """【修改】查詢指定球員的最後一發全壘打，並計算此後的相關數據。"""
    last_hr_at_bat = (
        db.query(models.AtBatDetailDB)
        .join(models.PlayerGameSummaryDB)
        .join(models.GameResultDB)
        .filter(models.PlayerGameSummaryDB.player_name == player_name)
        .filter(models.AtBatDetailDB.result_description_full.contains("全壘打"))
        .order_by(
            models.GameResultDB.game_date.desc(),
            models.AtBatDetailDB.sequence_in_game.desc(),
        )
        .options(
            joinedload(models.AtBatDetailDB.player_summary).joinedload(
                models.PlayerGameSummaryDB.game
            )
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
            models.GameResultDB.game_date >= last_hr_date,
        )
        .one()
    )

    return {
        "last_homerun": last_hr_at_bat,
        "game_date": last_hr_date,
        "days_since": (datetime.date.today() - last_hr_date).days,
        "games_since": stats_since.games_since,
        "at_bats_since": stats_since.at_bats_since,
    }


def find_at_bats_in_situation(
    db: Session, player_name: str, situation: models.RunnersSituation
) -> List[models.AtBatDetailDB]:
    """【修改】查詢指定球員在特定壘上情境下的所有打席紀錄。"""
    query = (
        db.query(models.AtBatDetailDB)
        .join(models.PlayerGameSummaryDB)
        .join(models.GameResultDB)
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

    at_bats = query.order_by(
        models.GameResultDB.game_date.desc(),
        models.AtBatDetailDB.sequence_in_game.desc(),
    ).all()
    return at_bats


def get_summaries_by_position(
    db: Session, position: str
) -> List[models.PlayerGameSummaryDB]:
    """查詢指定守備位置的所有球員出賽紀錄。"""
    summaries = (
        db.query(models.PlayerGameSummaryDB)
        .filter(models.PlayerGameSummaryDB.position == position)
        .join(models.GameResultDB)
        .order_by(models.GameResultDB.game_date.desc())
        .all()
    )
    return summaries


def find_next_at_bats_after_ibb(db: Session, player_name: str) -> List[Dict[str, Any]]:
    """【V2 版】使用 SQL 窗口函數 (LEAD) 高效查詢指定球員被故意四壞後，同一半局內下一位打者的打席結果。"""

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
) -> List[models.OnBaseStreak]:
    """
    【重構】查詢符合「連線」定義的打席序列。
    根據是否提供特定球員/棒次，採用不同策略以優化效能。
    """
    # 1. 從設定檔取得有效的打席結果列表
    valid_results = set(settings.STREAK_DEFINITIONS.get(definition_name, []))
    if not valid_results:
        logging.warning(f"無效的連線定義名稱: {definition_name}")
        return []

    # 2. 建立基礎查詢
    query = (
        db.query(models.AtBatDetailDB)
        .join(models.PlayerGameSummaryDB)
        .join(models.GameResultDB)
        .options(
            joinedload(models.AtBatDetailDB.player_summary).joinedload(
                models.PlayerGameSummaryDB.game
            )
        )
    )

    # 效能優化：如果提供了球員姓名，則只查詢這些球員參加過的比賽
    if player_names:
        game_ids_subquery = (
            select(models.PlayerGameSummaryDB.game_id)
            .where(models.PlayerGameSummaryDB.player_name.in_(player_names))
            .distinct()
        )
        query = query.filter(models.PlayerGameSummaryDB.game_id.in_(game_ids_subquery))

    # 排序是為了後續在 Python 中能正確處理序列
    all_at_bats = query.order_by(
        models.GameResultDB.id,
        models.AtBatDetailDB.inning,
        models.AtBatDetailDB.sequence_in_game,
    ).all()

    # 3. 根據查詢類型，選擇不同的處理策略
    all_streaks = []
    if player_names or lineup_positions:
        # 策略一：尋找符合指定「連續」序列的連線
        target_list = player_names if player_names else lineup_positions
        target_len = len(target_list)
        if target_len < min_length:  # 如果指定序列長度小於最小要求，則無結果
            return []

        for i in range(len(all_at_bats) - target_len + 1):
            potential_streak = all_at_bats[i : i + target_len]

            # 檢查點 1: 所有打席必須在同一個半局
            first_ab = potential_streak[0]
            if not all(
                ab.player_summary.game_id == first_ab.player_summary.game_id
                and ab.inning == first_ab.inning
                for ab in potential_streak
            ):
                continue

            # 檢查點 2: 所有打席都必須是有效的連線結果
            if not all(ab.result_short in valid_results for ab in potential_streak):
                continue

            # 檢查點 3: 序列必須完全匹配指定的球員或棒次
            is_match = True
            for j, ab in enumerate(potential_streak):
                if player_names:
                    if ab.player_summary.player_name != player_names[j]:
                        is_match = False
                        break
                elif lineup_positions:
                    try:
                        if int(ab.player_summary.batting_order) != lineup_positions[j]:
                            is_match = False
                            break
                    except (ValueError, TypeError):
                        is_match = False
                        break

            if is_match:
                all_streaks.append(potential_streak)
    else:
        # 策略二：尋找所有長度達標的泛用連線
        current_streak = []
        for i, at_bat in enumerate(all_at_bats):
            is_valid = at_bat.result_short in valid_results
            is_continuous = False
            if current_streak:
                prev_at_bat = current_streak[-1]
                if (
                    prev_at_bat.player_summary.game_id == at_bat.player_summary.game_id
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

    # 4. 將最終結果格式化為 Pydantic 模型
    result_models = []
    for streak in all_streaks:
        if not streak:
            continue
        game = streak[0].player_summary.game
        at_bat_models = [
            models.AtBatDetailForStreak(
                player_name=ab.player_summary.player_name,
                batting_order=ab.player_summary.batting_order,
                **ab.__dict__,
            )
            for ab in streak
        ]

        streak_model = models.OnBaseStreak(
            game_id=game.id,
            game_date=game.game_date,
            inning=streak[0].inning,
            streak_length=len(streak),
            runs_scored_during_streak=sum(ab.runs_scored_on_play for ab in streak),
            at_bats=at_bat_models,
        )
        result_models.append(streak_model)

    return result_models


def analyze_ibb_impact(db: Session, player_name: str) -> List[models.IbbImpactResult]:
    """
    【新增】分析指定球員被故意四壞後，對該半局總失分的影響。
    """
    # 1. 找出所有與該球員相關的比賽中的所有打席
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
            models.AtBatDetailDB.id,  # 使用 id 作為最終排序依據
        )
        .all()
    )

    results = []
    # 2. 在 Python 中遍歷所有打席，找出 IBB 事件並計算後續影響
    for i, at_bat in enumerate(all_related_at_bats):
        # 【修改】增加對 None 的檢查，避免 TypeError
        is_ibb = (
            at_bat.result_description_full
            and "故意四壞" in at_bat.result_description_full
        )
        is_target_player = at_bat.player_summary.player_name == player_name

        if is_ibb and is_target_player:
            ibb_event = at_bat
            subsequent_at_bats = []
            runs_scored_after = 0

            # 往後查找同一個半局的打席
            for next_ab in all_related_at_bats[i + 1 :]:
                if (
                    next_ab.player_summary.game_id == ibb_event.player_summary.game_id
                    and next_ab.inning == ibb_event.inning
                ):
                    subsequent_at_bats.append(next_ab)
                    runs_scored_after += next_ab.runs_scored_on_play
                else:
                    # 進入下一局或下一場比賽，結束查找
                    break

            # 3. 將結果組裝成 Pydantic 模型
            game = ibb_event.player_summary.game

            ibb_model = models.AtBatDetailForStreak(
                player_name=ibb_event.player_summary.player_name,
                batting_order=ibb_event.player_summary.batting_order,
                **ibb_event.__dict__,
            )

            subsequent_models = [
                models.AtBatDetailForStreak(
                    player_name=ab.player_summary.player_name,
                    batting_order=ab.player_summary.batting_order,
                    **ab.__dict__,
                )
                for ab in subsequent_at_bats
            ]

            impact_result = models.IbbImpactResult(
                game_id=game.id,
                game_date=game.game_date,
                inning=ibb_event.inning,
                intentional_walk=ibb_model,
                subsequent_at_bats=subsequent_models,
                runs_scored_after_ibb=runs_scored_after,
            )
            results.append(impact_result)

    # 由於查詢是升序的，為了讓 API 回傳最新的在前面，這裡進行反轉
    return results[::-1]
