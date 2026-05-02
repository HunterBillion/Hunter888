"""Weekly League models — social pressure engine.

Tables:
  - weekly_league_groups: one group per team+tier per week
  - weekly_league_membership: per-user league state
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WeeklyLeagueGroup(Base):
    """A league group for one week: ~10-15 users from same team, same tier."""
    __tablename__ = "weekly_league_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    week_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
    )
    league_tier: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )  # 0=Stажёр, 1=Специалист, 2=Профессионал, 3=Эксперт, 4=Легенда
    user_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )
    standings: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )  # [{user_id, full_name, weekly_xp, rank, avatar_url}]
    finalized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("week_start", "team_id", "league_tier", name="uq_league_group_week_team_tier"),
    )


class WeeklyLeagueMembership(Base):
    """Per-user league state tracking."""
    __tablename__ = "weekly_league_membership"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    current_tier: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )  # 0-4
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("weekly_league_groups.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    weekly_xp: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    rank_in_group: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    promotion_history: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )  # [{week, old_tier, new_tier, rank, action: "promoted"|"demoted"|"stayed"}]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
