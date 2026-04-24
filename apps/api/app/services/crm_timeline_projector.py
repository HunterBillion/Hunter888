"""CRM timeline projector (TZ-1 §10, §14.4).

Pure function layer that turns a ``DomainEvent`` into a ``ClientInteraction``
row plus a projection bookkeeping record. Lives separately from the
dual-write helper so replay/repair can call it without going through
producer code.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import ClientInteraction, InteractionType
from app.models.crm_projection import CrmTimelineProjectionState
from app.models.domain_event import DomainEvent

logger = logging.getLogger(__name__)

PROJECTION_NAME = "crm_timeline"
PROJECTION_VERSION = 1


def interaction_metadata_patch(event: DomainEvent, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Canonical metadata payload every projected ClientInteraction must carry."""
    patch: dict[str, Any] = {
        "domain_event_id": str(event.id),
        "schema_version": event.schema_version,
        "projection_name": PROJECTION_NAME,
        "projection_version": PROJECTION_VERSION,
    }
    if event.correlation_id:
        patch["correlation_id"] = event.correlation_id
    if extra:
        patch.update(extra)
    return patch


async def record_projection(
    db: AsyncSession,
    *,
    event: DomainEvent,
    interaction: ClientInteraction | None,
    status: str = "projected",
    error: str | None = None,
) -> CrmTimelineProjectionState:
    """Insert or return the projection-state row for (event, interaction).

    Idempotent on ``domain_event_id`` — re-running replay does not duplicate.
    """
    existing = (await db.execute(
        select(CrmTimelineProjectionState).where(
            CrmTimelineProjectionState.domain_event_id == event.id
        )
    )).scalar_one_or_none()
    if existing is not None:
        if interaction is not None and existing.interaction_id != interaction.id:
            existing.interaction_id = interaction.id
        if existing.status != status:
            existing.status = status
        existing.error = error
        return existing

    state = CrmTimelineProjectionState(
        domain_event_id=event.id,
        lead_client_id=event.lead_client_id,
        interaction_id=interaction.id if interaction is not None else None,
        projection_name=PROJECTION_NAME,
        projection_version=PROJECTION_VERSION,
        status=status,
        error=error,
    )
    db.add(state)
    await db.flush()
    return state


def infer_interaction_type(event_type: str, payload: dict[str, Any]) -> InteractionType:
    raw = (payload or {}).get("interaction_type")
    if raw:
        try:
            return InteractionType(raw)
        except ValueError:
            pass
    if event_type == "lead_client.lifecycle_changed":
        return InteractionType.status_change
    if event_type == "consent.updated":
        return InteractionType.consent_event
    if event_type.startswith("training."):
        session_mode = (payload or {}).get("session_mode")
        if session_mode == "call":
            return InteractionType.outbound_call
    return InteractionType.note


async def project_event_to_interaction(
    db: AsyncSession,
    *,
    event: DomainEvent,
    client_id: uuid.UUID,
    manager_id: uuid.UUID | None,
    content_override: str | None = None,
    duration_seconds: int | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> ClientInteraction:
    """Build a ClientInteraction from a DomainEvent, idempotent via projection state."""
    existing_state = (await db.execute(
        select(CrmTimelineProjectionState).where(
            CrmTimelineProjectionState.domain_event_id == event.id
        )
    )).scalar_one_or_none()
    if existing_state is not None and existing_state.interaction_id is not None:
        existing_interaction = await db.get(ClientInteraction, existing_state.interaction_id)
        if existing_interaction is not None:
            return existing_interaction

    payload: dict[str, Any] = event.payload_json or {}
    interaction_type = infer_interaction_type(event.event_type, payload)
    content = content_override
    if content is None:
        content = payload.get("content") or _default_content_for_event(event.event_type, payload)

    interaction = ClientInteraction(
        id=uuid.uuid4(),
        lead_client_id=event.lead_client_id,
        client_id=client_id,
        manager_id=manager_id,
        interaction_type=interaction_type,
        content=content,
        result=payload.get("result"),
        duration_seconds=duration_seconds if duration_seconds is not None else payload.get("duration_seconds"),
        old_status=payload.get("old_status"),
        new_status=payload.get("new_status"),
        metadata_=interaction_metadata_patch(event, extra_metadata),
    )
    db.add(interaction)
    await db.flush()
    await record_projection(db, event=event, interaction=interaction)
    return interaction


def _default_content_for_event(event_type: str, payload: dict[str, Any]) -> str | None:
    if event_type == "lead_client.lifecycle_changed":
        old = payload.get("old_status")
        new = payload.get("new_status")
        if old and new:
            return f"Смена статуса: {old} → {new}"
    if event_type == "consent.updated":
        state = payload.get("state")
        consent_type = payload.get("consent_type")
        if state and consent_type:
            verb = "получено" if state == "granted" else "отозвано"
            return f"Согласие {verb}: {consent_type}"
    if event_type.startswith("training."):
        return payload.get("summary")
    return None
