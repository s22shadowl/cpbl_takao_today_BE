# app/db_actions.py

import logging
import datetime
from typing import List, Dict, Any

# SQLAlchemy 的 Session，用於型別提示
from sqlalchemy.orm import Session
# 匯入我們定義的 SQLAlchemy 模型
from . import models

def store_game_and_get_id(db: Session, game_info: Dict[str, Any]) -> int | None:
    """
    【ORM版】將單場比賽概要資訊存入 game_results 表格。
    如果比賽記錄已存在，則不進行任何操作。
    無論如何，都會查詢並返回該筆記錄在資料庫中的主鍵 id。

    :param db: SQLAlchemy Session 物件
    :param game_info: 包含單場比賽資訊的字典
    :return: 該筆比賽記錄在資料庫中的 id (int)，如果失敗則返回 None
    """
    try:
        cpbl_game_id = game_info.get('cpbl_game_id')
        if not cpbl_game_id:
            return None

        # 1. 查詢比賽是否已存在
        existing_game = db.query(models.GameResultDB).filter(models.GameResultDB.cpbl_game_id == cpbl_game_id).first()

        if existing_game:
            return existing_game.id
        else:
            # 2. 如果不存在，則新增
            game_data_for_db = {
                'cpbl_game_id': game_info.get('cpbl_game_id'),
                'game_date': datetime.datetime.strptime(game_info['game_date'], "%Y-%m-%d").date(),
                'game_time': game_info.get('game_time'),
                'home_team': game_info.get('home_team'),
                'away_team': game_info.get('away_team'),
                'home_score': game_info.get('home_score'),
                'away_score': game_info.get('away_score'),
                'venue': game_info.get('venue'),
                'status': game_info.get('status'),
            }
            new_game = models.GameResultDB(**game_data_for_db)
            db.add(new_game)
            db.commit()
            db.refresh(new_game) # 刷新以獲取新產生的 id
            logging.info(f"新增比賽結果到資料庫: {new_game.cpbl_game_id}")
            return new_game.id

    except Exception as e:
        logging.error(f"儲存比賽結果時出錯: {e}", exc_info=True)
        db.rollback()
        return None

def update_player_season_stats(db: Session, season_stats_list: List[Dict[str, Any]]):
    """
    【ORM版】批次更新多位球員的球季累積數據。
    採用「先刪除後插入」的策略。
    """
    if not season_stats_list:
        return

    logging.info(f"準備批次更新 {len(season_stats_list)} 位球員的球季累積數據...")
    
    player_names_to_update = [stats['player_name'] for stats in season_stats_list]

    try:
        # 1. 一次性刪除所有即將更新的球員的舊記錄
        db.query(models.PlayerSeasonStatsDB).filter(
            models.PlayerSeasonStatsDB.player_name.in_(player_names_to_update)
        ).delete(synchronize_session=False)
        
        # 2. 準備新的 ORM 物件列表
        new_stats_objects = []
        for stats in season_stats_list:
            stats['data_retrieved_date'] = datetime.date.today().strftime("%Y-%m-%d")
            new_stats_objects.append(models.PlayerSeasonStatsDB(**stats))
            
        # 3. 一次性批次插入所有新記錄
        db.add_all(new_stats_objects)
        db.commit()
        logging.info(f"成功批次更新 {len(new_stats_objects)} 筆球員球季數據。")
    except Exception as e:
        logging.error(f"批次更新球員球季數據時出錯: {e}", exc_info=True)
        db.rollback()

def store_player_game_data(db: Session, game_id: int, all_players_data: List[Dict[str, Any]]):
    """【ORM版】儲存多位球員的單場總結與完整的逐打席記錄。"""
    if not all_players_data: return

    for player_data in all_players_data:
        summary_dict = player_data.get("summary", {})
        at_bats_details_list = player_data.get("at_bats_details", [])
        if not summary_dict: continue
        
        player_name = summary_dict.get("player_name")

        try:
            # 1. 處理/更新球員單場總結 (Upsert)
            summary_dict['game_id'] = game_id
            
            # 查詢現有記錄
            existing_summary = db.query(models.PlayerGameSummaryDB).filter_by(
                game_id=game_id, 
                player_name=player_name
            ).first()

            if existing_summary:
                # 更新現有記錄
                for key, value in summary_dict.items():
                    setattr(existing_summary, key, value)
                summary_orm_object = existing_summary
            else:
                # 新增記錄
                summary_orm_object = models.PlayerGameSummaryDB(**summary_dict)
                db.add(summary_orm_object)
            
            # 使用 merge 也是一種選擇，但手動控制更清晰
            # summary_orm_object = db.merge(models.PlayerGameSummaryDB(**summary_dict))

            db.flush() # 送出變更到資料庫，以便取得 summary_orm_object.id
            
            player_game_summary_id = summary_orm_object.id
            if not player_game_summary_id:
                logging.warning(f"無法取得球員 {player_name} 在比賽 {game_id} 的 summary_id。")
                continue

            # 2. 處理/更新逐打席記錄 (Upsert)
            for detail_dict in at_bats_details_list:
                detail_dict['player_game_summary_id'] = player_game_summary_id
                
                existing_detail = db.query(models.AtBatDetailDB).filter_by(
                    player_game_summary_id=player_game_summary_id,
                    sequence_in_game=detail_dict.get('sequence_in_game')
                ).first()

                if existing_detail:
                    for key, value in detail_dict.items():
                        setattr(existing_detail, key, value)
                else:
                    db.add(models.AtBatDetailDB(**detail_dict))

            logging.info(f"成功更新/儲存球員 [{player_name}] 的 {len(at_bats_details_list)} 筆逐打席記錄。")

        except Exception as e:
            logging.error(f"儲存球員 [{player_name}] 的單場比賽數據時出錯: {e}", exc_info=True)
            db.rollback() # 單一球員出錯時回滾該球員的操作
            continue # 繼續處理下一位球員

    db.commit() # 所有球員都處理完畢後，統一提交

def update_game_schedules(db: Session, games_list: List[Dict[str, Any]]):
    """【ORM版】更新比賽排程表。採用「先清空後批次插入」的策略。"""
    if not games_list:
        logging.info("沒有新的比賽排程需要更新。")
        return
        
    logging.info(f"準備更新資料庫中的比賽排程，共 {len(games_list)} 場...")
    
    try:
        # 1. 為了確保資料最新，先刪除所有舊的排程
        num_deleted = db.query(models.GameSchedule).delete()
        logging.info(f"已清空舊的比賽排程，共刪除 {num_deleted} 筆。")
        
        # 2. 準備新的 ORM 物件
        data_to_insert = []
        for game in games_list:
            data_to_insert.append(models.GameSchedule(
                game_id=game.get("game_id"),
                game_date=datetime.datetime.strptime(game['date'], "%Y-%m-%d").date(),
                game_time=game.get("game_time"),
                matchup=game.get("matchup")
            ))
        
        # 3. 批次插入
        db.add_all(data_to_insert)
        db.commit()
        logging.info(f"成功寫入 {len(data_to_insert)} 筆新的比賽排程。")
    except Exception as e:
        logging.error(f"更新比賽排程時發生錯誤: {e}", exc_info=True)
        db.rollback()

def get_all_schedules(db: Session) -> List[models.GameSchedule]:
    """【ORM版】從資料庫獲取所有已儲存的比賽排程。"""
    try:
        # 直接使用 ORM 查詢並排序
        schedules = db.query(models.GameSchedule).order_by(
            models.GameSchedule.game_date, 
            models.GameSchedule.game_time
        ).all()
        return schedules
    except Exception as e:
        logging.error(f"獲取比賽排程時發生錯誤: {e}", exc_info=True)
        return []