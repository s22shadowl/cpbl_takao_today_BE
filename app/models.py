# app/models.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    REAL,
    ForeignKey,
    UniqueConstraint,
    Enum,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
import datetime
import enum

from .db import Base

# ==============================================================================
# 0. Enums (列舉定義)
# ==============================================================================


class AtBatResultType(enum.Enum):
    UNSPECIFIED = "UNSPECIFIED"
    ON_BASE = "ON_BASE"  # 安打、保送、觸身
    OUT = "OUT"  # 三振、飛球、滾地出局
    SACRIFICE = "SACRIFICE"  # 犧牲打
    FIELDERS_CHOICE = "FIELDERS_CHOICE"  # 野手選擇
    ERROR = "ERROR"  # 因失誤上壘


# ==============================================================================
# 1. SQLAlchemy ORM Models (資料庫表格定義)
# ==============================================================================


class GameSchedule(Base):
    __tablename__ = "game_schedules"

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(String, unique=True, index=True)
    game_date = Column(Date)
    game_time = Column(String)
    matchup = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class GameResultDB(Base):
    __tablename__ = "game_results"

    id = Column(Integer, primary_key=True, index=True)
    cpbl_game_id = Column(String, unique=True, index=True)
    game_date = Column(Date, nullable=False, index=True)
    game_time = Column(String)
    home_team = Column(String, nullable=False)
    away_team = Column(String, nullable=False)
    home_score = Column(Integer)
    away_score = Column(Integer)
    venue = Column(String)
    status = Column(String)
    winning_pitcher = Column(String)
    losing_pitcher = Column(String)
    save_pitcher = Column(String)
    mvp = Column(String)
    game_duration = Column(String)
    attendance = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    player_summaries = relationship("PlayerGameSummaryDB", back_populates="game")

    __table_args__ = (
        UniqueConstraint(
            "game_date", "home_team", "away_team", name="_game_date_teams_uc"
        ),
    )


class PlayerGameSummaryDB(Base):
    __tablename__ = "player_game_summary"

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("game_results.id"), nullable=False)
    player_name = Column(String, nullable=False, index=True)
    team_name = Column(String)
    batting_order = Column(String)
    position = Column(String)
    plate_appearances = Column(Integer, default=0)
    at_bats = Column(Integer, default=0)
    runs_scored = Column(Integer, default=0)
    hits = Column(Integer, default=0)
    doubles = Column(Integer, default=0)
    triples = Column(Integer, default=0)
    homeruns = Column(Integer, default=0)
    rbi = Column(Integer, default=0)
    walks = Column(Integer, default=0)
    intentional_walks = Column(Integer, default=0)
    hit_by_pitch = Column(Integer, default=0)
    strikeouts = Column(Integer, default=0)
    stolen_bases = Column(Integer, default=0)
    caught_stealing = Column(Integer, default=0)
    sacrifice_hits = Column(Integer, default=0)
    sacrifice_flies = Column(Integer, default=0)
    gidp = Column(Integer, default=0)
    errors = Column(Integer, default=0)
    avg_cumulative = Column(REAL)
    obp_cumulative = Column(REAL)
    slg_cumulative = Column(REAL)
    ops_cumulative = Column(REAL)
    at_bat_results_summary = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    game = relationship("GameResultDB", back_populates="player_summaries")
    at_bat_details = relationship("AtBatDetailDB", back_populates="player_summary")

    __table_args__ = (
        UniqueConstraint("game_id", "player_name", "team_name", name="_game_player_uc"),
    )


class AtBatDetailDB(Base):
    __tablename__ = "at_bat_details"

    id = Column(Integer, primary_key=True, index=True)
    player_game_summary_id = Column(
        Integer, ForeignKey("player_game_summary.id"), nullable=False
    )
    inning = Column(Integer)
    sequence_in_game = Column(Integer)
    result_short = Column(String)
    result_description_full = Column(String)
    opposing_pitcher_name = Column(String)
    pitch_sequence_details = Column(String)
    runners_on_base_before = Column(String)
    outs_before = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    runs_scored_on_play = Column(Integer, default=0)
    result_type = Column(Enum(AtBatResultType), nullable=True, index=True)

    player_summary = relationship(
        "PlayerGameSummaryDB", back_populates="at_bat_details"
    )

    __table_args__ = (
        UniqueConstraint(
            "player_game_summary_id", "sequence_in_game", name="_summary_seq_uc"
        ),
    )


class PlayerSeasonStatsMixin:
    team_name = Column(String)
    data_retrieved_date = Column(String)
    games_played = Column(Integer, default=0)
    plate_appearances = Column(Integer, default=0)
    at_bats = Column(Integer, default=0)
    runs_scored = Column(Integer, default=0)
    hits = Column(Integer, default=0)
    rbi = Column(Integer, default=0)
    homeruns = Column(Integer, default=0)
    singles = Column(Integer, default=0)
    doubles = Column(Integer, default=0)
    triples = Column(Integer, default=0)
    total_bases = Column(Integer, default=0)
    strikeouts = Column(Integer, default=0)
    stolen_bases = Column(Integer, default=0)
    gidp = Column(Integer, default=0)
    sacrifice_hits = Column(Integer, default=0)
    sacrifice_flies = Column(Integer, default=0)
    walks = Column(Integer, default=0)
    intentional_walks = Column(Integer, default=0)
    hit_by_pitch = Column(Integer, default=0)
    caught_stealing = Column(Integer, default=0)
    ground_outs = Column(Integer, default=0)
    fly_outs = Column(Integer, default=0)
    avg = Column(REAL)
    obp = Column(REAL)
    slg = Column(REAL)
    ops = Column(REAL)
    go_ao_ratio = Column(REAL)
    sb_percentage = Column(REAL)
    silver_slugger_index = Column(REAL)


class PlayerSeasonStatsDB(Base, PlayerSeasonStatsMixin):
    __tablename__ = "player_season_stats"

    id = Column(Integer, primary_key=True, index=True)
    player_name = Column(String, unique=True, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class PlayerSeasonStatsHistoryDB(Base, PlayerSeasonStatsMixin):
    __tablename__ = "player_season_stats_history"

    id = Column(Integer, primary_key=True, index=True)
    player_name = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


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


class GameResultWithDetails(GameResult):
    player_summaries: List[PlayerGameSummary] = []


class Message(BaseModel):
    message: str


# 【新增】建立 Pydantic 基礎模型以共享球季數據欄位
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


# 【修改】讓 PlayerSeasonStats 繼承自基礎模型
class PlayerSeasonStats(PlayerSeasonStatsBase):
    id: int
    updated_at: Optional[datetime.datetime] = None

    model_config = ConfigDict(from_attributes=True)


# 【新增】為歷史紀錄表建立對應的 Pydantic 模型
class PlayerSeasonStatsHistory(PlayerSeasonStatsBase):
    id: int
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


# 【新增】定義壘上情境的 Enum，供 API 參數使用
class RunnersSituation(str, enum.Enum):
    BASES_EMPTY = "bases_empty"
    SCORING_POSITION = "scoring_position"
    BASES_LOADED = "bases_loaded"


# 【新增】定義「最後一轟」API 的回應模型
class LastHomerunStats(BaseModel):
    last_homerun: AtBatDetail
    game_date: datetime.date
    days_since: int
    games_since: int
    at_bats_since: int
