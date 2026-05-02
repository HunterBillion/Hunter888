"""Analytics events table — anonymous FE telemetry collector.

Revision ID: 20260502_005
Revises: 20260502_004
Create Date: 2026-05-02

Why this exists
---------------

The frontend has had `telemetry.track(event, payload)` call sites
(ScriptPanel, ScriptDrawer, WhisperPanel, training/[id]/call,
training/[id]) for several sprints, but `apps/web/src/lib/telemetry.ts`
was a stub: in dev it `console.log`'d, in prod it was a no-op. No
events left the browser, so we couldn't measure script-panel adoption,
mistake-detector trigger rate, retrain-widget effectiveness, or any of
the A/B-style decisions the events were designed to inform.

This migration ships the storage half. The router lives at
`apps/api/app/api/analytics.py`; the FE rewrite lives at
`apps/web/src/lib/telemetry.ts`.

Design notes
------------

* **Anonymous-OK.** `user_id` is nullable. Pre-login pages
  (/login, /register, /reset-password) can fire events without auth.
  The router rate-limits per-IP to bound DDoS surface.
* **`anon_session_id`** is a client-generated UUID stored in
  localStorage. Persists across reloads but not across browsers /
  incognito windows. Lets us stitch a session of events together
  without identifying a user.
* **`payload` is JSONB** — schema-on-read. Each event name has a
  conventional payload shape (see telemetry.ts EventName union),
  enforced FE-side via the typed track() signature, but the DB
  accepts arbitrary objects so we can ship new event types without
  a migration.
* **Retention: 90 days.** Postgres has no built-in TTL, so we
  document the rule here and provide
  `apps/api/scripts/cleanup_analytics.py` for a periodic cron.
  `created_at` is the truth; `occurred_at` is FE-reported and may
  drift from clock skew, so we partition / cleanup by the former.
* **Indexes** — three: by event_name+occurred_at (per-event
  cohorts), by user_id+occurred_at (per-user trail when authed),
  by created_at (retention sweep). Single-column index on
  anon_session_id intentionally omitted; UUID lookups via
  `=` go through the primary key path or aren't a hot read.
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "20260502_005"
down_revision: Union[str, Sequence[str], None] = "20260502_004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        # Nullable: anonymous events (pre-login pages) carry only the
        # anon_session_id. Authed events carry both for join'ability.
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "anon_session_id",
            UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("event_name", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # FE-reported event timestamp (may drift due to client clock).
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        # Server-side ingestion time. Use this for retention / partitioning.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        # Build-time release SHA from FE — lets us correlate event
        # rates with deploys.
        sa.Column("release_sha", sa.String(length=40), nullable=True),
        # User-agent + referer truncated; useful for browser-cohort splits
        # without needing to fingerprint.
        sa.Column("user_agent", sa.String(length=256), nullable=True),
    )

    # Per-event cohorts: "how many script_panel_toggle events in last
    # week, day-by-day". The (event_name, occurred_at DESC) order
    # matches the canonical query.
    op.create_index(
        "ix_analytics_events_name_occurred_at",
        "analytics_events",
        ["event_name", sa.text("occurred_at DESC")],
    )

    # Per-user trail: "what did this user do in their last session".
    # Filtered by NULL exclusion — anonymous rows aren't joined here.
    op.create_index(
        "ix_analytics_events_user_id_occurred_at",
        "analytics_events",
        ["user_id", sa.text("occurred_at DESC")],
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )

    # Retention sweep: cleanup script deletes WHERE created_at < now - 90d.
    op.create_index(
        "ix_analytics_events_created_at",
        "analytics_events",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_events_created_at", table_name="analytics_events")
    op.drop_index(
        "ix_analytics_events_user_id_occurred_at",
        table_name="analytics_events",
    )
    op.drop_index(
        "ix_analytics_events_name_occurred_at",
        table_name="analytics_events",
    )
    op.drop_table("analytics_events")
