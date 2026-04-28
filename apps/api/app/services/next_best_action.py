"""Next Best Action router for CRM/client state."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Attachment, ClientInteraction, ClientStatus, ManagerReminder, RealClient
from app.services.knowledge_review_policy import is_recommendation_safe


@dataclass(frozen=True)
class NextBestAction:
    action: str
    priority: int
    reason: str
    mode: str
    due_at: str | None = None
    payload: dict = field(default_factory=dict)
    # TZ-4 §11.2.1 — when this NBA's reasoning leans on a knowledge
    # chunk whose status is anything other than 'actual', the decision
    # is still served (so managers don't see "no recommendation" if the
    # whole legal base is mid-review) but flagged so the FE can render
    # a "источник требует проверки" warning chip. Empty list = no
    # knowledge dependency. ``outdated`` chunks are filtered out
    # entirely upstream by :func:`filter_safe_knowledge_refs`.
    requires_warning: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# TZ-4 §11.2.1 layer 2 — NBA decision boundary filter
def filter_safe_knowledge_refs(
    chunks: Iterable[object],
    *,
    needs_warning_status: Iterable[str] = ("disputed", "needs_review"),
) -> tuple[list[object], bool]:
    """Filter a list of knowledge chunks for NBA consumption.

    Per spec §11.2.1 the NBA decision boundary must drop ``outdated``
    chunks entirely (parity with the SQL filter at
    ``rag_legal.py:217``) AND surface a warning when surviving chunks
    are in ``disputed`` / ``needs_review`` so the recommendation can
    annotate ``requires_warning=True``.

    Returns ``(safe_chunks, requires_warning)``. The caller decides
    what to do with the warning flag — typical pattern is to set
    ``NextBestAction(requires_warning=True)`` so the FE chip renders.

    Today no NBA path actually consumes legal knowledge (verified
    2026-04-28); this filter ships ready so the next PR that wires
    knowledge refs into a recommendation has a single import target
    instead of re-deriving §11.2.1 inline.
    """
    safe: list[object] = []
    needs_warning = False
    warning_set = set(needs_warning_status)
    for chunk in chunks:
        status = getattr(chunk, "knowledge_status", None) or "actual"
        if not is_recommendation_safe(status):
            # outdated → dropped
            continue
        if status in warning_set:
            needs_warning = True
        safe.append(chunk)
    return safe, needs_warning


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def choose_next_best_action(
    *,
    client: RealClient,
    now: datetime | None = None,
    open_reminders: int = 0,
    pending_attachments: int = 0,
    last_interaction_result: str | None = None,
) -> NextBestAction:
    now = now or datetime.now(timezone.utc)
    status = client.status.value if hasattr(client.status, "value") else str(client.status)

    if client.next_contact_at and client.next_contact_at <= now:
        return NextBestAction(
            action="make_follow_up_call",
            priority=1,
            reason="Назначенный повторный контакт уже наступил",
            mode="call",
            due_at=_iso(client.next_contact_at),
            payload={"client_id": str(client.id), "status": status},
        )

    if open_reminders > 0:
        return NextBestAction(
            action="complete_open_reminder",
            priority=2,
            reason="Есть незакрытая CRM-задача по клиенту",
            mode="crm",
            due_at=_iso(client.next_contact_at),
            payload={"client_id": str(client.id), "open_reminders": open_reminders},
        )

    if pending_attachments > 0:
        return NextBestAction(
            action="process_documents",
            priority=2,
            reason="Есть документы без завершённой классификации/OCR",
            mode="crm",
            payload={"client_id": str(client.id), "pending_attachments": pending_attachments},
        )

    if status == ClientStatus.new.value:
        return NextBestAction(
            action="start_center_call",
            priority=3,
            reason="Новый клиент ещё не квалифицирован",
            mode="center",
            payload={"client_id": str(client.id)},
        )

    if status in {ClientStatus.contacted.value, ClientStatus.interested.value, ClientStatus.thinking.value}:
        due_at = client.next_contact_at or now + timedelta(hours=24)
        return NextBestAction(
            action="schedule_or_make_follow_up",
            priority=3,
            reason="Клиент в промежуточной стадии, нужен следующий контакт",
            mode="call",
            due_at=_iso(due_at),
            payload={"client_id": str(client.id), "last_interaction_result": last_interaction_result},
        )

    if status == ClientStatus.consent_given.value:
        return NextBestAction(
            action="request_documents",
            priority=3,
            reason="Согласие получено, следующий шаг — сбор документов",
            mode="chat",
            payload={"client_id": str(client.id), "required_documents": ["passport", "creditors", "bailiff_documents"]},
        )

    if status == ClientStatus.contract_signed.value:
        return NextBestAction(
            action="handoff_to_process",
            priority=4,
            reason="Договор подписан, клиент должен перейти в сопровождение процедуры",
            mode="crm",
            payload={"client_id": str(client.id)},
        )

    return NextBestAction(
        action="review_client_card",
        priority=5,
        reason="Нет срочного автоматического действия; нужна проверка карточки",
        mode="crm",
        payload={"client_id": str(client.id), "status": status},
    )


async def build_next_best_action(
    db: AsyncSession,
    *,
    client: RealClient,
    manager_id: uuid.UUID,
) -> NextBestAction:
    open_reminders = (await db.execute(
        select(func.count())
        .select_from(ManagerReminder)
        .where(
            ManagerReminder.client_id == client.id,
            ManagerReminder.manager_id == manager_id,
            ManagerReminder.is_completed == False,  # noqa: E712
        )
    )).scalar_one() or 0

    pending_attachments = (await db.execute(
        select(func.count())
        .select_from(Attachment)
        .where(
            Attachment.client_id == client.id,
            Attachment.status == "received",
            # B1 — accept BOTH spec-canonical (`ocr_pending` /
            # `classification_pending`) and legacy (`pending`) forms
            # during the migration window. Migration 20260427_004
            # updates rows in place; this OR keeps NBA correct even if
            # the migration runs after this code is deployed.
            (Attachment.ocr_status.in_(["ocr_pending", "pending"]))
            | (Attachment.classification_status.in_(["classification_pending", "pending"])),
        )
    )).scalar_one() or 0

    last_interaction = (await db.execute(
        select(ClientInteraction)
        .where(ClientInteraction.client_id == client.id)
        .order_by(ClientInteraction.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    return choose_next_best_action(
        client=client,
        open_reminders=int(open_reminders),
        pending_attachments=int(pending_attachments),
        last_interaction_result=last_interaction.result if last_interaction else None,
    )
