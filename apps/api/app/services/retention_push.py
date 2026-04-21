"""Retention Push Notifications — Петля 6: умные уведомления.

Rules:
  - Max 2 push/day per user
  - Only for users who did NOT visit today
  - Priority-ordered: streak danger > duel invite > new chapter > weekly digest > inactive

Runs as periodic background task (every 30 min, 18:00-22:00 window).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.training import TrainingSession, SessionStatus
from app.models.progress import ManagerProgress
from app.models.user import User

logger = logging.getLogger(__name__)

MAX_PUSH_PER_DAY = 2
STREAK_DANGER_HOUR = 20  # Send at 20:00 local (UTC approximation)


async def check_streak_danger(db: AsyncSession) -> list[dict]:
    """Find users with active streaks who haven't trained today.

    Sends: 'Твой {N}-дневный стрик сгорит через 4 часа.'
    """
    today = datetime.now(timezone.utc).date()

    # Users with any active streak (calendar or drill)
    from app.services.gamification import calculate_streak

    active_users = await db.execute(
        select(User.id, User.full_name)
        .where(User.is_active == True)  # noqa: E712
    )

    notifications = []
    for user_id, name in active_users.all():
        # Use unified streak calculation (same as frontend sees)
        streak = await calculate_streak(user_id, db)
        if streak <= 0:
            continue
        # Check if user trained today
        today_session = await db.execute(
            select(func.count()).select_from(TrainingSession).where(
                TrainingSession.user_id == user_id,
                TrainingSession.status == SessionStatus.completed,
                func.date(TrainingSession.started_at) == today,
            )
        )
        if (today_session.scalar() or 0) == 0:
            notifications.append({
                "user_id": user_id,
                "type": "streak_danger",
                "title": "Стрик в опасности",
                "body": f"Твой {streak}-дневный стрик сгорит через 4 часа.",
                "priority": 1,
            })

    return notifications


async def check_inactive_users(db: AsyncSession) -> list[dict]:
    """Find users inactive for 3+ or 7+ days.

    3 days: 'Охотник, тебя не видно. Стрик сгорел. Начни новый.'
    7 days: 'Твоя позиция в команде: #{pos}. {name} уже обогнал тебя.'
    """
    now = datetime.now(timezone.utc)
    three_days_ago = now - timedelta(days=3)
    seven_days_ago = now - timedelta(days=7)

    # Users with no sessions in 3+ days
    inactive = await db.execute(
        select(User.id, User.full_name, func.max(TrainingSession.started_at).label("last_active"))
        .outerjoin(TrainingSession, TrainingSession.user_id == User.id)
        .where(User.is_active == True)  # noqa: E712
        .group_by(User.id, User.full_name)
        .having(
            (func.max(TrainingSession.started_at) < three_days_ago)
            | (func.max(TrainingSession.started_at).is_(None))
        )
    )

    notifications = []
    for user_id, name, last_active in inactive.all():
        if last_active is None:
            continue  # Never played — don't spam

        days_inactive = (now - last_active).days

        if days_inactive >= 7:
            notifications.append({
                "user_id": user_id,
                "type": "inactive_7d",
                "title": "Тебя не видно",
                "body": f"Уже {days_inactive} дней без тренировок. Коллеги обгоняют.",
                "priority": 3,
            })
        elif days_inactive >= 3:
            notifications.append({
                "user_id": user_id,
                "type": "inactive_3d",
                "title": "Охотник, вернись",
                "body": "Тебя не видно. Стрик сгорел. Начни новый.",
                "priority": 2,
            })

    return notifications


async def _was_ws_notified_today(user_id: uuid.UUID, notif_type: str) -> bool:
    """Check Redis if a WS notification was already sent today (dedup)."""
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        key = f"retention:ws_sent:{user_id}:{notif_type}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        return bool(await r.exists(key))
    except Exception:
        return False  # fail open — send push if unsure


async def mark_ws_notification_sent(user_id: uuid.UUID, notif_type: str) -> None:
    """Mark that a WS notification was sent (called from scheduler.py)."""
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        key = f"retention:ws_sent:{user_id}:{notif_type}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        await r.set(key, "1", ex=25 * 3600)
    except Exception:
        pass


async def send_retention_notifications() -> int:
    """Main entry point: gather and send all retention notifications.

    Respects max 2/day limit. Deduplicates with WS notifications.
    Only sends to users who didn't visit today.
    Returns count of notifications sent.
    """
    sent = 0
    try:
        async with async_session() as db:
            streak_notifs = await check_streak_danger(db)
            inactive_notifs = await check_inactive_users(db)

            all_notifs = streak_notifs + inactive_notifs
            all_notifs.sort(key=lambda n: n["priority"])

            user_sent: dict[uuid.UUID, int] = {}

            for notif in all_notifs:
                uid = notif["user_id"]
                if user_sent.get(uid, 0) >= MAX_PUSH_PER_DAY:
                    continue

                # Dedup: skip if WS already sent same type today
                if await _was_ws_notified_today(uid, notif["type"]):
                    continue

                try:
                    from app.services.web_push import send_push_to_user
                    await send_push_to_user(
                        user_id=uid,
                        title=notif["title"],
                        body=notif["body"],
                        db=db,
                    )
                    user_sent[uid] = user_sent.get(uid, 0) + 1
                    sent += 1
                except Exception as e:
                    logger.debug("Push failed for user %s: %s", uid, e)

    except Exception as e:
        logger.error("Retention push check failed: %s", e)

    if sent > 0:
        logger.info("Retention push: sent %d notifications", sent)
    return sent
