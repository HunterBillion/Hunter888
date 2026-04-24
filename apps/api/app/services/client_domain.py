"""Canonical client-domain helpers for TZ-1 dual-write migration.

This module keeps existing CRM read/write flows alive while adding:
- canonical LeadClient bootstrap
- immutable DomainEvent journal writes
- CRM timeline projection bookkeeping

Read paths stay on existing tables for now. New writes go through these helpers
to avoid further schema drift.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Attachment, ClientInteraction, ClientStatus, InteractionType, RealClient
from app.models.crm_projection import CrmTimelineProjectionState
from app.models.domain_event import DomainEvent
from app.models.lead_client import LeadClient
from app.models.training import TrainingSession
from app.models.user import User


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
    if hasattr(value, "value") and not isinstance(value, str):
        try:
            return value.value
        except Exception:
            return str(value)
    return value


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


async def ensure_lead_client(
    db: AsyncSession,
    *,
    client: RealClient,
    owner_user: User | None = None,
) -> LeadClient:
    target_id = client.lead_client_id or client.id
    lead = await db.get(LeadClient, target_id)

    if lead is None:
        owner_id = owner_user.id if owner_user is not None else client.manager_id
        team_id = owner_user.team_id if owner_user is not None else None
        if team_id is None:
            team_id = (await db.execute(
                select(User.team_id).where(User.id == owner_id)
            )).scalar_one_or_none()
        lifecycle_stage, work_state = map_legacy_client_status(client.status)
        lead = LeadClient(
            id=target_id,
            owner_user_id=owner_id,
            team_id=team_id,
            lifecycle_stage=lifecycle_stage,
            work_state=work_state,
            status_tags=[],
            source_system="real_clients",
            source_ref=str(client.id),
        )
        db.add(lead)
        await db.flush()
    else:
        lifecycle_stage, work_state = map_legacy_client_status(client.status)
        lead.owner_user_id = owner_user.id if owner_user is not None else client.manager_id
        if owner_user is not None:
            lead.team_id = owner_user.team_id
        if lead.source_system is None:
            lead.source_system = "real_clients"
        if lead.source_ref is None:
            lead.source_ref = str(client.id)
        lead.lifecycle_stage = lifecycle_stage
        lead.work_state = work_state

    if client.lead_client_id != lead.id:
        client.lead_client_id = lead.id
    return lead


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
    key = idempotency_key or f"{event_type}:{uuid.uuid4()}"
    existing = (await db.execute(
        select(DomainEvent).where(DomainEvent.idempotency_key == key)
    )).scalar_one_or_none()
    if existing is not None:
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
        occurred_at=occurred_at or datetime.now(timezone.utc),
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
        return event
    except IntegrityError:
        existing = (await db.execute(
            select(DomainEvent).where(DomainEvent.idempotency_key == key)
        )).scalar_one()
        return existing


async def _projection_interaction_for_event(
    db: AsyncSession,
    *,
    domain_event_id: uuid.UUID,
) -> ClientInteraction | None:
    projection = (await db.execute(
        select(CrmTimelineProjectionState).where(
            CrmTimelineProjectionState.domain_event_id == domain_event_id
        )
    )).scalar_one_or_none()
    if projection is None or projection.interaction_id is None:
        return None
    return await db.get(ClientInteraction, projection.interaction_id)


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
    if idempotency_key:
        existing_event = (await db.execute(
            select(DomainEvent).where(DomainEvent.idempotency_key == idempotency_key)
        )).scalar_one_or_none()
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
        correlation_id=str(session_id) if session_id else None,
    )

    interaction.metadata_ = {
        **meta,
        "domain_event_id": str(event.id),
        "schema_version": event.schema_version,
        "projection_name": "crm_timeline",
        "projection_version": 1,
    }
    projection = CrmTimelineProjectionState(
        domain_event_id=event.id,
        lead_client_id=lead.id,
        interaction_id=interaction.id,
        projection_name="crm_timeline",
        projection_version=1,
        status="projected",
    )
    db.add(projection)
    await db.flush()
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
) -> DomainEvent:
    lead = await ensure_lead_client(db, client=client)
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
        correlation_id=str(session_id) if session_id else None,
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
            "scenario_version_id": str(session.scenario_version_id) if session.scenario_version_id else None,
            "session_mode": ((session.custom_params or {}).get("session_mode") or "chat").lower(),
            "score_total": session.score_total,
            "status": session.status.value if hasattr(session.status, "value") else str(session.status),
        },
        aggregate_type="training_session",
        aggregate_id=session.id,
        session_id=session.id,
        idempotency_key=f"training-real-case:{session.id}",
        correlation_id=str(session.id),
    )
    existing_interaction = await _projection_interaction_for_event(db, domain_event_id=event.id)
    if existing_interaction is not None:
        return existing_interaction, event

    session_mode = ((session.custom_params or {}).get("session_mode") or "chat").lower()
    interaction_type = InteractionType.outbound_call if session_mode == "call" else InteractionType.note
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
            "domain_event_id": str(event.id),
            "schema_version": event.schema_version,
            "projection_name": "crm_timeline",
            "projection_version": 1,
        },
    )
    db.add(interaction)
    await db.flush()
    projection = CrmTimelineProjectionState(
        domain_event_id=event.id,
        lead_client_id=lead.id,
        interaction_id=interaction.id,
        projection_name="crm_timeline",
        projection_version=1,
        status="projected",
    )
    db.add(projection)
    await db.flush()
    return interaction, event
