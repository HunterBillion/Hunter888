"""XP and Season Points logging (DOC_15)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class XPLog(Base):
    """Per-award XP tracking for analytics and anti-cheat."""
    __tablename__ = "xp_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # training_session, pvp_win, achievement, checkpoint, etc.
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)  # prestige/streak multiplier
    season_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # SP earned
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Season Points conversion rates (DOC_15)
SP_RATES: dict[str, int] = {
    "training_session": 10,
    "pvp_win": 15,
    "pvp_loss": 5,
    "knowledge_quiz": 8,
    "daily_goal": 5,
    "weekly_goal": 20,
    "monthly_goal": 50,
    "achievement": 10,      # base, multiplied by rarity
    "checkpoint": 10,
    "tournament": 30,
}

# Daily XP soft-cap (DOC_15)
DAILY_XP_SOFT_CAP = 1500  # After this: 50% multiplier on additional XP

# Prestige constants
MAX_PRESTIGE_LEVEL = 5
PRESTIGE_XP_BONUS = 0.1  # +10% per prestige level

# Season Pass: 30 tiers, ~100 SP per tier
SEASON_PASS_TIERS = 30
SP_PER_TIER = 100

# Hunter Score title bands
HUNTER_SCORE_TITLES: dict[str, tuple[float, float]] = {
    "Рекрут": (0, 19.9),
    "Стажёр": (20, 39.9),
    "Специалист": (40, 59.9),
    "Профессионал": (60, 74.9),
    "Эксперт": (75, 89.9),
    "Легенда": (90, 100),
}


def get_hunter_title(score: float) -> str:
    """Get Russian title for Hunter Score value."""
    for title, (lo, hi) in HUNTER_SCORE_TITLES.items():
        if lo <= score <= hi:
            return title
    return "Рекрут"
