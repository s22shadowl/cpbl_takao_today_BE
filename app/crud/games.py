# app/crud/games.py

import logging
import datetime
from typing import List, Dict, Any

from sqlalchemy.orm import Session, joinedload

from app import models


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
