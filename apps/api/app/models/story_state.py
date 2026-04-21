"""UserStoryState — persistent story arc progression per user.

Tracks the 12-chapter 'Путь Охотника' narrative. Separate from ContentSeason
(quarterly rotating content). This is the permanent progression.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserStoryState(Base):
    """Per-user story arc progression through 12 chapters / 4 epochs."""

    __tablename__ = "user_story_states"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_story_states_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Current position in the story
    current_chapter: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
    )  # 1-12
    current_epoch: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
    )  # 1-4
    chapter_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    # Progress within current chapter
    chapter_sessions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )  # sessions completed in current chapter
    chapter_avg_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
    )  # running average score
    chapter_best_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
    )

    # Specialization path (chosen at key narrative forks)
    specialization: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None,
    )  # "aggressive_closer" | "soft_consultant" | None

    # Epoch completion timestamps
    epoch_1_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    epoch_2_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    epoch_3_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    epoch_4_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Narrative state
    last_narrative_trigger: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
    )
    flashback_shown: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
