"""TZ-2 §12 follow-up policy — canonical TaskFollowUp creation.

Replaces the heuristic-on-emotion logic in ``crm_followup.py`` with a
typed policy that maps a session terminal_outcome to a structured
TaskFollowUp row. Coexists with ``ManagerReminder`` during the
migration window — both tables are written in dual-write mode.

The policy is deliberately small in this PR: only the most common
outcomes get explicit reasons, everything else gets ``manual``. Phase
3 (runtime_guard_engine) will extend the catalog as new emit-sites
land.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead_client import LeadClient, TaskFollowUp
from app.models.training import TrainingSession

logger = logging.getLogger(__name__)


# TZ-2 §12 reason catalog (must match the CHECK constraint in
# 20260425_005_tz2_task_followups.py).
REASONS: frozenset[str] = frozenset({
    "callback_requested",
    "client_requests_later",
    "need_documents_or_time",
    "continue_next_call",
    "needs_followup",
    "documents_required",
    "consent_pending",
    "manual",
})

CHANNELS: frozenset[str] = frozenset({"phone", "chat", "email", "meeting", "sms"})

STATUSES: frozenset[str] = frozenset({"pending", "in_progress", "done", "cancelled"})


# Maps a normalized terminal outcome (from completion_policy.to_tz2_outcome
# or the legacy alias set in crm_followup) to a §12 reason. Falls back to
# "manual" when nothing matches but a follow-up is still wanted.
_OUTCOME_TO_REASON: dict[str, str] = {
    "callback_requested": "callback_requested",
    "callback": "callback_requested",
    "needs_followup": "needs_followup",
    "continue_next_call": "continue_next_call",
    "continue_later": "continue_next_call",
    "documents_required": "documents_required",
    "need_documents": "documents_required",
    "client_requests_later": "client_requests_later",
    "consent_pending": "consent_pending",
}


def reason_for_outcome(outcome: str | None) -> str:
    """Map an outcome to a §12 reason. Returns ``manual`` for unknowns
    so the caller can still record a generic follow-up without bypassing
    the CHECK constraint."""
    if not outcome:
        return "manual"
    return _OUTCOME_TO_REASON.get(outcome.strip().lower(), "manual")


def channel_for_mode(mode: str | None) -> str | None:
    """Pick a default channel from the session mode."""
    if not mode:
        return None
    m = mode.lower()
    if m == "call":
        return "phone"
    if m == "chat":
        return "chat"
    if m == "center":
        return "phone"
    return None


async def ensure_task_followup_for_session(
    db: AsyncSession,
    *,
    session: TrainingSession,
    outcome: str | None,
    domain_event_id: uuid.UUID | None = None,
    delay_hours: int = 24,
) -> TaskFollowUp | None:
    """Idempotently create a TaskFollowUp for a finalized session.

    Idempotency key is ``(lead_client_id, session_id, status='pending')``
    — re-running the policy for the same session returns the existing row
    rather than creating a duplicate. Cancelled / done rows do NOT block
    a new pending one (after the previous one was actioned, the user can
    legitimately need another follow-up for the same session).

    Returns None when:
      * session has no real_client / lead_client (training_simulation)
      * outcome maps to 'manual' AND there is no explicit reason to
        create one (caller should pass an explicit reason then)
    """
    from app.services.runtime_metrics import record_followup_gap

    if session.real_client_id is None and session.lead_client_id is None:
        # Simulation path — expected, not an alert; counted so dashboards
        # can confirm gap-rate matches simulation/real_case ratio.
        record_followup_gap(
            reason="no_real_client",
            outcome=outcome,
            helper="task_followup_policy",
        )
        return None

    lead_id = session.lead_client_id
    if lead_id is None:
        # Resolve through the canonical anchor — same id as real_clients
        # during the migration window.
        existing_lead = await db.get(LeadClient, session.real_client_id)
        if existing_lead is None:
            record_followup_gap(
                reason="no_lead_resolution",
                outcome=outcome,
                helper="task_followup_policy",
            )
            return None
        lead_id = existing_lead.id

    reason = reason_for_outcome(outcome)
    if reason == "manual":
        # Don't auto-create generic follow-ups; let an explicit caller
        # do it with their own context.
        record_followup_gap(
            reason="manual_outcome",
            outcome=outcome,
            helper="task_followup_policy",
        )
        return None

    # Idempotency: existing pending row for the same (lead, session)?
    existing = (
        await db.execute(
            select(TaskFollowUp)
            .where(
                TaskFollowUp.lead_client_id == lead_id,
                TaskFollowUp.session_id == session.id,
                TaskFollowUp.status == "pending",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    due_at = datetime.now(timezone.utc) + timedelta(hours=delay_hours)
    mode = getattr(session, "mode", None) or (session.custom_params or {}).get("session_mode")

    followup = TaskFollowUp(
        id=uuid.uuid4(),
        lead_client_id=lead_id,
        session_id=session.id,
        domain_event_id=domain_event_id,
        reason=reason,
        channel=channel_for_mode(mode),
        due_at=due_at,
        status="pending",
        auto_generated=True,
    )
    db.add(followup)
    await db.flush()
    logger.info(
        "task_followup.created session=%s lead=%s reason=%s due=%s",
        session.id, lead_id, reason, due_at.isoformat(),
    )
    return followup
