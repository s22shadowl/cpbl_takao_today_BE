# app/crud/games.py

import logging
import datetime
from typing import List, Dict, Any

from sqlalchemy.orm import Session, joinedload
from typing import Sequence

from sqlalchemy import and_, or_, select

from app import models


def delete_game_if_exists(db: Session, cpbl_game_id: str, game_date: datetime.date):
    """
    【新增】根據 CPBL Game ID 和比賽日期，檢查並刪除已存在的比賽紀錄。
    利用 SQLAlchemy 的 cascade 行為，一併刪除關聯的 player_summaries 和 at_bat_details。
    """
    try:
        existing_game = (
            db.query(models.GameResultDB)
            .filter(
                and_(
                    models.GameResultDB.cpbl_game_id == cpbl_game_id,
                    models.GameResultDB.game_date == game_date,
                )
            )
            .first()
        )

        if existing_game:
            logging.info(
                f"找到已存在的比賽紀錄 (ID: {existing_game.id}, Date: {game_date})，準備刪除..."
            )
            db.delete(existing_game)
            db.flush()  # 執行刪除操作以確保 cascade 生效
            logging.info("已成功刪除舊的比賽紀錄及其關聯資料。")

    except Exception as e:
        logging.error(f"刪除舊比賽紀錄時發生錯誤: {e}", exc_info=True)
        raise


def create_game_and_get_id(db: Session, game_info: Dict[str, Any]) -> int | None:
    """
    【修改】儲存單場比賽概要資訊。
    此函式現在假設舊資料已被處理，只負責新增。
    :return: 新比賽記錄在資料庫中的 id (int)，如果失敗則返回 None
    """
    try:
        cpbl_game_id = game_info.get("cpbl_game_id")
        if not cpbl_game_id:
            return None

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


def get_games_by_date(
    db: Session, target_date: datetime.date
) -> List[models.GameSchedule]:
    """
    根據指定的日期，從資料庫中查詢所有「排程」。
    """
    return (
        db.query(models.GameSchedule)
        .filter(models.GameSchedule.game_date == target_date)
        .all()
    )


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


def get_completed_games_by_date(
    db: Session, game_date: datetime.date
) -> Sequence[models.GameResultDB]:
    """
    根據指定日期查詢所有已完成的比賽，並預先載入球員摘要。
    """
    statement = (
        select(models.GameResultDB)
        .where(
            and_(
                models.GameResultDB.game_date == game_date,
                models.GameResultDB.status == "Final",
            )
        )
        .options(joinedload(models.GameResultDB.player_summaries))
        .order_by(models.GameResultDB.id)
    )
    # 修正: 加入 .unique() 處理 joined load 可能造成的重複
    return db.execute(statement).unique().scalars().all()


def get_next_game_date_after(
    db: Session, after_date: datetime.date
) -> datetime.date | None:
    """
    查詢指定日期之後的下一個比賽日期。
    """
    statement = (
        select(models.GameResultDB.game_date)
        .where(models.GameResultDB.game_date > after_date)
        .order_by(models.GameResultDB.game_date.asc())
        .limit(1)
    )
    return db.execute(statement).scalar_one_or_none()


def get_last_completed_game_for_teams(
    db: Session, teams: list[str], before_date: datetime.date
) -> models.GameResultDB | None:
    """
    查詢指定球隊列表在特定日期之前的最後一場已完成比賽。
    """
    statement = (
        select(models.GameResultDB)
        .where(
            and_(
                models.GameResultDB.game_date < before_date,
                models.GameResultDB.status == "Final",
                or_(
                    models.GameResultDB.home_team.in_(teams),
                    models.GameResultDB.away_team.in_(teams),
                ),
            )
        )
        .options(joinedload(models.GameResultDB.player_summaries))
        .order_by(models.GameResultDB.game_date.desc(), models.GameResultDB.id.desc())
        .limit(1)
    )
    # 修正: 加入 .unique() 並使用 .scalars().first() 取得單一 ORM 物件
    return db.execute(statement).unique().scalars().first()
