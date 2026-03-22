"""Pydantic schemas for Agent 8 — PvP Battle system."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Matchmaking
# ---------------------------------------------------------------------------

class QueueJoinRequest(BaseModel):
    """Request to join PvP matchmaking queue."""
    pass  # Auth header provides user_id


class QueueStatusResponse(BaseModel):
    queue_position: int | None = None
    estimated_wait_seconds: int | None = None
    status: str  # waiting | matched | expired
    duel_id: uuid.UUID | None = None
    opponent_rating: float | None = None


class PvEFallbackResponse(BaseModel):
    """Offered when no PvP match found in 90s."""
    duel_id: uuid.UUID
    is_pve: bool = True
    bot_rating: float
    message: str = "Противник не найден. Предлагаем дуэль с AI-ботом."


# ---------------------------------------------------------------------------
# Duel
# ---------------------------------------------------------------------------

class RoundResult(BaseModel):
    round_number: int
    seller_id: uuid.UUID
    client_id: uuid.UUID
    seller_score: float = 0.0
    client_score: float = 0.0
    duration_seconds: int = 0
    key_moments: list[dict] = Field(default_factory=list)
    legal_accuracy_score: float = 0.0


class DuelResponse(BaseModel):
    id: uuid.UUID
    player1_id: uuid.UUID
    player2_id: uuid.UUID
    status: str
    difficulty: str
    round_number: int
    player1_total: float
    player2_total: float
    winner_id: uuid.UUID | None = None
    is_draw: bool = False
    is_pve: bool = False
    duration_seconds: int = 0
    round_1_data: dict | None = None
    round_2_data: dict | None = None
    anti_cheat_flags: list[dict] | None = None
    replay_url: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class DuelBriefResponse(BaseModel):
    """Brief shown to the CLIENT role player."""
    duel_id: uuid.UUID
    your_role: str  # "seller" or "client"
    archetype: str | None = None
    human_factors: dict | None = None
    difficulty: str
    scenario_title: str | None = None
    round_number: int
    time_limit_seconds: int = 600  # 10 minutes per round


# ---------------------------------------------------------------------------
# Rating
# ---------------------------------------------------------------------------

class RatingResponse(BaseModel):
    user_id: uuid.UUID
    rating: float
    rd: float
    volatility: float
    rank_tier: str
    rank_display: str
    wins: int
    losses: int
    draws: int
    total_duels: int
    placement_done: bool
    placement_count: int
    peak_rating: float
    peak_tier: str
    current_streak: int
    best_streak: int
    season_name: str | None = None
    last_played: datetime | None = None

    model_config = {"from_attributes": True}


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: uuid.UUID
    username: str
    avatar_url: str | None = None
    rating: float
    rank_tier: str
    rank_display: str
    wins: int
    losses: int
    total_duels: int
    current_streak: int


class LeaderboardResponse(BaseModel):
    season: str | None = None
    entries: list[LeaderboardEntry]
    total_players: int


# ---------------------------------------------------------------------------
# Anti-Cheat
# ---------------------------------------------------------------------------

class AntiCheatFlagResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    duel_id: uuid.UUID | None
    check_type: str
    score: float
    flagged: bool
    action_taken: str
    details: dict | None = None
    resolution: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Season
# ---------------------------------------------------------------------------

class SeasonResponse(BaseModel):
    id: uuid.UUID
    name: str
    start_date: datetime
    end_date: datetime
    is_active: bool
    rewards: dict | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# WebSocket messages
# ---------------------------------------------------------------------------

class WSMessage(BaseModel):
    """Base WebSocket message."""
    type: str
    data: dict = Field(default_factory=dict)


class WSAuthMessage(BaseModel):
    type: str = "auth"
    token: str


class WSDuelMessage(BaseModel):
    """Message sent during a duel (text from player)."""
    type: str = "duel.message"
    text: str
    timestamp: float | None = None


class WSJudgeScore(BaseModel):
    """Real-time scoring from AI judge."""
    type: str = "judge.score"
    selling_score: float = 0.0
    acting_score: float = 0.0
    legal_accuracy: float = 0.0
    breakdown: dict = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)
