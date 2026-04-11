"""Manager Wiki — persistent knowledge base per manager (Karpathy LLM Wiki pattern).

Each manager accumulates a personal wiki built from training session transcripts.
The LLM analyzes sessions, discovers patterns, and maintains structured pages
of insights, weaknesses, techniques, and recommendations.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class WikiStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    archived = "archived"


class WikiAction(str, enum.Enum):
    ingest_session = "ingest_session"
    daily_synthesis = "daily_synthesis"
    weekly_synthesis = "weekly_synthesis"
    monthly_review = "monthly_review"
    lint_pass = "lint_pass"
    manual_edit = "manual_edit"


class WikiPageType(str, enum.Enum):
    overview = "overview"
    pattern = "pattern"
    insight = "insight"
    recommendation = "recommendation"
    benchmark = "benchmark"
    log = "log"


class PatternCategory(str, enum.Enum):
    weakness = "weakness"
    strength = "strength"
    quirk = "quirk"
    misconception = "misconception"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ManagerWiki(Base):
    """Root wiki record per manager — one per user."""

    __tablename__ = "manager_wikis"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    manager_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active"
    )
    pages_count: Mapped[int] = mapped_column(Integer, default=0)
    sessions_ingested: Mapped[int] = mapped_column(Integer, default=0)
    patterns_discovered: Mapped[int] = mapped_column(Integer, default=0)
    last_ingest_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_daily_synthesis_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_weekly_synthesis_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_scheduled_update_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WikiPage(Base):
    """Individual wiki page (markdown content, versioned)."""

    __tablename__ = "wiki_pages"
    __table_args__ = (
        UniqueConstraint("wiki_id", "page_path", name="uq_wiki_pages_wiki_path"),
        Index("ix_wiki_pages_wiki_id_page_path", "wiki_id", "page_path"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wiki_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("manager_wikis.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_path: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # e.g. "patterns/WEAKNESS_MATRIX"
    content: Mapped[str] = mapped_column(Text, nullable=False)  # markdown
    version: Mapped[int] = mapped_column(Integer, default=1)
    source_sessions: Mapped[dict] = mapped_column(
        JSONB, default=list
    )  # list of session_id strings
    page_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    tags: Mapped[dict] = mapped_column(JSONB, default=list)  # list of strings
    # Phase 2: pgvector embedding for semantic wiki search
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WikiUpdateLog(Base):
    """Audit log of every wiki update action."""

    __tablename__ = "wiki_update_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wiki_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("manager_wikis.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    pages_modified: Mapped[int] = mapped_column(Integer, default=0)
    pages_created: Mapped[int] = mapped_column(Integer, default=0)
    patterns_discovered: Mapped[dict] = mapped_column(
        JSONB, default=list
    )  # list of pattern dicts
    triggered_by_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)


class ManagerPattern(Base):
    """Discovered behavioral pattern for a manager."""

    __tablename__ = "manager_patterns"
    __table_args__ = (
        UniqueConstraint(
            "manager_id", "pattern_code", name="uq_manager_patterns_code"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    manager_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pattern_code: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # e.g. "rush_price", "avoid_skeptic"
    category: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    sessions_in_pattern: Mapped[int] = mapped_column(Integer, default=0)
    impact_on_score_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    archetype_filter: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    mitigation_technique: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # after seeing 3+ times


class ManagerTechnique(Base):
    """Effective technique discovered from training sessions."""

    __tablename__ = "manager_techniques"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    manager_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    technique_code: Mapped[str] = mapped_column(String(100), nullable=False)
    technique_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    applicable_to_archetype: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    success_rate: Mapped[float] = mapped_column(Float, default=0.0)
    how_to_apply: Mapped[str | None] = mapped_column(Text, nullable=True)
    exemplar_sessions: Mapped[dict] = mapped_column(
        JSONB, default=list
    )  # list of session_id strings
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
