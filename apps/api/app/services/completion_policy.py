"""ConversationCompletionPolicy — unified terminal contract (Roadmap §6).

Before this module the platform had **seven** independent terminal paths
(REST end, WS end, emotion-fsm hangup, AI farewell, silence watchdog, WS
disconnect handler, PvP finalize). Each did a subset of the work:

* some saved scores, some didn't;
* two wrote ``ClientInteraction`` via ``log_training_real_case_summary``,
  five skipped it;
* three emitted ``EVENT_TRAINING_COMPLETED``, four didn't;
* silence/disconnect paths marked sessions ``abandoned``/``error``
  without follow-up reminder or CRM row, so the training never appeared
  in the manager's CRM timeline even though it happened.

This drift is the root cause RC-2: a terminal fact (the session ended)
produced different downstream state depending on *which* code path
ran. Downstream consumers — coach grader, XP award, CRM, analytics —
ended up with mismatched views.

``ConversationCompletionPolicy`` consolidates the post-terminal tail
(follow-up + CRM dual-write + canonical DomainEvent) behind one
function plus an explicit ``validate`` step that catches obvious
contract breaches early (e.g. hangup outcome on a center session).

The roll-out is two-phased:

1. **Phase A (``completion_policy_strict=False``, default).** Every
   terminal path calls ``finalize_training_session`` but the legacy
   side-effect block above it continues to do its own work. Policy
   ONLY stamps the three new columns (``terminal_outcome``/
   ``terminal_reason``/``completed_via``) and emits the canonical
   ``session.completed`` DomainEvent. No risk of regressing existing
   behaviour because the legacy code still runs.
2. **Phase B (``completion_policy_strict=True``, post-parity).** The
   legacy side-effect blocks short-circuit and the policy becomes
   authoritative for follow-up + CRM + event emit. Enabled per-env
   after 48h shadow parity observation.

All methods are idempotent by design: re-running ``finalize_*`` with
the same ``session_id`` + ``outcome`` reads the already-stamped columns
and returns the cached ``CompletionResult`` without re-emitting.
"""

from __future__ import annotations

import enum
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.pvp import PvPDuel
from app.models.training import SessionStatus, TrainingSession

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────


class TerminalOutcome(str, enum.Enum):
    """Normalized completion outcomes covering training + PvP.

    Training modes:
      * ``success`` — deal agreed / consultation booked
      * ``hard_reject`` — explicit "no, stop calling"
      * ``needs_followup`` — soft "let me think", explicit callback
      * ``need_documents`` — client promised to send paperwork
      * ``callback_requested`` — scheduled exact time
      * ``no_answer`` — did not pick up / hung up immediately
      * ``hangup`` — client ended the call mid-conversation
      * ``timeout`` — silence-watchdog expiry
      * ``technical_failed`` — LLM/STT/judge pipeline error
      * ``operator_aborted`` — user/system ended without a business outcome

    PvP modes:
      * ``pvp_win`` / ``pvp_loss`` / ``pvp_draw`` / ``pvp_abandoned``
    """

    success = "success"
    hard_reject = "hard_reject"
    needs_followup = "needs_followup"
    need_documents = "need_documents"
    callback_requested = "callback_requested"
    no_answer = "no_answer"
    hangup = "hangup"
    timeout = "timeout"
    technical_failed = "technical_failed"
    operator_aborted = "operator_aborted"

    pvp_win = "pvp_win"
    pvp_loss = "pvp_loss"
    pvp_draw = "pvp_draw"
    pvp_abandoned = "pvp_abandoned"


# TZ-2 §6.5 canonical outcome catalog. Internal TerminalOutcome values
# above predate the spec — they are kept for backward compatibility, but
# anything written to a CRM-facing surface (DomainEvent payload, follow-up
# policy lookup, dashboards) must speak the canonical names below.
# `to_tz2_outcome()` is the single mapper.
TZ2_CANONICAL_OUTCOMES: frozenset[str] = frozenset({
    "deal_agreed",
    "deal_not_agreed",
    "continue_next_call",
    "needs_followup",
    "documents_required",
    "callback_requested",
    "client_unreachable",
    "user_cancelled",
    "timeout",
    "error",
})

# Legacy → TZ-2 §6.5 mapping. Anything not in this map (e.g. PvP outcomes)
# is **not** a CRM-relevant outcome and to_tz2_outcome returns None for
# them so callers can decide to skip the CRM-facing emit instead of
# stamping a non-canonical value into a canonical column.
_LEGACY_TO_TZ2: dict[str, str] = {
    "success": "deal_agreed",
    "hard_reject": "deal_not_agreed",
    "needs_followup": "needs_followup",
    "need_documents": "documents_required",
    "callback_requested": "callback_requested",
    "no_answer": "client_unreachable",
    "hangup": "continue_next_call",
    "timeout": "timeout",
    "technical_failed": "error",
    "operator_aborted": "user_cancelled",
}


def to_tz2_outcome(value) -> str | None:
    """Normalize any legacy/canonical outcome string to the TZ-2 §6.5 catalog.

    Returns None if the value is not a CRM-relevant training outcome
    (e.g. PvP outcomes, unknown strings) — callers should skip the
    canonical-column write in that case rather than stamp a non-canonical
    value, which would defeat the lattice.
    """
    if value is None:
        return None
    raw = value.value if isinstance(value, enum.Enum) else str(value)
    raw = raw.strip().lower()
    if raw in TZ2_CANONICAL_OUTCOMES:
        return raw
    return _LEGACY_TO_TZ2.get(raw)


class TerminalReason(str, enum.Enum):
    """How the terminal event was triggered (diagnostic/analytics)."""

    user_ended = "user_ended"
    user_farewell_detected = "user_farewell_detected"
    client_farewell_detected = "client_farewell_detected"
    silence_timeout = "silence_timeout"
    ws_disconnect = "ws_disconnect"
    route_navigation = "route_navigation"
    matchmaking_timeout = "matchmaking_timeout"
    judge_failed = "judge_failed"
    judge_completed = "judge_completed"
    admin_aborted = "admin_aborted"


class CompletedVia(str, enum.Enum):
    """Which code path actually produced the completion record."""

    rest = "rest"
    ws = "ws"
    fsm = "fsm"
    timeout = "timeout"
    disconnect = "disconnect"
    pvp = "pvp"


_TRAINING_OUTCOMES = frozenset({
    TerminalOutcome.success,
    TerminalOutcome.hard_reject,
    TerminalOutcome.needs_followup,
    TerminalOutcome.need_documents,
    TerminalOutcome.callback_requested,
    TerminalOutcome.no_answer,
    TerminalOutcome.hangup,
    TerminalOutcome.timeout,
    TerminalOutcome.technical_failed,
    TerminalOutcome.operator_aborted,
})

_PVP_OUTCOMES = frozenset({
    TerminalOutcome.pvp_win,
    TerminalOutcome.pvp_loss,
    TerminalOutcome.pvp_draw,
    TerminalOutcome.pvp_abandoned,
})

# Center-mode sessions never "hang up" — the trainee is physically in a
# consultation room, not on a phone. Silence/disconnect outcomes can still
# fire for center sessions (the WS can drop) but ``hangup`` cannot.
_FORBIDDEN_BY_MODE: dict[str, frozenset[TerminalOutcome]] = {
    "center": frozenset({TerminalOutcome.hangup, TerminalOutcome.no_answer}),
}


class InvalidTerminalOutcome(ValueError):
    """Raised when an outcome is illegal for the mode."""


class InsufficientSessionActivity(ValueError):
    """Raised when the session has no recorded activity to finalize.

    Kept distinct from ``InvalidTerminalOutcome`` so callers can choose
    to auto-demote such cases to ``operator_aborted`` without retrying.
    """


# ── Result dataclass ─────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CompletionResult:
    session_id: uuid.UUID
    outcome: TerminalOutcome
    reason: TerminalReason
    completed_via: CompletedVia
    strict_mode: bool
    already_completed: bool
    events_emitted: tuple[str, ...]
    followup_id: uuid.UUID | None
    # F-L7-2 fix: explicit record of tail-step failures so callers can
    # alert/retry instead of treating a silently-caught exception as
    # success. Empty tuple = all steps either ran or were not requested.
    failures: tuple[str, ...] = ()


# ── Validation ───────────────────────────────────────────────────────────


def _session_mode(session: TrainingSession) -> str:
    params = session.custom_params or {}
    return (params.get("session_mode") or getattr(session, "source", None) or "chat").lower()


def validate(
    mode: str,
    outcome: TerminalOutcome,
    session: TrainingSession | None = None,
    *,
    is_pvp: bool = False,
) -> None:
    """Validate the (mode, outcome) pair before the finalize step.

    Centralised so every producer hits the same rules. Producer code can
    call this before collecting side effects (cheap) or skip it and
    rely on ``finalize_*`` (which also calls validate).
    """
    if is_pvp:
        if outcome not in _PVP_OUTCOMES:
            raise InvalidTerminalOutcome(
                f"Outcome {outcome.value} not allowed for PvP terminal contract"
            )
        return
    if outcome not in _TRAINING_OUTCOMES:
        raise InvalidTerminalOutcome(
            f"Outcome {outcome.value} not allowed for training terminal contract"
        )
    forbidden = _FORBIDDEN_BY_MODE.get(mode, frozenset())
    if outcome in forbidden:
        raise InvalidTerminalOutcome(
            f"Outcome {outcome.value} forbidden for mode={mode}"
        )


# ── Finalize — training sessions ─────────────────────────────────────────


async def finalize_training_session(
    db: AsyncSession,
    *,
    session: TrainingSession,
    outcome: TerminalOutcome,
    reason: TerminalReason,
    completed_via: CompletedVia,
    manager_id: uuid.UUID | None,
    allow_already_completed: bool = True,
    emit_followup: bool | None = None,
    emit_crm: bool | None = None,
    emit_gamification: bool | None = None,
) -> CompletionResult:
    """Stamp terminal columns + run the unified completion tail.

    When ``completion_policy_strict=False`` the tail is SKIPPED — the
    legacy side-effect blocks in the producers still own it. The policy
    only stamps the three new columns + emits the canonical DomainEvent.

    When ``completion_policy_strict=True`` the policy performs (in order,
    all in the caller's transaction):
      1. follow-up reminder via ``crm_followup.ensure_followup_for_session``
      2. CRM dual-write via
         ``client_domain.log_training_real_case_summary``
      3. gamification emit via ``event_bus.emit(EVENT_TRAINING_COMPLETED)``
    """
    mode = _session_mode(session)
    validate(mode, outcome, session=session, is_pvp=False)

    # Idempotency: a second call with the same outcome on an already-
    # finalized row is a no-op that returns the cached decision. This
    # matches the behaviour of ``event_bus.emit`` dedup keyed by
    # ``training_completed:{session_id}``.
    if session.terminal_outcome is not None:
        if not allow_already_completed:
            raise InvalidTerminalOutcome(
                f"Session {session.id} already finalized as "
                f"{session.terminal_outcome}"
            )
        try:
            cached_outcome = TerminalOutcome(session.terminal_outcome)
        except ValueError:
            cached_outcome = outcome
        try:
            cached_reason = TerminalReason(session.terminal_reason or reason.value)
        except ValueError:
            cached_reason = reason
        try:
            cached_via = CompletedVia(session.completed_via or completed_via.value)
        except ValueError:
            cached_via = completed_via
        return CompletionResult(
            session_id=session.id,
            outcome=cached_outcome,
            reason=cached_reason,
            completed_via=cached_via,
            strict_mode=bool(settings.completion_policy_strict),
            already_completed=True,
            events_emitted=(),
            followup_id=None,
        )

    # Phase A/B stamping — always done regardless of strict mode. This is
    # the cheapest, safest change and gives us parity telemetry.
    session.terminal_outcome = outcome.value
    session.terminal_reason = reason.value
    session.completed_via = completed_via.value
    if session.status == SessionStatus.active:
        session.status = SessionStatus.completed
    if session.ended_at is None:
        session.ended_at = datetime.now(UTC)

    # Keep scoring_details.call_outcome in sync for legacy readers that
    # still peek there. Delete once every consumer reads terminal_outcome.
    scoring_details = dict(session.scoring_details or {})
    scoring_details.setdefault("call_outcome", outcome.value)
    scoring_details["terminal_outcome"] = outcome.value
    scoring_details["terminal_reason"] = reason.value
    session.scoring_details = scoring_details

    strict = bool(settings.completion_policy_strict)
    # When wiring into a producer that ALREADY runs the legacy tail we
    # honour the producer-side flag (e.g. the REST end handler passes
    # emit_followup=False because it calls ensure_followup itself). In
    # strict mode we default the opposite — policy owns everything
    # unless the caller explicitly opts out.
    do_followup = emit_followup if emit_followup is not None else strict
    do_crm = emit_crm if emit_crm is not None else strict
    do_gamification = emit_gamification if emit_gamification is not None else strict

    events_emitted: list[str] = []
    failures: list[str] = []
    followup_id: uuid.UUID | None = None

    # F-L7-2 fix: each tail step runs in a SAVEPOINT so a failure rolls
    # back its partial writes instead of leaking half-applied state into
    # the caller's transaction. The outer stamp ``terminal_outcome/reason/
    # completed_via`` stays applied — that is intentional, the session
    # IS terminal regardless of whether the CRM bookkeeping succeeded —
    # but partial rows from a crashed follow-up/CRM/gamification step
    # are now discarded instead of being committed by the caller. The
    # failure is recorded in ``CompletionResult.failures`` so observers
    # (admin panel, alerts) can act on it.
    if do_followup and session.real_client_id is not None:
        try:
            async with db.begin_nested():
                from app.services.crm_followup import ensure_followup_for_session

                reminder = await ensure_followup_for_session(
                    db, session, outcome=outcome.value
                )
                if reminder is not None:
                    followup_id = reminder.id
                    events_emitted.append("crm.reminder_created")
        except Exception as exc:
            failures.append(f"followup:{type(exc).__name__}")
            logger.warning(
                "completion_policy.followup_failed session=%s", session.id, exc_info=True
            )

    if do_crm and session.real_client_id is not None:
        try:
            async with db.begin_nested():
                from app.services.client_domain import log_training_real_case_summary

                interaction, event = await log_training_real_case_summary(
                    db,
                    session=session,
                    source=f"completion_policy.{completed_via.value}",
                    manager_id=manager_id,
                )
                if event is not None and interaction is not None:
                    events_emitted.append("training.real_case_logged")
                elif event is not None and interaction is None:
                    # ``log_training_real_case_summary`` returned (None,
                    # event) because the emit path was disabled/failed
                    # — this is a recognised shadow-mode outcome, not a
                    # failure. Record it for visibility without
                    # classifying as an error.
                    failures.append("crm:event_not_persisted")
        except Exception as exc:
            failures.append(f"crm:{type(exc).__name__}")
            logger.warning(
                "completion_policy.crm_dual_write_failed session=%s",
                session.id, exc_info=True,
            )

    if do_gamification:
        try:
            from app.services.event_bus import (
                EVENT_TRAINING_COMPLETED,
                GameEvent,
                event_bus,
            )

            payload: dict[str, Any] = {
                "session_id": str(session.id),
                "scenario_id": str(session.scenario_id) if session.scenario_id else None,
                "scores": {
                    "total": session.score_total,
                    "human_factor": session.score_human_factor,
                    "narrative": session.score_narrative,
                    "legal": session.score_legal,
                },
                "outcome": outcome.value,
                "reason": reason.value,
                "completed_via": completed_via.value,
                "duration_seconds": session.duration_seconds,
                "source": session.source,
                "real_client_id": str(session.real_client_id) if session.real_client_id else None,
            }
            await event_bus.emit(
                GameEvent(
                    kind=EVENT_TRAINING_COMPLETED,
                    user_id=session.user_id,
                    db=db,
                    payload=payload,
                ),
                # Same key as the legacy emit paths — dedup is the whole
                # point of having a single ``finalize`` call.
                idempotency_key=f"training_completed:{session.id}",
            )
            events_emitted.append("training_completed")
        except Exception as exc:
            failures.append(f"gamification:{type(exc).__name__}")
            logger.warning(
                "completion_policy.gamification_emit_failed session=%s",
                session.id, exc_info=True,
            )

    # Canonical session.completed DomainEvent — always emitted so that
    # observability/parity dashboards can count finalizations regardless
    # of strict mode. Idempotent via deterministic key. Runs in its own
    # savepoint so a DomainEvent emit failure doesn't corrupt the
    # caller's transaction.
    if settings.completion_policy_emit_event and session.real_client_id is not None:
        try:
            async with db.begin_nested():
                from app.models.client import RealClient
                from app.services.client_domain import emit_client_event

                client = await db.get(RealClient, session.real_client_id)
                if client is not None:
                    await emit_client_event(
                        db,
                        client=client,
                        event_type="session.completed",
                        actor_type="user",
                        actor_id=manager_id,
                        source=f"completion_policy.{completed_via.value}",
                        payload={
                            "training_session_id": str(session.id),
                            "outcome": outcome.value,
                            "reason": reason.value,
                            "completed_via": completed_via.value,
                            "strict_mode": strict,
                        },
                        aggregate_type="training_session",
                        aggregate_id=session.id,
                        session_id=session.id,
                        idempotency_key=f"session-completed:{session.id}",
                        correlation_id=str(session.id),
                    )
                    events_emitted.append("session.completed")
        except Exception as exc:
            failures.append(f"session_completed_event:{type(exc).__name__}")
            logger.warning(
                "completion_policy.session_completed_event_failed session=%s",
                session.id, exc_info=True,
            )

    logger.info(
        "completion_policy.finalized",
        extra={
            "session_id": str(session.id),
            "outcome": outcome.value,
            "reason": reason.value,
            "completed_via": completed_via.value,
            "strict_mode": strict,
            "events_emitted": events_emitted,
            "failures": failures,
        },
    )

    return CompletionResult(
        session_id=session.id,
        outcome=outcome,
        reason=reason,
        completed_via=completed_via,
        strict_mode=strict,
        already_completed=False,
        events_emitted=tuple(events_emitted),
        followup_id=followup_id,
        failures=tuple(failures),
    )


# ── Finalize — PvP duels ─────────────────────────────────────────────────


async def finalize_pvp_duel(
    db: AsyncSession,
    *,
    duel: PvPDuel,
    outcome: TerminalOutcome,
    reason: TerminalReason,
    allow_already_completed: bool = True,
) -> CompletionResult:
    """Stamp terminal columns on a PvP duel.

    Unlike training this is ONLY bookkeeping — PvP rating, Arena points
    and ``EVENT_PVP_COMPLETED`` emission live in
    ``_finalize_duel``/``judge_full_duel`` and keep running there until
    we explicitly move them in a later phase. Lifting them here requires
    rating invariants the policy module doesn't own yet.
    """
    validate("pvp", outcome, is_pvp=True)

    if duel.terminal_outcome is not None:
        if not allow_already_completed:
            raise InvalidTerminalOutcome(
                f"Duel {duel.id} already finalized as {duel.terminal_outcome}"
            )
        try:
            cached_outcome = TerminalOutcome(duel.terminal_outcome)
        except ValueError:
            cached_outcome = outcome
        try:
            cached_reason = TerminalReason(duel.terminal_reason or reason.value)
        except ValueError:
            cached_reason = reason
        return CompletionResult(
            session_id=duel.id,
            outcome=cached_outcome,
            reason=cached_reason,
            completed_via=CompletedVia.pvp,
            strict_mode=bool(settings.completion_policy_strict),
            already_completed=True,
            events_emitted=(),
            followup_id=None,
        )

    duel.terminal_outcome = outcome.value
    duel.terminal_reason = reason.value

    logger.info(
        "completion_policy.pvp_finalized",
        extra={
            "duel_id": str(duel.id),
            "outcome": outcome.value,
            "reason": reason.value,
        },
    )

    return CompletionResult(
        session_id=duel.id,
        outcome=outcome,
        reason=reason,
        completed_via=CompletedVia.pvp,
        strict_mode=bool(settings.completion_policy_strict),
        already_completed=False,
        events_emitted=(),
        followup_id=None,
    )


# ── Public helpers ───────────────────────────────────────────────────────


def outcome_from_raw(raw: str | None) -> TerminalOutcome:
    """Best-effort map from a free-form ``call_outcome`` string to the
    canonical enum. Use at the adapter boundary — producers that already
    pass a ``TerminalOutcome`` don't need this.

    Unknown values collapse to ``operator_aborted`` so the finalize step
    still stamps something meaningful. This keeps historical behaviour
    where any non-terminal string was silently treated as "session
    ended by the user" in the REST handler.
    """
    if raw is None:
        return TerminalOutcome.operator_aborted
    lowered = raw.strip().lower()
    if not lowered:
        return TerminalOutcome.operator_aborted
    mapping = {
        "deal": TerminalOutcome.success,
        "deal_agreed": TerminalOutcome.success,
        "agreed": TerminalOutcome.success,
        "consultation_booked": TerminalOutcome.success,
        "meeting": TerminalOutcome.success,
        "rejected": TerminalOutcome.hard_reject,
        "lost": TerminalOutcome.hard_reject,
        "deal_not_agreed": TerminalOutcome.hard_reject,
        "hostile": TerminalOutcome.hard_reject,
        "hangup": TerminalOutcome.hangup,
        "hang_up": TerminalOutcome.hangup,
        "timeout": TerminalOutcome.timeout,
        "silence_timeout": TerminalOutcome.timeout,
        "no_answer": TerminalOutcome.no_answer,
        "callback": TerminalOutcome.callback_requested,
        "callback_requested": TerminalOutcome.callback_requested,
        "scheduled_callback": TerminalOutcome.callback_requested,
        "continue_next_call": TerminalOutcome.needs_followup,
        "continue_later": TerminalOutcome.needs_followup,
        "needs_followup": TerminalOutcome.needs_followup,
        "considering": TerminalOutcome.needs_followup,
        "negotiating": TerminalOutcome.needs_followup,
        "needs_documents": TerminalOutcome.need_documents,
        "need_documents": TerminalOutcome.need_documents,
        "documents_requested": TerminalOutcome.need_documents,
        "technical_failed": TerminalOutcome.technical_failed,
        "judge_failed": TerminalOutcome.technical_failed,
        "aborted": TerminalOutcome.operator_aborted,
        "operator_aborted": TerminalOutcome.operator_aborted,
    }
    return mapping.get(lowered, TerminalOutcome.operator_aborted)


__all__ = [
    "CompletedVia",
    "CompletionResult",
    "InsufficientSessionActivity",
    "InvalidTerminalOutcome",
    "TerminalOutcome",
    "TerminalReason",
    "finalize_pvp_duel",
    "finalize_training_session",
    "outcome_from_raw",
    "validate",
]
