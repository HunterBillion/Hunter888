"""User-filed reports about AI quiz answers (Issue: AI «тупит / уходит от закона»).

When a quiz/PvP user reads an AI verdict and disagrees («это не закон»,
«AI ошибся в статье»), they should be able to flag it from the history
tab. The flag lands here, then surfaces in the methodologist
KnowledgeReviewQueue (Variant B — same widget, new ``source_kind="user_report"``
filter chip) so a methodologist can decide whether the underlying RAG
chunk needs ``disputed`` / ``needs_review`` / ``outdated``.

This model deliberately does NOT change the existing
``LegalKnowledgeChunk.knowledge_status`` workflow. It just records the
user's complaint + the linked answer + the chunks that AI cited; the
methodologist still decides chunk-level status via the existing review
pipeline.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReportStatus(str, enum.Enum):
    open = "open"          # filed by user, no methodologist action yet
    accepted = "accepted"  # methodologist agrees, chunk status updated
    rejected = "rejected"  # methodologist disagrees (AI was right)


class KnowledgeAnswerReport(Base):
    __tablename__ = "knowledge_answer_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    answer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_answers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # User's reason — free text up to ~500 chars (FE will limit to 500).
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        SAEnum(ReportStatus, name="report_status"),
        nullable=False,
        default=ReportStatus.open,
        index=True,
    )
    # Snapshot of which chunks the AI cited (copy of
    # KnowledgeAnswer.rag_chunks_used at report time). This is what the
    # methodologist will likely flip to disputed/needs_review.
    linked_chunk_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_kareports_status_created", "status", "created_at"),
    )
