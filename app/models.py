# app/models.py

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
import datetime

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
    game_date: str
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
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)