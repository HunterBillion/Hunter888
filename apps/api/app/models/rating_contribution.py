"""Unified tournament-points ledger.

Every activity that should count toward tournaments / weekly leaderboards writes
one row here: Training session completed, PvP duel, Knowledge quiz, Story.

Keeps the source-of-truth for competitive rating separate from personal XP.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RatingSource(str, enum.Enum):
    training = "training"
    pvp = "pvp"
    knowledge = "knowledge"
    story = "story"


class RatingContribution(Base):
    """A single grain of "tournament points" earned by a user.

    One row per activity completion. Aggregated per (user, week) and per
    tournament to compute rankings and leaderboards.
    """

    __tablename__ = "rating_contributions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source: Mapped[RatingSource] = mapped_column(
        Enum(RatingSource, name="rating_source"),
        nullable=False,
    )
    # FK to the underlying entity (training_sessions / pvp_duels /
    # knowledge_quiz_sessions / client_stories). Not a real FK — we keep it
    # soft to tolerate cross-table polymorphism.
    source_ref_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ISO-week Monday for fast GROUP BY — precomputed at insert time.
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    earned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True,
    )

    tournament_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Breakdown of the TP calculation (for audit & debugging).
    # e.g. {"score_total": 78, "difficulty": 5, "formula": "score*0.8 + diff*2"}
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        # Idempotency: one contribution per activity completion, ever.
        UniqueConstraint("source", "source_ref_id", name="uq_rating_contrib_source"),
        # Fast weekly aggregate per user
        Index("ix_rating_contrib_user_week", "user_id", "week_start"),
    )
