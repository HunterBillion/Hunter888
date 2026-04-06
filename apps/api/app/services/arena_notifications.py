"""Arena-specific notification system.

Typed notification events for Arena Knowledge module:
- PvP challenges, match results, achievements
- Rating updates, weekly digests
- Cross-module knowledge recommendations

Uses the existing NotificationConnectionManager singleton from ws/notifications.py.

Block 5 (ТЗ_БЛОК_5_CROSS_MODULE): Notification integration.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.ws.notifications import notification_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Arena notification type definitions
# ---------------------------------------------------------------------------

ARENA_NOTIFICATION_TYPES: dict[str, dict] = {
    # PvP Challenges
    "arena.challenge": {
        "template": "⚔️ {challenger_name} вызывает на дуэль знаний! Категория: {category}",
        "force": True,
        "sound": "challenge",
        "action": "accept_challenge",
        "ttl": 60,
    },
    "arena.match_ready": {
        "template": "🏟 Матч начинается! Ваш соперник: {opponent_name}",
        "force": True,
        "sound": "match_start",
        "action": "navigate_to_match",
    },

    # Results
    "arena.match_result": {
        "template": "{result_emoji} Дуэль завершена: {result_text}. ELO: {rating_delta}",
        "force": False,
        "sound": "match_end",
    },

    # Achievements
    "arena.achievement": {
        "template": "🏆 Новое достижение: {achievement_name} (+{xp} XP)",
        "force": True,
        "sound": "achievement",
    },

    # Rating changes
    "arena.rating_update": {
        "template": "📊 Ваш рейтинг Арены: {new_rating} ({delta_text})",
        "force": False,
    },

    # Weekly digest
    "arena.weekly_digest": {
        "template": "📋 Еженедельный отчёт Арены: {sessions_count} тестов, accuracy {accuracy}%",
        "force": False,
    },

    # Cross-module
    "arena.knowledge_recommendation": {
        "template": "💡 Рекомендация: Ваш Legal Accuracy в тренировках низкий. Пройдите тест по {category}",
        "force": False,
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def send_arena_notification(
    user_id: uuid.UUID | str,
    event_type: str,
    data: dict,
) -> None:
    """Send an Arena-specific notification via WebSocket.

    Args:
        user_id: Target user ID.
        event_type: One of ARENA_NOTIFICATION_TYPES keys.
        data: Template variables for the notification message.
    """
    config = ARENA_NOTIFICATION_TYPES.get(event_type)
    if not config:
        logger.warning("Unknown arena notification type: %s", event_type)
        return

    # Format message from template
    try:
        message = config["template"].format(**data)
    except KeyError as e:
        logger.error(
            "Missing template var %s for notification %s", e, event_type,
        )
        message = f"Уведомление: {event_type}"

    event = {
        "type": "notification.new",
        "data": {
            "event_type": event_type,
            "message": message,
            "action": config.get("action"),
            "action_data": data,
            "sound": config.get("sound"),
            "ttl": config.get("ttl"),
            "force": config.get("force", False),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    await notification_manager.send_to_user(str(user_id), event)


async def broadcast_arena_notification(
    event_type: str,
    data: dict,
    *,
    exclude_user_id: str | uuid.UUID | None = None,
) -> None:
    """Broadcast an Arena notification to ALL connected users.

    Used for PvP challenge announcements.

    Args:
        event_type: One of ARENA_NOTIFICATION_TYPES keys.
        data: Template variables.
        exclude_user_id: Optional user to exclude (e.g. the challenger).
    """
    config = ARENA_NOTIFICATION_TYPES.get(event_type)
    if not config:
        logger.warning("Unknown arena notification type: %s", event_type)
        return

    try:
        message = config["template"].format(**data)
    except KeyError as e:
        logger.error("Missing template var %s for broadcast %s", e, event_type)
        message = f"Уведомление: {event_type}"

    event = {
        "type": "notification.new",
        "data": {
            "event_type": event_type,
            "message": message,
            "action": config.get("action"),
            "action_data": data,
            "sound": config.get("sound"),
            "ttl": config.get("ttl"),
            "force": config.get("force", False),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    exclude_str = str(exclude_user_id) if exclude_user_id else None

    # Broadcast to all connected users (optionally excluding one)
    for uid, connections in notification_manager.active_connections.items():
        if exclude_str and uid == exclude_str:
            continue
        for ws in connections:
            try:
                await ws.send_json(event)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Weekly leaderboard digest
# ---------------------------------------------------------------------------

async def send_weekly_leaderboard_digest() -> int:
    """Send weekly leaderboard summary to all users with arena ratings.

    Called by scheduler every Monday at 09:00.
    Returns number of notifications sent.
    """
    from app.database import async_session
    from sqlalchemy import select, func
    from app.models.pvp import PvPRating

    sent = 0
    try:
        async with async_session() as db:
            # Get top player
            top_result = await db.execute(
                select(PvPRating)
                .where(PvPRating.rating_type == "knowledge_arena", PvPRating.placement_done.is_(True))
                .order_by(PvPRating.rating.desc())
                .limit(1)
            )
            top_player = top_result.scalar_one_or_none()

            # Get all rated users
            result = await db.execute(
                select(PvPRating)
                .where(PvPRating.rating_type == "knowledge_arena", PvPRating.placement_done.is_(True))
                .order_by(PvPRating.rating.desc())
            )
            ratings = result.scalars().all()

            # Get total count
            total = len(ratings)
            if total == 0:
                return 0

            # Build rank map
            for rank, rating in enumerate(ratings, 1):
                leader_name = "—"
                leader_rating = 0
                if top_player:
                    from app.models.user import User
                    user_result = await db.execute(
                        select(User.full_name).where(User.id == top_player.user_id)
                    )
                    leader_name = user_result.scalar_one_or_none() or "—"
                    leader_rating = round(top_player.rating)

                data = {
                    "sessions_count": rating.total_duels,
                    "accuracy": round(rating.rating),
                    "rank": rank,
                    "total_players": total,
                    "leader_name": leader_name,
                    "leader_rating": leader_rating,
                }

                await send_arena_notification(
                    user_id=rating.user_id,
                    event_type="arena.weekly_digest",
                    data=data,
                )
                sent += 1

    except Exception as e:
        logger.error("Failed to send weekly digest: %s", e)

    logger.info("Weekly arena digest sent to %d users", sent)
    return sent
