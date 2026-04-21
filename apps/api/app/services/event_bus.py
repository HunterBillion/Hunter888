"""Gamification EventBus — transactional outbox pattern (S2-01).

Instead of fire-and-forget handler dispatch, events are persisted in the same
DB transaction as the business logic (outbox_events table).  A background
worker polls the outbox and processes events with retry + dead-letter.

Architecture:
  1. emit() → INSERT into outbox_events (same txn as caller)
  2. OutboxWorker → SELECT FOR UPDATE SKIP LOCKED → handler dispatch
  3. Retry: 3 attempts with exponential backoff (5s, 30s, 120s)
  4. Dead-letter: after max retries → status='failed', alert logged

Usage:
    from app.services.event_bus import event_bus, GameEvent

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
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Awaitable

from sqlalchemy import select, update
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

# Retry backoff schedule (seconds) — index = attempt number (0-based)
RETRY_DELAYS = [5, 30, 120]
MAX_ATTEMPTS = len(RETRY_DELAYS)


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
    """Transactional outbox event bus with background worker processing.

    emit() persists events to the outbox table in the caller's transaction.
    The background worker picks them up and dispatches to handlers with retry.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[HandlerFn]] = {}
        self._worker_task: asyncio.Task | None = None
        self._shutdown = asyncio.Event()

    def on(self, event_kind: str, handler: HandlerFn) -> None:
        """Register a handler for an event kind."""
        self._handlers.setdefault(event_kind, []).append(handler)

    async def emit(
        self,
        event: GameEvent,
        aggregate_id: uuid.UUID | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        """Persist event to outbox table in the caller's transaction.

        The event will be processed by the background worker after commit.
        If the caller's transaction rolls back, the event is also rolled back
        — this is the core guarantee of the outbox pattern.

        Idempotency: when ``idempotency_key`` is passed and the DB already has
        an OutboxEvent with that key (UNIQUE on idempotency_key), we log and
        silently skip. This lets two independent code paths (REST
        `/training/sessions/{id}/end` and WS `session.end` handler) both
        emit ``EVENT_TRAINING_COMPLETED`` for the same session without
        doubling XP / achievements / notifications — only the first arrival
        persists, the second is a safe no-op.

        Args:
            aggregate_id: Optional source entity ID (session_id, duel_id, etc.)
            idempotency_key: Optional dedup key. Auto-generated as
                ``{kind}:{user_id}:{aggregate_id or random}`` when not provided.
        """
        from app.models.outbox import OutboxEvent, OutboxStatus
        from sqlalchemy.exc import IntegrityError

        if idempotency_key is None:
            idempotency_key = (
                f"{event.kind}:{event.user_id}:{aggregate_id or uuid.uuid4()}"
            )

        outbox_event = OutboxEvent(
            id=uuid.uuid4(),
            event_type=event.kind,
            user_id=event.user_id,
            payload=event.payload,
            aggregate_id=aggregate_id,
            idempotency_key=idempotency_key,
            status=OutboxStatus.pending,
            attempts=0,
            max_attempts=MAX_ATTEMPTS,
            next_retry_at=datetime.now(timezone.utc),
        )
        event.db.add(outbox_event)
        # Do NOT commit — the caller's transaction will commit both
        # the business data and the outbox event atomically.
        try:
            await event.db.flush()
        except IntegrityError as exc:
            # Duplicate idempotency_key — another code path already enqueued
            # this event. Roll back the INSERT (otherwise the session is
            # poisoned) and log at INFO so we can observe double-emit
            # attempts without alarming.
            await event.db.rollback()
            logger.info(
                "EventBus emit deduped kind=%s user=%s key=%s (already pending/processed)",
                event.kind, event.user_id, idempotency_key,
            )
            _ = exc  # keep linters happy without noisy log line

    async def emit_immediate(self, event: GameEvent) -> None:
        """Dispatch event directly (legacy path for re-emissions within handlers).

        Used when a handler needs to trigger child events within the same
        worker iteration (e.g., achievement earned → notification).
        These child events are NOT persisted to outbox (already in worker context).
        """
        handlers = self._handlers.get(event.kind, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "EventBus immediate handler %s failed for event %s (user=%s)",
                    handler.__name__, event.kind, event.user_id,
                )

    # ── Background Worker ────────────────────────────────────────────────

    def start_worker(self, poll_interval: float = 1.0) -> None:
        """Start the background outbox worker."""
        if self._worker_task and not self._worker_task.done():
            logger.warning("OutboxWorker already running")
            return
        self._shutdown.clear()
        self._worker_task = asyncio.create_task(
            self._worker_loop(poll_interval),
            name="outbox-worker",
        )
        logger.info("OutboxWorker started (poll_interval=%.1fs)", poll_interval)

    async def stop_worker(self) -> None:
        """Gracefully stop the background worker."""
        self._shutdown.set()
        if self._worker_task:
            try:
                await asyncio.wait_for(self._worker_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("OutboxWorker did not stop in time, cancelling")
                self._worker_task.cancel()
            self._worker_task = None
        logger.info("OutboxWorker stopped")

    async def _worker_loop(self, poll_interval: float) -> None:
        """Main worker loop — polls outbox and processes events."""
        from app.database import async_session

        while not self._shutdown.is_set():
            processed = 0
            try:
                async with async_session() as db:
                    processed = await self._process_batch(db)
            except Exception:
                logger.exception("OutboxWorker batch processing failed")

            # Adaptive polling: faster when events exist, slower when idle
            wait = 0.1 if processed > 0 else poll_interval
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=wait)
                break  # shutdown requested
            except asyncio.TimeoutError:
                pass  # normal timeout, continue polling

    async def _process_batch(self, db: AsyncSession, batch_size: int = 50) -> int:
        """Process a batch of pending outbox events.

        Uses SELECT FOR UPDATE SKIP LOCKED for safe concurrent processing.
        Returns count of processed events.
        """
        from app.models.outbox import OutboxEvent, OutboxStatus

        now = datetime.now(timezone.utc)

        # Fetch pending events ready for processing
        result = await db.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.status.in_([OutboxStatus.pending, OutboxStatus.processing]),
                OutboxEvent.next_retry_at <= now,
            )
            .order_by(OutboxEvent.created_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        events = list(result.scalars().all())

        if not events:
            return 0

        processed = 0
        for outbox_event in events:
            success = await self._process_single(db, outbox_event)
            if success:
                processed += 1

        await db.commit()
        return processed

    async def _process_single(self, db: AsyncSession, outbox_event) -> bool:
        """Process a single outbox event through all registered handlers.

        Returns True if all handlers succeeded, False otherwise.
        """
        from app.models.outbox import OutboxStatus

        handlers = self._handlers.get(outbox_event.event_type, [])
        if not handlers:
            # No handlers for this event type — mark as processed
            outbox_event.status = OutboxStatus.processed
            outbox_event.processed_at = datetime.now(timezone.utc)
            return True

        # Build a GameEvent for handler dispatch
        event = GameEvent(
            kind=outbox_event.event_type,
            user_id=outbox_event.user_id,
            db=db,
            payload=outbox_event.payload or {},
        )

        outbox_event.status = OutboxStatus.processing
        outbox_event.attempts += 1

        try:
            for handler in handlers:
                await handler(event)

            # All handlers succeeded
            outbox_event.status = OutboxStatus.processed
            outbox_event.processed_at = datetime.now(timezone.utc)
            outbox_event.last_error = None
            return True

        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-500:]}"
            outbox_event.last_error = error_msg[:2000]

            if outbox_event.attempts >= outbox_event.max_attempts:
                # Dead-letter: max retries exhausted
                outbox_event.status = OutboxStatus.failed
                logger.error(
                    "DEAD-LETTER: Event %s (type=%s, user=%s) failed after %d attempts: %s",
                    outbox_event.id, outbox_event.event_type,
                    outbox_event.user_id, outbox_event.attempts, error_msg[:200],
                )
            else:
                # Schedule retry with exponential backoff
                delay_idx = min(outbox_event.attempts - 1, len(RETRY_DELAYS) - 1)
                delay = RETRY_DELAYS[delay_idx]
                outbox_event.status = OutboxStatus.pending
                outbox_event.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                logger.warning(
                    "Event %s (type=%s, user=%s) failed attempt %d/%d, retry in %ds: %s",
                    outbox_event.id, outbox_event.event_type,
                    outbox_event.user_id, outbox_event.attempts,
                    outbox_event.max_attempts, delay, str(exc)[:100],
                )

            return False

    # ── Monitoring ─────────────────────────────────────────────────────────

    async def get_outbox_stats(self, db: AsyncSession) -> dict:
        """Get outbox queue statistics for monitoring."""
        from sqlalchemy import func
        from app.models.outbox import OutboxEvent, OutboxStatus

        result = await db.execute(
            select(OutboxEvent.status, func.count(OutboxEvent.id))
            .group_by(OutboxEvent.status)
        )
        stats = dict(result.all())
        return {
            "pending": stats.get(OutboxStatus.pending, 0),
            "processing": stats.get(OutboxStatus.processing, 0),
            "processed": stats.get(OutboxStatus.processed, 0),
            "failed": stats.get(OutboxStatus.failed, 0),
            "worker_running": self._worker_task is not None and not self._worker_task.done(),
        }

    async def retry_failed_events(self, db: AsyncSession, event_id: uuid.UUID | None = None) -> int:
        """Admin action: retry failed (dead-letter) events.

        If event_id is provided, retry only that event.
        Otherwise, retry all failed events.
        """
        from app.models.outbox import OutboxEvent, OutboxStatus

        query = (
            update(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.failed)
            .values(
                status=OutboxStatus.pending,
                attempts=0,
                next_retry_at=datetime.now(timezone.utc),
                last_error=None,
            )
        )
        if event_id:
            query = query.where(OutboxEvent.id == event_id)

        result = await db.execute(query)
        count = result.rowcount or 0
        if count:
            await db.commit()
            logger.info("Retried %d failed outbox events", count)
        return count


# ─── Singleton ───────────────────────────────────────────────────────────────

event_bus = EventBus()


# ─── Built-in handlers ───────────────────────────────────────────────────────

async def _handle_achievements(event: GameEvent) -> None:
    """Check and award achievements after any game event."""
    from app.services.gamification import check_and_award_achievements_with_streak
    newly_earned, streak_days = await check_and_award_achievements_with_streak(event.user_id, event.db)
    if newly_earned:
        logger.info(
            "Awarded %d achievement(s) to user %s: %s",
            len(newly_earned), event.user_id,
            [a.get("slug", a.get("title", "?")) for a in newly_earned],
        )
        # Dispatch child events immediately (within worker context)
        for ach in newly_earned:
            await event_bus.emit_immediate(GameEvent(
                kind=EVENT_ACHIEVEMENT_EARNED,
                user_id=event.user_id,
                db=event.db,
                payload=ach,
            ))

    # Emit streak_updated event (streak reused from achievement check — no extra DB query)
    try:
        if streak_days >= 1:
            await event_bus.emit_immediate(GameEvent(
                kind=EVENT_STREAK_UPDATED,
                user_id=event.user_id,
                db=event.db,
                payload={"streak_days": streak_days},
            ))
    except Exception:
        logger.debug("Streak event emission failed for user %s", event.user_id, exc_info=True)


async def _handle_goals(event: GameEvent) -> None:
    """Check goal completions after training sessions and award XP."""
    from app.services.daily_goals import check_goal_completions
    completed = await check_goal_completions(event.user_id, event.db)
    if not completed:
        return

    logger.info(
        "Completed %d goal(s) for user %s: %s",
        len(completed), event.user_id,
        [g["goal_id"] for g in completed],
    )

    # Award XP for each newly completed goal (with dedup via GoalCompletionLog)
    from app.services.daily_goals import award_goal_xp
    for goal in completed:
        awarded = await award_goal_xp(event.user_id, goal, event.db)
        if awarded:
            goal["xp_awarded"] = True
        await event_bus.emit_immediate(GameEvent(
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
            await event_bus.emit_immediate(GameEvent(
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
    """Push real-time WS notification + Web Push for achievements, goals, level-ups."""
    from app.ws.notifications import notification_manager

    # 1. WebSocket notification (immediate, if tab is open)
    # send_to_user expects (user_id, event: dict) — wrap payload accordingly.
    if event.kind == EVENT_ACHIEVEMENT_EARNED:
        await notification_manager.send_to_user(
            str(event.user_id),
            {"event_type": "achievement.earned", "data": event.payload},
        )
    elif event.kind == EVENT_GOAL_COMPLETED:
        await notification_manager.send_to_user(
            str(event.user_id),
            {"event_type": "goal.completed", "data": event.payload},
        )
    elif event.kind == EVENT_LEVEL_UP:
        await notification_manager.send_to_user(
            str(event.user_id),
            {"event_type": "level.up", "data": event.payload},
        )

    elif event.kind == EVENT_STREAK_UPDATED:
        streak_days = event.payload.get("streak_days", 0)
        if streak_days >= 3:  # Only notify on meaningful streaks
            await notification_manager.send_to_user(
                str(event.user_id),
                {"event_type": "streak.updated", "data": event.payload},
            )

    # 2. Web Push notification (reaches users even when tab is closed)
    try:
        from app.services.web_push import send_push_to_user

        title = ""
        body = ""
        url = None

        if event.kind == EVENT_ACHIEVEMENT_EARNED:
            ach_name = event.payload.get("name", event.payload.get("title", "Достижение"))
            title = "Новое достижение!"
            body = ach_name
            url = "/profile"
        elif event.kind == EVENT_GOAL_COMPLETED:
            goal_label = event.payload.get("label", "Цель")
            goal_xp = event.payload.get("xp", 0)
            title = f"Цель выполнена! +{goal_xp} XP"
            body = goal_label
            url = "/home"
        elif event.kind == EVENT_LEVEL_UP:
            new_level = event.payload.get("new_level", "?")
            title = f"Новый уровень: {new_level}!"
            body = event.payload.get("new_level_name", "Поздравляем с повышением!")
            url = "/profile"
        elif event.kind == EVENT_STREAK_UPDATED:
            streak_days = event.payload.get("streak_days", 0)
            # Push only for milestone streaks
            if streak_days in (3, 7, 14, 21, 30, 60, 90):
                title = f"Серия {streak_days} дней!"
                body = f"Вы тренируетесь {streak_days} дней подряд. Так держать!"
                url = "/home"

        if title:
            await send_push_to_user(
                event.db,
                user_id=event.user_id,
                title=title,
                body=body,
                url=url,
                tag=event.kind,
            )
    except Exception:
        # Web Push is optional — don't block main flow if it fails
        logger.debug("Web Push failed for event %s user %s", event.kind, event.user_id, exc_info=True)


async def _handle_league_xp(event: GameEvent) -> None:
    """Add training XP to weekly league counter."""
    try:
        from app.services.weekly_league import add_weekly_xp
        xp = event.payload.get("xp_earned", 0)
        if xp <= 0:
            # Estimate XP from score if not provided
            score = event.payload.get("score", 0)
            xp = max(10, int(score * 0.5))  # rough estimate
        await add_weekly_xp(event.user_id, xp, event.db)
    except Exception:
        logger.debug("League XP update failed for user %s", event.user_id, exc_info=True)


async def _handle_home_session_to_crm(event: GameEvent) -> None:
    """Auto-create a ClientStory for single-call sessions from /home.

    This makes home sessions appear in the Game CRM kanban board.
    """
    try:
        db = event.db
        session_id = event.payload.get("session_id")
        if not session_id:
            return

        from app.models.training import TrainingSession
        from app.models.roleplay import ClientStory

        session = await db.get(TrainingSession, uuid.UUID(str(session_id)))
        if not session:
            return

        # Only handle home sessions without an existing story
        source = (session.custom_params or {}).get("source") or getattr(session, "source", None)
        if source != "home" or session.client_story_id is not None:
            return

        # Determine lifecycle state from emotion timeline
        emotion_timeline = session.emotion_timeline or []
        final_emotion = "cold"
        if isinstance(emotion_timeline, list) and emotion_timeline:
            last_entry = emotion_timeline[-1]
            if isinstance(last_entry, dict):
                final_emotion = last_entry.get("state", "cold")

        lifecycle_map = {
            "deal": "DEAL_CLOSED",
            "callback": "CALLBACK_SCHEDULED",
            "hostile": "REJECTED",
            "hangup": "REJECTED",
        }
        lifecycle_state = lifecycle_map.get(final_emotion, "FIRST_CONTACT")

        # Create a single-call ClientStory
        story = ClientStory(
            user_id=session.user_id,
            story_name=f"Звонок с /home — {session.started_at.strftime('%d.%m %H:%M') if session.started_at else 'сессия'}",
            total_calls_planned=1,
            current_call_number=1,
            is_completed=True,
            personality_profile=(session.custom_params or {}).get("waiting_client_profile", {}),
            lifecycle_state=lifecycle_state,
            relationship_score=session.score_total or 50.0,
            total_calls=1,
            ended_at=session.ended_at,
        )
        db.add(story)
        await db.flush()

        # Link session to story
        session.client_story_id = story.id
        session.call_number_in_story = 1
        await db.flush()

        logger.info(
            "Home session %s → CRM story %s (lifecycle=%s)",
            session_id, story.id, lifecycle_state,
        )
    except Exception:
        logger.warning(
            "Home→CRM handler failed for session %s",
            event.payload.get("session_id"),
            exc_info=True,
        )


# ─── Tournament Points (TP) handlers — unified tournament economy ─────────────
# Every completed activity (training / PvP / knowledge / story) writes a row to
# `rating_contributions` and, if a tournament is active for this week, ties it
# to that tournament.

def _iso_week_start(dt: datetime) -> "datetime.date":
    """Monday of the ISO week containing dt (UTC)."""
    from datetime import date
    local = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    local_naive = local.astimezone(timezone.utc).date()
    weekday = local_naive.weekday()  # 0 = Monday
    from datetime import timedelta
    return local_naive - timedelta(days=weekday)


async def _write_contribution(
    db: AsyncSession,
    user_id: uuid.UUID,
    source: str,
    source_ref_id: uuid.UUID,
    points: int,
    payload: dict | None,
    earned_at: datetime,
) -> uuid.UUID | None:
    """Idempotent INSERT into rating_contributions. Returns new row id or None if duplicate."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.rating_contribution import RatingContribution

    week_start = _iso_week_start(earned_at)
    new_id = uuid.uuid4()
    stmt = (
        pg_insert(RatingContribution.__table__)
        .values(
            id=new_id,
            user_id=user_id,
            source=source,
            source_ref_id=source_ref_id,
            points=int(points),
            week_start=week_start,
            earned_at=earned_at,
            payload=payload or {},
        )
        .on_conflict_do_nothing(constraint="uq_rating_contrib_source")
        .returning(RatingContribution.id)
    )
    result = await db.execute(stmt)
    row = result.fetchone()
    if row is None:
        return None
    await _try_assign_to_tournament(db, row[0], user_id, source, earned_at, points)
    return row[0]


async def _try_assign_to_tournament(
    db: AsyncSession,
    contribution_id: uuid.UUID,
    user_id: uuid.UUID,
    source: str,
    earned_at: datetime,
    points: int,
) -> None:
    """Find matching active tournament and tag the contribution + upsert TournamentEntry."""
    from app.models.tournament import Tournament, TournamentEntry
    from app.models.rating_contribution import RatingContribution

    try:
        q = await db.execute(
            select(Tournament).where(
                Tournament.is_active == True,  # noqa: E712
                Tournament.week_start <= earned_at,
                Tournament.week_end >= earned_at,
                Tournament.score_source.in_([source, "mixed"]),
            )
        )
        tournaments = q.scalars().all()

        for t in tournaments:
            # Tag contribution
            await db.execute(
                update(RatingContribution)
                .where(RatingContribution.id == contribution_id)
                .values(tournament_id=t.id)
            )

            # Upsert TournamentEntry — sum of contributions for this tournament
            entry_q = await db.execute(
                select(TournamentEntry).where(
                    TournamentEntry.tournament_id == t.id,
                    TournamentEntry.user_id == user_id,
                )
            )
            entry = entry_q.scalar_one_or_none()
            if entry is None:
                entry = TournamentEntry(
                    tournament_id=t.id,
                    user_id=user_id,
                    # session_id is nullable now — keep None for unified TP entries
                    score=float(points),
                    attempt_number=1,
                )
                db.add(entry)
            else:
                entry.score = float(entry.score or 0) + float(points)
                entry.attempt_number = (entry.attempt_number or 0) + 1
    except Exception:
        logger.warning("Failed to assign contribution %s to tournament", contribution_id, exc_info=True)


async def _handle_training_to_tp(event: GameEvent) -> None:
    """EVENT_TRAINING_COMPLETED → write TP contribution."""
    try:
        from app.models.training import TrainingSession
        from app.services.tournament_points import training_to_tp

        session_id = event.payload.get("session_id")
        if not session_id:
            return
        session = await event.db.get(TrainingSession, uuid.UUID(str(session_id)))
        if not session or session.score_total is None:
            return
        # Difficulty from scenario relation — default 5 if missing
        diff = 5
        try:
            from app.models.scenario import Scenario
            scen = await event.db.get(Scenario, session.scenario_id) if session.scenario_id else None
            if scen and getattr(scen, "difficulty", None):
                diff = int(scen.difficulty)
        except Exception:
            pass

        points = training_to_tp(session.score_total, diff)
        await _write_contribution(
            event.db,
            user_id=event.user_id,
            source="training",
            source_ref_id=session.id,
            points=points,
            payload={"score_total": session.score_total, "difficulty": diff},
            earned_at=session.ended_at or session.started_at or datetime.now(timezone.utc),
        )
    except Exception:
        logger.warning("TP handler (training) failed", exc_info=True)


async def _handle_pvp_to_tp(event: GameEvent) -> None:
    """EVENT_PVP_COMPLETED → write TP contribution."""
    try:
        from app.services.tournament_points import pvp_to_tp
        p = event.payload or {}
        duel_id = p.get("duel_id")
        if not duel_id:
            return
        is_winner = bool(p.get("is_winner", False))
        elo_delta = int(p.get("elo_delta", 0) or 0)
        is_pve = bool(p.get("is_pve", False))
        points = pvp_to_tp(is_winner, elo_delta, is_pve)
        await _write_contribution(
            event.db,
            user_id=event.user_id,
            source="pvp",
            source_ref_id=uuid.UUID(str(duel_id)),
            points=points,
            payload={"is_winner": is_winner, "elo_delta": elo_delta, "is_pve": is_pve},
            earned_at=datetime.now(timezone.utc),
        )
    except Exception:
        logger.warning("TP handler (pvp) failed", exc_info=True)


async def _handle_knowledge_to_tp(event: GameEvent) -> None:
    """EVENT_KNOWLEDGE_QUIZ_COMPLETED → write TP contribution."""
    try:
        from app.services.tournament_points import knowledge_to_tp
        p = event.payload or {}
        quiz_session_id = p.get("quiz_session_id") or p.get("session_id")
        if not quiz_session_id:
            return
        correct = int(p.get("correct_answers", 0) or 0)
        total = int(p.get("total_questions", 0) or 0)
        arena_win = p.get("arena_win")
        points = knowledge_to_tp(correct, total, arena_win)
        if points <= 0:
            return
        await _write_contribution(
            event.db,
            user_id=event.user_id,
            source="knowledge",
            source_ref_id=uuid.UUID(str(quiz_session_id)),
            points=points,
            payload={"correct": correct, "total": total, "arena_win": arena_win},
            earned_at=datetime.now(timezone.utc),
        )
    except Exception:
        logger.warning("TP handler (knowledge) failed", exc_info=True)


async def _handle_story_to_tp(event: GameEvent) -> None:
    """EVENT_STORY_COMPLETED → write TP contribution."""
    try:
        from app.services.tournament_points import story_to_tp
        p = event.payload or {}
        story_id = p.get("story_id")
        if not story_id:
            return
        avg = float(p.get("avg_score", 0) or 0)
        calls = int(p.get("calls_completed", 0) or 0)
        full = bool(p.get("fully_completed", False))
        points = story_to_tp(avg, calls, full)
        if points <= 0:
            return
        await _write_contribution(
            event.db,
            user_id=event.user_id,
            source="story",
            source_ref_id=uuid.UUID(str(story_id)),
            points=points,
            payload={"avg_score": avg, "calls_completed": calls, "fully_completed": full},
            earned_at=datetime.now(timezone.utc),
        )
    except Exception:
        logger.warning("TP handler (story) failed", exc_info=True)


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

    # Notifications for earned achievements, completed goals, level ups, streaks
    event_bus.on(EVENT_ACHIEVEMENT_EARNED, _handle_notification)
    event_bus.on(EVENT_GOAL_COMPLETED, _handle_notification)
    event_bus.on(EVENT_LEVEL_UP, _handle_notification)
    event_bus.on(EVENT_STREAK_UPDATED, _handle_notification)

    # Weekly league XP tracking
    event_bus.on(EVENT_TRAINING_COMPLETED, _handle_league_xp)

    # Home sessions → auto-create ClientStory for CRM kanban
    event_bus.on(EVENT_TRAINING_COMPLETED, _handle_home_session_to_crm)

    # Unified tournament economy — every activity feeds TP ledger
    event_bus.on(EVENT_TRAINING_COMPLETED, _handle_training_to_tp)
    event_bus.on(EVENT_PVP_COMPLETED, _handle_pvp_to_tp)
    event_bus.on(EVENT_KNOWLEDGE_QUIZ_COMPLETED, _handle_knowledge_to_tp)
    event_bus.on(EVENT_STORY_COMPLETED, _handle_story_to_tp)

    logger.info("EventBus: registered %d default handlers", sum(
        len(h) for h in event_bus._handlers.values()
    ))
