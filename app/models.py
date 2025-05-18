from pydantic import BaseModel, Field
from typing import Optional, List
import datetime

class PlayerDailyStatBase(BaseModel):
    player_name: str
    game_date: str # YYYY-MM-DD
    team: Optional[str] = None
    opponent: Optional[str] = None
    at_bats: Optional[int] = Field(default=0)
    runs: Optional[int] = Field(default=0)
    hits: Optional[int] = Field(default=0)
    rbis: Optional[int] = Field(default=0)
    homeruns: Optional[int] = Field(default=0)
    strikeouts: Optional[int] = Field(default=0)
    walks: Optional[int] = Field(default=0)
    stolen_bases: Optional[int] = Field(default=0)
    avg: Optional[float] = None
    obp: Optional[float] = None
    slg: Optional[float] = None
    pitching_wins: Optional[int] = Field(default=0)
    pitching_losses: Optional[int] = Field(default=0)
    pitching_saves: Optional[int] = Field(default=0)
    innings_pitched: Optional[str] = None # e.g., "6.1"
    pitching_hits_allowed: Optional[int] = Field(default=0)
    pitching_runs_allowed: Optional[int] = Field(default=0)
    pitching_earned_runs: Optional[int] = Field(default=0)
    pitching_walks: Optional[int] = Field(default=0)
    pitching_strikeouts: Optional[int] = Field(default=0)
    era: Optional[float] = None
    whip: Optional[float] = None

class PlayerDailyStat(PlayerDailyStatBase):
    id: int
    created_at: datetime.datetime

    class Config:
        orm_mode = True # 讓 Pydantic 可以從 ORM 物件 (或類似字典的 row 物件) 讀取數據

class GameResultBase(BaseModel):
    game_date: str # YYYY-MM-DD
    game_time: Optional[str] = None # HH:MM
    home_team: str
    away_team: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    venue: Optional[str] = None
    status: Optional[str] = None
    winning_pitcher: Optional[str] = None
    losing_pitcher: Optional[str] = None
    save_pitcher: Optional[str] = None
    mvp: Optional[str] = None

class GameResult(GameResultBase):
    id: int
    created_at: datetime.datetime

    class Config:
        orm_mode = True

class Message(BaseModel): # 用於簡單的回應訊息
    message: str