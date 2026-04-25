"""Canonical client-domain helpers (TZ-1 Фаза 2: dual-write).

Responsibilities:
- bootstrap a canonical ``LeadClient`` per ``RealClient`` (1:1 physical anchor);
- append immutable ``DomainEvent`` rows;
- delegate CRM-timeline materialization to ``crm_timeline_projector``;
- bind ``Attachment`` / ``TrainingSession`` to a ``lead_client_id``.

Design notes
------------
* Read paths stay on legacy tables until ``client_domain_cutover_read_enabled``.
* Writes that change lifecycle/work_state must go through one of the helpers
  here — anything else is an architectural defect per TZ §10.3.
* ``idempotency_key`` is **mandatory** on event producers. We still accept a
  ``None`` for fire-and-forget notes, but that path will never dedupe retries
  and logs a warning so we can catch it in audits.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.client import (
    Attachment,
    ClientInteraction,
    ClientStatus,
    InteractionType,
    RealClient,
)
from app.models.crm_projection import CrmTimelineProjectionState
from app.models.domain_event import DomainEvent
from app.models.lead_client import LeadClient
from app.models.training import TrainingSession
from app.models.user import User
from app.services.crm_timeline_projector import (
    PROJECTION_NAME,
    PROJECTION_VERSION,
    interaction_metadata_patch,
    record_projection,
)

logger = logging.getLogger(__name__)


# In-process Prometheus-style counter for DomainEvent emissions. Exposed in
# text format via /admin/client-domain/metrics. Lives in the module so
# every worker reports its own slice; aggregation happens at the scraper
# level. Thread-safe to keep gunicorn workers + asyncio safe under load.
_emit_counter_lock = threading.Lock()
_emit_counter: dict[tuple[str, str, str, str], int] = defaultdict(int)


def _record_emit(event_type: str, source: str, actor_type: str, outcome: str) -> None:
    """Bump the in-process emit counter. ``outcome`` ∈ {emitted, deduped, skipped, failed}."""
    with _emit_counter_lock:
        _emit_counter[(event_type, source, actor_type, outcome)] += 1


def get_emit_counters() -> dict[tuple[str, str, str, str], int]:
    """Snapshot of the emit counter for /metrics rendering."""
    with _emit_counter_lock:
        return dict(_emit_counter)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "value") and not isinstance(value, (str, bytes, bytearray)):
        try:
            return value.value
        except Exception:
            return str(value)
    return value


def _hash_payload(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "0"
    blob = json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _derive_idempotency_key(
    event_type: str,
    *,
    aggregate_id: uuid.UUID | None,
    actor_id: uuid.UUID | None,
    payload: dict[str, Any] | None,
    session_id: uuid.UUID | None,
) -> str:
    """Deterministic fallback when caller did not pass a key explicitly.

    TZ §9.1.4 mandates an idempotency_key on every producer. Rather than a
    pure random UUID (which silently defeats dedup on retries), we derive one
    from the event's natural keys so the same business action produces the
    same key. Callers that can craft a stronger key should still do so.
    """
    parts = [
        event_type,
        str(aggregate_id or "0"),
        str(actor_id or "0"),
        str(session_id or "0"),
        _hash_payload(payload),
    ]
    return ":".join(parts)


LIFECYCLE_STAGES: frozenset[str] = frozenset({
    "new",
    "contacted",
    "interested",
    "consultation",
    "thinking",
    "consent_received",
    "contract_signed",
    "documents_in_progress",
    "case_in_progress",
    "completed",
    "lost",
})

WORK_STATES: frozenset[str] = frozenset({
    "active",
    "callback_scheduled",
    "waiting_client",
    "waiting_documents",
    "consent_pending",
    "paused",
    "consent_revoked",
    "duplicate_review",
    "archived",
})


def map_legacy_client_status(status: ClientStatus | str | None) -> tuple[str, str]:
    raw = status.value if isinstance(status, ClientStatus) else str(status or "").strip().lower()
    lifecycle = {
        "new": "new",
        "contacted": "contacted",
        "interested": "interested",
        "consultation": "consultation",
        "thinking": "thinking",
        "consent_given": "consent_received",
        "contract_signed": "contract_signed",
        "in_process": "case_in_progress",
        "paused": "case_in_progress",
        "completed": "completed",
        "lost": "lost",
        "consent_revoked": "consent_received",
    }.get(raw, "new")
    work_state = {
        "paused": "paused",
        "consent_revoked": "consent_revoked",
    }.get(raw, "active")
    return lifecycle, work_state


# ── LeadClient bootstrap ────────────────────────────────────────────────────


async def ensure_lead_client(
    db: AsyncSession,
    *,
    client: RealClient,
    owner_user: User | None = None,
) -> LeadClient:
    """Create-or-attach the canonical LeadClient for a RealClient.

    Safety:
    - Does NOT overwrite owner/team on an existing record (prevents churn when
      called from read paths or unrelated owners). Update is explicit —
      callers that really want to reassign ownership should mutate the
      LeadClient directly.
    - Lifecycle/work_state are backfilled ONLY if the LeadClient has the
      default ("new"/"active") — otherwise direct changes to the canonical
      record are preserved.
    """
    target_id = client.lead_client_id or client.id
    lead = await db.get(LeadClient, target_id)

    if lead is None:
        owner_id = owner_user.id if owner_user is not None else client.manager_id
        team_id = owner_user.team_id if owner_user is not None else None
        if team_id is None:
            team_id = (
                await db.execute(select(User.team_id).where(User.id == owner_id))
            ).scalar_one_or_none()
        lifecycle_stage, work_state = map_legacy_client_status(client.status)
        # SAVEPOINT-wrapped INSERT so two concurrent workers creating the
        # same LeadClient collapse to one row: the loser catches
        # IntegrityError, rolls back just the savepoint (outer txn intact),
        # and re-reads the winner's row.
        candidate = LeadClient(
            id=target_id,
            owner_user_id=owner_id,
            team_id=team_id,
            lifecycle_stage=lifecycle_stage,
            work_state=work_state,
            status_tags=[],
            source_system="real_clients",
            source_ref=str(client.id),
        )
        try:
            async with db.begin_nested():
                db.add(candidate)
                await db.flush()
            lead = candidate
        except IntegrityError:
            lead = await db.get(LeadClient, target_id)
            if lead is None:
                raise
    else:
        if lead.source_system is None:
            lead.source_system = "real_clients"
        if lead.source_ref is None:
            lead.source_ref = str(client.id)
        # Only backfill lifecycle/work_state while they still sit at defaults
        # AND legacy status disagrees — avoids clobbering canonical updates.
        if lead.lifecycle_stage == "new" and lead.work_state == "active":
            lifecycle_stage, work_state = map_legacy_client_status(client.status)
            if (lifecycle_stage, work_state) != ("new", "active"):
                lead.lifecycle_stage = lifecycle_stage
                lead.work_state = work_state

    if client.lead_client_id != lead.id:
        client.lead_client_id = lead.id
    return lead


# ── DomainEvent emit ────────────────────────────────────────────────────────


async def emit_domain_event(
    db: AsyncSession,
    *,
    lead_client_id: uuid.UUID,
    event_type: str,
    actor_type: str,
    actor_id: uuid.UUID | None,
    source: str,
    payload: dict[str, Any] | None = None,
    aggregate_type: str | None = None,
    aggregate_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    call_attempt_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
    occurred_at: datetime | None = None,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> DomainEvent:
    if not settings.client_domain_dual_write_enabled:
        # Return a transient DomainEvent that is NOT persisted. Callers that
        # need the ID for projection bookkeeping should check
        # ``settings.client_domain_dual_write_enabled`` themselves.
        _record_emit(event_type, source[:30], actor_type, "skipped")
        return DomainEvent(
            id=uuid.uuid4(),
            lead_client_id=lead_client_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            source=source[:30],
            payload_json=_json_safe(payload or {}),
            idempotency_key=idempotency_key or "disabled",
            schema_version=1,
            correlation_id=correlation_id,
        )

    key = idempotency_key or _derive_idempotency_key(
        event_type,
        aggregate_id=aggregate_id,
        actor_id=actor_id,
        payload=payload,
        session_id=session_id,
    )

    existing = (
        await db.execute(select(DomainEvent).where(DomainEvent.idempotency_key == key))
    ).scalar_one_or_none()
    if existing is not None:
        _record_emit(event_type, source[:30], actor_type, "deduped")
        return existing

    event = DomainEvent(
        lead_client_id=lead_client_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        session_id=session_id,
        call_attempt_id=call_attempt_id,
        actor_type=actor_type,
        actor_id=actor_id,
        source=source[:30],
        occurred_at=occurred_at or datetime.now(UTC),
        payload_json=_json_safe(payload or {}),
        idempotency_key=key,
        schema_version=1,
        causation_id=causation_id,
        correlation_id=correlation_id,
    )
    try:
        async with db.begin_nested():
            db.add(event)
            await db.flush()
        _record_emit(event_type, source[:30], actor_type, "emitted")
        logger.info(
            "domain_event.emitted",
            extra={
                "event_type": event_type,
                "lead_client_id": str(lead_client_id),
                "domain_event_id": str(event.id),
                "correlation_id": correlation_id,
                "source": source,
            },
        )
        return event
    except IntegrityError:
        existing = (
            await db.execute(select(DomainEvent).where(DomainEvent.idempotency_key == key))
        ).scalar_one()
        _record_emit(event_type, source[:30], actor_type, "deduped")
        return existing
    except Exception as exc:
        _record_emit(event_type, source[:30], actor_type, "failed")
        if settings.client_domain_strict_emit:
            raise
        logger.warning(
            "domain_event.emit_failed",
            extra={
                "event_type": event_type,
                "lead_client_id": str(lead_client_id),
                "error": str(exc),
            },
            exc_info=True,
        )
        return event


def is_event_persisted(event: DomainEvent | None) -> bool:
    """Return True iff the event is a real, DB-persisted row.

    F-L7-3/F-L7-4 fix. ``emit_domain_event`` can return three flavours:

      * fully-persisted happy-path event — attached to a session, has a
        db-assigned ``created_at``;
      * "disabled" stub when ``client_domain_dual_write_enabled=False``;
      * transient no-flush event when a generic exception was swallowed
        under ``client_domain_strict_emit=False``.

    Prior to this helper, every caller blindly wrote ``event.id`` into
    ``ClientInteraction.metadata.domain_event_id``, producing a UUID
    that didn't exist in ``domain_events``. Parity counters then *under*
    reported drift because the interaction looked linked.

    Callers now gate every projection/metadata write on this predicate.
    """
    if event is None:
        return False
    if event.idempotency_key == "disabled":
        return False
    from sqlalchemy.inspection import inspect as _insp

    try:
        state = _insp(event, raiseerr=False)
    except Exception:  # pragma: no cover — defensive
        return False
    if state is None:
        return False
    # A truly-persisted row is either ``persistent`` (alive in the
    # session) or has a DB-assigned created_at (flushed at least once).
    if state.transient or state.detached:
        return getattr(event, "created_at", None) is not None
    return True


async def _projection_interaction_for_event(
    db: AsyncSession,
    *,
    domain_event_id: uuid.UUID,
) -> ClientInteraction | None:
    projection = (
        await db.execute(
            select(CrmTimelineProjectionState).where(
                CrmTimelineProjectionState.domain_event_id == domain_event_id
            )
        )
    ).scalar_one_or_none()
    if projection is None or projection.interaction_id is None:
        return None
    return await db.get(ClientInteraction, projection.interaction_id)


# ── Dual-write helpers used by producers ────────────────────────────────────


async def create_crm_interaction_with_event(
    db: AsyncSession,
    *,
    client: RealClient,
    interaction_type: InteractionType,
    content: str | None,
    result: str | None = None,
    duration_seconds: int | None = None,
    manager_id: uuid.UUID | None = None,
    old_status: str | None = None,
    new_status: str | None = None,
    metadata: dict[str, Any] | None = None,
    event_type: str = "crm.interaction_logged",
    payload: dict[str, Any] | None = None,
    source: str = "api",
    actor_type: str = "user",
    actor_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
) -> tuple[ClientInteraction, DomainEvent]:
    """Write a ClientInteraction row + paired DomainEvent in the same txn."""
    if idempotency_key:
        existing_event = (
            await db.execute(
                select(DomainEvent).where(DomainEvent.idempotency_key == idempotency_key)
            )
        ).scalar_one_or_none()
        if existing_event is not None:
            existing_interaction = await _projection_interaction_for_event(
                db, domain_event_id=existing_event.id
            )
            if existing_interaction is not None:
                return existing_interaction, existing_event

    lead = await ensure_lead_client(db, client=client)
    meta = _json_safe(dict(metadata or {}))
    interaction = ClientInteraction(
        id=uuid.uuid4(),
        lead_client_id=lead.id,
        client_id=client.id,
        manager_id=manager_id,
        interaction_type=interaction_type,
        content=content,
        result=result,
        duration_seconds=duration_seconds,
        old_status=old_status,
        new_status=new_status,
        metadata_=meta or None,
    )
    db.add(interaction)
    await db.flush()

    event_payload = {
        "interaction_id": str(interaction.id),
        "client_id": str(client.id),
        "lead_client_id": str(lead.id),
        "interaction_type": interaction_type.value,
        "content": content,
        "result": result,
        "duration_seconds": duration_seconds,
        "old_status": old_status,
        "new_status": new_status,
        "metadata": meta or None,
    }
    if payload:
        event_payload.update(_json_safe(payload))

    event = await emit_domain_event(
        db,
        lead_client_id=lead.id,
        event_type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        source=source,
        payload=event_payload,
        aggregate_type="client_interaction",
        aggregate_id=interaction.id,
        session_id=session_id,
        idempotency_key=idempotency_key,
        causation_id=str(interaction.id),
        correlation_id=str(session_id) if session_id else str(interaction.id),
    )

    # F-L7-3/F-L7-4 guard: only stamp metadata + build projection when the
    # event actually made it into ``domain_events``. ``emit_domain_event``
    # may return a transient stub when dual-write is disabled or when a
    # non-strict emit failure happens; writing ``event.id`` into the
    # interaction metadata in those cases produces a fake
    # ``domain_event_id`` that parity counters then undercount as drift.
    if is_event_persisted(event):
        interaction.metadata_ = {**meta, **interaction_metadata_patch(event)}
        await record_projection(db, event=event, interaction=interaction)
    return interaction, event


async def emit_client_event(
    db: AsyncSession,
    *,
    client: RealClient,
    event_type: str,
    actor_type: str,
    actor_id: uuid.UUID | None,
    source: str,
    payload: dict[str, Any] | None = None,
    aggregate_type: str | None = None,
    aggregate_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> DomainEvent:
    lead = await ensure_lead_client(db, client=client)
    # §15.1 correlation chain must be non-null. Prefer the most specific
    # anchor available: session > aggregate > client. The client.id fallback
    # ties orphan lifecycle events back to the canonical case so timeline
    # joins still work for events with no inherent session/aggregate.
    resolved_correlation_id = correlation_id or (
        str(session_id)
        if session_id
        else (str(aggregate_id) if aggregate_id else str(client.id))
    )
    return await emit_domain_event(
        db,
        lead_client_id=lead.id,
        event_type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        source=source,
        payload=_json_safe(payload) if payload else None,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        session_id=session_id,
        idempotency_key=idempotency_key,
        causation_id=causation_id,
        correlation_id=resolved_correlation_id,
    )


async def bind_attachment_to_lead_client(
    db: AsyncSession,
    *,
    attachment: Attachment,
    client: RealClient,
) -> uuid.UUID:
    lead = await ensure_lead_client(db, client=client)
    attachment.lead_client_id = lead.id
    return lead.id


async def bind_session_to_lead_client(
    db: AsyncSession,
    *,
    session: TrainingSession,
    client: RealClient,
) -> uuid.UUID:
    lead = await ensure_lead_client(db, client=client)
    session.lead_client_id = lead.id
    return lead.id


# ── Training real-case bridge ───────────────────────────────────────────────


async def log_training_real_case_summary(
    db: AsyncSession,
    *,
    session: TrainingSession,
    source: str,
    manager_id: uuid.UUID | None,
) -> tuple[ClientInteraction, DomainEvent] | tuple[None, None]:
    if session.real_client_id is None:
        return None, None
    client = await db.get(RealClient, session.real_client_id)
    if client is None:
        return None, None
    lead = await ensure_lead_client(db, client=client)
    session_mode = ((session.custom_params or {}).get("session_mode") or "chat").lower()
    event = await emit_domain_event(
        db,
        lead_client_id=lead.id,
        event_type="training.real_case_logged",
        actor_type="user",
        actor_id=manager_id,
        source=source,
        payload={
            "training_session_id": str(session.id),
            "scenario_id": str(session.scenario_id) if session.scenario_id else None,
            "scenario_version_id": str(session.scenario_version_id)
            if session.scenario_version_id
            else None,
            "session_mode": session_mode,
            "score_total": session.score_total,
            "status": session.status.value
            if hasattr(session.status, "value")
            else str(session.status),
        },
        aggregate_type="training_session",
        aggregate_id=session.id,
        session_id=session.id,
        idempotency_key=f"training-real-case:{session.id}",
        correlation_id=str(session.id),
    )
    # F-L7-4 guard: if the DomainEvent was not persisted (dual-write
    # disabled OR non-strict emit error), skip the CRM interaction +
    # projection bookkeeping entirely. Legacy producers still write to
    # ``client_interactions`` via their own paths; we just don't manufacture
    # a fake ``domain_event_id``. The caller receives ``(None, event)`` so
    # it can log the dropped case without mistaking it for success.
    if not is_event_persisted(event):
        return None, event

    existing_interaction = await _projection_interaction_for_event(db, domain_event_id=event.id)
    if existing_interaction is not None:
        return existing_interaction, event

    interaction_type = (
        InteractionType.outbound_call if session_mode == "call" else InteractionType.note
    )
    score_value = int(session.score_total) if session.score_total is not None else 0
    interaction = ClientInteraction(
        id=uuid.uuid4(),
        lead_client_id=lead.id,
        client_id=client.id,
        manager_id=manager_id,
        interaction_type=interaction_type,
        duration_seconds=session.duration_seconds,
        content=(
            f"Тренировка #{session.id.hex[:8]} "
            f"({'звонок' if session_mode == 'call' else 'чат'}) — {score_value} баллов"
        ),
        metadata_={
            "training_session_id": str(session.id),
            "scenario_id": str(session.scenario_id) if session.scenario_id else None,
            "session_mode": session_mode,
            "total_score": session.score_total,
            "source": session.source,
            **interaction_metadata_patch(event),
        },
    )
    db.add(interaction)
    await db.flush()
    await record_projection(db, event=event, interaction=interaction)
    return interaction, event


__all__ = [
    "PROJECTION_NAME",
    "PROJECTION_VERSION",
    "bind_attachment_to_lead_client",
    "bind_session_to_lead_client",
    "create_crm_interaction_with_event",
    "emit_client_event",
    "emit_domain_event",
    "ensure_lead_client",
    "is_event_persisted",
    "log_training_real_case_summary",
    "map_legacy_client_status",
]
