# app/models.py

from sqlalchemy import (Column, Integer, String, Date, DateTime, REAL,
                        ForeignKey, UniqueConstraint)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pydantic import BaseModel, ConfigDict
from typing import Optional
import datetime

from .db import Base # 從我們新的 db.py 匯入 Base

# ==============================================================================
# 1. SQLAlchemy ORM Models (資料庫表格定義)
#    這些類別定義了資料庫中的表格結構
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
    
    # 關聯到 player_game_summary
    player_summaries = relationship("PlayerGameSummaryDB", back_populates="game")

    __table_args__ = (UniqueConstraint('game_date', 'home_team', 'away_team', name='_game_date_teams_uc'),)


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
    
    __table_args__ = (UniqueConstraint('game_id', 'player_name', 'team_name', name='_game_player_uc'),)


class AtBatDetailDB(Base):
    __tablename__ = "at_bat_details"

    id = Column(Integer, primary_key=True, index=True)
    player_game_summary_id = Column(Integer, ForeignKey("player_game_summary.id"), nullable=False)
    inning = Column(Integer)
    sequence_in_game = Column(Integer)
    result_short = Column(String)
    result_description_full = Column(String)
    opposing_pitcher_name = Column(String)
    pitch_sequence_details = Column(String)
    runners_on_base_before = Column(String)
    outs_before = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    player_summary = relationship("PlayerGameSummaryDB", back_populates="at_bat_details")

    __table_args__ = (UniqueConstraint('player_game_summary_id', 'sequence_in_game', name='_summary_seq_uc'),)


class PlayerSeasonStatsDB(Base):
    __tablename__ = "player_season_stats"
    
    id = Column(Integer, primary_key=True, index=True)
    player_name = Column(String, unique=True, nullable=False, index=True)
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
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ==============================================================================
# 2. Pydantic Models (API 資料驗證模型)
#    這些類別定義了 API 請求和回應的資料格式
# ==============================================================================

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


class Message(BaseModel):
    message: str


class PlayerSeasonStats(BaseModel):
    id: int
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
    updated_at: Optional[datetime.datetime] = None

    model_config = ConfigDict(from_attributes=True)