"""Parity + repair utilities for the unified client domain (TZ-1 §17, §18).

Surface three things runnable without a full worker process:

1. :func:`parity_report` — scan the dual-write state and return counts for
   "interactions without domain_event_id", "events without projection",
   "projections without interaction_id". Use from ops scripts before cutover.
2. :func:`repair_missing_projections` — build projection rows for events
   that still lack one (e.g., a projector crash after the event committed).
3. :func:`repair_missing_events_for_interactions` — retroactively backfill
   DomainEvent rows for ``ClientInteraction`` records that still miss
   ``metadata.domain_event_id``. Idempotent on the deterministic key
   ``repair:client_interaction:<id>``.

Keep this module thin: it composes the canonical helpers. No business
decisions live here.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import ClientInteraction, RealClient
from app.models.crm_projection import CrmTimelineProjectionState
from app.models.domain_event import DomainEvent
from app.services.client_domain import emit_domain_event, ensure_lead_client
from app.services.crm_timeline_projector import (
    interaction_metadata_patch,
    record_projection,
)

logger = logging.getLogger(__name__)


async def parity_report(db: AsyncSession) -> dict[str, Any]:
    """Return counts the ops team uses to gate cutover (TZ §17, §20)."""
    total_interactions = (
        await db.execute(select(func.count()).select_from(ClientInteraction))
    ).scalar_one()
    total_events = (await db.execute(select(func.count()).select_from(DomainEvent))).scalar_one()
    total_projections = (
        await db.execute(select(func.count()).select_from(CrmTimelineProjectionState))
    ).scalar_one()

    interactions_without_event = (
        await db.execute(
            select(func.count())
            .select_from(ClientInteraction)
            .where(
                (ClientInteraction.metadata_.is_(None))
                | (~ClientInteraction.metadata_.has_key("domain_event_id"))  # noqa: W504
            )
        )
    ).scalar_one()

    events_without_projection = (
        await db.execute(
            select(func.count())
            .select_from(DomainEvent)
            .outerjoin(
                CrmTimelineProjectionState,
                CrmTimelineProjectionState.domain_event_id == DomainEvent.id,
            )
            .where(CrmTimelineProjectionState.id.is_(None))
            .where(
                DomainEvent.event_type.in_(
                    [
                        "crm.interaction_logged",
                        "lead_client.lifecycle_changed",
                        "consent.updated",
                        "training.real_case_logged",
                        "session.attachment_linked",
                    ]
                )
            )
        )
    ).scalar_one()

    projections_orphaned = (
        await db.execute(
            select(func.count())
            .select_from(CrmTimelineProjectionState)
            .where(CrmTimelineProjectionState.interaction_id.is_(None))
        )
    ).scalar_one()

    events_without_lead = (
        await db.execute(
            select(func.count())
            .select_from(DomainEvent)
            .where(DomainEvent.lead_client_id.is_(None))
        )
    ).scalar_one()

    return {
        "total_interactions": int(total_interactions),
        "total_events": int(total_events),
        "total_projections": int(total_projections),
        "interactions_without_domain_event_id": int(interactions_without_event),
        "events_without_projection": int(events_without_projection),
        "projections_without_interaction": int(projections_orphaned),
        "events_without_lead_client_id": int(events_without_lead),
    }


async def repair_missing_projections(db: AsyncSession, *, limit: int = 500) -> int:
    """Create CrmTimelineProjectionState rows for events that lack one.

    We only attach a projection row (marked ``status='repaired'``) — we do
    not try to reconstruct the ``ClientInteraction`` content from the event
    payload here, because the producer path already wrote it. This repair
    closes the bookkeeping gap, not the CRM-side data gap.
    """
    orphan_events = (
        (
            await db.execute(
                select(DomainEvent)
                .outerjoin(
                    CrmTimelineProjectionState,
                    CrmTimelineProjectionState.domain_event_id == DomainEvent.id,
                )
                .where(CrmTimelineProjectionState.id.is_(None))
                .order_by(DomainEvent.occurred_at.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    repaired = 0
    for event in orphan_events:
        interaction_id = (event.payload_json or {}).get("interaction_id")
        interaction = None
        if interaction_id:
            try:
                interaction = await db.get(ClientInteraction, uuid.UUID(interaction_id))
            except (ValueError, TypeError):
                interaction = None
        await record_projection(db, event=event, interaction=interaction, status="repaired")
        repaired += 1
    logger.info("client_domain_repair.projections_filled", extra={"count": repaired})
    return repaired


async def repair_missing_events_for_interactions(db: AsyncSession, *, limit: int = 500) -> int:
    """Backfill DomainEvent + projection for legacy interactions that still
    miss ``metadata.domain_event_id``. Idempotent on the derived key.
    """
    stmt = (
        select(ClientInteraction)
        .join(RealClient, RealClient.id == ClientInteraction.client_id)
        .where(
            (ClientInteraction.metadata_.is_(None))
            | (~ClientInteraction.metadata_.has_key("domain_event_id"))  # noqa: W504
        )
        .order_by(ClientInteraction.created_at.asc())
        .limit(limit)
    )
    orphans = (await db.execute(stmt)).scalars().all()
    repaired = 0
    for interaction in orphans:
        client = await db.get(RealClient, interaction.client_id)
        if client is None:
            continue
        lead = await ensure_lead_client(db, client=client)
        event_type = (
            "lead_client.lifecycle_changed"
            if interaction.interaction_type.value == "status_change"
            else "crm.interaction_logged"
        )
        payload = {
            "interaction_id": str(interaction.id),
            "client_id": str(client.id),
            "lead_client_id": str(lead.id),
            "interaction_type": interaction.interaction_type.value,
            "content": interaction.content,
            "result": interaction.result,
            "duration_seconds": interaction.duration_seconds,
            "old_status": interaction.old_status,
            "new_status": interaction.new_status,
            "source": "repair",
        }
        event = await emit_domain_event(
            db,
            lead_client_id=lead.id,
            event_type=event_type,
            actor_type="migration",
            actor_id=interaction.manager_id,
            source="repair",
            payload=payload,
            aggregate_type="client_interaction",
            aggregate_id=interaction.id,
            idempotency_key=f"repair:client_interaction:{interaction.id}",
            occurred_at=interaction.created_at,
            correlation_id=str(interaction.id),
        )
        meta = dict(interaction.metadata_ or {})
        meta.update(interaction_metadata_patch(event))
        interaction.metadata_ = meta
        interaction.lead_client_id = lead.id
        await record_projection(db, event=event, interaction=interaction, status="repaired")
        repaired += 1
    logger.info("client_domain_repair.events_backfilled", extra={"count": repaired})
    return repaired
