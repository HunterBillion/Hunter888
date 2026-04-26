from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import ManagerReminder, RealClient
from app.models.training import TrainingSession
from app.services.client_domain import emit_client_event
from app.services.session_state import normalize_session_outcome

logger = logging.getLogger(__name__)


FOLLOW_UP_OUTCOMES = {
    "callback",
    "callback_requested",
    "continue_next_call",
    "continue_later",
    "needs_followup",
    "scheduled_callback",
}

FOLLOW_UP_EMOTIONS = {
    "callback",
    "considering",
    "negotiating",
}

def _last_emotion_state(emotion_timeline: Any) -> str | None:
    timeline = emotion_timeline
    if isinstance(timeline, dict):
        timeline = timeline.get("timeline") or timeline.get("events")
    if not isinstance(timeline, list):
        return None

    for item in reversed(timeline):
        if isinstance(item, dict):
            state = item.get("state") or item.get("emotion")
            if state:
                return str(state)
    return None


def infer_followup_outcome(session: TrainingSession) -> str | None:
    details = session.scoring_details or {}
    for key in ("call_outcome", "outcome", "result"):
        value = details.get(key)
        if value:
            return normalize_session_outcome(value)
    return _last_emotion_state(session.emotion_timeline)


def should_create_followup(outcome: str | None) -> bool:
    normalized = normalize_session_outcome(outcome)
    if not normalized:
        return False
    return normalized in FOLLOW_UP_OUTCOMES or normalized in FOLLOW_UP_EMOTIONS


async def ensure_followup_for_session(
    db: AsyncSession,
    session: TrainingSession,
    *,
    outcome: str | None = None,
    delay_hours: int = 24,
) -> ManagerReminder | None:
    """Create one CRM follow-up reminder when a linked session needs continuation."""
    if not session.real_client_id:
        return None

    explicit_outcome = normalize_session_outcome(outcome)
    effective_outcome = explicit_outcome or infer_followup_outcome(session)
    if not should_create_followup(effective_outcome):
        return None

    session_marker = session.id.hex[:8]
    existing = (await db.execute(
        select(ManagerReminder)
        .where(
            ManagerReminder.client_id == session.real_client_id,
            ManagerReminder.auto_generated == True,  # noqa: E712
            ManagerReminder.is_completed == False,  # noqa: E712
            ManagerReminder.message.contains(session_marker),
        )
        .limit(1)
    )).scalar_one_or_none()
    if existing:
        return existing

    client = await db.get(RealClient, session.real_client_id)
    if client is None:
        return None

    now = datetime.now(timezone.utc)
    planned_at = client.next_contact_at
    if planned_at is None or planned_at <= now:
        planned_at = now + timedelta(hours=delay_hours)
        client.next_contact_at = planned_at

    reminder = ManagerReminder(
        id=uuid.uuid4(),
        manager_id=session.user_id,
        client_id=session.real_client_id,
        remind_at=planned_at,
        message=(
            f"Повторный контакт после тренировки #{session_marker}: "
            "клиент хочет продолжить разговор"
        ),
        auto_generated=True,
    )
    db.add(reminder)

    domain_event = await emit_client_event(
        db,
        client=client,
        event_type="crm.reminder_created",
        actor_type="system",
        actor_id=session.user_id,
        source="crm_followup",
        payload={
            "reminder_id": str(reminder.id),
            "remind_at": planned_at.isoformat(),
            "session_id": str(session.id),
            "outcome": effective_outcome,
            "auto_generated": True,
            "next_contact_at": planned_at.isoformat(),
        },
        aggregate_type="manager_reminder",
        aggregate_id=reminder.id,
        session_id=session.id,
        idempotency_key=f"crm-followup:{session.id}:{session_marker}",
        correlation_id=str(session.id),
    )

    # TZ-2 §12 dual-write: also create the canonical TaskFollowUp row,
    # linked to the same domain_event for the timeline join. Failure here
    # is logged but doesn't block the legacy ManagerReminder write — the
    # canonical table is still in adoption phase.
    try:
        from app.services.task_followup_policy import ensure_task_followup_for_session

        await ensure_task_followup_for_session(
            db,
            session=session,
            outcome=effective_outcome,
            domain_event_id=getattr(domain_event, "id", None),
            delay_hours=int((planned_at - now).total_seconds() // 3600) or 24,
        )
    except Exception:
        logger.warning(
            "task_followup dual-write failed for session %s — legacy reminder kept",
            session.id, exc_info=True,
        )

    return reminder
