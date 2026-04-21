"""
Web Push notification service (Task X6).

ТЗ v2, раздел 7.4:
- VAPID-based Web Push (RFC 8292)
- Subscription management (create / delete / list)
- Send push to specific user or broadcast to team
- Handles expired subscriptions gracefully
- Integrates with notification system (ClientNotification)

Dependencies:
  pip install pywebpush  (or use manual VAPID implementation)

If pywebpush is not installed, falls back to a stub that logs warnings.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

# ── Try to import pywebpush ──
try:
    from pywebpush import webpush, WebPushException

    HAS_PYWEBPUSH = True
except ImportError:
    HAS_PYWEBPUSH = False
    logger.warning("pywebpush not installed — Web Push will be stubbed (pip install pywebpush)")


# ─── Push Subscription Model ────────────────────────────────────────────────
# Stored in a lightweight table. We create it via Alembic migration.

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PushSubscription(Base):
    """Browser push subscription for a user."""

    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(200), nullable=False)
    auth: Mapped[str] = mapped_column(String(100), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_push_sub_user_endpoint", "user_id", "endpoint", unique=True),
    )


# ─── Service ─────────────────────────────────────────────────────────────────


async def save_subscription(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None = None,
    current_user_id: uuid.UUID | None = None,
) -> PushSubscription:
    """
    Register or update a push subscription for a user.
    Upsert by (user_id, endpoint).

    S1-04: If current_user_id is provided, validates ownership.
    """
    if current_user_id is not None and current_user_id != user_id:
        raise ValueError(f"Ownership violation: user {current_user_id} cannot manage subscriptions for {user_id}")
    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == user_id,
            PushSubscription.endpoint == endpoint,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.p256dh = p256dh
        existing.auth = auth
        existing.is_active = True
        existing.user_agent = user_agent
        existing.last_used_at = datetime.now(timezone.utc)
        return existing

    sub = PushSubscription(
        id=uuid.uuid4(),
        user_id=user_id,
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth,
        user_agent=user_agent,
    )
    db.add(sub)
    return sub


async def remove_subscription(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    endpoint: str,
) -> bool:
    """Remove a push subscription. Returns True if found and deleted."""
    result = await db.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == user_id,
            PushSubscription.endpoint == endpoint,
        )
    )
    return (result.rowcount or 0) > 0


async def get_user_subscriptions(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[PushSubscription]:
    """Get all active subscriptions for a user."""
    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == user_id,
            PushSubscription.is_active == True,  # noqa: E712
        )
    )
    return list(result.scalars().all())


# ─── Push Sending ────────────────────────────────────────────────────────────


async def send_push_to_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    title: str,
    body: str,
    url: str | None = None,
    icon: str | None = None,
    tag: str | None = None,
    data: dict | None = None,
    current_user_id: uuid.UUID | None = None,
) -> int:
    """
    Send a Web Push notification to all active subscriptions of a user.
    Returns count of successful deliveries.

    S1-04: If current_user_id is provided, validates ownership (user can only push to self).
    Server-side callers (event_bus, notifications) pass current_user_id=None (trusted).
    """
    if current_user_id is not None and current_user_id != user_id:
        logger.warning("Push ownership violation: user %s tried to push to %s", current_user_id, user_id)
        return 0
    if not settings.web_push_configured:
        logger.debug("Web Push not configured, skipping push to user %s", user_id)
        return 0

    subscriptions = await get_user_subscriptions(db, user_id)
    if not subscriptions:
        return 0

    payload = json.dumps(
        {
            "title": title,
            "body": body,
            "url": url or "/",
            "icon": icon or "/icon-192.png",
            "tag": tag,
            "data": data or {},
        },
        ensure_ascii=False,
    )

    success_count = 0
    expired_subs: list[uuid.UUID] = []

    import asyncio
    for sub in subscriptions:
        ok = await asyncio.to_thread(_send_single_push, sub, payload)
        if ok:
            success_count += 1
            sub.last_used_at = datetime.now(timezone.utc)
        elif ok is None:
            # Subscription expired / invalid
            expired_subs.append(sub.id)

    # Deactivate expired subscriptions in DB
    if expired_subs:
        from sqlalchemy import update

        await db.execute(
            update(PushSubscription)
            .where(PushSubscription.id.in_(expired_subs))
            .values(is_active=False)
        )
        logger.info("Deactivated %d expired push subscriptions for user %s", len(expired_subs), user_id)

    return success_count


def _send_single_push(sub: PushSubscription, payload: str) -> bool | None:
    """
    Send a push to a single subscription.
    Returns True on success, False on transient error, None on expired/invalid subscription.
    """
    if not HAS_PYWEBPUSH:
        logger.warning("pywebpush not installed, cannot send push to %s", sub.endpoint[:60])
        return False

    subscription_info = {
        "endpoint": sub.endpoint,
        "keys": {
            "p256dh": sub.p256dh,
            "auth": sub.auth,
        },
    }

    try:
        webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
        )
        return True
    except WebPushException as e:
        response = getattr(e, "response", None)
        status_code = getattr(response, "status_code", None) if response else None

        if status_code in (404, 410):
            # Subscription expired or unsubscribed
            logger.info("Push subscription expired (HTTP %s): %s", status_code, sub.endpoint[:60])
            return None
        elif status_code == 429:
            logger.warning("Push rate limited: %s", sub.endpoint[:60])
            return False
        else:
            logger.error("Push failed (HTTP %s): %s — %s", status_code, sub.endpoint[:60], e)
            return False
    except Exception as e:
        logger.error("Push exception: %s — %s", sub.endpoint[:60], e)
        return False


# ─── VAPID Key Generation Utility ────────────────────────────────────────────


def generate_vapid_keys() -> dict[str, str]:
    """
    Generate VAPID key pair for Web Push.
    Call once, save keys to .env:
      VAPID_PUBLIC_KEY=<public>
      VAPID_PRIVATE_KEY=<private>
      VAPID_SUBJECT=mailto:admin@example.com
    """
    try:
        from py_vapid import Vapid

        vapid = Vapid()
        vapid.generate_keys()
        return {
            "public_key": vapid.public_key_urlsafe_base64,
            "private_key": vapid.private_key_urlsafe_base64,
        }
    except ImportError:
        # Fallback: generate via cryptography lib
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.backends import default_backend
        import base64

        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        public_key = private_key.public_key()

        # Export raw keys
        private_numbers = private_key.private_numbers()
        public_numbers = private_numbers.public_numbers

        # Private key: 32 bytes
        priv_bytes = private_numbers.private_value.to_bytes(32, byteorder="big")
        # Public key: 65 bytes (uncompressed: 0x04 + x + y)
        pub_bytes = (
            b"\x04"
            + public_numbers.x.to_bytes(32, byteorder="big")
            + public_numbers.y.to_bytes(32, byteorder="big")
        )

        return {
            "public_key": base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode(),
            "private_key": base64.urlsafe_b64encode(priv_bytes).rstrip(b"=").decode(),
        }
