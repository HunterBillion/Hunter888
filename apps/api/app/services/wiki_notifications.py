"""Wiki-specific notification system.

Sends notifications to ROP/admin when wiki events occur:
- New pattern discovered for a manager
- Daily/weekly synthesis completed
- Wiki ingest error (persistent)

Uses the existing NotificationConnectionManager singleton from ws/notifications.py.
"""

import logging
import uuid
from datetime import datetime, timezone

from app.ws.notifications import notification_manager, send_typed_notification

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Wiki notification type definitions
# ---------------------------------------------------------------------------

WIKI_NOTIFICATION_TYPES: dict[str, dict] = {
    "wiki.pattern_discovered": {
        "template": "🔍 Новый паттерн у {manager_name}: {pattern_code} ({category})",
        "force": False,
        "sound": "insight",
    },
    "wiki.pattern_confirmed": {
        "template": "✅ Паттерн подтверждён у {manager_name}: {pattern_code} (замечен {count}+ раз)",
        "force": True,
        "sound": "alert",
    },
    "wiki.daily_synthesis_done": {
        "template": "📊 Дневной синтез завершён: {wikis_count} wiki обновлено, тренд: {trend}",
        "force": False,
    },
    "wiki.weekly_synthesis_done": {
        "template": "📈 Недельный синтез завершён: {wikis_count} wiki обновлено",
        "force": False,
    },
    "wiki.ingest_error": {
        "template": "⚠️ Ошибка инжеста wiki для {manager_name}: {error}",
        "force": True,
        "sound": "error",
    },
    "wiki.manager_weakness": {
        "template": "🚨 Слабость у {manager_name}: {description}",
        "force": True,
        "sound": "alert",
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def send_wiki_notification(
    user_id: uuid.UUID | str,
    event_type: str,
    data: dict,
) -> None:
    """Send a Wiki-specific notification via WebSocket.

    Args:
        user_id: Target user ID (typically ROP or admin).
        event_type: One of WIKI_NOTIFICATION_TYPES keys.
        data: Template variables for the notification message.
    """
    config = WIKI_NOTIFICATION_TYPES.get(event_type)
    if not config:
        logger.warning("Unknown wiki notification type: %s", event_type)
        return

    try:
        message = config["template"].format(**data)
    except KeyError as e:
        logger.error("Missing template var %s for wiki notification %s", e, event_type)
        message = f"Wiki: {event_type}"

    event = {
        "type": "notification.new",
        "data": {
            "event_type": event_type,
            "message": message,
            "title": "Wiki",
            "body": message,
            "action": "navigate_to_wiki",
            "action_url": data.get("action_url", "/admin/wiki"),
            "action_data": data,
            "sound": config.get("sound"),
            "force": config.get("force", False),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    await notification_manager.send_to_user(str(user_id), event)


async def notify_rop_about_pattern(
    manager_id: uuid.UUID,
    manager_name: str,
    pattern_code: str,
    category: str,
    description: str,
    sessions_count: int,
    db=None,
) -> int:
    """Notify ROP(s) and admin(s) about a new or confirmed pattern.

    Finds the manager's team ROP and all admins, sends them a notification.
    Returns number of notifications sent.
    """
    sent = 0

    try:
        if db is None:
            from app.database import async_session
            async with async_session() as db:
                return await _do_notify_rop(
                    db, manager_id, manager_name, pattern_code,
                    category, description, sessions_count,
                )
        return await _do_notify_rop(
            db, manager_id, manager_name, pattern_code,
            category, description, sessions_count,
        )
    except Exception as e:
        logger.warning("Failed to notify ROP about pattern: %s", e)
        return 0


async def _do_notify_rop(
    db,
    manager_id: uuid.UUID,
    manager_name: str,
    pattern_code: str,
    category: str,
    description: str,
    sessions_count: int,
) -> int:
    """Internal: find ROPs/admins and send notifications."""
    from sqlalchemy import select
    from app.models.user import User, UserRole

    sent = 0

    # Find the manager's team ROP
    manager = await db.get(User, manager_id)
    if not manager:
        return 0

    rop_ids = set()
    admin_ids = set()

    # If manager has a team, find the team's ROP
    if manager.team_id:
        rop_r = await db.execute(
            select(User.id).where(
                User.team_id == manager.team_id,
                User.role == UserRole.rop,
                User.is_active == True,  # noqa: E712
            )
        )
        rop_ids = {r[0] for r in rop_r.all()}

    # Also notify all admins
    admin_r = await db.execute(
        select(User.id).where(
            User.role == UserRole.admin,
            User.is_active == True,  # noqa: E712
        )
    )
    admin_ids = {r[0] for r in admin_r.all()}

    all_recipients = rop_ids | admin_ids

    # Determine event type
    is_confirmed = sessions_count >= 3
    event_type = "wiki.pattern_confirmed" if is_confirmed else "wiki.pattern_discovered"

    data = {
        "manager_id": str(manager_id),
        "manager_name": manager_name,
        "pattern_code": pattern_code,
        "category": category,
        "description": description[:200],
        "count": sessions_count,
        "action_url": f"/admin/wiki",
    }

    for uid in all_recipients:
        try:
            await send_wiki_notification(uid, event_type, data)
            sent += 1
        except Exception as e:
            logger.debug("Failed to notify %s: %s", uid, e)

    if sent > 0:
        logger.info(
            "Wiki pattern notification sent to %d users: %s for %s",
            sent, pattern_code, manager_name,
        )

    return sent


async def notify_synthesis_complete(
    synthesis_type: str,  # "daily" or "weekly"
    results: list[dict],
) -> None:
    """Notify admins that synthesis completed."""
    from app.database import async_session
    from sqlalchemy import select
    from app.models.user import User, UserRole

    completed = [r for r in results if r.get("status") == "completed"]
    if not completed:
        return

    try:
        async with async_session() as db:
            admin_r = await db.execute(
                select(User.id).where(
                    User.role == UserRole.admin,
                    User.is_active == True,  # noqa: E712
                )
            )
            admin_ids = [r[0] for r in admin_r.all()]

            event_type = (
                "wiki.daily_synthesis_done"
                if synthesis_type == "daily"
                else "wiki.weekly_synthesis_done"
            )

            # Determine overall trend
            trends = [r.get("score_trend", "stable") for r in completed if "score_trend" in r]
            trend = trends[0] if len(set(trends)) == 1 else "mixed"

            data = {
                "wikis_count": len(completed),
                "trend": trend,
                "synthesis_type": synthesis_type,
                "action_url": "/admin/wiki",
            }

            for uid in admin_ids:
                try:
                    await send_wiki_notification(uid, event_type, data)
                except Exception:
                    pass

    except Exception as e:
        logger.warning("Failed to notify about synthesis: %s", e)
