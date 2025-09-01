# app/schemas.py

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Optional, List, Union
import datetime

from app.models import AtBatResultType

# ==============================================================================
# 2. Pydantic Models (API 資料驗證模型)
# ==============================================================================


class AtBatDetail(BaseModel):
    id: int
    inning: Optional[int] = None
    sequence_in_game: Optional[int] = None
    result_short: Optional[str] = None
    result_description_full: Optional[str] = None
    opposing_pitcher_name: Optional[str] = None
    pitch_sequence_details: Optional[str] = None
    runners_on_base_before: Optional[str] = None
    outs_before: Optional[int] = None
    runs_scored_on_play: int
    result_type: Optional[AtBatResultType] = None

    model_config = ConfigDict(from_attributes=True)


class SituationalAtBatDetail(AtBatDetail):
    """擴充 AtBatDetail，增加比賽日期與對戰對手資訊。"""

    game_date: datetime.date = Field(..., description="比賽日期")
    opponent_team: str = Field(..., description="對戰球隊")


class PlayerGameSummary(BaseModel):
    id: int
    game_id: int
    player_name: str
    team_name: Optional[str] = None
    batting_order: Optional[str] = None
    position: Optional[str] = None
    plate_appearances: int
    at_bats: int
    runs_scored: int
    hits: int
    doubles: int
    triples: int
    homeruns: int
    rbi: int
    walks: int
    intentional_walks: int
    hit_by_pitch: int
    strikeouts: int
    stolen_bases: int
    caught_stealing: int
    sacrifice_hits: int
    sacrifice_flies: int
    gidp: int
    errors: int
    avg_cumulative: Optional[float] = None
    at_bat_results_summary: Optional[str] = None
    created_at: datetime.datetime

    at_bat_details: List[AtBatDetail] = []

    model_config = ConfigDict(from_attributes=True)


class GameResult(BaseModel):
    id: int
    cpbl_game_id: Optional[str] = None
    game_date: datetime.date
    game_time: Optional[str] = None
    home_team: str
    away_team: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    venue: Optional[str] = None
    status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# [T29 新增] 用於 /games/season 端點的回應模型
class SeasonGame(BaseModel):
    game_date: datetime.date
    game_id: int
    home_team: str
    away_team: str

    model_config = ConfigDict(from_attributes=True)


class GameResultWithDetails(GameResult):
    player_summaries: List[PlayerGameSummary] = []


class Message(BaseModel):
    message: str


class PlayerSeasonStatsBase(BaseModel):
    player_name: str
    team_name: Optional[str] = None
    data_retrieved_date: Optional[str] = None
    games_played: int
    plate_appearances: int
    at_bats: int
    runs_scored: int
    hits: int
    rbi: int
    homeruns: int
    singles: int
    doubles: int
    triples: int
    total_bases: int
    strikeouts: int
    stolen_bases: int
    gidp: int
    sacrifice_hits: int
    sacrifice_flies: int
    walks: int
    intentional_walks: int
    hit_by_pitch: int
    caught_stealing: int
    ground_outs: int
    fly_outs: int
    avg: Optional[float] = None
    obp: Optional[float] = None
    slg: Optional[float] = None
    ops: Optional[float] = None
    go_ao_ratio: Optional[float] = None
    sb_percentage: Optional[float] = None
    silver_slugger_index: Optional[float] = None


class PlayerSeasonStats(PlayerSeasonStatsBase):
    id: int
    updated_at: Optional[datetime.datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PlayerSeasonStatsHistory(PlayerSeasonStatsBase):
    id: int
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


# [修正] 建立一個包含所有生涯數據欄位的 Pydantic 基礎模型
class PlayerCareerStatsBase(BaseModel):
    player_name: str
    debut_date: Optional[datetime.date] = None
    handedness: Optional[str] = None
    games_played: int
    plate_appearances: int
    at_bats: int
    runs_scored: int
    hits: int
    singles: int
    doubles: int
    triples: int
    homeruns: int
    rbi: int
    total_bases: int
    strikeouts: int
    walks: int
    intentional_walks: int
    hit_by_pitch: int
    stolen_bases: int
    caught_stealing: int
    sacrifice_hits: int
    sacrifice_flies: int
    gidp: int
    ground_outs: int
    fly_outs: int
    avg: Optional[float] = None
    obp: Optional[float] = None
    slg: Optional[float] = None
    ops: Optional[float] = None
    go_ao_ratio: Optional[float] = None
    sb_percentage: Optional[float] = None
    ops_plus: Optional[float] = None
    k_percentage: Optional[float] = None
    bb_percentage: Optional[float] = None
    bb_per_k: Optional[float] = None
    babip: Optional[float] = None
    bip_percentage: Optional[float] = None


# [修正] PlayerCareerStats 現在繼承自新的 Pydantic 基礎模型
class PlayerCareerStats(PlayerCareerStatsBase):
    id: int
    updated_at: Optional[datetime.datetime] = None

    model_config = ConfigDict(from_attributes=True)


class LastHomerunStats(BaseModel):
    last_homerun: AtBatDetail
    game_date: datetime.date
    days_since: int
    games_since: int
    at_bats_since: int
    career_stats: Optional[PlayerCareerStats] = Field(None, description="球員生涯數據")


class NextAtBatResult(BaseModel):
    intentional_walk: AtBatDetail
    next_at_bat: Optional[AtBatDetail] = None

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# 3. 「連線」功能專用 Pydantic 模型
# ==============================================================================


class AtBatDetailForStreak(AtBatDetail):
    """為「連線」功能擴充的打席模型，額外包含打者姓名與棒次資訊。"""

    player_name: str = Field(..., description="打者姓名")
    batting_order: Optional[str] = Field(None, description="棒次")


class OnBaseStreak(BaseModel):
    """代表一次完整「連線」事件的模型。"""

    game_id: int = Field(..., description="比賽的唯一 ID")
    game_date: datetime.date = Field(..., description="比賽日期")
    inning: int = Field(..., description="事件發生的局數")
    streak_length: int = Field(..., description="此次連線的人次長度")
    opponent_team: str = Field(..., description="對戰球隊")
    runs_scored_during_streak: int = Field(
        ..., description="在這次連線期間得到的總分數"
    )
    at_bats: List[AtBatDetailForStreak] = Field(
        ..., description="組成此次連線的所有打席詳細紀錄"
    )


# ==============================================================================
# 4. 「故意四壞影響」功能專用 Pydantic 模型
# ==============================================================================


class IbbImpactResult(BaseModel):
    """代表一次故意四壞事件及其後續影響的模型。"""

    game_id: int = Field(..., description="比賽的唯一 ID")
    game_date: datetime.date = Field(..., description="比賽日期")
    inning: int = Field(..., description="事件發生的局數")
    opponent_team: str = Field(..., description="對戰球隊")
    intentional_walk: AtBatDetailForStreak = Field(
        ..., description="故意四壞的打席紀錄"
    )
    subsequent_at_bats: List[AtBatDetailForStreak] = Field(
        ..., description="該半局後續的所有打席"
    )
    runs_scored_after_ibb: int = Field(
        ..., description="在 IBB 之後，該半局得到的總分數"
    )

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# 5. Dashboard Schemas
# ==============================================================================


class DashboardHasGamesResponse(BaseModel):
    status: Literal["HAS_TODAY_GAMES"]
    games: list["GameResultWithDetails"]


class DashboardNoGamesResponse(BaseModel):
    status: Literal["NO_TODAY_GAMES"]
    next_game_date: Union[datetime.date, None] = Field(
        None,
        description="下一場比賽的日期",
        examples=["2025-08-17"],
    )
    last_target_team_game: Union["GameResultWithDetails", None] = Field(
        None, description="目標球隊的上一場完整比賽數據"
    )


DashboardResponse = Union[DashboardHasGamesResponse, DashboardNoGamesResponse]


# ==============================================================================
# [T31-1] Positions API Schemas
# ==============================================================================


class CalendarDataItem(BaseModel):
    date: datetime.date
    starter_player_name: str
    substitute_player_names: List[str] = []
    starter_player_summary: PlayerGameSummary


# [T31-4 新增] 球員年度守備數據模型
class PlayerFieldingStats(BaseModel):
    id: int
    player_name: str
    team_name: Optional[str] = None
    position: Optional[str] = None
    games_played: int
    total_chances: int
    putouts: int
    assists: int
    errors: int
    double_plays: int
    triple_plays: int
    passed_balls: int
    caught_stealing_catcher: int
    stolen_bases_allowed_catcher: int
    fielding_percentage: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


# [T31-4 修正] 修正 PlayerStatsForPositionAnalysis 模型以包含所有必要欄位
class PlayerStatsForPositionAnalysis(BaseModel):
    player_name: str  # [修正] 新增 player_name 欄位
    batting_stats: Optional[PlayerSeasonStats] = None
    fielding_stats: List[PlayerFieldingStats] = []

    model_config = ConfigDict(from_attributes=True)


class PositionAnalysisResponse(BaseModel):
    calendar_data: List[CalendarDataItem]
    player_stats: List[PlayerStatsForPositionAnalysis]
