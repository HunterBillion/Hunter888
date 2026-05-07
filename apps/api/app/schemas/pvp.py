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
    player1_rating_delta: float = 0.0
    player2_rating_delta: float = 0.0
    rating_change_applied: bool = False
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

class SeasonTopReward(BaseModel):
    """One row in PvPSeason.top_rewards — what the rank=N finisher gets."""
    rank: int
    ap: int
    badge: str | None = None

    model_config = {"from_attributes": True}


class SeasonResponse(BaseModel):
    id: uuid.UUID
    name: str
    start_date: datetime
    end_date: datetime
    is_active: bool
    rewards: dict | None = None
    top_rewards: list[SeasonTopReward] | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# PvE Modes (DOC_10)
# ---------------------------------------------------------------------------

class PvELadderCreateResponse(BaseModel):
    """Response when creating a PvE Ladder run."""
    run_id: uuid.UUID
    total_bots: int = 5
    current_bot_index: int = 0
    first_duel_id: uuid.UUID | None = None
    message: str = "Bot Ladder запущена. Побеждайте 5 ботов последовательно!"

    model_config = {"from_attributes": True}


class PvEBossCreateResponse(BaseModel):
    """Response when creating a PvE Boss Rush run."""
    run_id: uuid.UUID
    boss_index: int
    boss_type: str
    duel_id: uuid.UUID | None = None
    message: str = "Boss Rush: приготовьтесь к бою с боссом!"

    model_config = {"from_attributes": True}


class PvEMirrorCreateResponse(BaseModel):
    """Response when creating a PvE Mirror Match."""
    duel_id: uuid.UUID
    message: str = "Mirror Match: победите своё отражение!"
    style_summary: dict | None = None

    model_config = {"from_attributes": True}


class TierChangeResponse(BaseModel):
    """Tier change notification after duel."""
    promotion_started: bool = False
    target_tier: str | None = None
    demoted: bool = False
    new_tier: str | None = None
    demotion_warning: bool = False
    losses_until_demotion: int | None = None
    series_wins: int = 0
    series_losses: int = 0
    series_matches_needed: int = 3


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


# ---------------------------------------------------------------------------
# DOC_09: New PvP Mode Schemas
# ---------------------------------------------------------------------------

class RapidFireCreateRequest(BaseModel):
    """Request to create a Rapid Fire match."""
    pass  # Auth header provides user_id


class RapidFireCreateResponse(BaseModel):
    """Response after creating a Rapid Fire match."""
    match_id: uuid.UUID
    total_rounds: int = 5
    time_per_round: int = 120
    messages_per_round: int = 5
    message: str = "Rapid Fire: 5 мини-раундов по 2 минуты!"


class GauntletCreateRequest(BaseModel):
    """Request to create a Gauntlet run."""
    total_duels: int = Field(default=3, ge=3, le=5)


class GauntletCreateResponse(BaseModel):
    """Response after creating a Gauntlet run."""
    run_id: uuid.UUID
    total_duels: int
    base_difficulty: str
    cooldown_hours: int = 6
    message: str = "Испытание: серия дуэлей с нарастающей сложностью!"


class GauntletCooldownResponse(BaseModel):
    """Gauntlet cooldown status."""
    on_cooldown: bool
    seconds_remaining: int = 0


class TeamCreateRequest(BaseModel):
    """Request to create a Team 2v2 battle."""
    partner_id: uuid.UUID


class TeamCreateResponse(BaseModel):
    """Response after creating a Team 2v2 battle."""
    team_id: uuid.UUID
    player1_id: uuid.UUID
    player2_id: uuid.UUID
    message: str = "Командная битва 2v2: оба продают, AI клиенты — разные!"


class RapidFireResultResponse(BaseModel):
    """Rapid Fire match result."""
    match_id: uuid.UUID
    total_score: float
    normalized_score: float
    mini_scores: list[dict] = Field(default_factory=list)
    archetypes: list[str] = Field(default_factory=list)
    rating_delta: float = 0.0
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class GauntletResultResponse(BaseModel):
    """Gauntlet run result."""
    run_id: uuid.UUID
    total_score: float
    completed_duels: int
    total_duels: int
    losses: int
    is_eliminated: bool
    scores: list[float] = Field(default_factory=list)
    difficulties: list[str] = Field(default_factory=list)
    rating_bonus: float = 0.0
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Content→Arena PR-4: characters available in /pvp lobby
# ---------------------------------------------------------------------------


class AvailableCharacter(BaseModel):
    """One pickable client preset for a PvP/PvE duel.

    Represents a row from ``custom_characters`` filtered by visibility
    rules (own + ``is_shared=true``). The frontend renders these as
    cards in the matchmaking screen so the player can pick a specific
    persona to face instead of getting a random archetype.
    """

    id: uuid.UUID
    name: str
    archetype: str
    profession: str | None = None
    difficulty: int = 5
    description: str | None = None
    is_own: bool = Field(default=False, description="True if this preset belongs to the requesting user")
    is_shared: bool = Field(default=False, description="True if visible to others via share")
    play_count: int = 0
    avg_score: int | None = None

    model_config = {"from_attributes": True}


class AvailableCharactersResponse(BaseModel):
    own: list[AvailableCharacter] = Field(default_factory=list)
    shared: list[AvailableCharacter] = Field(default_factory=list)
    total: int = 0
