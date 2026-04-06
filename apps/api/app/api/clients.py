"""
REST API — Модуль «Связь с клиентом» (Agent 7).
Эндпоинты: clients, consents, interactions, notifications, reminders.
ТЗ v2, разделы 5.1–5.4.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import errors as err
from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.client import (
    ClientConsent,
    ClientInteraction,
    ClientNotification,
    ClientStatus,
    ManagerReminder,
    NotificationChannel,
    NotificationStatus,
    RealClient,
)
from app.models.user import User, UserRole
from app.schemas.client import (
    AuditLogListResponse,
    AuditLogResponse,
    BulkReassignRequest,
    BulkReassignResponse,
    ClientCreateRequest,
    ClientCreateResponse,
    ClientDuplicateResponse,
    ClientExportRequest,
    ClientListResponse,
    ClientMergeRequest,
    ClientResponse,
    ClientStatsAnonymizedResponse,
    ClientStatsResponse,
    ClientStatusChangeRequest,
    ClientUpdateRequest,
    ConsentCreateRequest,
    ConsentResponse,
    ConsentRevokeRequest,
    ConsentVerifyResponse,
    InteractionCreateRequest,
    InteractionResponse,
    InteractionSummaryResponse,
    NotificationListResponse,
    NotificationResponse,
    PipelineResponse,
    ReminderCreateRequest,
    ReminderResponse,
    SendNotificationRequest,
)
from app.services.audit import write_audit_log
from app.services.recommendation_engine import RecommendationEngine, report_to_dict
from app.services.client_service import (
    change_client_status,
    check_notification_rate_limit,
    confirm_consent_token,
    create_client,
    create_consent_with_token,
    create_interaction,
    find_duplicates,
    get_client,
    get_client_stats,
    get_interaction_summary,
    get_pipeline,
    grant_consent,
    list_clients,
    revoke_consent,
    soft_delete_client,
    update_client,
    verify_consent_token,
)
from app.ws.notifications import send_ws_notification

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def _consent_verify_url(token: str) -> str:
    base = settings.frontend_url.rstrip("/")
    return f"{base}/consent/verify/{token}"


def _default_consent_legal_text(consent_type: str) -> str:
    text_map = {
        "data_processing": "Я подтверждаю согласие на обработку моих персональных данных для сопровождения обращения по банкротству.",
        "contact_allowed": "Я разрешаю связаться со мной по телефону, в мессенджерах и по email по моему обращению.",
        "consultation_agreed": "Я подтверждаю согласие на проведение консультации по вопросу банкротства физических лиц.",
        "bfl_procedure": "Я подтверждаю согласие на запуск подготовки к процедуре банкротства и сбор необходимых данных.",
        "marketing": "Я подтверждаю согласие на получение информационных сообщений и материалов.",
    }
    return text_map.get(consent_type, "Я подтверждаю согласие с условиями обработки данных и сопровождения обращения.")


# ══════════════════════════════════════════════════════════════════════════════
# CLIENTS CRUD
# ══════════════════════════════════════════════════════════════════════════════


@router.post("", response_model=ClientCreateResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def api_create_client(
    body: ClientCreateRequest,
    request: Request,
    user: User = Depends(require_role("manager", "rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Создать карточку клиента (с проверкой дублей по телефону)."""
    client, warning, dupe_ids = await create_client(
        db,
        manager=user,
        full_name=body.full_name,
        phone=body.phone,
        email=body.email,
        debt_amount=body.debt_amount,
        debt_details=body.debt_details,
        source=body.source,
        notes=body.notes,
        next_contact_at=body.next_contact_at,
        initial_consent_type=body.initial_consent_type,
        initial_consent_channel=body.initial_consent_channel,
        request=request,
    )
    return ClientCreateResponse(
        client=_client_to_response(client),
        duplicate_warning=warning,
        duplicate_ids=dupe_ids or None,
    )


@router.get("", response_model=ClientListResponse)
async def api_list_clients(
    request: Request,
    status_param: list[str] | None = Query(None, alias="status"),
    manager_id: uuid.UUID | None = None,
    search: str | None = None,
    source: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: User = Depends(require_role("manager", "rop", "admin", "methodologist")),
    db: AsyncSession = Depends(get_db),
):
    """Список клиентов с фильтрацией и пагинацией."""
    clients, total = await list_clients(
        db,
        user=user,
        status_filter=status_param,
        manager_id=manager_id,
        search=search,
        source=source,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page,
    )
    pages = (total + per_page - 1) // per_page
    return ClientListResponse(
        items=[_client_to_response(c) for c in clients],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.get("/pipeline", response_model=list[PipelineResponse])
async def api_get_pipeline(
    user: User = Depends(require_role("manager", "rop", "admin", "methodologist")),
    db: AsyncSession = Depends(get_db),
):
    """Воронка: count по статусам для канбан-доски."""
    data = await get_pipeline(db, user=user)
    return [PipelineResponse(**item) for item in data]


@router.get("/pipeline/stats")
async def api_get_pipeline_stats(
    user: User = Depends(require_role("manager", "rop", "admin", "methodologist")),
    db: AsyncSession = Depends(get_db),
):
    """
    B-FIX-1: Комбинированная статистика воронки — status + count + total_debt.
    Фронт ожидает: PipelineStats[] = [{status, count, total_debt}].
    """
    data = await get_pipeline(db, user=user)
    return data


@router.get("/stats", response_model=ClientStatsResponse)
async def api_get_stats(
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Статистика воронки: конверсия, средний цикл, потери."""
    return await get_client_stats(db, user=user)


@router.get("/stats/anonymized", response_model=ClientStatsAnonymizedResponse)
async def api_get_stats_anonymized(
    user: User = Depends(require_role("methodologist", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Анонимизированная статистика для методолога."""
    stats = await get_client_stats(db, user=user, anonymized=True)
    return ClientStatsAnonymizedResponse(
        total_clients=stats["total_clients"],
        by_status=stats["by_status"],
        conversion_rates=stats["conversion_rates"],
        avg_cycle_days=stats.get("avg_cycle_days"),
        lost_reasons_distribution={},
    )


@router.get("/duplicates")
async def api_get_duplicates(
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Список дублей по телефону."""
    return await find_duplicates(db, user=user)


@router.post("/bulk/reassign", response_model=BulkReassignResponse)
@limiter.limit("5/minute")
async def api_bulk_reassign(
    body: BulkReassignRequest,
    request: Request,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Массовое переназначение клиентов другому менеджеру."""
    reassigned = 0
    errors = []

    for client_id in body.client_ids:
        try:
            client = await get_client(db, client_id=client_id, user=user)
            old_manager = client.manager_id
            client.manager_id = body.new_manager_id

            await write_audit_log(
                db,
                actor=user,
                action="bulk_reassign",
                entity_type="real_clients",
                entity_id=client.id,
                old_values={"manager_id": str(old_manager)},
                new_values={"manager_id": str(body.new_manager_id)},
                request=request,
            )
            reassigned += 1
        except HTTPException as e:
            errors.append(f"{client_id}: {e.detail}")

    await db.flush()
    return BulkReassignResponse(reassigned=reassigned, errors=errors)


@router.post("/bulk/export")
@limiter.limit("3/minute")
async def api_bulk_export(
    body: ClientExportRequest | None = None,
    user: User = Depends(require_role("rop", "admin", "methodologist")),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Экспорт выбранных клиентов в JSON."""
    selected_ids = body.client_ids if body and body.client_ids else []
    if selected_ids:
        clients: list[RealClient] = []
        for client_id in selected_ids:
            try:
                clients.append(await get_client(db, client_id=client_id, user=user))
            except HTTPException:
                continue
    else:
        # Cap export at 500 clients per request to prevent OOM on large datasets.
        # Admin/methodologist can use selected_ids for targeted exports.
        _EXPORT_MAX = 500
        clients, _ = await list_clients(db, user=user, per_page=_EXPORT_MAX)
    total = len(clients)

    await write_audit_log(
        db,
        actor=user,
        action="export_data",
        entity_type="real_clients",
        new_values={"count": total, "role": user.role.value},
        request=request,
    )

    return {
        "items": [_client_to_response(c).model_dump(mode="json") for c in clients],
        "count": total,
        "role": user.role.value,
    }


# ─── B-FIX-4: Audit Log — MUST be before /{client_id} to avoid UUID parse ──
from app.models.client import AuditLog


@router.get("/audit-log", response_model=AuditLogListResponse)
async def api_get_audit_log(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    actor_id: uuid.UUID | None = Query(None, description="Фильтр по исполнителю"),
    entity_type: str | None = Query(None, description="Фильтр по типу сущности (real_clients, client_consents)"),
    action: str | None = Query(None, description="Фильтр по действию (create_client, revoke_consent...)"),
    date_from: datetime | None = Query(None, description="Начало периода (ISO 8601)"),
    date_to: datetime | None = Query(None, description="Конец периода (ISO 8601)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """
    Просмотр audit log (152-ФЗ compliance). Доступ: только admin.
    """
    query = select(AuditLog).order_by(AuditLog.created_at.desc())

    if actor_id:
        query = query.where(AuditLog.actor_id == actor_id)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if action:
        query = query.where(AuditLog.action == action)
    if date_from:
        query = query.where(AuditLog.created_at >= date_from)
    if date_to:
        query = query.where(AuditLog.created_at <= date_to)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * per_page
    rows = await db.execute(query.offset(offset).limit(per_page))
    logs = list(rows.scalars().all())

    items = []
    for log in logs:
        actor_name = None
        if log.actor:
            actor_name = log.actor.full_name or log.actor.email
        items.append(
            AuditLogResponse(
                id=log.id,
                actor_id=log.actor_id,
                actor_name=actor_name,
                actor_role=log.actor_role,
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                old_values=log.old_values,
                new_values=log.new_values,
                ip_address=log.ip_address,
                created_at=log.created_at,
            )
        )

    return AuditLogListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{client_id}", response_model=ClientResponse)
async def api_get_client(
    client_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_role("manager", "rop", "admin", "methodologist")),
    db: AsyncSession = Depends(get_db),
):
    """Детали клиента + история + согласия."""
    client = await get_client(db, client_id=client_id, user=user, request=request)
    consents_result = await db.execute(
        select(ClientConsent)
        .where(ClientConsent.client_id == client.id)
        .order_by(ClientConsent.created_at.desc())
    )
    interactions_result = await db.execute(
        select(ClientInteraction)
        .where(ClientInteraction.client_id == client.id)
        .order_by(ClientInteraction.created_at.desc())
        .limit(200)
    )
    client.consents = list(consents_result.scalars().all())
    client.interactions = list(interactions_result.scalars().all())
    return _client_to_response(client, include_details=True)


@router.put("/{client_id}", response_model=ClientResponse)
@limiter.limit("20/minute")
async def api_update_client(
    client_id: uuid.UUID,
    body: ClientUpdateRequest,
    request: Request,
    user: User = Depends(require_role("manager", "rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Обновить карточку клиента."""
    updates = body.model_dump(exclude_none=True)
    client = await update_client(
        db, client_id=client_id, user=user, updates=updates, request=request
    )
    return _client_to_response(client)


@router.patch("/{client_id}/status", response_model=ClientResponse)
@limiter.limit("20/minute")
async def api_change_status(
    client_id: uuid.UUID,
    body: ClientStatusChangeRequest,
    request: Request,
    user: User = Depends(require_role("manager", "rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Сменить статус клиента (с валидацией перехода)."""
    client = await change_client_status(
        db,
        client_id=client_id,
        user=user,
        new_status=body.new_status,
        reason=body.reason,
        request=request,
    )
    return _client_to_response(client)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def api_delete_client(
    client_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete клиента (только admin)."""
    await soft_delete_client(db, client_id=client_id, user=user, request=request)


@router.post("/{client_id}/merge")
@limiter.limit("5/minute")
async def api_merge_clients(
    client_id: uuid.UUID,
    body: ClientMergeRequest,
    request: Request,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Объединить дубли: история duplicate → main, duplicate deactivated."""
    main_client = await get_client(db, client_id=client_id, user=user)
    dupe_client = await get_client(db, client_id=body.duplicate_id, user=user)

    # Перенос взаимодействий
    result = await db.execute(
        select(ClientInteraction).where(ClientInteraction.client_id == dupe_client.id)
    )
    for interaction in result.scalars().all():
        interaction.client_id = main_client.id

    # Перенос согласий (если нет конфликтов)
    result = await db.execute(
        select(ClientConsent).where(ClientConsent.client_id == dupe_client.id)
    )
    for consent in result.scalars().all():
        consent.client_id = main_client.id

    # Деактивация дубля
    dupe_client.is_active = False

    await write_audit_log(
        db,
        actor=user,
        action="merge_clients",
        entity_type="real_clients",
        entity_id=main_client.id,
        old_values={"duplicate_id": str(dupe_client.id)},
        new_values={"merged": True, "duplicate_deactivated": True},
        request=request,
    )

    await db.flush()
    return {"status": "merged", "main_id": str(main_client.id)}


# ══════════════════════════════════════════════════════════════════════════════
# CONSENTS
# ══════════════════════════════════════════════════════════════════════════════


@router.post("/{client_id}/consents", response_model=ConsentResponse, status_code=201)
@limiter.limit("10/minute")
async def api_create_consent(
    client_id: uuid.UUID,
    body: ConsentCreateRequest,
    request: Request,
    user: User = Depends(require_role("manager", "rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Зафиксировать новое согласие клиента."""
    client = await get_client(db, client_id=client_id, user=user)
    consent = await grant_consent(
        db,
        client=client,
        consent_type=body.consent_type,
        channel=body.channel,
        recorded_by=user,
        legal_text_version=body.legal_text_version,
        evidence_url=body.evidence_url,
        ip_address=body.ip_address,
        user_agent=body.user_agent,
        request=request,
    )
    return _consent_to_response(consent)


@router.get("/{client_id}/consents", response_model=list[ConsentResponse])
async def api_list_consents(
    client_id: uuid.UUID,
    user: User = Depends(require_role("manager", "rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Все согласия клиента (активные + отозванные)."""
    result = await db.execute(
        select(ClientConsent)
        .where(ClientConsent.client_id == client_id)
        .order_by(ClientConsent.created_at.desc())
    )
    return [_consent_to_response(c) for c in result.scalars().all()]


@router.post("/{client_id}/consents/{consent_id}/revoke", response_model=ConsentResponse)
@limiter.limit("5/minute")
async def api_revoke_consent(
    client_id: uuid.UUID,
    consent_id: uuid.UUID,
    body: ConsentRevokeRequest,
    request: Request,
    user: User = Depends(require_role("manager", "rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Отозвать согласие клиента (152-ФЗ, audit_log)."""
    consent = await revoke_consent(
        db, consent_id=consent_id, user=user, reason=body.reason, request=request
    )
    return _consent_to_response(consent)


@router.post("/{client_id}/consents/send-link")
@limiter.limit("3/minute")
async def api_send_consent_link(
    client_id: uuid.UUID,
    consent_type: str = Query(...),
    request: Request = None,
    user: User = Depends(require_role("manager", "rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Отправить SMS-ссылку на подтверждение согласия."""
    client = await get_client(db, client_id=client_id, user=user)

    if not client.phone:
        raise HTTPException(status_code=400, detail="У клиента не указан телефон")

    consent = await create_consent_with_token(
        db, client=client, consent_type=consent_type, recorded_by=user, request=request
    )

    verify_url = _consent_verify_url(consent.token)
    notification = ClientNotification(
        recipient_type="client",
        recipient_id=client.id,
        client_id=client.id,
        channel=NotificationChannel.sms,
        title="Ссылка на подтверждение согласия",
        body=f"{client.full_name}, подтвердите согласие: {verify_url}",
        template_id="consent_link",
        status=NotificationStatus.sent,
        sent_at=datetime.now(timezone.utc),
        delivered_at=datetime.now(timezone.utc),
        metadata_={"verify_url": verify_url, "consent_type": consent_type},
    )
    db.add(notification)

    manager_notification = ClientNotification(
        recipient_type="manager",
        recipient_id=user.id,
        client_id=client.id,
        channel=NotificationChannel.in_app,
        title="Ссылка на согласие создана",
        body=f"{client.full_name}: ссылка готова и ожидает подтверждения.",
        template_id="consent_link_created",
        status=NotificationStatus.sent,
        sent_at=datetime.now(timezone.utc),
        metadata_={"client_id": str(client.id), "verify_url": verify_url},
    )
    db.add(manager_notification)
    await db.flush()
    await send_ws_notification(
        user.id,
        event_type="notification.new",
        data={
            "id": str(manager_notification.id),
            "title": manager_notification.title,
            "body": manager_notification.body,
            "type": "consent",
            "client_id": str(client.id),
        },
    )

    return {
        "status": "link_created",
        "token": consent.token,
        "verify_url": verify_url,
        "expires_at": consent.token_expires_at.isoformat() if consent.token_expires_at else None,
    }


# ── Public consent verification (rate limited) ──────────────────────────────


@router.get("/consents/verify/{token}", response_model=ConsentVerifyResponse)
async def api_verify_consent_get(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Публичный эндпоинт: клиент смотрит форму подтверждения."""
    consent = await verify_consent_token(db, token=token)
    if not consent:
        raise HTTPException(status_code=410, detail="Ссылка недействительна или истекла")

    # Загружаем клиента
    result = await db.execute(
        select(RealClient).where(RealClient.id == consent.client_id)
    )
    client = result.scalar_one_or_none()

    return ConsentVerifyResponse(
        client_name=client.full_name if client else "Клиент",
        consent_type=consent.consent_type,
        legal_text=_default_consent_legal_text(consent.consent_type),
        status="pending" if not consent.token_used_at else "confirmed",
    )


@router.post("/consents/verify/{token}")
@limiter.limit("10/minute")
async def api_verify_consent_post(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Публичный эндпоинт: клиент подтверждает согласие."""
    consent = await verify_consent_token(db, token=token)
    if not consent:
        raise HTTPException(status_code=410, detail="Ссылка недействительна или истекла")

    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not ip:
        ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")[:500]

    await confirm_consent_token(db, consent=consent, ip_address=ip, user_agent=ua)

    return {"status": "confirmed", "consent_type": consent.consent_type}


# ══════════════════════════════════════════════════════════════════════════════
# INTERACTIONS
# ══════════════════════════════════════════════════════════════════════════════


@router.post("/{client_id}/interactions", response_model=InteractionResponse, status_code=201)
@limiter.limit("20/minute")
async def api_create_interaction(
    client_id: uuid.UUID,
    body: InteractionCreateRequest,
    request: Request,
    user: User = Depends(require_role("manager", "rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Записать взаимодействие (звонок, встречу, заметку)."""
    # Проверяем доступ
    await get_client(db, client_id=client_id, user=user)

    interaction = await create_interaction(
        db,
        client_id=client_id,
        manager=user,
        interaction_type=body.interaction_type,
        content=body.content,
        result=body.result,
        duration_seconds=body.duration_seconds,
    )
    return _interaction_to_response(interaction)


@router.get("/{client_id}/interactions", response_model=list[InteractionResponse])
async def api_list_interactions(
    client_id: uuid.UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    user: User = Depends(require_role("manager", "rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Таймлайн всех взаимодействий с клиентом."""
    await get_client(db, client_id=client_id, user=user)

    result = await db.execute(
        select(ClientInteraction)
        .where(ClientInteraction.client_id == client_id)
        .order_by(ClientInteraction.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    return [_interaction_to_response(i) for i in result.scalars().all()]


@router.get("/{client_id}/interactions/summary", response_model=InteractionSummaryResponse)
async def api_interaction_summary(
    client_id: uuid.UUID,
    user: User = Depends(require_role("manager", "rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Краткая сводка: кол-во звонков, встреч, дней в воронке."""
    await get_client(db, client_id=client_id, user=user)
    return await get_interaction_summary(db, client_id=client_id)


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════


@router.post("/{client_id}/notify")
@limiter.limit("10/minute")
async def api_send_notification(
    client_id: uuid.UUID,
    body: SendNotificationRequest,
    request: Request,
    user: User = Depends(require_role("manager", "rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Отправить уведомление клиенту (SMS/WA/Email) с rate limiting."""
    client = await get_client(db, client_id=client_id, user=user)

    # Rate limit check (ТЗ v2, раздел 7.1)
    await check_notification_rate_limit(db, client_id=client_id, channel=body.channel)

    notification = ClientNotification(
        recipient_type="client",
        recipient_id=client.id,
        client_id=client.id,
        channel=NotificationChannel(body.channel),
        title=f"Уведомление для {client.full_name}",
        body=body.custom_message,
        template_id=body.template_id,
        status=NotificationStatus.pending,
    )
    db.add(notification)

    await write_audit_log(
        db,
        actor=user,
        action="send_notification",
        entity_type="client_notifications",
        entity_id=notification.id,
        new_values={"channel": body.channel, "client_id": str(client_id)},
        request=request,
    )

    has_destination = (
        (body.channel == "sms" and bool(client.phone))
        or (body.channel == "whatsapp" and bool(client.phone))
        or (body.channel == "email" and bool(client.email))
    )
    notification.status = NotificationStatus.sent if has_destination else NotificationStatus.failed
    notification.sent_at = datetime.now(timezone.utc)
    if has_destination:
        notification.delivered_at = datetime.now(timezone.utc)
        notification.metadata_ = {
            "delivery_mode": "simulated_gateway",
            "recipient": client.phone if body.channel in {"sms", "whatsapp"} else client.email,
        }
    else:
        notification.failed_reason = "У клиента отсутствует контакт для выбранного канала"

    manager_notice = ClientNotification(
        recipient_type="manager",
        recipient_id=user.id,
        client_id=client.id,
        channel=NotificationChannel.in_app,
        title="Уведомление клиенту отправлено" if has_destination else "Уведомление не отправлено",
        body=(
            f"{client.full_name}: канал {body.channel} поставлен в очередь."
            if has_destination
            else f"{client.full_name}: не удалось отправить через {body.channel}, отсутствует контакт."
        ),
        template_id="client_notification_result",
        status=NotificationStatus.sent,
        sent_at=datetime.now(timezone.utc),
        metadata_={"client_id": str(client.id), "channel": body.channel},
    )
    db.add(manager_notice)

    await db.flush()
    await send_ws_notification(
        user.id,
        event_type="notification.new",
        data={
            "id": str(manager_notice.id),
            "title": manager_notice.title,
            "body": manager_notice.body,
            "type": "system" if has_destination else "warning",
            "client_id": str(client.id),
        },
    )
    return {
        "status": "sent" if has_destination else "failed",
        "notification_id": str(notification.id),
        "channel": body.channel,
        "failed_reason": notification.failed_reason,
    }


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS (In-App)
# ══════════════════════════════════════════════════════════════════════════════


notifications_router = APIRouter()


@notifications_router.get("", response_model=NotificationListResponse)
async def api_my_notifications(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Мои in-app уведомления."""
    query = (
        select(ClientNotification)
        .where(
            ClientNotification.recipient_type == "manager",
            ClientNotification.recipient_id == user.id,
            ClientNotification.channel == NotificationChannel.in_app,
        )
        .order_by(ClientNotification.created_at.desc())
    )

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Unread count
    unread_q = select(func.count()).where(
        ClientNotification.recipient_type == "manager",
        ClientNotification.recipient_id == user.id,
        ClientNotification.channel == NotificationChannel.in_app,
        ClientNotification.read_at.is_(None),
    )
    unread = (await db.execute(unread_q)).scalar() or 0

    result = await db.execute(
        query.offset((page - 1) * per_page).limit(per_page)
    )

    return NotificationListResponse(
        items=[_notification_to_response(n) for n in result.scalars().all()],
        total=total,
        unread_count=unread,
    )


@notifications_router.post("/{notification_id}/read")
async def api_read_notification(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Отметить уведомление как прочитанное."""
    result = await db.execute(
        select(ClientNotification).where(
            ClientNotification.id == notification_id,
            ClientNotification.recipient_id == user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Уведомление не найдено")

    notification.read_at = datetime.now(timezone.utc)
    notification.status = NotificationStatus.read
    await db.flush()
    return {"status": "read"}


@notifications_router.post("/read-all")
async def api_read_all_notifications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Отметить все уведомления прочитанными."""
    from sqlalchemy import update

    await db.execute(
        update(ClientNotification)
        .where(
            ClientNotification.recipient_id == user.id,
            ClientNotification.read_at.is_(None),
        )
        .values(read_at=datetime.now(timezone.utc), status=NotificationStatus.read)
    )
    await db.flush()
    return {"status": "all_read"}


@notifications_router.get("/unread-count")
async def api_unread_count(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Счётчик непрочитанных (для badge)."""
    result = await db.execute(
        select(func.count()).where(
            ClientNotification.recipient_type == "manager",
            ClientNotification.recipient_id == user.id,
            ClientNotification.channel == NotificationChannel.in_app,
            ClientNotification.read_at.is_(None),
        )
    )
    return {"unread_count": result.scalar() or 0}


# ── X6: Web Push Subscription endpoints ──────────────────────────────────────


@notifications_router.get("/push/vapid-key")
async def api_vapid_public_key():
    """Return VAPID public key for client-side subscription."""
    return {"public_key": settings.vapid_public_key or ""}


@notifications_router.post("/push/subscribe")
async def api_push_subscribe(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a push subscription for the current user."""
    from app.services.web_push import save_subscription

    body = await request.json()
    endpoint = body.get("endpoint")
    keys = body.get("keys", {})
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")

    if not endpoint or not p256dh or not auth:
        raise HTTPException(status_code=400, detail=err.MISSING_SUBSCRIPTION_DATA)

    sub = await save_subscription(
        db,
        user_id=user.id,
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth,
        user_agent=request.headers.get("User-Agent"),
    )
    await db.commit()

    return {"status": "subscribed", "id": str(sub.id)}


@notifications_router.post("/push/unsubscribe")
async def api_push_unsubscribe(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a push subscription."""
    from app.services.web_push import remove_subscription

    body = await request.json()
    endpoint = body.get("endpoint")
    if not endpoint:
        raise HTTPException(status_code=400, detail=err.MISSING_ENDPOINT)

    removed = await remove_subscription(db, user_id=user.id, endpoint=endpoint)
    await db.commit()

    return {"status": "unsubscribed" if removed else "not_found"}


@notifications_router.post("/push/test")
async def api_push_test(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a test push notification to the current user."""
    from app.services.web_push import send_push_to_user

    count = await send_push_to_user(
        db,
        user_id=user.id,
        title="Hunter888 — Тест",
        body="Push-уведомления работают!",
        tag="test",
    )
    await db.commit()

    return {"status": "sent", "delivered_to": count}


# ══════════════════════════════════════════════════════════════════════════════
# REMINDERS
# ══════════════════════════════════════════════════════════════════════════════


reminders_router = APIRouter()


@reminders_router.get("", response_model=list[ReminderResponse])
async def api_my_reminders(
    include_completed: bool = False,
    user: User = Depends(require_role("manager", "rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Мои напоминания (сегодня + предстоящие)."""
    query = (
        select(ManagerReminder)
        .where(ManagerReminder.manager_id == user.id)
    )
    if not include_completed:
        query = query.where(ManagerReminder.is_completed == False)  # noqa: E712

    query = query.order_by(ManagerReminder.remind_at.asc())
    result = await db.execute(query)
    return [_reminder_to_response(r) for r in result.scalars().all()]


@reminders_router.post("", response_model=ReminderResponse, status_code=201)
async def api_create_reminder(
    body: ReminderCreateRequest,
    user: User = Depends(require_role("manager", "rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Создать напоминание."""
    # Проверяем доступ к клиенту
    await get_client(db, client_id=body.client_id, user=user)

    reminder = ManagerReminder(
        manager_id=user.id,
        client_id=body.client_id,
        remind_at=body.remind_at,
        message=body.message,
        auto_generated=False,
    )
    db.add(reminder)
    await db.flush()
    return _reminder_to_response(reminder)


@reminders_router.post("/{reminder_id}/complete")
async def api_complete_reminder(
    reminder_id: uuid.UUID,
    user: User = Depends(require_role("manager", "rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Отметить напоминание выполненным."""
    result = await db.execute(
        select(ManagerReminder).where(
            ManagerReminder.id == reminder_id,
            ManagerReminder.manager_id == user.id,
        )
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        raise HTTPException(status_code=404, detail="Напоминание не найдено")

    reminder.is_completed = True
    reminder.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return {"status": "completed"}


@reminders_router.delete("/{reminder_id}", status_code=204)
async def api_delete_reminder(
    reminder_id: uuid.UUID,
    user: User = Depends(require_role("manager", "rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Удалить напоминание."""
    result = await db.execute(
        select(ManagerReminder).where(
            ManagerReminder.id == reminder_id,
            ManagerReminder.manager_id == user.id,
        )
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        raise HTTPException(status_code=404, detail="Напоминание не найдено")

    await db.delete(reminder)
    await db.flush()


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS — Response builders
# ══════════════════════════════════════════════════════════════════════════════


def _client_to_response(client: RealClient, include_details: bool = False) -> ClientResponse:
    debt_details = client.debt_details or {}
    creditors = debt_details.get("creditors")
    tags = debt_details.get("tags")

    resp = ClientResponse(
        id=client.id,
        manager_id=client.manager_id,
        manager_name=client.manager.full_name if client.manager else None,
        full_name=client.full_name,
        phone=client.phone,
        email=client.email,
        status=client.status.value,
        is_active=client.is_active,
        debt_amount=client.debt_amount,
        debt_details=client.debt_details,
        source=client.source,
        notes=client.notes,
        next_contact_at=client.next_contact_at,
        lost_reason=client.lost_reason,
        lost_count=client.lost_count,
        last_status_change_at=client.last_status_change_at,
        created_at=client.created_at,
        updated_at=client.updated_at,
        city=debt_details.get("city"),
        income=debt_details.get("income"),
        creditors=creditors if isinstance(creditors, list) else [],
        tags=tags if isinstance(tags, list) else [],
    )
    if include_details and getattr(client, "consents", None):
        resp.active_consents = [
            _consent_to_response(c) for c in client.consents if c.revoked_at is None
        ]
        resp.consents = [_consent_to_response(c) for c in client.consents]
    if include_details and getattr(client, "interactions", None):
        resp.recent_interactions = [_interaction_to_response(i) for i in client.interactions[:10]]
        resp.interactions = [_interaction_to_response(i) for i in client.interactions]
    return resp


def _consent_to_response(consent: ClientConsent) -> ConsentResponse:
    return ConsentResponse(
        id=consent.id,
        client_id=consent.client_id,
        consent_type=consent.consent_type,
        channel=consent.channel.value if consent.channel else None,
        legal_text_version=consent.legal_text_version,
        granted_at=consent.granted_at,
        revoked_at=consent.revoked_at,
        revoked_reason=consent.revoked_reason,
        recorded_by=consent.recorded_by,
        recorder_name=consent.recorder.full_name if consent.recorder else None,
        evidence_url=consent.evidence_url,
        is_active=consent.is_active,
        created_at=consent.created_at,
    )


def _interaction_to_response(interaction: ClientInteraction) -> InteractionResponse:
    return InteractionResponse(
        id=interaction.id,
        client_id=interaction.client_id,
        manager_id=interaction.manager_id,
        manager_name=interaction.manager.full_name if interaction.manager else None,
        interaction_type=interaction.interaction_type.value,
        content=interaction.content,
        result=interaction.result,
        duration_seconds=interaction.duration_seconds,
        old_status=interaction.old_status,
        new_status=interaction.new_status,
        created_at=interaction.created_at,
    )


def _notification_to_response(n: ClientNotification) -> NotificationResponse:
    return NotificationResponse(
        id=n.id,
        title=n.title,
        body=n.body,
        channel=n.channel.value,
        status=n.status.value,
        client_id=n.client_id,
        read_at=n.read_at,
        created_at=n.created_at,
    )


def _reminder_to_response(r: ManagerReminder) -> ReminderResponse:
    return ReminderResponse(
        id=r.id,
        manager_id=r.manager_id,
        client_id=r.client_id,
        client_name=r.client.full_name if r.client else None,
        remind_at=r.remind_at,
        message=r.message,
        is_completed=r.is_completed,
        completed_at=r.completed_at,
        auto_generated=r.auto_generated,
        created_at=r.created_at,
    )


def _debt_range(amount) -> str:
    """Анонимизация суммы долга для методолога."""
    if not amount:
        return "unknown"
    a = float(amount)
    if a < 300_000:
        return "< 300K"
    if a < 1_000_000:
        return "300K-1M"
    if a < 5_000_000:
        return "1M-5M"
    return "> 5M"


# ─── X5: Recommendation Engine ──────────────────────────────────────────────


@router.get("/recommendations/my")
async def get_my_recommendations(
    period_days: int = Query(90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Персональные рекомендации менеджера на основе анализа потерь.
    ТЗ v2, Task X5.
    """
    engine = RecommendationEngine(period_days=period_days)
    report = await engine.generate_report(
        db,
        manager_id=current_user.id,
        manager_name=current_user.full_name or "",
    )
    return report_to_dict(report)


@router.get("/recommendations/{manager_id}")
async def get_manager_recommendations(
    manager_id: uuid.UUID,
    period_days: int = Query(90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("rop", "admin")),
):
    """
    Рекомендации для конкретного менеджера (доступ: РОП, админ).
    ТЗ v2, Task X5.
    """
    # Verify manager exists
    result = await db.execute(select(User).where(User.id == manager_id))
    manager = result.scalar_one_or_none()
    if not manager:
        raise HTTPException(status_code=404, detail=err.MANAGER_NOT_FOUND)

    engine = RecommendationEngine(period_days=period_days)
    report = await engine.generate_report(
        db,
        manager_id=manager_id,
        manager_name=manager.full_name or "",
    )
    return report_to_dict(report)



# (audit-log route moved above /{client_id} to fix UUID parse error)


# ─── Graph Visualization Data ────────────────────────────────────────────────

from app.models.client import ALLOWED_STATUS_TRANSITIONS


_GRAPH_MAX_CLIENTS = 5000  # Hard cap to prevent unbounded memory usage


@router.get("/graph/data")
async def api_get_graph_data(
    limit: int = Query(default=_GRAPH_MAX_CLIENTS, ge=1, le=_GRAPH_MAX_CLIENTS),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin", "rop", "methodologist")),
):
    """
    Данные для lifecycle-графа клиентов и статусных переходов.
    Ограничено до {_GRAPH_MAX_CLIENTS} клиентов для защиты от OOM.
    """
    from collections import Counter

    # ── Фильтр по роли ──
    base_filter = RealClient.is_active.is_(True)
    if current_user.role == UserRole.manager:
        role_filter = RealClient.manager_id == current_user.id
    elif current_user.role == UserRole.rop:
        if not current_user.team_id:
            return {"nodes": [], "links": [], "status_counts": {}, "transitions": [],
                    "total_clients": 0, "total_managers": 0, "truncated": False}
        team_members = select(User.id).where(User.team_id == current_user.team_id)
        role_filter = RealClient.manager_id.in_(team_members)
    else:
        role_filter = True  # admin / methodologist see all

    # ── Status counts via DB aggregate (no full load) ──
    count_query = (
        select(RealClient.status, func.count(RealClient.id))
        .where(base_filter)
        .where(role_filter)
        .group_by(RealClient.status)
    )
    count_rows = await db.execute(count_query)
    status_counts = {
        (s.value if hasattr(s, "value") else str(s)): cnt
        for s, cnt in count_rows.all()
    }
    total_matching = sum(status_counts.values())
    truncated = total_matching > limit

    # ── Load clients with cap ──
    query = (
        select(RealClient)
        .where(base_filter)
        .where(role_filter)
        .order_by(RealClient.created_at.desc())
        .limit(limit)
    )
    rows = await db.execute(query)
    clients = rows.scalars().all()

    # ── Manager counts via Counter (O(n) not O(n²)) ──
    mgr_counter: Counter = Counter(c.manager_id for c in clients if c.manager_id)
    manager_ids = set(mgr_counter.keys())

    mgr_rows = await db.execute(
        select(User).where(User.id.in_(manager_ids)) if manager_ids else select(User).where(False)
    )
    managers = {m.id: m for m in mgr_rows.scalars().all()}

    # ── Build nodes ──
    nodes = []

    for mid, mgr in managers.items():
        nodes.append({
            "id": f"mgr-{mid}",
            "type": "manager",
            "label": mgr.full_name or mgr.email or "Менеджер",
            "role": mgr.role.value if hasattr(mgr.role, "value") else str(mgr.role),
            "client_count": mgr_counter[mid],
        })

    for c in clients:
        s = c.status.value if hasattr(c.status, "value") else str(c.status)
        nodes.append({
            "id": f"cli-{c.id}",
            "type": "client",
            "label": c.full_name or "Без имени",
            "status": s,
            "debt_amount": float(c.debt_amount) if c.debt_amount else 0,
            "source": c.source or "unknown",
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })

    # ── Build links ──
    links = [
        {"source": f"cli-{c.id}", "target": f"mgr-{c.manager_id}", "type": "managed_by"}
        for c in clients if c.manager_id
    ]

    # Status transition edges (static from the pipeline definition)
    transitions = []
    for from_status, to_statuses in ALLOWED_STATUS_TRANSITIONS.items():
        fs = from_status.value if hasattr(from_status, "value") else str(from_status)
        for ts in to_statuses:
            tsv = ts.value if hasattr(ts, "value") else str(ts)
            transitions.append({"from": fs, "to": tsv})

    return {
        "nodes": nodes,
        "links": links,
        "status_counts": status_counts,
        "transitions": transitions,
        "total_clients": total_matching,
        "total_managers": len(managers),
        "truncated": truncated,
    }
