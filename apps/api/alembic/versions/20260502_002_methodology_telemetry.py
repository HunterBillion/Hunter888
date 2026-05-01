"""TZ-8 PR-D — methodology telemetry: chunk_kind column + relaxed FK.

Revision ID: 20260502_002
Revises: 20260501_003, 20260502_001
Create Date: 2026-05-01

Two coordinated changes that unblock cross-source telemetry on the
existing ``chunk_usage_logs`` table without forking it into three
parallel tables (legal-only / wiki-only / methodology-only — each
with its own retrieval and outcome columns).

This is a **merge revision**: both ``20260501_003`` (PR #159
emergency) and ``20260502_001`` (TZ-8 PR-A) are heads after their
respective merges, so the chain has a fork. Combining them here
keeps ``alembic heads`` returning a single tip going forward.

Change 1: ``chunk_kind`` discriminator column
---------------------------------------------

Adds ``chunk_usage_logs.chunk_kind`` (``String(20)``, NOT NULL,
``server_default='legal'``). Three valid values:

  * ``'legal'``        — ``chunk_id`` references ``legal_knowledge_chunks.id``
  * ``'wiki'``         — ``chunk_id`` references ``wiki_pages.id``
  * ``'methodology'``  — ``chunk_id`` references ``methodology_chunks.id``

The default + backfill writes ``'legal'`` to every existing row,
which is correct: every pre-PR-D row was logged from the legal RAG
path (the only path that called ``log_chunk_usage`` until this PR).

Change 2: relax the FK on ``chunk_id``
--------------------------------------

The current FK ``chunk_usage_logs.chunk_id → legal_knowledge_chunks.id``
would block any INSERT with a ``chunk_id`` that points at a
``wiki_pages.id`` or ``methodology_chunks.id``. We drop the FK
(keeping the column + index) and instead enforce the JOIN at query
time using ``chunk_kind``. This pattern matches how
``ScenarioVersion.scenario_template_id`` got polymorphic-ish
references in TZ-3 (no pg native polymorphism).

Idempotent
----------

Same ``_*_exists`` guards as ``20260423_004_add_knowledge_status``
so re-runs in a local Docker stack don't error.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260502_002"
# Merge revision — depends on BOTH heads at the time of authoring.
# After this lands, ``alembic heads`` returns ``20260502_002`` only.
down_revision: Union[str, Sequence[str], None] = (
    "20260501_003",
    "20260502_001",
)
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


def _fk_exists(constraint_name: str, table_name: str) -> bool:
    conn = op.get_bind()
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.table_constraints "
                "WHERE constraint_name = :n AND table_name = :t "
                "AND constraint_type = 'FOREIGN KEY'"
            ),
            {"n": constraint_name, "t": table_name},
        ).fetchone()
    )


def _index_exists(index_name: str) -> bool:
    conn = op.get_bind()
    return bool(
        conn.execute(
            sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
            {"n": index_name},
        ).fetchone()
    )


# ── Upgrade ────────────────────────────────────────────────────────────


def upgrade() -> None:
    # 1. ``chunk_kind`` column. Default 'legal' so every existing row
    #    gets the right discriminator without a separate UPDATE step.
    if not _column_exists("chunk_usage_logs", "chunk_kind"):
        op.add_column(
            "chunk_usage_logs",
            sa.Column(
                "chunk_kind",
                sa.String(length=20),
                nullable=False,
                server_default="legal",
            ),
        )

    # 2. Composite index on (chunk_kind, chunk_id) so the typical
    #    "find all usages of this methodology chunk" query plans
    #    cleanly without a sequential scan.
    if not _index_exists("ix_chunk_usage_logs_kind_chunk"):
        op.create_index(
            "ix_chunk_usage_logs_kind_chunk",
            "chunk_usage_logs",
            ["chunk_kind", "chunk_id"],
        )

    # 3. Relax the FK on chunk_id. SQLAlchemy auto-named the
    #    constraint ``chunk_usage_logs_chunk_id_fkey`` (the default
    #    Postgres pattern). Drop it; the column stays.
    fk_name = "chunk_usage_logs_chunk_id_fkey"
    if _fk_exists(fk_name, "chunk_usage_logs"):
        op.drop_constraint(fk_name, "chunk_usage_logs", type_="foreignkey")


# ── Downgrade ──────────────────────────────────────────────────────────


def downgrade() -> None:
    # Re-add the FK first (it's the strict one — restoring this on a
    # DB that already has wiki/methodology rows in chunk_usage_logs
    # will fail, which is *the right* behaviour: rolling back means
    # admitting we wrote rows that the legacy schema can't represent).
    if not _fk_exists("chunk_usage_logs_chunk_id_fkey", "chunk_usage_logs"):
        op.create_foreign_key(
            "chunk_usage_logs_chunk_id_fkey",
            "chunk_usage_logs",
            "legal_knowledge_chunks",
            ["chunk_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if _index_exists("ix_chunk_usage_logs_kind_chunk"):
        op.drop_index(
            "ix_chunk_usage_logs_kind_chunk", table_name="chunk_usage_logs"
        )
    if _column_exists("chunk_usage_logs", "chunk_kind"):
        op.drop_column("chunk_usage_logs", "chunk_kind")
