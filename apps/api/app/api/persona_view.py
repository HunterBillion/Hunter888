"""TZ-4 §6.3 / §6.4 — per-client persona memory read endpoint.

Powers the "Память клиента" section on `/clients/[id]` so the
manager can see at a glance:

  * the cross-session :class:`MemoryPersona` row (identity facts +
    confirmed slots),
  * the most recent :class:`SessionPersonaSnapshot` (immutable
    snapshot taken at session start) + its
    ``mutation_blocked_count`` observability counter,
  * counts of canonical persona events (``snapshot_captured`` /
    ``updated`` / ``slot_locked`` / ``conflict_detected``) over a
    rolling window so the manager has a sense of how stable the
    AI's identity perception has been.

Read-only. The actual writers stay in
:mod:`app.services.persona_memory` (D3) — this endpoint is purely
a projection for the FE card. Same role gate as the rest of
``/clients/...`` (manager / rop / admin).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.database import get_db
from app.models.client import RealClient
from app.models.domain_event import DomainEvent
from app.models.persona import MemoryPersona, SessionPersonaSnapshot
from app.models.training import TrainingSession
from app.models.user import User


router = APIRouter(prefix="/clients", tags=["clients", "persona"])

_require_client_view = require_role("manager", "rop", "admin")


class MemoryPersonaView(BaseModel):
    id: uuid.UUID
    lead_client_id: uuid.UUID
    full_name: str
    gender: str
    role_title: str | None
    address_form: str
    tone: str
    do_not_ask_again_slots: list[str]
    confirmed_facts: dict[str, dict] = Field(default_factory=dict)
    version: int
    last_confirmed_at: datetime
    updated_at: datetime


class SessionSnapshotView(BaseModel):
    session_id: uuid.UUID
    full_name: str
    address_form: str
    captured_from: str
    captured_at: datetime
    mutation_blocked_count: int


class PersonaEventCounts(BaseModel):
    snapshot_captured: int = 0
    updated: int = 0
    slot_locked: int = 0
    conflict_detected: int = 0


class ClientPersonaMemoryResponse(BaseModel):
    real_client_id: uuid.UUID
    lead_client_id: uuid.UUID | None
    persona: MemoryPersonaView | None = None
    last_snapshot: SessionSnapshotView | None = None
    event_counts_window_days: int
    event_counts: PersonaEventCounts


@router.get(
    "/{client_id}/persona-memory",
    response_model=ClientPersonaMemoryResponse,
    summary="TZ-4 persona memory + snapshot + event counts for one client",
)
async def get_client_persona_memory(
    client_id: uuid.UUID,
    days: int = 30,
    user: User = Depends(_require_client_view),
    db: AsyncSession = Depends(get_db),
) -> ClientPersonaMemoryResponse:
    """Read-only projection of the persona layer for the FE card.

    Days window applies to the canonical event counts only — the
    persona row itself and the latest snapshot are returned regardless
    of age.
    """
    # 1. Resolve client + check the manager owns it (or rop/admin).
    client = (
        await db.execute(select(RealClient).where(RealClient.id == client_id))
    ).scalar_one_or_none()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Клиент не найден"
        )
    if user.role.value == "manager" and client.manager_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Карточка принадлежит другому менеджеру",
        )

    lead_client_id = client.lead_client_id

    persona_view: MemoryPersonaView | None = None
    if lead_client_id is not None:
        # Audit-2026-04-28 dedup: re-use the canonical lookup from
        # ``persona_memory.get_for_lead`` instead of re-implementing
        # the SELECT inline. Three different callsites used to do the
        # same query; consolidating to one helper means a future filter
        # (soft-delete column, schema-version filter, ...) lands once.
        from app.services import persona_memory
        persona = await persona_memory.get_for_lead(
            db, lead_client_id=lead_client_id
        )
        if persona is not None:
            persona_view = MemoryPersonaView(
                id=persona.id,
                lead_client_id=persona.lead_client_id,
                full_name=persona.full_name,
                gender=persona.gender,
                role_title=persona.role_title,
                address_form=persona.address_form,
                tone=persona.tone,
                do_not_ask_again_slots=list(persona.do_not_ask_again_slots or []),
                confirmed_facts=dict(persona.confirmed_facts or {}),
                version=persona.version,
                last_confirmed_at=persona.last_confirmed_at,
                updated_at=persona.updated_at,
            )

    # 2. Latest snapshot — joined via TrainingSession.real_client_id so
    # snapshots without a lead anchor (home_preview class) are still
    # visible if they belong to this client.
    snapshot_row = (
        await db.execute(
            select(SessionPersonaSnapshot)
            .join(
                TrainingSession,
                TrainingSession.id == SessionPersonaSnapshot.session_id,
            )
            .where(TrainingSession.real_client_id == client_id)
            .order_by(SessionPersonaSnapshot.captured_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    last_snapshot: SessionSnapshotView | None = None
    if snapshot_row is not None:
        last_snapshot = SessionSnapshotView(
            session_id=snapshot_row.session_id,
            full_name=snapshot_row.full_name,
            address_form=snapshot_row.address_form,
            captured_from=snapshot_row.captured_from,
            captured_at=snapshot_row.captured_at,
            mutation_blocked_count=snapshot_row.mutation_blocked_count,
        )

    # 3. Event counts — only when we have a lead anchor (events
    # reference lead_client_id). Without a lead, there are no
    # canonical events to count.
    counts = PersonaEventCounts()
    if lead_client_id is not None:
        window_from = datetime.now(UTC) - timedelta(days=max(1, days))
        rows = (
            await db.execute(
                select(DomainEvent.event_type, func.count(DomainEvent.id))
                .where(DomainEvent.lead_client_id == lead_client_id)
                .where(DomainEvent.event_type.in_(
                    [
                        "persona.snapshot_captured",
                        "persona.updated",
                        "persona.slot_locked",
                        "persona.conflict_detected",
                    ]
                ))
                .where(DomainEvent.occurred_at >= window_from)
                .group_by(DomainEvent.event_type)
            )
        ).all()
        for et, n in rows:
            if et == "persona.snapshot_captured":
                counts.snapshot_captured = int(n)
            elif et == "persona.updated":
                counts.updated = int(n)
            elif et == "persona.slot_locked":
                counts.slot_locked = int(n)
            elif et == "persona.conflict_detected":
                counts.conflict_detected = int(n)

    return ClientPersonaMemoryResponse(
        real_client_id=client_id,
        lead_client_id=lead_client_id,
        persona=persona_view,
        last_snapshot=last_snapshot,
        event_counts_window_days=days,
        event_counts=counts,
    )
