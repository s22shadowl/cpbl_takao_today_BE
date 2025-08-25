# app/services/data_persistence.py

import logging
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from app.crud import games, players

logger = logging.getLogger(__name__)


def prepare_game_storage(db: Session, game_info: Dict) -> Optional[int]:
    """
    準備儲存比賽資料的空間。

    此函式會執行「先刪除後新增」的冪等性策略：
    1. 根據 cpbl_game_id 和 game_date 刪除可能已存在的舊比賽資料。
    2. 建立新的比賽紀錄並回傳其在資料庫中的 ID。

    Args:
        db (Session): SQLAlchemy 的資料庫會話物件。
        game_info (Dict): 包含單場比賽基本資訊的字典。

    Returns:
        Optional[int]: 新建立的比賽在資料庫中的 ID，若建立失敗則回傳 None。
    """
    cpbl_game_id = game_info.get("cpbl_game_id")
    game_date = game_info.get("game_date_obj")

    if not cpbl_game_id or not game_date:
        logger.error("缺少 cpbl_game_id 或 game_date_obj，無法準備比賽儲存空間。")
        return None

    try:
        games.delete_game_if_exists(db, cpbl_game_id, game_date)
        game_id_in_db = games.create_game_and_get_id(db, game_info)
        return game_id_in_db
    except Exception as e:
        logger.error(
            f"準備比賽儲存空間時失敗 (Game ID: {cpbl_game_id}): {e}", exc_info=True
        )
        return None


def commit_player_game_data(
    db: Session, game_id: int, final_player_data_list: List[Dict]
):
    """
    將處理完成的球員逐場比賽數據儲存至資料庫。

    Args:
        db (Session): SQLAlchemy 的資料庫會話物件。
        game_id (int): 對應的比賽在資料庫中的 ID。
        final_player_data_list (List[Dict]): 包含所有球員摘要與打席細節的最終資料列表。
    """
    try:
        players.store_player_game_data(db, game_id, final_player_data_list)
        logger.info(f"已將 Game ID: {game_id} 的球員數據加入會話，待提交。")
    except Exception as e:
        logger.error(f"儲存球員數據時失敗 (Game ID: {game_id}): {e}", exc_info=True)
        # 讓呼叫者決定是否要 rollback
        raise
