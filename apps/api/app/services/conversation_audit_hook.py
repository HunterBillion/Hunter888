"""Runtime audit hook that connects the WS message-out path to the
TZ-4 conversation policy engine + ws_outbox push surface.

Why this module exists
----------------------

D5 added :mod:`app.services.conversation_policy_engine` with six
canonical checks and an emit-violation helper, but no production code
was calling them yet — the engine was a primitive, not an active
guard. D6 added FE badges (:py:`PolicyViolationCounter`,
:py:`PersonaConflictBadge`) that self-hide at zero and wait for events
to fire.

D7.6 (this module) is the missing wiring: a single function the WS
training handler calls after every assistant message lands, which:

  1. Loads the per-session persona context
     (:class:`SessionPersonaSnapshot` + :class:`MemoryPersona` if any)
     so the persona-aware checks can fire.
  2. Calls :func:`engine.audit_assistant_reply` against the saved
     reply + last-N assistant replies for the near-repeat check.
  3. Persists every violation as a
     ``conversation.policy_violation_detected`` Domain Event via
     :func:`engine.emit_violation`.
  4. Bumps :func:`persona_memory.record_conflict_attempt` when the
     audit surfaces ``unjustified_identity_change`` — the snapshot
     drift counter is the §9.2 invariant 1 observability hook.
  5. Pushes one WS outbox event per violation to the session's
     manager so the FE badges go live in real time.

Failure mode: the hook NEVER raises into the WS handler. Audit is a
side-channel concern; an audit/emit/push failure must not surface to
the manager as a 5xx or a dropped reply. All errors are swallowed
with a loud log; the regression alarm is the absence of expected
events in the timeline.

Warn-only contract (§12.3.1): every code path here runs in warn-only
mode by default. The engine's :func:`enforce_enabled` controls the
``should_block`` flag inside :class:`PolicyAuditResult`, but **this
hook intentionally does not block** even when ``should_block`` is
True — message blocking belongs in the producer (LLM call site), not
in the post-save audit. The hook only writes audit signals; D7.2
will land the producer-side block once warn-only telemetry justifies
the flip.
"""
from __future__ import annotations

import logging
import uuid
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.persona import MemoryPersona, SessionPersonaSnapshot
from app.services import conversation_policy_engine as engine
from app.services import persona_memory
from app.services.ws_delivery import enqueue as ws_enqueue

logger = logging.getLogger(__name__)


# Public WS event types — kept stable so the FE subscription doesn't
# drift when we extend the audit surface.
WS_EVENT_POLICY_VIOLATION = "conversation.policy_violation_detected"
WS_EVENT_PERSONA_CONFLICT = "persona.conflict_detected"


async def audit_and_publish_assistant_reply(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    reply: str,
    previous_assistant_replies: Sequence[str] | None = None,
    mode: object | None = None,
) -> int:
    """Run the §10.2 audit on a freshly-saved assistant reply and fan
    out every violation to the canonical event log + WS outbox.

    Returns the number of violations emitted (zero on the happy path).
    Always returns — never raises into the caller. Exceptions are
    logged and swallowed because audit is a side-channel concern.
    """
    if not reply or not reply.strip():
        return 0

    try:
        snapshot = await _load_snapshot(db, session_id=session_id)
        persona = await _load_persona(db, snapshot=snapshot)
    except Exception:  # pragma: no cover — defensive
        logger.exception(
            "conversation_audit_hook.load_persona_context_failed session=%s",
            session_id,
        )
        snapshot = None
        persona = None

    try:
        result = engine.audit_assistant_reply(
            reply=reply,
            mode=mode,
            previous_assistant_replies=previous_assistant_replies,
            snapshot=snapshot,
            persona=persona,
        )
    except Exception:  # pragma: no cover — defensive
        logger.exception(
            "conversation_audit_hook.audit_failed session=%s", session_id,
        )
        return 0

    if result.is_clean:
        return 0

    # Persist every violation as a canonical DomainEvent.
    try:
        await engine.emit_violation(
            db,
            result=result,
            session_id=session_id,
            lead_client_id=snapshot.lead_client_id if snapshot else None,
            actor_id=user_id,
            source="ws.training.audit_hook",
        )
    except Exception:  # pragma: no cover — defensive
        logger.exception(
            "conversation_audit_hook.emit_violation_failed session=%s",
            session_id,
        )

    # If the audit surfaced an identity change, record a snapshot
    # drift attempt so the §9.2 invariant 1 counter bumps. This is
    # the bridge from "audit caught it" to "snapshot observability".
    if snapshot is not None:
        for v in result.violations:
            if v.code == engine.ViolationCode.UNJUSTIFIED_IDENTITY_CHANGE:
                try:
                    await persona_memory.record_conflict_attempt(
                        db,
                        snapshot=snapshot,
                        attempted_field="address_form",
                        attempted_value=v.evidence,
                        actor_id=user_id,
                        source="ws.training.audit_hook",
                    )
                except Exception:  # pragma: no cover — defensive
                    logger.exception(
                        "conversation_audit_hook.record_conflict_failed "
                        "session=%s",
                        session_id,
                    )
                break  # one per audit run is enough

    # Fan out to the WS outbox so the manager's session UI picks up
    # the live signal. We send one WS event per violation so the FE
    # PolicyViolationCounter can update its severity buckets without
    # decoding nested arrays. The persona-conflict counter is fed by
    # a second event class with a richer payload.
    try:
        await _push_violations_to_ws(
            db,
            user_id=user_id,
            session_id=session_id,
            result=result,
        )
    except Exception:  # pragma: no cover — defensive
        logger.exception(
            "conversation_audit_hook.ws_push_failed session=%s", session_id,
        )

    return len(result.violations)


async def _load_snapshot(
    db: AsyncSession, *, session_id: uuid.UUID
) -> SessionPersonaSnapshot | None:
    return (
        await db.execute(
            select(SessionPersonaSnapshot).where(
                SessionPersonaSnapshot.session_id == session_id
            )
        )
    ).scalar_one_or_none()


async def _load_persona(
    db: AsyncSession, *, snapshot: SessionPersonaSnapshot | None
) -> MemoryPersona | None:
    if snapshot is None or snapshot.lead_client_id is None:
        return None
    return (
        await db.execute(
            select(MemoryPersona).where(
                MemoryPersona.lead_client_id == snapshot.lead_client_id
            )
        )
    ).scalar_one_or_none()


async def _push_violations_to_ws(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    result: engine.PolicyAuditResult,
) -> None:
    """Dual publish: durable WS outbox (drainable on reconnect) + live
    push via :mod:`app.ws.notifications` manager so connected
    sessions receive the frame in-tab without polling.

    Persona-identity violations also publish a
    ``persona.conflict_detected`` frame so the dedicated badge can
    count them separately from the generic policy counter.
    """
    # Live-push helper. Imported lazily so a notifications-module
    # bootstrap failure (rare, but possible during shutdown) doesn't
    # take the audit path with it.
    try:
        from app.ws.notifications import send_ws_notification as _live_push
    except Exception:  # pragma: no cover — defensive
        _live_push = None  # type: ignore[assignment]

    for v in result.violations:
        policy_payload = {
            "session_id": str(session_id),
            "code": v.code.value,
            "severity": v.severity,
            "message": v.message,
            "evidence": v.evidence,
            "enforce_active": result.enforce_active,
        }
        await ws_enqueue(
            db,
            user_id=user_id,
            event_type=WS_EVENT_POLICY_VIOLATION,
            payload=policy_payload,
            correlation_id=str(session_id),
        )
        if _live_push is not None:
            try:
                await _live_push(
                    user_id,
                    event_type=WS_EVENT_POLICY_VIOLATION,
                    data=policy_payload,
                )
            except Exception:  # pragma: no cover — defensive
                logger.exception(
                    "conversation_audit_hook.live_push_policy_failed session=%s",
                    session_id,
                )

        if v.code in {
            engine.ViolationCode.PERSONA_CONFLICT,
            engine.ViolationCode.UNJUSTIFIED_IDENTITY_CHANGE,
            engine.ViolationCode.ASKED_KNOWN_SLOT_AGAIN,
        }:
            persona_payload = {
                "session_id": str(session_id),
                "code": v.code.value,
                "attempted_field": v.evidence.get("attempted_field")
                if isinstance(v.evidence, dict)
                else None,
                "evidence": v.evidence,
            }
            await ws_enqueue(
                db,
                user_id=user_id,
                event_type=WS_EVENT_PERSONA_CONFLICT,
                payload=persona_payload,
                correlation_id=str(session_id),
            )
            if _live_push is not None:
                try:
                    await _live_push(
                        user_id,
                        event_type=WS_EVENT_PERSONA_CONFLICT,
                        data=persona_payload,
                    )
                except Exception:  # pragma: no cover — defensive
                    logger.exception(
                        "conversation_audit_hook.live_push_persona_failed session=%s",
                        session_id,
                    )


def previous_assistant_replies_from_history(
    history: Iterable[dict], *, limit: int = 5
) -> list[str]:
    """Helper for the WS handler — slice the last N assistant turns
    out of the full message history. Encapsulated here so the hook
    owns the contract (the engine's near-repeat check expects a list
    of strings, ordered most-recent-last is fine since the check
    iterates them all)."""
    out: list[str] = []
    for m in history:
        if m.get("role") == "assistant":
            content = m.get("content")
            if isinstance(content, str) and content.strip():
                out.append(content)
    return out[-limit:]


__all__ = [
    "WS_EVENT_PERSONA_CONFLICT",
    "WS_EVENT_POLICY_VIOLATION",
    "audit_and_publish_assistant_reply",
    "previous_assistant_replies_from_history",
]
