"""XP Events — time-limited multiplier events (2x Happy Hours, etc.).

Creates urgency and FOMO. Active events apply a multiplier to all XP earned.
Admin-created or auto-scheduled (1 random hour per week).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.xp_event import XPEvent

logger = logging.getLogger(__name__)


@dataclass
class ActiveEvent:
    """Currently active XP event."""
    id: str
    name: str
    multiplier: float
    ends_at: str
    minutes_remaining: int


async def get_active_event(db: AsyncSession) -> ActiveEvent | None:
    """Get currently active XP event, if any."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(XPEvent).where(
            XPEvent.is_active == True,  # noqa: E712
            XPEvent.start_at <= now,
            XPEvent.end_at > now,
        ).limit(1)
    )
    event = result.scalar_one_or_none()
    if not event:
        return None

    minutes_remaining = max(0, int((event.end_at - now).total_seconds() / 60))
    return ActiveEvent(
        id=str(event.id),
        name=event.name,
        multiplier=event.multiplier,
        ends_at=event.end_at.isoformat(),
        minutes_remaining=minutes_remaining,
    )


async def get_xp_multiplier(db: AsyncSession) -> float:
    """Get current XP multiplier (1.0 if no event active)."""
    event = await get_active_event(db)
    return event.multiplier if event else 1.0


async def create_happy_hour(
    db: AsyncSession,
    *,
    name: str = "Happy Hour: 2x XP!",
    description: str = "Двойной XP на все тренировки!",
    multiplier: float = 2.0,
    duration_minutes: int = 60,
) -> XPEvent:
    """Create a Happy Hour event starting now."""
    now = datetime.now(timezone.utc)
    event = XPEvent(
        name=name,
        description=description,
        multiplier=multiplier,
        start_at=now,
        end_at=now + timedelta(minutes=duration_minutes),
        is_active=True,
    )
    db.add(event)
    await db.flush()

    logger.info(
        "Happy Hour created: %s, multiplier=%.1f, duration=%d min",
        name, multiplier, duration_minutes,
    )
    return event
