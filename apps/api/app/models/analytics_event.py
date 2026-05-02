"""Analytics event — anonymous FE telemetry collector.

See alembic/versions/20260502_005_analytics_events.py for the
table definition rationale (anonymous-OK, JSONB payload, 90-day
retention, indexed on event_name+occurred_at and user_id+occurred_at).

This model is read-only at the moment. Inserts go via the bulk-insert
path in `app.api.analytics.collect_events` which uses
`session.execute(insert(AnalyticsEvent), [...])` for batch efficiency.
ORM accessors here are kept thin for the cleanup script and any
ad-hoc analytics queries.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    # Nullable: pre-login pages can fire events without auth.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Client-generated UUID stitching one browser session worth of events
    # together. Persisted in localStorage; survives reloads, not browsers.
    anon_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    event_name: Mapped[str] = mapped_column(String(64), nullable=False)

    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    # FE-reported timestamp. May drift from server time.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Server-side ingestion. Use this for retention sweeps.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    release_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)
