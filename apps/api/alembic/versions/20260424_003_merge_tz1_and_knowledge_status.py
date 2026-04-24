"""Merge alembic heads (TZ-1 foundation + add_knowledge_status).

Revision ID: 20260424_003
Revises: 20260424_002, 20260423_004
Create Date: 2026-04-24

Why this exists
---------------
Two parallel branches grew a ``head`` in the alembic graph at the same time:

* ``20260423_004_add_knowledge_status`` — chains back through
  ``20260423_003`` to the original initial_schema root.
* ``20260424_002_tz1_client_domain_foundation`` — chains back through
  ``20260424_001`` and ``reviews_use_deleted``, which has
  ``down_revision=None`` (acting as a second root).

``alembic upgrade head`` refuses to pick between them and stops CI with
``Multiple head revisions are present for given argument 'head'``. This
migration is a no-op that lists both revisions as its ``down_revision``
so the graph converges back to one head and ``upgrade head`` works.

There are no schema changes here on purpose — the TZ-1 tables and the
knowledge_status column are already in place upstream.
"""

from __future__ import annotations

from typing import Sequence, Union


revision: str = "20260424_003"
down_revision: Union[str, Sequence[str], None] = (
    "20260424_002",
    "20260423_004",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No-op. Exists purely to merge the two open heads in the migration
    # graph so ``alembic upgrade head`` resolves to a single target.
    pass


def downgrade() -> None:
    # No-op. Downgrading through this node simply splits back into the
    # two prior heads — nothing to undo.
    pass
