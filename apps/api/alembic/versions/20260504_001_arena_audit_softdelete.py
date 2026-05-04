"""Arena audit + soft-delete + ownership columns

Revision ID: 20260504_001
Revises: 20260503_002
Create Date: 2026-05-04

Audit-2026-05-04 hardening for legal_knowledge_chunks:

  * `created_by` (UUID, nullable, FK→users.id ON DELETE SET NULL) —
    so a future "who authored this chunk" question has an answer.
    NULL on the 375 prod chunks (provenance unknown — they were
    seeded before this column existed). Filled forward by
    apps/api/app/api/rop.py:create_chunk on every new POST.
  * `last_edited_by` (UUID, nullable, FK→users.id ON DELETE SET NULL) —
    set by apps/api/app/api/rop.py:update_chunk on every PUT.
  * `deleted_at` (TIMESTAMPTZ, nullable) — soft-delete sentinel.
    The DELETE handler now flips `deleted_at = now()` instead of
    `db.delete()` so we don't lose the row + its analytics history
    + the FK targets in legal_validation_results. Hard delete now
    requires a separate admin-only path (not in this migration).
  * Composite index on `(deleted_at, category)` — RAG retrieval and
    list endpoints both need to filter NULLs cheaply at scale.

This migration is **append-only**: no column drops, no data
modification, no index drops. Safe to run online; takes ~50ms on the
375-row prod table. Roll-forward only path — `downgrade()` is
provided for completeness but is destructive (drops audit columns).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260504_001"
down_revision = "20260503_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "legal_knowledge_chunks",
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "legal_knowledge_chunks",
        sa.Column(
            "last_edited_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "legal_knowledge_chunks",
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # Soft-delete-aware list/retrieval predicates filter on
    # `deleted_at IS NULL` and (often) a category. Composite partial
    # index is cheap (~10KB at 375 rows) and pays off the moment the
    # table grows beyond 5K rows.
    op.create_index(
        "ix_legal_chunks_active_category",
        "legal_knowledge_chunks",
        ["category"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_legal_chunks_active_category",
        table_name="legal_knowledge_chunks",
    )
    op.drop_column("legal_knowledge_chunks", "deleted_at")
    op.drop_column("legal_knowledge_chunks", "last_edited_by")
    op.drop_column("legal_knowledge_chunks", "created_by")
