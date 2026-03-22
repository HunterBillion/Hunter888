"""
Audit Log Service — 152-ФЗ compliance.
Автоматическое логирование всех CRUD-операций с ПДн.
APPEND-ONLY: только INSERT, без UPDATE/DELETE.
"""

import logging
import uuid
from datetime import datetime

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import AuditLog
from app.models.user import User

logger = logging.getLogger(__name__)


async def write_audit_log(
    db: AsyncSession,
    *,
    actor: User | None = None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
    request: Request | None = None,
) -> AuditLog:
    """
    Записать в audit_log. Вызывается из сервисов и API-хендлеров.

    Args:
        db: Сессия БД
        actor: Пользователь, совершивший действие (None для системных)
        action: Тип действия (create_client, update_client, etc.)
        entity_type: Тип сущности (real_clients, client_consents, etc.)
        entity_id: ID затронутой записи
        old_values: Значения ДО изменения
        new_values: Значения ПОСЛЕ изменения
        request: FastAPI Request (для IP и User-Agent)
    """
    ip_address = None
    user_agent = None

    if request:
        # Получаем реальный IP (учитываем прокси)
        ip_address = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not ip_address:
            ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")[:500]

    entry = AuditLog(
        id=uuid.uuid4(),
        actor_id=actor.id if actor else None,
        actor_role=actor.role.value if actor else "system",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=_sanitize_for_json(old_values),
        new_values=_sanitize_for_json(new_values),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.add(entry)
    # Не делаем commit — он произойдёт вместе с основной операцией

    logger.info(
        "AUDIT: %s by %s on %s/%s",
        action,
        actor.email if actor else "system",
        entity_type,
        entity_id,
    )

    return entry


def _sanitize_for_json(data: dict | None) -> dict | None:
    """Преобразует значения в JSON-сериализуемый формат."""
    if data is None:
        return None

    sanitized = {}
    for key, value in data.items():
        if isinstance(value, uuid.UUID):
            sanitized[key] = str(value)
        elif isinstance(value, datetime):
            sanitized[key] = value.isoformat()
        elif hasattr(value, "value"):  # Enum
            sanitized[key] = value.value
        else:
            sanitized[key] = value

    return sanitized


def model_to_audit_dict(instance, fields: list[str]) -> dict:
    """
    Извлекает указанные поля из ORM-модели для audit_log.
    Используется для фиксации old_values / new_values.
    """
    result = {}
    for field in fields:
        value = getattr(instance, field, None)
        if isinstance(value, uuid.UUID):
            result[field] = str(value)
        elif isinstance(value, datetime):
            result[field] = value.isoformat() if value else None
        elif hasattr(value, "value"):  # Enum
            result[field] = value.value
        else:
            result[field] = value
    return result


# Поля для аудита по типам сущностей
CLIENT_AUDIT_FIELDS = [
    "full_name", "phone", "email", "status", "is_active",
    "debt_amount", "source", "notes", "manager_id",
    "next_contact_at", "lost_reason", "lost_count",
]

CONSENT_AUDIT_FIELDS = [
    "consent_type", "channel", "granted_at", "revoked_at",
    "revoked_reason", "legal_text_version",
]
