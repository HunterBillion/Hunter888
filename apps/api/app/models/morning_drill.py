"""Morning warm-up session model.

Persists the result of a completed 3-5 question morning drill. One row
per completed warm-up. See migration 20260420_001 for table shape and
rationale for the split between `completed_at` (exact moment) and `date`
(fast index key for daily-goal lookup).
"""

from __future__ import annotations

import uuid
from datetime import date as date_type, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MorningDrillSession(Base):
    """One completed morning warm-up run."""

    __tablename__ = "morning_drill_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Opaque id returned by `GET /morning-drill` — kept for debugging /
    # cross-referencing client logs. NOT a primary key.
    drill_session_id: Mapped[str] = mapped_column(String(64), nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_answers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # [{question_id, kind, answer, ok, matched_keywords}]
    # Stored so the review screen can re-show the user what they wrote.
    answers: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list
    )

    # Populated on INSERT = completed_at::date. Indexed with user_id for the
    # daily_warmup goal lookup. We denormalise instead of an expression index
    # so the query planner uses a plain btree scan — cheaper and portable.
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
