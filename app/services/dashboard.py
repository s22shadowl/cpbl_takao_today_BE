# app/services/dashboard.py

from datetime import date

from sqlalchemy.orm import Session

from app import schemas
from app.crud import games
from app.config import Settings
from app.utils.parsing_helpers import (
    calculate_last_10_games_record,
    calculate_current_streak,
)


class DashboardService:
    def __init__(self, db: Session, settings: Settings):
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

        next_game_schedule = games.get_next_game_schedule_after(
            self.db, after_date=today
        )
        next_game_status = None
        if next_game_schedule:
            next_game_status = schemas.NextGameStatus(
                game_date=next_game_schedule.game_date,
                game_time=next_game_schedule.game_time,
                matchup=next_game_schedule.matchup,
            )

        if completed_games_today:
            return schemas.DashboardHasGamesResponse(
                status="HAS_TODAY_GAMES",
                games=completed_games_today,
                next_game_status=next_game_status,
            )
        else:
            last_target_team_game = games.get_last_completed_game_for_teams(
                self.db,
                teams=self.settings.TARGET_TEAMS,
                before_date=today,
            )

            # 計算目標球隊的近期戰況
            target_team_status = None
            # 確保設定檔中至少有一個目標球隊
            if self.settings.TARGET_TEAMS:
                # 以第一個目標球隊為準
                target_team_name = self.settings.TARGET_TEAMS[0]
                recent_games = games.get_last_n_completed_games_for_team(
                    self.db, team_name=target_team_name, limit=10
                )

                if recent_games:
                    last_10_record = calculate_last_10_games_record(
                        games=list(recent_games), team_name=target_team_name
                    )
                    current_streak = calculate_current_streak(
                        games=list(recent_games), team_name=target_team_name
                    )
                    target_team_status = schemas.TeamRecentStatus(
                        team_name=target_team_name,
                        last_10_games_record=last_10_record,
                        current_streak_description=current_streak,
                    )

            return schemas.DashboardNoGamesResponse(
                status="NO_TODAY_GAMES",
                next_game_status=next_game_status,
                last_target_team_game=last_target_team_game,
                target_team_status=target_team_status,
            )
