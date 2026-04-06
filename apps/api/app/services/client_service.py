"""
ClientService — бизнес-логика модуля «Связь с клиентом».

Валидация переходов, дедупликация, consent HMAC-токены,
rate limiting уведомлений, автотаймауты.
"""

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, Request, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.client import (
    ALLOWED_STATUS_TRANSITIONS,
    AuditLog,
    ClientConsent,
    ClientInteraction,
    ClientNotification,
    ClientStatus,
    ConsentChannel,
    InteractionType,
    ManagerReminder,
    NotificationChannel,
    NotificationStatus,
    RealClient,
)
from app.models.user import User, UserRole
from app.services.audit import (
    CLIENT_AUDIT_FIELDS,
    CONSENT_AUDIT_FIELDS,
    model_to_audit_dict,
    write_audit_log,
)
from app.ws.notifications import send_ws_notification, send_ws_to_rop_team

logger = logging.getLogger(__name__)


# ── Константы (настраиваемые через env) ──────────────────────────────────────

LOST_COOLDOWN_DAYS = getattr(settings, "lost_cooldown_days", 3)
LOST_MAX_RETRIES = getattr(settings, "lost_max_retries", 3)
THINKING_TIMEOUT_DAYS = getattr(settings, "thinking_timeout_days", 30)
CONSENT_TOKEN_TTL_HOURS = getattr(settings, "consent_token_ttl_hours", 72)
_default_consent_secret = __import__("secrets").token_hex(32)
CONSENT_TOKEN_SECRET = getattr(settings, "consent_token_secret", None) or _default_consent_secret
SMS_RATE_LIMIT_DAY = getattr(settings, "sms_rate_limit_day", 3)
WA_RATE_LIMIT_DAY = getattr(settings, "wa_rate_limit_day", 1)
EMAIL_RATE_LIMIT_DAY = getattr(settings, "email_rate_limit_day", 2)


# ══════════════════════════════════════════════════════════════════════════════
# CLIENT CRUD
# ══════════════════════════════════════════════════════════════════════════════


async def create_client(
    db: AsyncSession,
    *,
    manager: User,
    full_name: str,
    phone: str | None = None,
    email: str | None = None,
    debt_amount: Decimal | None = None,
    debt_details: dict | None = None,
    source: str | None = None,
    notes: str | None = None,
    next_contact_at: datetime | None = None,
    initial_consent_type: str | None = None,
    initial_consent_channel: str | None = None,
    request: Request | None = None,
) -> tuple[RealClient, str | None, list[uuid.UUID]]:
    """
    Создать карточку клиента с проверкой дублей (ТЗ v2, раздел 3.4).

    Returns:
        (client, duplicate_warning, duplicate_ids)
    """
    duplicate_warning = None
    duplicate_ids: list[uuid.UUID] = []

    # ── Дедупликация по телефону ──
    if phone:
        dupes = await _check_duplicates(db, phone=phone, manager_id=manager.id)
        if dupes["same_manager"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Клиент с телефоном {phone} уже есть в вашей базе",
            )
        if dupes["other_managers"]:
            duplicate_warning = (
                f"Внимание: клиент с телефоном {phone} уже ведётся другим менеджером"
            )
            duplicate_ids = [d.id for d in dupes["other_managers"]]

    # ── Создание ──
    client = RealClient(
        id=uuid.uuid4(),
        manager_id=manager.id,
        full_name=full_name,
        phone=phone,
        email=email,
        status=ClientStatus.new,
        is_active=True,
        debt_amount=debt_amount,
        debt_details=debt_details,
        source=source,
        notes=notes,
        next_contact_at=next_contact_at,
        lost_count=0,
        last_status_change_at=datetime.now(timezone.utc),
    )
    db.add(client)

    # ── Audit ──
    await write_audit_log(
        db,
        actor=manager,
        action="create_client",
        entity_type="real_clients",
        entity_id=client.id,
        new_values=model_to_audit_dict(client, CLIENT_AUDIT_FIELDS),
        request=request,
    )

    # ── Первое согласие (опционально) ──
    if initial_consent_type:
        await grant_consent(
            db,
            client=client,
            consent_type=initial_consent_type,
            channel=initial_consent_channel or "phone_call",
            recorded_by=manager,
            request=request,
        )

    await db.flush()
    return client, duplicate_warning, duplicate_ids


async def get_client(
    db: AsyncSession,
    *,
    client_id: uuid.UUID,
    user: User,
    request: Request | None = None,
) -> RealClient:
    """Получить клиента с проверкой доступа по роли."""
    result = await db.execute(
        select(RealClient).where(
            RealClient.id == client_id,
            RealClient.is_active == True,  # noqa: E712
        )
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(status_code=404, detail="Клиент не найден")

    # Проверка доступа (B-FIX-2: async + team_id join)
    await _check_client_access(client, user, db)

    # Audit: просмотр клиента (только для ПДн-значимых просмотров)
    await write_audit_log(
        db,
        actor=user,
        action="view_client",
        entity_type="real_clients",
        entity_id=client.id,
        request=request,
    )

    return client


async def list_clients(
    db: AsyncSession,
    *,
    user: User,
    status_filter: list[str] | None = None,
    manager_id: uuid.UUID | None = None,
    search: str | None = None,
    source: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[RealClient], int]:
    """
    Список клиентов с фильтрацией (ТЗ v2, раздел 5.2).
    Видимость: manager — свои, rop — команда, admin/methodologist — все.
    """
    query = select(RealClient).where(RealClient.is_active == True)  # noqa: E712

    # ── Фильтр по роли ──
    if user.role == UserRole.manager:
        query = query.where(RealClient.manager_id == user.id)
    elif user.role == UserRole.rop:
        if not user.team_id:
            query = query.where(False)
        else:
            # РОП видит клиентов своей команды
            team_members = select(User.id).where(User.team_id == user.team_id)
            query = query.where(RealClient.manager_id.in_(team_members))
    # admin и methodologist видят всех

    # ── Фильтры ──
    if status_filter:
        query = query.where(RealClient.status.in_(status_filter))
    if manager_id:
        query = query.where(RealClient.manager_id == manager_id)
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                RealClient.full_name.ilike(search_term),
                RealClient.phone.ilike(search_term),
            )
        )
    if source:
        query = query.where(RealClient.source == source)
    if date_from:
        query = query.where(RealClient.created_at >= date_from)
    if date_to:
        query = query.where(RealClient.created_at <= date_to)

    # ── Count ──
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # ── Sort (allowlist to prevent IDOR via attribute reflection) ──
    _ALLOWED_SORT_FIELDS = {
        "created_at", "updated_at", "full_name", "status", "phone", "email",
    }
    safe_sort_by = sort_by if sort_by in _ALLOWED_SORT_FIELDS else "created_at"
    sort_column = getattr(RealClient, safe_sort_by, RealClient.created_at)
    if sort_order in ("asc", "desc"):
        query = query.order_by(sort_column.asc() if sort_order == "asc" else sort_column.desc())
    else:
        query = query.order_by(sort_column.desc())

    # ── Pagination ──
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    clients = list(result.scalars().all())

    return clients, total


async def update_client(
    db: AsyncSession,
    *,
    client_id: uuid.UUID,
    user: User,
    updates: dict,
    request: Request | None = None,
) -> RealClient:
    """Обновить карточку клиента с audit_log."""
    client = await get_client(db, client_id=client_id, user=user)
    old_values = model_to_audit_dict(client, CLIENT_AUDIT_FIELDS)

    for field, value in updates.items():
        if value is not None and hasattr(client, field):
            setattr(client, field, value)

    client.updated_at = datetime.now(timezone.utc)

    new_values = model_to_audit_dict(client, CLIENT_AUDIT_FIELDS)

    await write_audit_log(
        db,
        actor=user,
        action="update_client",
        entity_type="real_clients",
        entity_id=client.id,
        old_values=old_values,
        new_values=new_values,
        request=request,
    )

    await db.flush()
    return client


async def change_client_status(
    db: AsyncSession,
    *,
    client_id: uuid.UUID,
    user: User,
    new_status: str,
    reason: str | None = None,
    request: Request | None = None,
) -> RealClient:
    """
    Сменить статус клиента с валидацией перехода (ТЗ v2, раздел 3.1).
    """
    client = await get_client(db, client_id=client_id, user=user)
    old_status = client.status

    # Парсим новый статус
    try:
        target_status = ClientStatus(new_status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Неизвестный статус: {new_status}",
        )

    # ── Валидация перехода ──
    allowed = ALLOWED_STATUS_TRANSITIONS.get(old_status, [])
    if target_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Переход {old_status.value} → {target_status.value} недопустим. "
                   f"Допустимые: {[s.value for s in allowed]}",
        )

    # ── Специальные правила ──

    # lost → contacted: cooldown + лимит (ТЗ v2, раздел 3.2)
    if old_status == ClientStatus.lost and target_status == ClientStatus.contacted:
        await _validate_lost_to_contacted(client)

    # consent_given / contract_signed → consent_revoked: обязательна причина
    if target_status == ClientStatus.consent_revoked and not reason:
        raise HTTPException(
            status_code=400,
            detail="Для отзыва согласия необходимо указать причину",
        )

    # ── Применение ──
    old_values = {"status": old_status.value, "lost_reason": client.lost_reason}

    client.status = target_status
    client.last_status_change_at = datetime.now(timezone.utc)

    if target_status == ClientStatus.lost:
        client.lost_reason = reason
        client.lost_count += 1
    elif target_status == ClientStatus.consent_revoked:
        client.lost_reason = reason  # Используем как причину отзыва

    new_values = {"status": target_status.value, "lost_reason": client.lost_reason}

    # ── Interaction запись ──
    interaction = ClientInteraction(
        id=uuid.uuid4(),
        client_id=client.id,
        manager_id=user.id,
        interaction_type=InteractionType.status_change,
        content=reason or f"Смена статуса: {old_status.value} → {target_status.value}",
        old_status=old_status.value,
        new_status=target_status.value,
    )
    db.add(interaction)

    # ── Audit ──
    await write_audit_log(
        db,
        actor=user,
        action="change_status",
        entity_type="real_clients",
        entity_id=client.id,
        old_values=old_values,
        new_values=new_values,
        request=request,
    )

    await db.flush()

    # ── B-FIX-5: WS-уведомления о смене статуса ──
    ws_data = {
        "client_id": str(client.id),
        "client_name": client.full_name,
        "old_status": old_status.value,
        "new_status": target_status.value,
        "manager_id": str(user.id),
        "reason": reason,
    }
    try:
        await send_ws_notification(
            client.manager_id,
            event_type="client.status_changed",
            data=ws_data,
        )
        # Уведомить РОП команды
        if user.team_id:
            await send_ws_to_rop_team(
                str(user.team_id),
                event_type="client.status_changed",
                data=ws_data,
            )
    except Exception:
        logger.warning("WS notification failed for status change %s", client.id, exc_info=True)

    return client


async def soft_delete_client(
    db: AsyncSession,
    *,
    client_id: uuid.UUID,
    user: User,
    request: Request | None = None,
) -> None:
    """Soft-delete: is_active=false + audit_log (только admin)."""
    client = await get_client(db, client_id=client_id, user=user)

    old_values = {"is_active": True}
    client.is_active = False
    client.updated_at = datetime.now(timezone.utc)

    await write_audit_log(
        db,
        actor=user,
        action="delete_client",
        entity_type="real_clients",
        entity_id=client.id,
        old_values=old_values,
        new_values={"is_active": False},
        request=request,
    )

    await db.flush()


# ══════════════════════════════════════════════════════════════════════════════
# CONSENTS
# ══════════════════════════════════════════════════════════════════════════════


async def grant_consent(
    db: AsyncSession,
    *,
    client: RealClient,
    consent_type: str,
    channel: str,
    recorded_by: User,
    legal_text_version: str | None = None,
    evidence_url: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request: Request | None = None,
) -> ClientConsent:
    """Зафиксировать новое согласие клиента."""
    consent = ClientConsent(
        id=uuid.uuid4(),
        client_id=client.id,
        consent_type=consent_type,
        channel=ConsentChannel(channel) if channel else None,
        legal_text_version=legal_text_version,
        granted_at=datetime.now(timezone.utc),
        recorded_by=recorded_by.id,
        evidence_url=evidence_url,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(consent)

    # Interaction
    interaction = ClientInteraction(
        id=uuid.uuid4(),
        client_id=client.id,
        manager_id=recorded_by.id,
        interaction_type=InteractionType.consent_event,
        content=f"Согласие получено: {consent_type} (канал: {channel})",
    )
    db.add(interaction)

    # Audit
    await write_audit_log(
        db,
        actor=recorded_by,
        action="grant_consent",
        entity_type="client_consents",
        entity_id=consent.id,
        new_values=model_to_audit_dict(consent, CONSENT_AUDIT_FIELDS),
        request=request,
    )

    await db.flush()
    return consent


async def revoke_consent(
    db: AsyncSession,
    *,
    consent_id: uuid.UUID,
    user: User,
    reason: str,
    request: Request | None = None,
) -> ClientConsent:
    """Отозвать согласие (ТЗ v2, раздел 2.2 — 152-ФЗ)."""
    result = await db.execute(
        select(ClientConsent).where(ClientConsent.id == consent_id)
    )
    consent = result.scalar_one_or_none()

    if not consent:
        raise HTTPException(status_code=404, detail="Согласие не найдено")
    if consent.revoked_at is not None:
        raise HTTPException(status_code=400, detail="Согласие уже отозвано")

    old_values = model_to_audit_dict(consent, CONSENT_AUDIT_FIELDS)

    consent.revoked_at = datetime.now(timezone.utc)
    consent.revoked_reason = reason

    # Audit
    await write_audit_log(
        db,
        actor=user,
        action="revoke_consent",
        entity_type="client_consents",
        entity_id=consent.id,
        old_values=old_values,
        new_values=model_to_audit_dict(consent, CONSENT_AUDIT_FIELDS),
        request=request,
    )

    await db.flush()

    # ── B-FIX-5: WS-уведомления об отзыве согласия ──
    # Нужен client_id для контекста — достаём из consent
    ws_data = {
        "client_id": str(consent.client_id),
        "consent_id": str(consent.id),
        "consent_type": consent.consent_type,
        "reason": reason,
        "revoked_by": str(user.id),
    }
    try:
        # Получаем клиента для manager_id
        client_result = await db.execute(
            select(RealClient.manager_id).where(RealClient.id == consent.client_id)
        )
        manager_id = client_result.scalar_one_or_none()
        if manager_id:
            await send_ws_notification(
                manager_id,
                event_type="consent.revoked",
                data=ws_data,
            )
        # Уведомить РОП команды
        if user.team_id:
            await send_ws_to_rop_team(
                str(user.team_id),
                event_type="consent.revoked",
                data=ws_data,
            )
    except Exception:
        logger.warning("WS notification failed for consent revoke %s", consent.id, exc_info=True)

    return consent


def generate_consent_token(client_id: uuid.UUID, consent_type: str) -> str:
    """
    Генерация HMAC-SHA256 токена для SMS-подтверждения (ТЗ v2, раздел 12.1).
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    message = f"{client_id}:{consent_type}:{timestamp}"
    token = hmac.new(
        CONSENT_TOKEN_SECRET.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()
    return token


async def create_consent_with_token(
    db: AsyncSession,
    *,
    client: RealClient,
    consent_type: str,
    recorded_by: User,
    request: Request | None = None,
) -> ClientConsent:
    """Создать согласие с HMAC-токеном для SMS-подтверждения."""
    token = generate_consent_token(client.id, consent_type)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=CONSENT_TOKEN_TTL_HOURS)

    consent = ClientConsent(
        id=uuid.uuid4(),
        client_id=client.id,
        consent_type=consent_type,
        channel=ConsentChannel.sms_link,
        token=token,
        token_expires_at=expires_at,
        granted_at=datetime.now(timezone.utc),
        recorded_by=recorded_by.id,
    )
    db.add(consent)

    await write_audit_log(
        db,
        actor=recorded_by,
        action="grant_consent",
        entity_type="client_consents",
        entity_id=consent.id,
        new_values={"consent_type": consent_type, "channel": "sms_link", "token_created": True},
        request=request,
    )

    await db.flush()
    return consent


async def verify_consent_token(
    db: AsyncSession,
    *,
    token: str,
) -> ClientConsent | None:
    """Проверить токен при переходе клиента по ссылке."""
    result = await db.execute(
        select(ClientConsent).where(ClientConsent.token == token)
    )
    consent = result.scalar_one_or_none()

    if not consent:
        return None

    # Токен уже использован
    if consent.token_used_at is not None:
        return None

    # Токен просрочен
    if consent.token_expires_at and datetime.now(timezone.utc) > consent.token_expires_at:
        return None

    return consent


async def confirm_consent_token(
    db: AsyncSession,
    *,
    consent: ClientConsent,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> ClientConsent:
    """Клиент подтвердил по ссылке — инвалидировать токен."""
    consent.token_used_at = datetime.now(timezone.utc)
    consent.ip_address = ip_address
    consent.user_agent = user_agent

    await write_audit_log(
        db,
        actor=None,
        action="grant_consent",
        entity_type="client_consents",
        entity_id=consent.id,
        new_values={"token_confirmed": True, "ip": ip_address},
    )

    await db.flush()
    return consent


# ══════════════════════════════════════════════════════════════════════════════
# INTERACTIONS
# ══════════════════════════════════════════════════════════════════════════════


async def create_interaction(
    db: AsyncSession,
    *,
    client_id: uuid.UUID,
    manager: User,
    interaction_type: str,
    content: str | None = None,
    result: str | None = None,
    duration_seconds: int | None = None,
) -> ClientInteraction:
    """Записать взаимодействие менеджер ↔ клиент."""
    interaction = ClientInteraction(
        id=uuid.uuid4(),
        client_id=client_id,
        manager_id=manager.id,
        interaction_type=InteractionType(interaction_type),
        content=content,
        result=result,
        duration_seconds=duration_seconds,
    )
    db.add(interaction)
    await db.flush()
    return interaction


async def get_interaction_summary(
    db: AsyncSession,
    *,
    client_id: uuid.UUID,
) -> dict:
    """Сводка по взаимодействиям клиента."""
    result = await db.execute(
        select(
            ClientInteraction.interaction_type,
            func.count().label("cnt"),
        )
        .where(ClientInteraction.client_id == client_id)
        .group_by(ClientInteraction.interaction_type)
    )
    counts = {row.interaction_type.value: row.cnt for row in result.all()}

    # Последнее взаимодействие
    last_result = await db.execute(
        select(ClientInteraction.created_at)
        .where(ClientInteraction.client_id == client_id)
        .order_by(ClientInteraction.created_at.desc())
        .limit(1)
    )
    last_at = last_result.scalar_one_or_none()

    # Дней в воронке
    client_result = await db.execute(
        select(RealClient.created_at).where(RealClient.id == client_id)
    )
    created = client_result.scalar_one_or_none()
    days = (datetime.now(timezone.utc) - created).days if created else 0

    return {
        "total_calls": counts.get("outbound_call", 0) + counts.get("inbound_call", 0),
        "total_meetings": counts.get("meeting", 0),
        "total_sms": counts.get("sms_sent", 0),
        "total_whatsapp": counts.get("whatsapp_sent", 0),
        "total_emails": counts.get("email_sent", 0),
        "total_notes": counts.get("note", 0),
        "days_in_funnel": days,
        "last_interaction_at": last_at,
    }


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS — RATE LIMITING
# ══════════════════════════════════════════════════════════════════════════════


async def check_notification_rate_limit(
    db: AsyncSession,
    *,
    client_id: uuid.UUID,
    channel: str,
) -> None:
    """
    Проверить rate limit для уведомлений клиенту (ТЗ v2, раздел 7.1).
    """
    limits = {
        "sms": SMS_RATE_LIMIT_DAY,
        "whatsapp": WA_RATE_LIMIT_DAY,
        "email": EMAIL_RATE_LIMIT_DAY,
    }
    limit = limits.get(channel)
    if not limit:
        return

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)

    result = await db.execute(
        select(func.count()).where(
            ClientNotification.client_id == client_id,
            ClientNotification.channel == NotificationChannel(channel),
            ClientNotification.recipient_type == "client",
            ClientNotification.created_at >= today_start,
        )
    )
    count = result.scalar() or 0

    if count >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Клиенту уже отправлено {count} {channel} сегодня. "
                   f"Лимит: {limit}/день. Попробуйте завтра или обратитесь к РОП.",
        )


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE & STATS
# ══════════════════════════════════════════════════════════════════════════════


async def get_pipeline(
    db: AsyncSession,
    *,
    user: User,
) -> list[dict]:
    """Воронка: count + total_debt по статусам."""
    query = (
        select(
            RealClient.status,
            func.count().label("cnt"),
            func.coalesce(func.sum(RealClient.debt_amount), 0).label("total_debt"),
        )
        .where(RealClient.is_active == True)  # noqa: E712
    )

    if user.role == UserRole.rop:
        if not user.team_id:
            query = query.where(False)
        else:
            team_members = select(User.id).where(User.team_id == user.team_id)
            query = query.where(RealClient.manager_id.in_(team_members))
    elif user.role == UserRole.manager:
        query = query.where(RealClient.manager_id == user.id)

    query = query.group_by(RealClient.status)
    result = await db.execute(query)

    return [
        {"status": row.status.value, "count": row.cnt, "total_debt": float(row.total_debt)}
        for row in result.all()
    ]


async def get_client_stats(
    db: AsyncSession,
    *,
    user: User,
    anonymized: bool = False,
) -> dict:
    """Статистика воронки (ТЗ v2, раздел 5.1)."""
    pipeline = await get_pipeline(db, user=user)
    by_status = {item["status"]: item["count"] for item in pipeline}
    total = sum(by_status.values())

    # Конверсии
    contacted = by_status.get("contacted", 0) + by_status.get("interested", 0)
    consent = by_status.get("consent_given", 0) + by_status.get("contract_signed", 0)
    conversion = round(consent / contacted * 100, 1) if contacted > 0 else 0

    stats = {
        "total_clients": total,
        "by_status": by_status,
        "conversion_rates": {"contacted_to_consent": conversion},
        "avg_cycle_days": None,
        "lost_reasons": {},
    }

    if not anonymized:
        # Средний цикл сделки (от created_at до completed)
        avg_query = select(
            func.avg(
                func.extract("epoch", RealClient.updated_at - RealClient.created_at) / 86400
            )
        ).where(
            RealClient.status == ClientStatus.completed,
            RealClient.is_active == True,  # noqa: E712
        )
        if user.role == UserRole.rop:
            if not user.team_id:
                avg_query = avg_query.where(False)
            else:
                team_members = select(User.id).where(User.team_id == user.team_id)
                avg_query = avg_query.where(RealClient.manager_id.in_(team_members))
        elif user.role == UserRole.manager:
            avg_query = avg_query.where(RealClient.manager_id == user.id)

        avg_result = await db.execute(avg_query)
        stats["avg_cycle_days"] = round(avg_result.scalar() or 0, 1)

    return stats


# ══════════════════════════════════════════════════════════════════════════════
# DEDUPLICATION
# ══════════════════════════════════════════════════════════════════════════════


async def _check_duplicates(
    db: AsyncSession,
    *,
    phone: str,
    manager_id: uuid.UUID,
) -> dict:
    """Проверка дублей по телефону (ТЗ v2, раздел 3.4)."""
    result = await db.execute(
        select(RealClient).where(
            RealClient.phone == phone,
            RealClient.is_active == True,  # noqa: E712
        )
    )
    dupes = list(result.scalars().all())

    same_manager = [d for d in dupes if d.manager_id == manager_id]
    other_managers = [d for d in dupes if d.manager_id != manager_id]

    return {"same_manager": same_manager, "other_managers": other_managers}


async def find_duplicates(
    db: AsyncSession,
    *,
    user: User,
) -> list[dict]:
    """GET /clients/duplicates — найти дубли по телефону."""
    if user.role == UserRole.rop and not user.team_id:
        return []

    phone_query = (
        select(RealClient.phone)
        .where(
            RealClient.is_active == True,  # noqa: E712
            RealClient.phone.isnot(None),
        )
    )

    if user.role == UserRole.rop and user.team_id:
        team_members = select(User.id).where(User.team_id == user.team_id)
        phone_query = phone_query.where(RealClient.manager_id.in_(team_members))

    subquery = phone_query.group_by(RealClient.phone).having(func.count() > 1)

    query = select(RealClient).where(RealClient.phone.in_(subquery))
    if user.role == UserRole.rop and user.team_id:
        team_members = select(User.id).where(User.team_id == user.team_id)
        query = query.where(RealClient.manager_id.in_(team_members))

    result = await db.execute(query.order_by(RealClient.phone, RealClient.created_at))

    clients = list(result.scalars().all())

    # Группируем по телефону
    groups: dict[str, list] = {}
    for c in clients:
        groups.setdefault(c.phone, []).append(c)

    return [{"phone": phone, "clients": cls} for phone, cls in groups.items()]


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════


async def _check_client_access(
    client: RealClient,
    user: User,
    db: AsyncSession,
) -> None:
    """
    Проверка доступа к клиенту (B-FIX-2):
    - admin → всё
    - manager → только свои клиенты
    - rop → клиенты своей команды (join к users.team_id)
    - methodologist → read-only доступ ко всем клиентам
    """
    if user.role == UserRole.admin:
        return
    if user.role == UserRole.methodologist:
        return
    if user.role == UserRole.manager:
        if client.manager_id != user.id:
            raise HTTPException(status_code=403, detail="Нет доступа к этому клиенту")
        return
    if user.role == UserRole.rop:
        if not user.team_id:
            raise HTTPException(status_code=403, detail="РОП не привязан к команде")
        # Проверяем, что менеджер клиента в той же команде
        result = await db.execute(
            select(User.team_id).where(User.id == client.manager_id)
        )
        manager_team_id = result.scalar_one_or_none()
        if manager_team_id != user.team_id:
            raise HTTPException(status_code=403, detail="Клиент не в вашей команде")
        return


async def _validate_lost_to_contacted(client: RealClient) -> None:
    """Валидация возврата lost → contacted (ТЗ v2, раздел 3.2)."""
    # Лимит попыток
    if client.lost_count >= LOST_MAX_RETRIES:
        raise HTTPException(
            status_code=400,
            detail=f"Достигнут лимит повторных попыток ({LOST_MAX_RETRIES})",
        )

    # Cooldown
    if client.last_status_change_at:
        cooldown_end = client.last_status_change_at + timedelta(days=LOST_COOLDOWN_DAYS)
        if datetime.now(timezone.utc) < cooldown_end:
            days_left = (cooldown_end - datetime.now(timezone.utc)).days + 1
            raise HTTPException(
                status_code=400,
                detail=f"Cooldown: повторная попытка возможна через {days_left} дн.",
            )
