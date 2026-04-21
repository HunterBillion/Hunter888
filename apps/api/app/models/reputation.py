"""Reputation system model (Agent 5 — Gamification upgrade).

ManagerReputation is a cross-cutting entity that influences:
- Gamification (badges, tier display)
- Emotion engine (initial emotion weight shifting)
- Scenario engine (min_difficulty by tier)
- Game Director (client generation warmth)

Reputation score: 0-100, calculated via EMA (α=0.15) from session scores.
Decay: -2/day after 7 days of inactivity.
Active impact: bad session (score < 30) = -3, good (60-80) = +1, excellent (80+) = +2.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReputationTier(str, enum.Enum):
    """5 reputation tiers mapped to manager progression in BFL domain."""
    trainee = "trainee"          # Стажёр     0-20
    manager = "manager"          # Менеджер   21-40
    senior = "senior"            # Старший    41-60
    expert = "expert"            # Эксперт    61-80
    hunter = "hunter"            # Хантер     81-100


# Tier boundaries: (min_score, max_score)
TIER_BOUNDARIES: dict[ReputationTier, tuple[int, int]] = {
    ReputationTier.trainee: (0, 20),
    ReputationTier.manager: (21, 40),
    ReputationTier.senior: (41, 60),
    ReputationTier.expert: (61, 80),
    ReputationTier.hunter: (81, 100),
}

# Tier → display name (Russian)
TIER_DISPLAY_NAMES: dict[ReputationTier, str] = {
    ReputationTier.trainee: "Стажёр",
    ReputationTier.manager: "Менеджер",
    ReputationTier.senior: "Старший менеджер",
    ReputationTier.expert: "Эксперт",
    ReputationTier.hunter: "Хантер",
}

# Tier → minimum scenario difficulty (for scenario_engine integration)
TIER_MIN_DIFFICULTY: dict[ReputationTier, int] = {
    ReputationTier.trainee: 1,
    ReputationTier.manager: 2,
    ReputationTier.senior: 3,
    ReputationTier.expert: 5,
    ReputationTier.hunter: 6,
}

# Tier → client warmth modifier (DOC_03 §26: affects initial PAD.Pleasure)
TIER_CLIENT_WARMTH: dict[ReputationTier, float] = {
    ReputationTier.trainee: 0.3,     # Warm start — forgiving
    ReputationTier.manager: 0.1,     # Standard
    ReputationTier.senior: 0.0,      # Neutral
    ReputationTier.expert: -0.1,     # Cold start
    ReputationTier.hunter: -0.2,     # Hostile start — frequent traps
}

# EMA smoothing parameters for reputation score
REPUTATION_EMA_ALPHA = 0.15     # new_score = 0.15 × session + 0.85 × old
REPUTATION_PASSIVE_DECAY = -2   # per day after 7 days inactivity
REPUTATION_DEFAULT_SCORE = 50   # Starting score = Senior Manager tier

# Tier → badge icon
TIER_BADGES: dict[ReputationTier, str] = {
    ReputationTier.trainee: "🟢",
    ReputationTier.manager: "🔵",
    ReputationTier.senior: "🟣",
    ReputationTier.expert: "🟠",
    ReputationTier.hunter: "🔴",
}


class ManagerReputation(Base):
    """Persistent reputation state for each manager.

    Fields:
    - score: current reputation score 0-100
    - tier: calculated tier enum
    - ema_state: internal EMA accumulator (used by reputation service)
    - sessions_rated: total sessions that contributed to reputation
    - last_session_at: timestamp of last completed session (for decay calculation)
    - last_decay_at: timestamp of last decay application
    - history: JSONB array of recent reputation changes [{delta, reason, timestamp}, ...]
    """
    __tablename__ = "manager_reputations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True
    )
    score: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)
    tier: Mapped[ReputationTier] = mapped_column(
        Enum(ReputationTier), nullable=False, default=ReputationTier.senior
    )
    ema_state: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)
    sessions_rated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_session_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_decay_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    peak_score: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)
    peak_tier: Mapped[ReputationTier] = mapped_column(
        Enum(ReputationTier), nullable=False, default=ReputationTier.senior
    )
    history: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
