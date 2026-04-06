"""Gamification EventBus — centralised async event dispatch (Wave 1, Task 1.6).

Instead of scattered `check_and_award_achievements` / `check_goal_completions`
calls after every session, callers emit a typed event and the bus routes it
to all registered handlers (achievements, goals, XP, notifications).

Usage:
    from app.services.event_bus import event_bus, GameEvent

    # After training session completes:
    await event_bus.emit(GameEvent(
        kind="training_completed",
        user_id=user.id,
        db=db,
        payload={"score": 85.0, "session_id": str(session.id)},
    ))
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ─── Event types ─────────────────────────────────────────────────────────────

EVENT_TRAINING_COMPLETED = "training_completed"
EVENT_ARENA_COMPLETED = "arena_completed"
EVENT_PVP_COMPLETED = "pvp_completed"
EVENT_STORY_COMPLETED = "story_completed"
EVENT_STREAK_UPDATED = "streak_updated"
EVENT_LEVEL_UP = "level_up"
EVENT_ACHIEVEMENT_EARNED = "achievement_earned"
EVENT_GOAL_COMPLETED = "goal_completed"
EVENT_KNOWLEDGE_QUIZ_COMPLETED = "knowledge_quiz_completed"

ALL_EVENTS = {
    EVENT_TRAINING_COMPLETED,
    EVENT_ARENA_COMPLETED,
    EVENT_PVP_COMPLETED,
    EVENT_STORY_COMPLETED,
    EVENT_STREAK_UPDATED,
    EVENT_LEVEL_UP,
    EVENT_ACHIEVEMENT_EARNED,
    EVENT_GOAL_COMPLETED,
    EVENT_KNOWLEDGE_QUIZ_COMPLETED,
}


@dataclass
class GameEvent:
    """Typed event payload flowing through the bus."""
    kind: str
    user_id: uuid.UUID
    db: AsyncSession
    payload: dict[str, Any] = field(default_factory=dict)


# Handler signature: async (event: GameEvent) -> None
HandlerFn = Callable[[GameEvent], Awaitable[None]]


class EventBus:
    """In-process async event bus with ordered handler dispatch."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[HandlerFn]] = {}

    def on(self, event_kind: str, handler: HandlerFn) -> None:
        """Register a handler for an event kind."""
        self._handlers.setdefault(event_kind, []).append(handler)

    async def emit(self, event: GameEvent) -> None:
        """Dispatch event to all registered handlers.

        Handlers run sequentially so DB session is safe.
        Individual handler errors are logged but don't block others.
        """
        handlers = self._handlers.get(event.kind, [])
        if not handlers:
            return

        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "EventBus handler %s failed for event %s (user=%s)",
                    handler.__name__, event.kind, event.user_id,
                )


# ─── Singleton ───────────────────────────────────────────────────────────────

event_bus = EventBus()


# ─── Built-in handlers ───────────────────────────────────────────────────────

async def _handle_achievements(event: GameEvent) -> None:
    """Check and award achievements after any game event."""
    from app.services.gamification import check_and_award_achievements
    newly_earned = await check_and_award_achievements(event.user_id, event.db)
    if newly_earned:
        logger.info(
            "Awarded %d achievement(s) to user %s: %s",
            len(newly_earned), event.user_id,
            [a.get("slug", a.get("title", "?")) for a in newly_earned],
        )
        # Re-emit so notification handler can pick them up
        for ach in newly_earned:
            await event_bus.emit(GameEvent(
                kind=EVENT_ACHIEVEMENT_EARNED,
                user_id=event.user_id,
                db=event.db,
                payload=ach,
            ))


async def _handle_goals(event: GameEvent) -> None:
    """Check goal completions after training sessions."""
    from app.services.daily_goals import check_goal_completions
    completed = await check_goal_completions(event.user_id, event.db)
    if completed:
        logger.info(
            "Completed %d goal(s) for user %s: %s",
            len(completed), event.user_id,
            [g["goal_id"] for g in completed],
        )
        for goal in completed:
            await event_bus.emit(GameEvent(
                kind=EVENT_GOAL_COMPLETED,
                user_id=event.user_id,
                db=event.db,
                payload=goal,
            ))


async def _handle_arena_achievements(event: GameEvent) -> None:
    """Check arena-specific achievements after arena/pvp events."""
    from app.services.gamification import check_arena_achievements
    newly_earned = await check_arena_achievements(event.user_id, event.db)
    if newly_earned:
        logger.info(
            "Awarded %d arena achievement(s) to user %s",
            len(newly_earned), event.user_id,
        )
        for ach in newly_earned:
            await event_bus.emit(GameEvent(
                kind=EVENT_ACHIEVEMENT_EARNED,
                user_id=event.user_id,
                db=event.db,
                payload=ach,
            ))


async def _handle_training_to_srs(event: GameEvent) -> None:
    """Feed weak legal areas from training into Knowledge SRS system.

    When a training session's L10 legal accuracy reveals weak categories,
    seed SRS entries so the user gets targeted review in Knowledge Quiz.
    """
    from app.services.spaced_repetition import record_review

    weak_categories = event.payload.get("weak_legal_categories", [])
    if not weak_categories:
        return

    seeded = 0
    for cat in weak_categories[:5]:  # cap at 5 per session
        category = cat.get("category", "")
        article_refs = cat.get("article_refs", [])
        if not category:
            continue
        # Create SRS entries for each article reference in the weak category
        for ref in article_refs[:3]:  # cap at 3 refs per category
            try:
                await record_review(
                    event.db,
                    user_id=event.user_id,
                    question_text=f"Повторить: {ref} ({cat.get('display_name', category)})",
                    question_category=category,
                    is_correct=False,  # Mark as incorrect to prioritize review
                    response_time_ms=None,
                    hint_used=False,
                )
                seeded += 1
            except Exception:
                logger.warning(
                    "Failed to seed SRS for user=%s category=%s ref=%s",
                    event.user_id, category, ref, exc_info=True,
                )

    if seeded:
        logger.info(
            "Seeded %d SRS entries from training weak areas for user %s",
            seeded, event.user_id,
        )


async def _handle_notification(event: GameEvent) -> None:
    """Push real-time WS notification for achievements and goals."""
    from app.ws.notifications import notification_manager

    if event.kind == EVENT_ACHIEVEMENT_EARNED:
        await notification_manager.send_to_user(
            str(event.user_id),
            event_type="achievement.earned",
            data=event.payload,
        )
    elif event.kind == EVENT_GOAL_COMPLETED:
        await notification_manager.send_to_user(
            str(event.user_id),
            event_type="goal.completed",
            data=event.payload,
        )
    elif event.kind == EVENT_LEVEL_UP:
        await notification_manager.send_to_user(
            str(event.user_id),
            event_type="level.up",
            data=event.payload,
        )


# ─── Registration ────────────────────────────────────────────────────────────

def setup_default_handlers() -> None:
    """Register all built-in handlers. Call once at app startup."""
    # Training → achievements + goals
    event_bus.on(EVENT_TRAINING_COMPLETED, _handle_achievements)
    event_bus.on(EVENT_TRAINING_COMPLETED, _handle_goals)

    # Training → feed weak legal areas into Knowledge SRS
    event_bus.on(EVENT_TRAINING_COMPLETED, _handle_training_to_srs)

    # Story completion → achievements
    event_bus.on(EVENT_STORY_COMPLETED, _handle_achievements)

    # Arena/PvP → arena achievements
    event_bus.on(EVENT_ARENA_COMPLETED, _handle_arena_achievements)
    event_bus.on(EVENT_PVP_COMPLETED, _handle_arena_achievements)

    # Knowledge quiz → achievements
    event_bus.on(EVENT_KNOWLEDGE_QUIZ_COMPLETED, _handle_achievements)

    # Notifications for earned achievements, completed goals, level ups
    event_bus.on(EVENT_ACHIEVEMENT_EARNED, _handle_notification)
    event_bus.on(EVENT_GOAL_COMPLETED, _handle_notification)
    event_bus.on(EVENT_LEVEL_UP, _handle_notification)

    logger.info("EventBus: registered %d default handlers", sum(
        len(h) for h in event_bus._handlers.values()
    ))
