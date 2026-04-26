"""Migrate methodologist users to rop role (data-only, enum kept).

Revision ID: 20260426_002
Revises: 20260426_001
Create Date: 2026-04-26

Phase 1 of the methodologist → rop role consolidation. The product
decision is to retire the methodologist role entirely; ROPs inherit
all former methodologist permissions (scenario CRUD, prompt registry,
arena chunks, scoring config). To stay non-breaking for the pilot
during cutover, this migration is **data-only**:

  * UPDATE users SET role='rop' WHERE role='methodologist'
  * The PostgreSQL enum value 'methodologist' is **NOT removed yet** —
    that lands in a follow-up migration (Phase 3) AFTER the frontend
    has dropped its /methodologist/* URLs (Phase 2 of the rollout).

Why split the data write from the enum drop:
  * Postgres cannot drop an enum value while ANY column still uses it.
    Even if zero users have role='methodologist' after this UPDATE, the
    column type still admits it; the drop has to wait for the type
    rebuild (rename old type, create new without the value, alter
    column USING cast, drop old type) which is a blocking operation
    we don't want to ship in the same hotfix as the data move.
  * Frontend pilots may have stale tokens or cached session payloads
    that include role='methodologist'. Keeping the enum value live
    prevents 500s during the transition window.

Down migration: NOT REVERSIBLE in the data direction (we don't track
which user used to be a methodologist). Down does nothing — if a
rollback is needed, restore from a logical backup.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260426_002"
down_revision: Union[str, Sequence[str], None] = "20260426_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Single UPDATE — idempotent. No-op on a clean DB.
    op.execute(
        sa.text(
            "UPDATE users SET role = 'rop' WHERE role = 'methodologist'"
        )
    )


def downgrade() -> None:
    # No-op: we cannot tell which rop rows were originally methodologist.
    # Restore from a backup if you need the old assignments back.
    pass
