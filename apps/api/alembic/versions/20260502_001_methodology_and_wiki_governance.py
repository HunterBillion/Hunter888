"""TZ-8 PR-A — methodology_chunks + WikiPage governance carry-over.

Revision ID: 20260502_001
Revises: 20260501_001
Create Date: 2026-05-01

PR-A of the TZ-8 (per-team methodology RAG) plan
(``docs/TZ-8_methodology_rag.md``). Two coordinated schema moves
that *must* land in the same revision so the runtime never sees a
half-applied state:

  1. Create ``methodology_chunks`` (the new per-team playbook
     table). pgvector ``Vector(768)`` column for embeddings,
     ``ivfflat`` cosine index, three composite indexes for the
     hot retrieval / authz filters, and a ``UNIQUE(team_id, title)``
     to prevent duplicate playbook names inside one team.

  2. Add four governance columns to ``wiki_pages`` —
     ``knowledge_status``, ``last_reviewed_at``, ``last_reviewed_by``,
     ``review_due_at``. Closes the deferred governance item from
     PR-X / PR #153 (the foundation prerequisite). Backfill all
     existing rows to ``actual`` so :func:`rag_wiki.retrieve_wiki_context`
     keeps returning them after the new ``WHERE knowledge_status IN
     ('actual','disputed')`` filter lands. NOT NULL is enforced via
     ``server_default='actual'`` so the backfill happens at the
     moment of column creation — no two-phase orchestration needed.

The revision number is ``20260502_001`` and ``down_revision`` is
``20260501_002`` (TZ-5's ``manager_kpi_targets``) — both of those
landed on ``main`` while this PR was being authored. The chain
stays linear: ``20260429_002`` → ``20260501_001`` →
``20260501_002`` → ``20260502_001``.

Idempotent guards (``_column_exists`` / ``_index_exists``) match the
pattern from ``20260423_004_add_knowledge_status.py`` so re-runs
during local debugging don't error out.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20260502_001"
down_revision: Union[str, Sequence[str], None] = "20260501_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Idempotent guards ─────────────────────────────────────────────────


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table_name, "c": column_name},
        ).fetchone()
    )


def _index_exists(index_name: str) -> bool:
    conn = op.get_bind()
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM pg_indexes WHERE indexname = :n"
            ),
            {"n": index_name},
        ).fetchone()
    )


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = :t"
            ),
            {"t": table_name},
        ).fetchone()
    )


# ── Upgrade ────────────────────────────────────────────────────────────


def upgrade() -> None:
    # ── 1. methodology_chunks ──
    if not _table_exists("methodology_chunks"):
        op.create_table(
            "methodology_chunks",
            # Identity
            sa.Column(
                "id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            # Ownership
            sa.Column(
                "team_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                sa.ForeignKey("teams.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "author_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            # Content
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("kind", sa.String(length=30), nullable=False),
            sa.Column(
                "tags",
                sa.dialects.postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "keywords",
                sa.dialects.postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            # Governance
            sa.Column(
                "knowledge_status",
                sa.String(length=30),
                nullable=False,
                server_default="actual",
            ),
            sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "last_reviewed_by",
                sa.dialects.postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("review_due_at", sa.DateTime(timezone=True), nullable=True),
            # Embedding
            sa.Column("embedding", Vector(768), nullable=True),
            sa.Column("embedding_model", sa.String(length=64), nullable=True),
            sa.Column("embedding_updated_at", sa.DateTime(timezone=True), nullable=True),
            # Audit
            sa.Column(
                "version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            # Constraints
            sa.UniqueConstraint(
                "team_id", "title", name="uq_methodology_team_title"
            ),
        )

        # Hot-path filter indexes — see model docstring for the
        # query shape these support.
        op.create_index(
            "ix_methodology_chunks_team_id",
            "methodology_chunks",
            ["team_id"],
        )
        op.create_index(
            "ix_methodology_chunks_author_id",
            "methodology_chunks",
            ["author_id"],
        )
        op.create_index(
            "ix_methodology_chunks_kind",
            "methodology_chunks",
            ["kind"],
        )
        op.create_index(
            "ix_methodology_chunks_knowledge_status",
            "methodology_chunks",
            ["knowledge_status"],
        )
        op.create_index(
            "ix_methodology_chunks_review_due_at",
            "methodology_chunks",
            ["review_due_at"],
        )
        op.create_index(
            "ix_methodology_chunks_team_status",
            "methodology_chunks",
            ["team_id", "knowledge_status"],
        )
        op.create_index(
            "ix_methodology_chunks_team_kind",
            "methodology_chunks",
            ["team_id", "kind"],
        )

        # ivfflat index on the embedding. ``lists=100`` is the
        # starting point — recommended ratio is ``rows / lists ≈ 50``;
        # at ~5k rows this gives 50 buckets which is the right shape.
        # Re-tune (or migrate to HNSW) once a team crosses ~5k chunks.
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_methodology_chunks_embedding "
            "ON methodology_chunks USING ivfflat "
            "(embedding vector_cosine_ops) WITH (lists = 100)"
        )

    # ── 2. WikiPage governance carry-over ──
    #
    # The ``server_default='actual'`` does the row-level backfill at
    # column-creation time, so the column is non-nullable from the
    # very moment the migration commits. No second pass needed.

    if not _column_exists("wiki_pages", "knowledge_status"):
        op.add_column(
            "wiki_pages",
            sa.Column(
                "knowledge_status",
                sa.String(length=30),
                nullable=False,
                server_default="actual",
            ),
        )
        op.create_index(
            "ix_wiki_pages_knowledge_status",
            "wiki_pages",
            ["knowledge_status"],
        )

    if not _column_exists("wiki_pages", "last_reviewed_at"):
        op.add_column(
            "wiki_pages",
            sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _column_exists("wiki_pages", "last_reviewed_by"):
        op.add_column(
            "wiki_pages",
            sa.Column(
                "last_reviewed_by",
                sa.dialects.postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    if not _column_exists("wiki_pages", "review_due_at"):
        op.add_column(
            "wiki_pages",
            sa.Column("review_due_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_wiki_pages_review_due_at",
            "wiki_pages",
            ["review_due_at"],
        )


# ── Downgrade ──────────────────────────────────────────────────────────


def downgrade() -> None:
    # WikiPage governance — drop indexes first, then columns.
    if _index_exists("ix_wiki_pages_review_due_at"):
        op.drop_index("ix_wiki_pages_review_due_at", table_name="wiki_pages")
    for col in ("review_due_at", "last_reviewed_by", "last_reviewed_at"):
        if _column_exists("wiki_pages", col):
            op.drop_column("wiki_pages", col)
    if _column_exists("wiki_pages", "knowledge_status"):
        if _index_exists("ix_wiki_pages_knowledge_status"):
            op.drop_index(
                "ix_wiki_pages_knowledge_status", table_name="wiki_pages"
            )
        op.drop_column("wiki_pages", "knowledge_status")

    # methodology_chunks — drop the table outright; CASCADE handles
    # any FK from a future child table that didn't exist yet.
    if _table_exists("methodology_chunks"):
        op.execute(
            "DROP INDEX IF EXISTS ix_methodology_chunks_embedding"
        )
        op.drop_table("methodology_chunks")
