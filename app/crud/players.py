# app/crud/players.py

import logging
import datetime
from typing import List, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy.inspection import inspect
from app import models


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
    """
    【重構】準備多位球員的單場總結與完整的逐打席記錄以供儲存。
    採用批次查詢優化，避免 N+1 問題。
    """
    if not all_players_data:
        return

    summary_cols = {c.key for c in inspect(models.PlayerGameSummaryDB).column_attrs}
    detail_cols = {c.key for c in inspect(models.AtBatDetailDB).column_attrs}

    try:
        # --- 效能優化：批次查詢 ---
        # 1. 一次性獲取此場比賽所有已存在的球員摘要
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

        # 2. 預先載入所有摘要的 ID，以準備查詢打席紀錄
        db.flush()
        summary_ids = [s.id for s in existing_summaries_map.values()]
        newly_created_summaries = [
            s
            for s in db.new
            if isinstance(s, models.PlayerGameSummaryDB) and s.game_id == game_id
        ]
        summary_ids.extend([s.id for s in newly_created_summaries if s.id])

        # 3. 一次性獲取所有相關的已存在打席紀錄
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

            # 使用預先載入的 map 進行判斷
            summary_orm_object = existing_summaries_map.get(player_name)
            if summary_orm_object:
                for key, value in filtered_summary.items():
                    setattr(summary_orm_object, key, value)
            else:
                summary_orm_object = models.PlayerGameSummaryDB(**filtered_summary)
                db.add(summary_orm_object)

            db.flush()  # 確保新建立的 summary 獲得 ID
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

                # 使用預先載入的 map 進行判斷
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
