# app/models.py

from sqlalchemy import (
    Boolean,
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
import enum
import sqlalchemy as sa

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
    INCOMPLETE_PA = "incomplete_pa"  # [新增] 用於表示未完成的打席


class RunnersSituation(str, enum.Enum):
    BASES_EMPTY = "bases_empty"
    SCORING_POSITION = "scoring_position"
    BASES_LOADED = "bases_loaded"


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

    # 【修正】新增 cascade="all, delete-orphan" 以確保級聯刪除正常運作
    player_summaries = relationship(
        "PlayerGameSummaryDB", back_populates="game", cascade="all, delete-orphan"
    )

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
    # 【修正】新增 cascade="all, delete-orphan"
    at_bat_details = relationship(
        "AtBatDetailDB", back_populates="player_summary", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("game_id", "player_name", "team_name", name="_game_player_uc"),
    )


class AtBatDetailDB(Base):
    __tablename__ = "at_bat_details"

    id = Column(Integer, primary_key=True, index=True)
    # 新增 game_id 欄位，並建立外鍵關聯與索引
    game_id = Column(Integer, ForeignKey("game_results.id"), nullable=False, index=True)
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
    is_score_from_description = Column(  # [新增] 用於驗證的標記
        Boolean, nullable=False, default=False, server_default=sa.false()
    )

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


# --- 【新增】球員生涯數據 Mixin ---
class PlayerCareerStatsMixin:
    # 基本資訊
    debut_date = Column(Date, nullable=True)
    handedness = Column(String, nullable=True)  # 投打習慣

    # 傳統數據
    games_played = Column(Integer, default=0)
    plate_appearances = Column(Integer, default=0)
    at_bats = Column(Integer, default=0)
    runs_scored = Column(Integer, default=0)
    hits = Column(Integer, default=0)
    singles = Column(Integer, default=0)
    doubles = Column(Integer, default=0)
    triples = Column(Integer, default=0)
    homeruns = Column(Integer, default=0)
    rbi = Column(Integer, default=0)
    total_bases = Column(Integer, default=0)
    strikeouts = Column(Integer, default=0)
    walks = Column(Integer, default=0)
    intentional_walks = Column(Integer, default=0)
    hit_by_pitch = Column(Integer, default=0)
    stolen_bases = Column(Integer, default=0)
    caught_stealing = Column(Integer, default=0)
    sacrifice_hits = Column(Integer, default=0)
    sacrifice_flies = Column(Integer, default=0)
    gidp = Column(Integer, default=0)
    ground_outs = Column(Integer, default=0)
    fly_outs = Column(Integer, default=0)

    # 比率數據
    avg = Column(REAL)
    obp = Column(REAL)
    slg = Column(REAL)
    ops = Column(REAL)
    go_ao_ratio = Column(REAL)
    sb_percentage = Column(REAL)

    # 進階數據
    ops_plus = Column(REAL)
    k_percentage = Column(REAL)
    bb_percentage = Column(REAL)
    bb_per_k = Column(REAL)
    babip = Column(REAL)
    bip_percentage = Column(REAL)


# --- 【修改】擴充球員生涯數據表格 ---
class PlayerCareerStatsDB(Base, PlayerCareerStatsMixin):
    __tablename__ = "player_career_stats"

    id = Column(Integer, primary_key=True, index=True)
    player_name = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
