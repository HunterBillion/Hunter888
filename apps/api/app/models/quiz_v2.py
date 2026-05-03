"""ORM model for ``quiz_v2_answer_keys`` (Path A grader storage).

Mirrors ``LegalKnowledgeChunk`` review-lifecycle columns
(``knowledge_status``, ``is_active``, ``source``, ``original_confidence``,
``reviewed_by/at``) so the existing ``knowledge_review_policy.mark_reviewed``
state machine and ``KnowledgeReviewQueue`` UI can be reused without copy.

Design doc: ``docs/QUIZ_V2_ARENA_DESIGN.md`` §6.
Migration:  ``alembic/versions/20260503_001_quiz_v2_answer_keys.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class QuizV2AnswerKey(Base):
    """A pre-computed answer key for a quiz question generated from a chunk.

    Identity: ``(chunk_id, question_hash, team_id)`` — UNIQUE. ``team_id IS NULL``
    is the global baseline; non-NULL rows are per-team overrides (Q-NEW-4).
    """

    __tablename__ = "quiz_v2_answer_keys"
    __table_args__ = (
        UniqueConstraint(
            "chunk_id",
            "question_hash",
            "team_id",
            name="uq_quiz_v2_answer_keys_chunk_hash_team",
        ),
        CheckConstraint(
            "flavor IN ('factoid', 'strategic')",
            name="ck_quiz_v2_answer_keys_flavor",
        ),
        CheckConstraint(
            "match_strategy IN ('exact', 'synonyms', 'regex', 'keyword', 'embedding')",
            name="ck_quiz_v2_answer_keys_match_strategy",
        ),
        CheckConstraint(
            "knowledge_status IN ('actual', 'disputed', 'outdated', 'needs_review')",
            name="ck_quiz_v2_answer_keys_status",
        ),
        CheckConstraint(
            "source IN ('llm_backfill', 'admin_editor', 'seed_loader')",
            name="ck_quiz_v2_answer_keys_source",
        ),
        CheckConstraint(
            "original_confidence IS NULL OR (original_confidence >= 0 AND original_confidence <= 1)",
            name="ck_quiz_v2_answer_keys_confidence_bounds",
        ),
        Index(
            "ix_quiz_v2_answer_keys_lookup",
            "chunk_id",
            "question_hash",
            "team_id",
        ),
        Index(
            "ix_quiz_v2_answer_keys_chunk",
            "chunk_id",
        ),
        Index(
            "ix_quiz_v2_answer_keys_review_queue",
            "knowledge_status",
            postgresql_where="is_active = false",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("legal_knowledge_chunks.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=True,
    )
    question_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    flavor: Mapped[str] = mapped_column(String(16), nullable=False)
    expected_answer: Mapped[str] = mapped_column(Text, nullable=False)
    match_strategy: Mapped[str] = mapped_column(String(16), nullable=False)
    match_config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    synonyms: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    article_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    knowledge_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="needs_review"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    original_confidence: Mapped[float | None] = mapped_column(
        Numeric(precision=4, scale=3), nullable=True
    )
    generated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
