# app/crud/players.py

import logging
import datetime
from typing import List, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy.inspection import inspect
from app import models


def create_or_update_player_career_stats(db: Session, player_stats: Dict[str, Any]):
    """
    新增或更新單一球員的生涯數據。

    這個函式會根據 player_name 檢查球員是否存在於 PlayerCareerStatsDB。
    如果存在，則更新其生涯數據；如果不存在，則建立一筆新紀錄。

    Args:
        db: SQLAlchemy Session 物件。
        player_stats: 一個包含球員姓名和其生涯數據的字典。
                      預期鍵值包含 'player_name' 及 PlayerCareerStatsMixin 中定義的欄位。
    """
    player_name = player_stats.get("player_name")
    if not player_name:
        logging.warning("缺少 player_name，無法新增或更新生涯數據。")
        return

    try:
        # 檢查球員是否已存在
        existing_player = (
            db.query(models.PlayerCareerStatsDB)
            .filter(models.PlayerCareerStatsDB.player_name == player_name)
            .first()
        )

        if existing_player:
            # 更新現有紀錄
            logging.info(f"更新球員 [{player_name}] 的生涯數據...")
            for key, value in player_stats.items():
                if key != "player_name":
                    setattr(existing_player, key, value)
        else:
            # 建立新紀錄
            logging.info(f"為球員 [{player_name}] 建立新的生涯數據紀錄...")
            new_player = models.PlayerCareerStatsDB(**player_stats)
            db.add(new_player)

        # db.commit() # 注意：commit 操作應由 service 層管理
        logging.info(f"已準備好球員 [{player_name}] 的生涯數據待提交。")

    except Exception as e:
        logging.error(f"處理球員 [{player_name}] 的生涯數據時出錯: {e}", exc_info=True)
        raise


def store_player_season_stats_and_history(
    db: Session, season_stats_list: List[Dict[str, Any]]
):
    """
    儲存最新的球員球季數據，並同時在歷史紀錄表中新增一筆快照。
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
        for stats_data in season_stats_list:
            # 【修正】複製字典並移除模型中不存在的 'player_url' 鍵
            stats_for_db = stats_data.copy()
            stats_for_db.pop("player_url", None)
            stats_for_db["data_retrieved_date"] = datetime.date.today().strftime(
                "%Y-%m-%d"
            )
            new_stats_objects.append(models.PlayerSeasonStatsDB(**stats_for_db))
        db.add_all(new_stats_objects)

        # 2. 新增至 PlayerSeasonStatsHistoryDB (日誌式)
        history_stats_objects = []
        for stats_data in season_stats_list:
            # 【修正】複製字典並移除模型中不存在的鍵
            stats_for_history = stats_data.copy()
            stats_for_history.pop("player_url", None)
            stats_for_history.pop("updated_at", None)
            history_stats_objects.append(
                models.PlayerSeasonStatsHistoryDB(**stats_for_history)
            )
        db.add_all(history_stats_objects)

        logging.info(
            f"已準備 {len(new_stats_objects)} 筆球員球季數據與 {len(history_stats_objects)} 筆歷史數據待提交。"
        )
    except Exception as e:
        logging.error(f"準備更新球員球季數據時出錯: {e}", exc_info=True)
        raise


def store_player_fielding_stats(db: Session, fielding_stats_list: List[Dict[str, Any]]):
    """
    [T31-3 新增] 儲存最新的球員年度守備數據。

    採用覆蓋式更新：先刪除既有紀錄，再新增本次抓取的紀錄。
    """
    if not fielding_stats_list:
        return

    logging.info(f"準備批次更新 {len(fielding_stats_list)} 筆球員的年度守備數據...")

    # 取得所有本次要更新的球員姓名
    player_names_to_update = {stats["player_name"] for stats in fielding_stats_list}

    try:
        # 1. 刪除這些球員的所有既有守備數據
        db.query(models.PlayerFieldingStatsDB).filter(
            models.PlayerFieldingStatsDB.player_name.in_(player_names_to_update)
        ).delete(synchronize_session=False)

        # 2. 準備並新增本次抓取到的新數據
        new_stats_objects = [
            models.PlayerFieldingStatsDB(**stats_data)
            for stats_data in fielding_stats_list
        ]
        db.add_all(new_stats_objects)

        logging.info(f"已準備 {len(new_stats_objects)} 筆球員守備數據待提交。")
    except Exception as e:
        logging.error(f"準備更新球員年度守備數據時出錯: {e}", exc_info=True)
        raise


def store_player_game_data(
    db: Session, game_id: int, all_players_data: List[Dict[str, Any]]
):
    """
    準備多位球員的單場總結與完整的逐打席記錄以供儲存。
    採用批次查詢優化，避免 N+1 問題。
    """
    if not all_players_data:
        return

    summary_cols = {c.key for c in inspect(models.PlayerGameSummaryDB).column_attrs}
    detail_cols = {c.key for c in inspect(models.AtBatDetailDB).column_attrs}

    try:
        # --- 效能優化：批次查詢 ---
        player_names_in_request = [
            p["summary"]["player_name"]
            for p in all_players_data
            if p.get("summary") and p["summary"].get("player_name")
        ]
        existing_summaries_query = db.query(models.PlayerGameSummaryDB).filter(
            models.PlayerGameSummaryDB.game_id == game_id,
            models.PlayerGameSummaryDB.player_name.in_(player_names_in_request),
        )
        existing_summaries_map = {
            s.player_name: s for s in existing_summaries_query.all()
        }

        db.flush()
        summary_ids = [s.id for s in existing_summaries_map.values()]
        newly_created_summaries = [
            s
            for s in db.new
            if isinstance(s, models.PlayerGameSummaryDB) and s.game_id == game_id
        ]
        summary_ids.extend([s.id for s in newly_created_summaries if s.id])

        existing_details_map = {}
        if summary_ids:
            existing_details_query = db.query(models.AtBatDetailDB).filter(
                models.AtBatDetailDB.player_game_summary_id.in_(summary_ids)
            )
            existing_details_map = {
                (d.player_game_summary_id, d.sequence_in_game): d
                for d in existing_details_query.all()
            }
        # --- 批次查詢結束 ---

        for player_data in all_players_data:
            summary_dict = player_data.get("summary", {})
            at_bats_details_list = player_data.get("at_bats_details", [])
            if not summary_dict or not summary_dict.get("player_name"):
                continue

            player_name = summary_dict["player_name"]
            summary_dict["game_id"] = game_id
            filtered_summary = {
                k: v for k, v in summary_dict.items() if k in summary_cols
            }

            summary_orm_object = existing_summaries_map.get(player_name)
            if summary_orm_object:
                for key, value in filtered_summary.items():
                    setattr(summary_orm_object, key, value)
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
                detail_dict["game_id"] = game_id
                filtered_detail = {
                    k: v for k, v in detail_dict.items() if k in detail_cols
                }
                sequence = detail_dict.get("sequence_in_game")
                detail_key = (player_game_summary_id, sequence)
                existing_detail = existing_details_map.get(detail_key)

                if existing_detail:
                    for key, value in filtered_detail.items():
                        setattr(existing_detail, key, value)
                else:
                    db.add(models.AtBatDetailDB(**filtered_detail))

            logging.info(
                f"已準備球員 [{player_name}] 的 {len(at_bats_details_list)} 筆逐打席記錄待提交。"
            )

    except Exception as e:
        logging.error(f"準備儲存球員單場比賽數據時出錯: {e}", exc_info=True)
        raise
