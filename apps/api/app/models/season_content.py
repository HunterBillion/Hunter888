"""Content Seasons & Chapters — narrative structure for 18-month retention.

Each season (1 quarter) = new business context (crisis, expansion, etc.)
Each chapter (1 month) = narrative arc with specific scenarios + challenges.
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
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ContentSeason(Base):
    """Quarterly content season with themed business scenario."""
    __tablename__ = "content_seasons"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True,
    )  # "season_1", "season_2"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    theme: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )  # crisis_management, market_expansion, team_scaling, restructuring
    start_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    end_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    chapter_count: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    scenario_pool: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )  # scenario_ids available this season
    special_archetypes: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )  # season-exclusive archetypes
    rewards: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict,
    )  # {completion_xp, title, border, ...}
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )


class SeasonChapter(Base):
    """Monthly chapter within a season — narrative arc with missions."""
    __tablename__ = "season_chapters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    season_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_seasons.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    narrative_intro: Mapped[str] = mapped_column(
        Text, nullable=False, default="",
    )  # Story text shown to user when chapter unlocks
    unlocks_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )  # Calendar-gated opening
    scenario_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )
    challenge_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
