# app/services/dashboard.py

from datetime import date

from sqlalchemy.orm import Session

from app import schemas
from app.crud import games
from app.config import Settings  # 修改 import 風格


class DashboardService:
    def __init__(self, db: Session, settings: Settings):  # 修改型別提示
        self.db = db
        self.settings = settings

    def get_today_dashboard_data(self) -> schemas.DashboardResponse:
        """
        獲取今日儀表板的數據，根據是否有已完成的比賽決定回應的結構。
        """
        today = date.today()
        completed_games_today = games.get_completed_games_by_date(
            self.db, game_date=today
        )

        if completed_games_today:
            return schemas.DashboardHasGamesResponse(
                status="HAS_TODAY_GAMES",
                games=completed_games_today,
            )
        else:
            next_game_date = games.get_next_game_date_after(self.db, after_date=today)
            last_target_team_game = games.get_last_completed_game_for_teams(
                self.db,
                teams=self.settings.TARGET_TEAMS,
                before_date=today,
            )

            return schemas.DashboardNoGamesResponse(
                status="NO_TODAY_GAMES",
                next_game_date=next_game_date,
                last_target_team_game=last_target_team_game,
            )
