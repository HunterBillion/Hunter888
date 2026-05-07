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
    Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func,
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
    llm_perplexity = "llm_perplexity"  # Level 3++: LLM-based perplexity scoring
    multi_account = "multi_account"    # Level 4: IP/UA/behavioral fingerprint


class AntiCheatAction(str, enum.Enum):
    """Action taken when anti-cheat flags a player."""
    none = "none"
    flag_review = "flag_review"         # Increase monitoring
    temp_ban_24h = "temp_ban_24h"       # Temporary ban
    rating_freeze = "rating_freeze"     # Freeze rating pending review
    rating_penalty = "rating_penalty"   # Rating deduction
    disqualification = "disqualification"  # Manual-only after review


class PvPRankTier(str, enum.Enum):
    """Competitive rank tiers: 8 tiers × 3 divisions = 24 ranks (DOC_13)."""
    # Iron (0-999)
    iron_3 = "iron_3"
    iron_2 = "iron_2"
    iron_1 = "iron_1"
    # Bronze (1000-1399)
    bronze_3 = "bronze_3"
    bronze_2 = "bronze_2"
    bronze_1 = "bronze_1"
    # Silver (1400-1699)
    silver_3 = "silver_3"
    silver_2 = "silver_2"
    silver_1 = "silver_1"
    # Gold (1700-1999)
    gold_3 = "gold_3"
    gold_2 = "gold_2"
    gold_1 = "gold_1"
    # Platinum (2000-2299)
    platinum_3 = "platinum_3"
    platinum_2 = "platinum_2"
    platinum_1 = "platinum_1"
    # Diamond (2300-2599)
    diamond_3 = "diamond_3"
    diamond_2 = "diamond_2"
    diamond_1 = "diamond_1"
    # Master (2600-2899)
    master_3 = "master_3"
    master_2 = "master_2"
    master_1 = "master_1"
    # Grandmaster (2900+)
    grandmaster = "grandmaster"
    # Unranked
    unranked = "unranked"
    # Legacy aliases (backward compat)
    bronze = "bronze_2"
    silver = "silver_2"
    gold = "gold_2"
    platinum = "platinum_2"
    diamond = "diamond_2"


class DuelDifficulty(str, enum.Enum):
    """Difficulty tier for the CLIENT role brief."""
    easy = "easy"            # ×1.0 — cooperative client, few objections
    medium = "medium"        # ×1.3 — skeptic, comparisons, questions
    hard = "hard"            # ×1.6 — aggressive, threats, manipulation


class RatingType(str, enum.Enum):
    """Rating type — separate rating tracks."""
    training_duel = "training_duel"       # Original: duel-based sales training
    knowledge_arena = "knowledge_arena"   # 127-FZ knowledge PvP arena
    team_battle = "team_battle"           # DOC_09: Team 2v2 rating
    rapid_fire = "rapid_fire"             # DOC_09: Rapid Fire rating


class DuelMode(str, enum.Enum):
    """PvP game modes (DOC_09: 1 → 4 modes)."""
    classic = "classic"       # Standard 2-round duel with role swap
    team2v2 = "team2v2"       # 2v2 team battle
    rapid = "rapid"           # 5 mini-rounds × 2 min, seller only
    gauntlet = "gauntlet"     # 3-5 serial duels with progressive difficulty


# Tier boundaries: 24 ranks (DOC_13)
RANK_TIER_BOUNDARIES: dict[PvPRankTier, tuple[int, int]] = {
    PvPRankTier.iron_3: (0, 332), PvPRankTier.iron_2: (333, 666), PvPRankTier.iron_1: (667, 999),
    PvPRankTier.bronze_3: (1000, 1132), PvPRankTier.bronze_2: (1133, 1266), PvPRankTier.bronze_1: (1267, 1399),
    PvPRankTier.silver_3: (1400, 1499), PvPRankTier.silver_2: (1500, 1599), PvPRankTier.silver_1: (1600, 1699),
    PvPRankTier.gold_3: (1700, 1799), PvPRankTier.gold_2: (1800, 1899), PvPRankTier.gold_1: (1900, 1999),
    PvPRankTier.platinum_3: (2000, 2099), PvPRankTier.platinum_2: (2100, 2199), PvPRankTier.platinum_1: (2200, 2299),
    PvPRankTier.diamond_3: (2300, 2399), PvPRankTier.diamond_2: (2400, 2499), PvPRankTier.diamond_1: (2500, 2599),
    PvPRankTier.master_3: (2600, 2699), PvPRankTier.master_2: (2700, 2799), PvPRankTier.master_1: (2800, 2899),
    PvPRankTier.grandmaster: (2900, 9999),
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
    PvPRankTier.iron_3: "Железо III", PvPRankTier.iron_2: "Железо II", PvPRankTier.iron_1: "Железо I",
    PvPRankTier.bronze_3: "Бронза III", PvPRankTier.bronze_2: "Бронза II", PvPRankTier.bronze_1: "Бронза I",
    PvPRankTier.silver_3: "Серебро III", PvPRankTier.silver_2: "Серебро II", PvPRankTier.silver_1: "Серебро I",
    PvPRankTier.gold_3: "Золото III", PvPRankTier.gold_2: "Золото II", PvPRankTier.gold_1: "Золото I",
    PvPRankTier.platinum_3: "Платина III", PvPRankTier.platinum_2: "Платина II", PvPRankTier.platinum_1: "Платина I",
    PvPRankTier.diamond_3: "Алмаз III", PvPRankTier.diamond_2: "Алмаз II", PvPRankTier.diamond_1: "Алмаз I",
    PvPRankTier.master_3: "Мастер III", PvPRankTier.master_2: "Мастер II", PvPRankTier.master_1: "Мастер I",
    PvPRankTier.grandmaster: "Грандмастер",
}

# Tier name → (floor, ceiling) for promotion/demotion checks
TIER_FLOORS: dict[str, int] = {
    "iron": 0, "bronze": 1000, "silver": 1400, "gold": 1700,
    "platinum": 2000, "diamond": 2300, "master": 2600, "grandmaster": 2900,
}


def rank_from_rating(rating: float, placement_done: bool) -> PvPRankTier:
    """Determine rank tier from Glicko-2 rating (DOC_13: 24 ranks)."""
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
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player2_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Content→Arena PR-2 (2026-05-01) — link to TZ-3 publish flow.
    # ``scenario_template_id`` is the template the matchmaker picked; the
    # ``current_published_version_id`` of that template at duel-creation
    # time is captured in ``scenario_version_id`` so the duel renders the
    # immutable snapshot even if the template later points elsewhere
    # (TZ-3 §8 invariant 4 — ScenarioVersion is the source of truth).
    # Both columns are nullable: legacy duels (created before this
    # migration) have NULL and fall back to the legacy ``scenarios`` row
    # picked via ``_load_duel_context``.
    scenario_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scenario_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    scenario_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scenario_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # DOC_14: archetype used in CLIENT role (for cross-recommendations)
    archetype_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[DuelStatus] = mapped_column(
        Enum(DuelStatus), nullable=False, default=DuelStatus.pending
    )
    mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="classic", server_default="classic",
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
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
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
    # DOC_10: PvE mode type (standard/ladder/boss/training/mirror)
    pve_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    pve_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Glicko-2 rating changes applied
    rating_change_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    player1_rating_delta: Mapped[float] = mapped_column(Float, default=0.0)
    player2_rating_delta: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Phase A (2026-04-20): persistent post-match analytics — previously the
    # judge computed these per-round and we re-derived on replay load. Having
    # them as first-class columns unblocks rapid "похожие дуэли" queries.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    turning_point: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Phase 1 (Roadmap §6) ConversationCompletionPolicy — unified terminal
    # contract shared with TrainingSession. Values are from the
    # ``TerminalOutcome``/``TerminalReason`` enums in
    # ``services.completion_policy``. PvP uses a subset
    # (``pvp_win``/``pvp_loss``/``pvp_draw``/``pvp_abandoned``).
    terminal_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    terminal_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)


class PvPRating(Base):
    """Glicko-2 rating state per user.

    Parameters:
    - rating (r): starts at 1500, range 0-3000
    - rd: rating deviation (uncertainty), starts at 350, decreases with games
    - volatility (σ): consistency measure, starts at 0.06
    - RD decay: +15/week inactive, cap at 250
    """
    __tablename__ = "pvp_ratings"
    __table_args__ = (
        UniqueConstraint("user_id", "rating_type", name="uq_pvp_rating_user_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rating_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="training_duel",
    )  # "training_duel" | "knowledge_arena"

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
        UUID(as_uuid=True), ForeignKey("pvp_seasons.id", use_alter=True), nullable=True, index=True
    )

    # Timestamps
    last_played: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_rd_decay: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # DOC_13: Demotion protection
    demotion_shield_losses: Mapped[int] = mapped_column(Integer, default=0)
    demotion_warning_issued: Mapped[bool] = mapped_column(Boolean, default=False)
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
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
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
    matched_with: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    duel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pvp_duels.id", ondelete="SET NULL"), nullable=True, index=True
    )


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
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    duel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pvp_duels.id", ondelete="SET NULL"), nullable=True, index=True
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

    # Top-N leaderboard rewards (added 2026-05-07).
    # List of {rank: int, ap: int, badge?: str}. Coexists with `rewards`:
    # tier rewards = "what every Diamond gets", top_rewards = "what the
    # leaderboard top-N earn extra". Used by the /pvp slim hero banner
    # ("Сезон до 31 мая · топ-1 = 100 AP") and /pvp/leaderboard.
    top_rewards: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UserFingerprint(Base):
    """Device/network fingerprint for multi-account detection.

    Each login/session records IP, User-Agent, and optional browser fingerprint.
    Shared fingerprints across different user IDs flag potential multi-accounts.
    """
    __tablename__ = "user_fingerprints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), index=True)
    user_agent: Mapped[str | None] = mapped_column(String(500))
    ua_hash: Mapped[str | None] = mapped_column(String(32), index=True)
    # First 32 chars of SHA-256 of normalized UA for fast grouping
    browser_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    # Optional JS-collected fingerprint hash (canvas, webGL, etc.)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(30), default="login")
    # "login" | "duel_start" | "tournament_join"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# DOC_09: New PvP Mode Models
# ---------------------------------------------------------------------------

class PvPTeam(Base):
    """Team pairing for 2v2 Team Battle mode."""
    __tablename__ = "pvp_teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player1_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    player2_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    avg_rating: Mapped[float] = mapped_column(Float, nullable=False, default=1500.0)
    duel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("pvp_duels.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GauntletRun(Base):
    """Gauntlet series tracking (3-5 PvE duels with progressive difficulty)."""
    __tablename__ = "pvp_gauntlet_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    total_duels: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    completed_duels: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duel_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    scores: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    difficulties: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_bonus: Mapped[float | None] = mapped_column(Float, nullable=True)
    rd_bonus: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_eliminated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RapidFireMatch(Base):
    """Rapid Fire series tracking (5 mini-rounds x 2 min each)."""
    __tablename__ = "pvp_rapid_fire_matches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player1_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    player2_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    is_pve: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archetypes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    mini_scores: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    difficulty_progression: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    bonuses: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    rating_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# DOC_10: PvE Mode Models
# ---------------------------------------------------------------------------

class PvEMode(str, enum.Enum):
    """PvE game modes (DOC_10: 5 modes)."""
    standard = "standard"     # Standard bot (fallback from PvP queue)
    ladder = "ladder"         # Bot Ladder: 5 progressive bots
    boss = "boss"             # Boss Rush: 3 unique bosses
    training = "training"     # Training Match: with AI coach
    mirror = "mirror"         # Mirror Match: fight your own style


class PvELadderRun(Base):
    """Bot Ladder series (5 progressive PvE bots, DOC_10 §2.2)."""
    __tablename__ = "pve_ladder_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    current_bot_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bots_defeated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cumulative_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    bot_configs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    duel_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    all_defeated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    xp_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PvEBossRun(Base):
    """Boss Rush individual boss attempt (DOC_10 §2.3)."""
    __tablename__ = "pve_boss_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    boss_index: Mapped[int] = mapped_column(Integer, nullable=False)
    boss_type: Mapped[str] = mapped_column(String(50), nullable=False)
    duel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("pvp_duels.id", ondelete="SET NULL"), nullable=True, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_defeated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    special_mechanics_log: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# DOC_13: Promotion Series, Season Rewards, Arena Points
# ---------------------------------------------------------------------------

class PromotionSeries(Base):
    """BO3 promotion series for tier advancement (DOC_13)."""
    __tablename__ = "promotion_series"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rating_type: Mapped[str] = mapped_column(String(50), nullable=False)
    from_tier: Mapped[str] = mapped_column(String(30), nullable=False)
    to_tier: Mapped[str] = mapped_column(String(30), nullable=False)
    matches_played: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    duel_ids: Mapped[list] = mapped_column(JSONB, default=list)
    result: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "promoted" | "failed" | None
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SeasonReward(Base):
    """Season-end tier-based rewards (DOC_13)."""
    __tablename__ = "season_rewards"
    __table_args__ = (
        UniqueConstraint("season_id", "user_id", name="uq_season_reward_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pvp_seasons.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    final_rating: Mapped[float] = mapped_column(Float, nullable=False)
    final_tier: Mapped[str] = mapped_column(String(30), nullable=False)
    xp_reward: Mapped[int] = mapped_column(Integer, nullable=False)
    ap_reward: Mapped[int] = mapped_column(Integer, nullable=False)
    title_reward: Mapped[str | None] = mapped_column(String(200), nullable=True)
    border_reward: Mapped[str | None] = mapped_column(String(100), nullable=True)
    achievement_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    awarded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class APPurchase(Base):
    """Arena Points purchase history (DOC_13)."""
    __tablename__ = "ap_purchases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(50), nullable=False)
    item_id: Mapped[str] = mapped_column(String(100), nullable=False)
    cost_ap: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
