"""ORM model for legal_document — hierarchical law + court practice corpus.

Companion to legal_knowledge_chunks (curated fact cards). This table holds:
  - raw 127-ФЗ with chapter/article/item hierarchy (parent_id)
  - court practice (ВС РФ, арбитражные суды) with paragraph-level decomposition

Parent-child retrieval pattern:
  - retrieve against child (item / paragraph) — high precision
  - return context from parent (full article / full decision) — high recall

embedding_v2 uses gemini-embedding-001@768 (shadow column — coexists with
the legacy embeddings living in legal_knowledge_chunks).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LegalDocument(Base):
    __tablename__ = "legal_document"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("legal_document.id", ondelete="CASCADE"),
        nullable=True,
    )
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # 'law_fz' | 'law_chapter' | 'law_article' | 'law_item'
    # | 'court_case' | 'court_paragraph'
    doc_source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # '127-FZ' | 'vsrf' | 'arbitral_sudact' | ...
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")
    )
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_v2: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(64), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sql_text("true"))
    retrieval_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # Phase A (2026-04-20) — enrichment bookkeeping.
    # `summary` is a 1-paragraph LLM-generated digest (S5 stage), `qa_generated_at`
    # tracks when Q&A pairs were synthesised from this document (S3 stage).
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    qa_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("now()")
    )

    parent = relationship("LegalDocument", remote_side="LegalDocument.id", back_populates="children")
    children = relationship(
        "LegalDocument", back_populates="parent", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<LegalDocument {self.doc_type} #{self.number} '{(self.title or '')[:40]}'>"
