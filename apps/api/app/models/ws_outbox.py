"""WsOutboxEvent — guaranteed WebSocket delivery (Roadmap §10).

The existing ``_send_to_user`` helpers are fire-and-forget: if the
target user is not connected at the millisecond the message is
produced, the event disappears and ``logger.warning`` is all we see.
PvP ``match.found`` is the most visible victim — one player goes offline
during matchmaking and the other sits forever on a spinner.

``WsOutboxEvent`` is a durable queue: critical messages are persisted
in the same DB transaction as the business logic that produced them,
then a background worker (or a ``process_pending_for_user`` call on
reconnect) drains the queue through the connection registry. Messages
that cross their ``expires_at`` TTL without delivery are logged and
marked failed — nothing gets stuck forever.

Schema separate from ``outbox_events`` (the gamification fan-out) —
that table has domain-specific fields (``user_id`` nullable, retry
schedule tuned for handler failures) that don't map cleanly to
WS delivery semantics. Keeping them parallel avoids cross-contamination.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WsOutboxStatus(str, PyEnum):
    pending = "pending"
    delivered = "delivered"
    expired = "expired"
    failed = "failed"


class WsOutboxEvent(Base):
    __tablename__ = "ws_outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=WsOutboxStatus.pending.value, index=True)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Producer-chosen correlation id so UI can dedupe on reconnect.
    correlation_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_ws_outbox_user_status", "user_id", "status"),
        Index("ix_ws_outbox_expires_at", "expires_at"),
    )
