"""Methodology chunks: add ``is_deleted`` for soft-delete (B5-01).

Revision ID: 20260502_006
Revises: 20260502_005
Create Date: 2026-05-02

Why this exists
---------------

Audit B5-01 found ``DELETE /api/methodology/chunks/{id}`` performed a
hard SQL DELETE (``await db.delete(chunk)``). Hard delete on a row
referenced by ``chunk_usage_logs`` (whose FK was relaxed in
``20260502_002_methodology_telemetry``) leaves orphaned analytics
rows and breaks the audit timeline — there is no way to ask
"why did the team's «Скрипт по дорого» disappear?" once the row is gone.

Other RAG-eligible tables already follow the soft-delete convention:
``chunk_usage_logs`` has ``is_deleted`` (`models/rag.py:234`). This
migration brings ``methodology_chunks`` in line.

Schema change
-------------

Single column add:
  ``methodology_chunks.is_deleted BOOLEAN NOT NULL DEFAULT FALSE``

Plus a btree index on the column. The retrieval hot path
(``rag_methodology.search``) and the list endpoint both add a
``WHERE NOT is_deleted`` filter in this same PR, so the index pays
itself back immediately at first read.

Idempotent
----------

``IF NOT EXISTS`` guards on both the column and the index — safe to
re-run on any DB shape (fresh dev, prod that already migrated, etc.).

Reversibility
-------------

``downgrade()`` drops the index and column. The data flag itself is
NOT preserved — any chunk soft-deleted by the time of a downgrade
will become visible again at the previous level. Acceptable: the
DELETE endpoint at the previous revision was hard-delete anyway, so
there is no "soft-deleted state" to roll back into.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260502_006"
down_revision: Union[str, Sequence[str], None] = "20260502_005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE methodology_chunks "
            "ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN "
            "NOT NULL DEFAULT FALSE"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_methodology_chunks_is_deleted "
            "ON methodology_chunks (is_deleted)"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DROP INDEX IF EXISTS ix_methodology_chunks_is_deleted")
    )
    op.execute(
        sa.text("ALTER TABLE methodology_chunks DROP COLUMN IF EXISTS is_deleted")
    )
