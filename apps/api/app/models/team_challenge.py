"""Team Challenge persistence models — S3-01.

Replaces the in-memory _challenges dict with proper PostgreSQL storage.
Two tables:
  - team_challenges: challenge metadata (who, what, when, status)
  - team_challenge_progress: per-team score snapshots (updated on session complete)
"""

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ChallengeStatus(str, PyEnum):
    pending = "pending"
    active = "active"
    completed = "completed"
    expired = "expired"
    cancelled = "cancelled"


class ChallengeType(str, PyEnum):
    score_avg = "score_avg"          # Average score comparison
    completion_rate = "completion_rate"  # Who completes more sessions
    streak = "streak"                # Longest combined streak


class TeamChallenge(Base):
    """Persistent team-vs-team challenge."""

    __tablename__ = "team_challenges"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    team_a_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_b_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    challenge_type: Mapped[str] = mapped_column(
        String(30), default=ChallengeType.score_avg.value, nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), default=ChallengeStatus.active.value, nullable=False,
        index=True,
    )
    scenario_code: Mapped[str | None] = mapped_column(String(100))
    bonus_xp: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    winner_team_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(),
    )

    # Relationships
    creator = relationship("User", foreign_keys=[created_by], lazy="selectin")
    team_a = relationship("Team", foreign_keys=[team_a_id], lazy="selectin")
    team_b = relationship("Team", foreign_keys=[team_b_id], lazy="selectin")
    winner_team = relationship("Team", foreign_keys=[winner_team_id], lazy="selectin")
    progress_entries: Mapped[list["TeamChallengeProgress"]] = relationship(
        back_populates="challenge", cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_team_challenges_teams", "team_a_id", "team_b_id"),
        Index("ix_team_challenges_status_deadline", "status", "deadline"),
    )


class TeamChallengeProgress(Base):
    """Per-team progress snapshot within a challenge."""

    __tablename__ = "team_challenge_progress"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("team_challenges.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    completed_sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_members: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    challenge: Mapped["TeamChallenge"] = relationship(back_populates="progress_entries")

    __table_args__ = (
        UniqueConstraint("challenge_id", "team_id", name="uq_challenge_team"),
        Index("ix_tcp_challenge_team", "challenge_id", "team_id"),
    )
