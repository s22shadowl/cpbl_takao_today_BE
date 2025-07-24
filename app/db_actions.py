# app/db_actions.py

import logging
import datetime
from typing import List, Dict, Any

from sqlalchemy.orm import Session, joinedload
from sqlalchemy.inspection import inspect

from . import models


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
