"""PvP Duel models (Agent 8 — Tournament / PvP Battle).

Data models:
- PvPDuel: individual duel between two managers
- PvPRating: Glicko-2 rating per user (separate from reputation)
- PvPMatchQueue: matchmaking queue entry
- AntiCheatLog: anti-cheat detection log
- PvPSeason: seasonal reset data

Glicko-2 parameters: rating (r=1500), deviation (RD=350), volatility (σ=0.06).
PvP rank tiers: Bronze < 1400, Silver 1400-1700, Gold 1700-2000, Platinum 2000-2300, Diamond 2300+.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DuelStatus(str, enum.Enum):
    """Lifecycle of a PvP duel."""
    pending = "pending"            # Matched, waiting for both to connect
    round_1 = "round_1"           # First round in progress
    swap = "swap"                  # Role swap interval
    round_2 = "round_2"           # Second round in progress
    judging = "judging"            # AI judge evaluating
    completed = "completed"        # Finished, scores assigned
    cancelled = "cancelled"        # One player disconnected / timeout
    disputed = "disputed"          # Under manual review


class MatchQueueStatus(str, enum.Enum):
    """Player's state in the matchmaking queue."""
    waiting = "waiting"
    matched = "matched"
    expired = "expired"
    cancelled = "cancelled"


class AntiCheatCheckType(str, enum.Enum):
    """Three-level anti-cheat system."""
    statistical = "statistical"      # Level 1: score deviation analysis
    behavioral = "behavioral"        # Level 2: ML pattern analysis
    ai_detector = "ai_detector"      # Level 3: text perplexity + burstiness
    latency = "latency"              # Level 3+: response latency analysis
    semantic = "semantic"            # Level 3+: vocabulary complexity jump


class AntiCheatAction(str, enum.Enum):
    """Action taken when anti-cheat flags a player."""
    none = "none"
    flag_review = "flag_review"         # Increase monitoring
    temp_ban_24h = "temp_ban_24h"       # Temporary ban
    rating_freeze = "rating_freeze"     # Freeze rating pending review
    rating_penalty = "rating_penalty"   # Rating deduction
    disqualification = "disqualification"  # Manual-only after review


class PvPRankTier(str, enum.Enum):
    """Competitive rank tiers (separate from reputation tiers)."""
    bronze = "bronze"        # < 1400
    silver = "silver"        # 1400-1700
    gold = "gold"            # 1700-2000
    platinum = "platinum"    # 2000-2300
    diamond = "diamond"      # 2300+
    unranked = "unranked"    # < 10 placement matches


class DuelDifficulty(str, enum.Enum):
    """Difficulty tier for the CLIENT role brief."""
    easy = "easy"            # ×1.0 — cooperative client, few objections
    medium = "medium"        # ×1.3 — skeptic, comparisons, questions
    hard = "hard"            # ×1.6 — aggressive, threats, manipulation


# Tier boundaries
RANK_TIER_BOUNDARIES: dict[PvPRankTier, tuple[int, int]] = {
    PvPRankTier.bronze: (0, 1399),
    PvPRankTier.silver: (1400, 1699),
    PvPRankTier.gold: (1700, 1999),
    PvPRankTier.platinum: (2000, 2299),
    PvPRankTier.diamond: (2300, 3000),
}

# Difficulty multipliers for acting score
DIFFICULTY_MULTIPLIERS: dict[DuelDifficulty, float] = {
    DuelDifficulty.easy: 1.0,
    DuelDifficulty.medium: 1.3,
    DuelDifficulty.hard: 1.6,
}

# Tier display names (Russian)
RANK_DISPLAY_NAMES: dict[PvPRankTier, str] = {
    PvPRankTier.unranked: "Без ранга",
    PvPRankTier.bronze: "Бронза",
    PvPRankTier.silver: "Серебро",
    PvPRankTier.gold: "Золото",
    PvPRankTier.platinum: "Платина",
    PvPRankTier.diamond: "Алмаз",
}


def rank_from_rating(rating: float, placement_done: bool) -> PvPRankTier:
    """Determine rank tier from Glicko-2 rating."""
    if not placement_done:
        return PvPRankTier.unranked
    for tier, (lo, hi) in RANK_TIER_BOUNDARIES.items():
        if lo <= rating <= hi:
            return tier
    return PvPRankTier.diamond if rating > 3000 else PvPRankTier.bronze


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class PvPDuel(Base):
    """A single PvP duel between two managers.

    Each duel has 2 rounds (role swap):
    - Round 1: player1 SELLS, player2 is CLIENT
    - Round 2: player2 SELLS, player1 is CLIENT
    Winner = highest total (selling_score + acting_score across both rounds).
    """
    __tablename__ = "pvp_duels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    player1_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    player2_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id"), nullable=True
    )

    status: Mapped[DuelStatus] = mapped_column(
        Enum(DuelStatus), nullable=False, default=DuelStatus.pending
    )
    difficulty: Mapped[DuelDifficulty] = mapped_column(
        Enum(DuelDifficulty), nullable=False, default=DuelDifficulty.medium
    )

    # Round data — separate JSONB per round
    round_1_data: Mapped[dict | None] = mapped_column(JSONB)
    # {seller_id, client_id, seller_score, client_score, duration_seconds, key_moments: [...]}
    round_2_data: Mapped[dict | None] = mapped_column(JSONB)

    # Final aggregated scores
    player1_total: Mapped[float] = mapped_column(Float, default=0.0)
    player2_total: Mapped[float] = mapped_column(Float, default=0.0)
    winner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    is_draw: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timing
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    round_number: Mapped[int] = mapped_column(Integer, default=1)  # Current round

    # Anti-cheat
    anti_cheat_flags: Mapped[list[dict] | None] = mapped_column(JSONB)
    # [{check_type, player_id, score, flagged, details}]

    # Replay
    replay_url: Mapped[str | None] = mapped_column(String(500))

    # PvE flag (duel vs AI bot when queue is empty)
    is_pve: Mapped[bool] = mapped_column(Boolean, default=False)

    # Glicko-2 rating changes applied
    rating_change_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    player1_rating_delta: Mapped[float] = mapped_column(Float, default=0.0)
    player2_rating_delta: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PvPRating(Base):
    """Glicko-2 rating state per user.

    Parameters:
    - rating (r): starts at 1500, range 0-3000
    - rd: rating deviation (uncertainty), starts at 350, decreases with games
    - volatility (σ): consistency measure, starts at 0.06
    - RD decay: +15/week inactive, cap at 250
    """
    __tablename__ = "pvp_ratings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False, index=True
    )

    # Glicko-2 core parameters
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=1500.0)
    rd: Mapped[float] = mapped_column(Float, nullable=False, default=350.0)
    volatility: Mapped[float] = mapped_column(Float, nullable=False, default=0.06)

    # Rank
    rank_tier: Mapped[PvPRankTier] = mapped_column(
        Enum(PvPRankTier), nullable=False, default=PvPRankTier.unranked
    )

    # Statistics
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    total_duels: Mapped[int] = mapped_column(Integer, default=0)
    placement_done: Mapped[bool] = mapped_column(Boolean, default=False)
    placement_count: Mapped[int] = mapped_column(Integer, default=0)  # out of 10

    # Peak tracking
    peak_rating: Mapped[float] = mapped_column(Float, default=1500.0)
    peak_tier: Mapped[PvPRankTier] = mapped_column(
        Enum(PvPRankTier), nullable=False, default=PvPRankTier.unranked
    )

    # Win/loss streak
    current_streak: Mapped[int] = mapped_column(Integer, default=0)  # +N win, -N loss
    best_streak: Mapped[int] = mapped_column(Integer, default=0)

    # Season
    season_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pvp_seasons.id", use_alter=True), nullable=True
    )

    # Timestamps
    last_played: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_rd_decay: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PvPMatchQueue(Base):
    """Matchmaking queue entry.

    Logic: find opponent where |r1-r2| < 200 + (RD1+RD2)/2.
    If no match in 90s → offer PvE duel.
    """
    __tablename__ = "pvp_match_queue"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=1500.0)
    rd: Mapped[float] = mapped_column(Float, nullable=False, default=350.0)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[MatchQueueStatus] = mapped_column(
        Enum(MatchQueueStatus), nullable=False, default=MatchQueueStatus.waiting
    )
    # Range expands over time: base_range + (seconds_waited * expansion_rate)
    expanded_range: Mapped[float] = mapped_column(Float, default=0.0)
    matched_with: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    duel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class AntiCheatLog(Base):
    """Anti-cheat detection log entry.

    Level 1 (statistical): score deviation, unnatural win streaks
    Level 2 (behavioral): scripts, auto-responses, copy-paste
    Level 3 (ai_detector): perplexity + burstiness + latency + semantic
    """
    __tablename__ = "pvp_anti_cheat_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    duel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pvp_duels.id"), nullable=True, index=True
    )
    check_type: Mapped[AntiCheatCheckType] = mapped_column(
        Enum(AntiCheatCheckType), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 0.0-1.0 confidence that cheating occurred
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    action_taken: Mapped[AntiCheatAction] = mapped_column(
        Enum(AntiCheatAction), nullable=False, default=AntiCheatAction.none
    )
    details: Mapped[dict | None] = mapped_column(JSONB)
    # {metrics: {...}, thresholds: {...}, raw_signals: [...]}

    # Resolution
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(String(50))
    # "clean" | "cheating_confirmed" | "false_positive"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PvPSeason(Base):
    """Seasonal PvP data. Monthly soft reset.

    Reset formula: r_new = r * 0.75 + 1500 * 0.25, RD = 150.
    """
    __tablename__ = "pvp_seasons"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # e.g. "Season 1 — March 2026"
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Rewards per tier at season end
    rewards: Mapped[dict | None] = mapped_column(JSONB)
    # {diamond: {xp: 500, badge: "..."}, platinum: {xp: 300, ...}, ...}

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
