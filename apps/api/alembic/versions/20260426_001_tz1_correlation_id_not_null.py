"""TZ-1 §15.1 — domain_events.correlation_id NOT NULL.

Revision ID: 20260426_001
Revises: 20260425_005
Create Date: 2026-04-26

The §15.1 invariant 4 says every DomainEvent must carry a correlation_id
so timeline replay and audit joins (session → events → projections) work.
The Phase 1 model shipped the column as nullable because the helper
always set it; the audit (TZ-1 §13.4 follow-up) flagged that an honest
reader of the schema cannot assume the column is populated, and a single
forgetful caller would silently start emitting NULLs that timeline joins
would drop.

This migration:
  1. Backfills any existing NULL correlation_id with the canonical
     fallback chain `session_id → aggregate_id → lead_client_id`. This
     matches the helper's new default in `client_domain.emit_domain_event`
     so the historical and live paths agree.
  2. Adds NOT NULL on the column.

Pre-flight is run inside the migration so a clean prod (where the helper
already set correlation_id everywhere) finishes in milliseconds with no
rows touched. A dirty staging where some test rows leaked NULL gets
coerced rather than failing the deploy.

Down migration drops NOT NULL only — it does not re-introduce NULLs.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260426_001"
down_revision: Union[str, Sequence[str], None] = "20260425_005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1 — backfill NULLs using the same fallback chain the runtime
    # helper now applies. Idempotent: no-op when prod is already clean.
    op.execute(
        sa.text(
            """
            UPDATE domain_events
               SET correlation_id = COALESCE(
                   correlation_id,
                   session_id::text,
                   aggregate_id::text,
                   lead_client_id::text
               )
             WHERE correlation_id IS NULL
            """
        )
    )

    # Step 2 — enforce NOT NULL. Postgres has to scan the table to verify
    # but that is cheap relative to the rest of the deploy and the gain
    # (compile-time guarantee on every reader) is worth it.
    op.alter_column(
        "domain_events",
        "correlation_id",
        existing_type=sa.String(length=120),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "domain_events",
        "correlation_id",
        existing_type=sa.String(length=120),
        nullable=True,
    )
