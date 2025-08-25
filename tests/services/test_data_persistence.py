# tests/services/test_data_persistence.py

import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import datetime

from app.services import data_persistence


@patch("app.services.data_persistence.games")
@patch("app.services.data_persistence.logger")
def test_prepare_game_storage_success(mock_logger, mock_games_crud):
    """測試 prepare_game_storage 成功執行的路徑。"""
    mock_db = MagicMock(spec=Session)
    game_date = datetime.date(2025, 8, 12)
    game_info = {"cpbl_game_id": "G01", "game_date_obj": game_date}
    mock_games_crud.create_game_and_get_id.return_value = 123

    result = data_persistence.prepare_game_storage(mock_db, game_info)

    mock_games_crud.delete_game_if_exists.assert_called_once_with(
        mock_db, "G01", game_date
    )
    mock_games_crud.create_game_and_get_id.assert_called_once_with(mock_db, game_info)
    assert result == 123
    mock_logger.error.assert_not_called()


@patch("app.services.data_persistence.games")
@patch("app.services.data_persistence.logger")
def test_prepare_game_storage_db_error(mock_logger, mock_games_crud):
    """測試當資料庫操作失敗時，prepare_game_storage 能優雅地處理錯誤。"""
    mock_db = MagicMock(spec=Session)
    game_date = datetime.date(2025, 8, 12)
    game_info = {"cpbl_game_id": "G01", "game_date_obj": game_date}
    mock_games_crud.create_game_and_get_id.side_effect = SQLAlchemyError(
        "DB connection failed"
    )

    result = data_persistence.prepare_game_storage(mock_db, game_info)

    assert result is None
    mock_logger.error.assert_called_once()


@patch("app.services.data_persistence.players")
@patch("app.services.data_persistence.logger")
def test_commit_player_game_data_success(mock_logger, mock_players_crud):
    """測試 commit_player_game_data 成功呼叫 CRUD 函式。"""
    mock_db = MagicMock(spec=Session)
    game_id = 123
    player_data = [{"player_name": "Player A"}]

    data_persistence.commit_player_game_data(mock_db, game_id, player_data)

    mock_players_crud.store_player_game_data.assert_called_once_with(
        mock_db, 123, player_data
    )
    mock_logger.error.assert_not_called()


@patch("app.services.data_persistence.players")
def test_commit_player_game_data_propagates_error(mock_players_crud):
    """測試 commit_player_game_data 會將底層的異常向上傳遞。"""
    mock_db = MagicMock(spec=Session)
    game_id = 123
    player_data = [{"player_name": "Player A"}]
    mock_players_crud.store_player_game_data.side_effect = ValueError(
        "Invalid data format"
    )

    with pytest.raises(ValueError, match="Invalid data format"):
        data_persistence.commit_player_game_data(mock_db, game_id, player_data)
