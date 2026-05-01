"""Allow domain_events.lead_client_id NULL for non-CRM events (TZ-5 training_material)

Revision ID: 20260501_003
Revises: 20260501_002
Create Date: 2026-05-01

Background
----------

TZ-5 (PR #100/#116/#152) introduced a separate event type set for the
training-material pipeline (``attachment.uploaded`` /
``scenario_draft_extracting`` / ``scenario_draft_ready``). These events
are emitted by `ingest_training_material` for files NOT bound to any
CRM client — `lead_client_id` is intentionally NULL on the row.

The `client_domain.emit_domain_event` helper does set
`correlation_id` correctly via the `aggregate_id` fallback (= attachment.id)
when `lead_client_id` is NULL. But the underlying `domain_events.lead_client_id`
column was declared `NOT NULL` since TZ-1 — so the very first
POST `/rop/scenarios/import` would have failed with `IntegrityError`.

The 5-agent audit (2026-05-01) caught this before any prod traffic hit
the endpoint. Fix: relax `NOT NULL`. The non-NULL-ness was a TZ-1
invariant for CRM-timeline joins; non-CRM events (training material)
join on `correlation_id` (set from `aggregate_id`) instead, which is
already the contract documented in `client_domain.py:389-402`.

Re-runnability
--------------

Idempotent — `op.alter_column` for nullable=True is a no-op when
already nullable. No data backfill required (existing rows have
non-NULL values; the column transition is widening).

Downgrade safety
----------------

Re-tightening to NOT NULL requires either deleting all training-material
events or backfilling them — gated behind ``ALLOW_DOMAIN_EVENT_DOWNGRADE_DATA_LOSS``
env var with the same pattern used in `20260429_001` for safety.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260501_003"
down_revision: Union[str, Sequence[str], None] = "20260501_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "domain_events",
        "lead_client_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    import os as _os

    bind = op.get_bind()
    null_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM domain_events WHERE lead_client_id IS NULL"
        )
    ).scalar_one()
    if null_count and int(null_count) > 0:
        if _os.getenv("ALLOW_DOMAIN_EVENT_DOWNGRADE_DATA_LOSS") != "1":
            raise RuntimeError(
                f"Refusing to downgrade: {null_count} domain_events rows have "
                "lead_client_id IS NULL (TZ-5 training_material events). "
                "Set ALLOW_DOMAIN_EVENT_DOWNGRADE_DATA_LOSS=1 to confirm "
                "data loss, or revert the feature via a forward migration."
            )
        bind.execute(
            sa.text("DELETE FROM domain_events WHERE lead_client_id IS NULL")
        )
    op.alter_column(
        "domain_events",
        "lead_client_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
