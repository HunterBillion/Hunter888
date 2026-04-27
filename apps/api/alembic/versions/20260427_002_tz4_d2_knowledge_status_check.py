"""TZ-4 D2 — piggyback CHECK constraint on legal_knowledge_chunks.knowledge_status

Revision ID: 20260427_002
Revises: 20260427_001
Create Date: 2026-04-27

Spec ref: TZ-4 §6.2.1 / §8.1 — ``knowledge_status`` enum is one of
{actual, disputed, outdated, needs_review}. The column has been
free-form ``String(30)`` since the original schema; D4 will start
writing all four values from the review-policy cron, so the CHECK
constraint must land before D4 to prevent typos like ``"outdate"``
silently shipping to prod.

Why D2 and not D4
-----------------

Per Q2 of the D1.1 review thread, the user explicitly asked us to
piggyback this CHECK constraint into D2 instead of waiting for D4 —
same review cycle, no extra DB round-trip when the cron eventually
ships, and one fewer migration to coordinate during the D4 series.

Why this is safe today
----------------------

Production state at the time of authoring (verified via
``SELECT knowledge_status, COUNT(*) FROM legal_knowledge_chunks GROUP BY 1``):

    knowledge_status | count
    -----------------+-------
    actual           |   375

So all existing rows pass the constraint without backfill. The
defensive UPDATE block below is still emitted to keep the migration
re-runnable on environments that were seeded with non-canonical
values (dev / staging) — it normalises any non-canonical row to
``'actual'`` before the CHECK lands so the migration cannot fail
mid-flight.

Re-runnability
--------------

The constraint is added behind a ``_constraint_exists`` guard so a
re-run on a database that already has the constraint (e.g. after a
partial rollback) is a no-op rather than a hard error. This mirrors
the pattern used in ``20260427_001_tz4_d1_foundation.py``.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# ── Alembic identifiers ──────────────────────────────────────────────────
revision: str = "20260427_002"
down_revision: Union[str, Sequence[str], None] = "20260427_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CHECK_CONSTRAINT_NAME = "ck_legal_knowledge_chunks_knowledge_status"
ALLOWED_VALUES = ("actual", "disputed", "outdated", "needs_review")


def _constraint_exists(name: str) -> bool:
    bind = op.get_bind()
    return (
        bind.execute(
            sa.text(
                "SELECT 1 FROM pg_constraint WHERE conname = :name LIMIT 1"
            ),
            {"name": name},
        ).scalar()
        is not None
    )


def upgrade() -> None:
    bind = op.get_bind()

    # Pre-flight normalisation: any row that ended up with a non-canonical
    # status from a legacy seed gets bumped to 'actual'. Quote the IN-list
    # values into the SQL itself (no bind params) — sa.text + bind on a
    # tuple of literals is fragile across drivers, and these four values
    # are themselves part of the schema contract so inlining is fine.
    in_list = ", ".join(f"'{v}'" for v in ALLOWED_VALUES)
    bind.execute(
        sa.text(
            f"UPDATE legal_knowledge_chunks "
            f"SET knowledge_status = 'actual' "
            f"WHERE knowledge_status IS NULL "
            f"   OR knowledge_status NOT IN ({in_list})"
        )
    )

    if not _constraint_exists(CHECK_CONSTRAINT_NAME):
        op.create_check_constraint(
            CHECK_CONSTRAINT_NAME,
            "legal_knowledge_chunks",
            f"knowledge_status IN ({in_list})",
        )


def downgrade() -> None:
    if _constraint_exists(CHECK_CONSTRAINT_NAME):
        op.drop_constraint(
            CHECK_CONSTRAINT_NAME, "legal_knowledge_chunks", type_="check"
        )
