"""
Pydantic-схемы для модуля «Связь с клиентом» (Agent 7).
Request/Response модели для всех API эндпоинтов.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


# ── Clients ──────────────────────────────────────────────────────────────────


class ClientCreateRequest(BaseModel):
    """POST /api/clients — создать карточку клиента"""

    full_name: str = Field(..., min_length=1, max_length=200)
    phone: str | None = Field(None, max_length=20, pattern=r"^\+?[0-9\s\-\(\)]{7,20}$")
    email: str | None = Field(None, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    debt_amount: Decimal | None = Field(None, ge=0, decimal_places=2)
    debt_details: dict | None = None
    source: str | None = Field(None, max_length=100)
    notes: str | None = None
    next_contact_at: datetime | None = None

    # Опциональное первое согласие при создании
    initial_consent_type: str | None = Field(None, max_length=50)
    initial_consent_channel: str | None = Field(None, max_length=20)


class ClientUpdateRequest(BaseModel):
    """PUT /api/clients/{id} — обновить карточку"""

    full_name: str | None = Field(None, min_length=1, max_length=200)
    phone: str | None = Field(None, max_length=20)
    email: str | None = Field(None, max_length=255)
    debt_amount: Decimal | None = Field(None, ge=0)
    debt_details: dict | None = None
    source: str | None = Field(None, max_length=100)
    notes: str | None = None
    next_contact_at: datetime | None = None


class ClientStatusChangeRequest(BaseModel):
    """PATCH /api/clients/{id}/status — сменить статус"""

    new_status: str = Field(..., max_length=50)
    reason: str | None = Field(None, max_length=500)
    # Для lost: причина потери
    # Для consent_revoked: причина отзыва


class ClientResponse(BaseModel):
    """Ответ с карточкой клиента"""

    id: uuid.UUID
    manager_id: uuid.UUID
    manager_name: str | None = None
    full_name: str
    phone: str | None
    email: str | None
    status: str
    is_active: bool
    debt_amount: Decimal | None
    debt_details: dict | None
    source: str | None
    notes: str | None
    next_contact_at: datetime | None
    lost_reason: str | None
    lost_count: int
    last_status_change_at: datetime | None
    created_at: datetime
    updated_at: datetime

    # Вложенные данные (опционально)
    active_consents: list["ConsentResponse"] | None = None
    recent_interactions: list["InteractionResponse"] | None = None

    model_config = {"from_attributes": True}


class ClientListResponse(BaseModel):
    """Пагинированный список клиентов"""

    items: list[ClientResponse]
    total: int
    page: int
    per_page: int
    pages: int


class ClientDuplicateResponse(BaseModel):
    """Результат проверки дублей"""

    phone: str
    duplicates: list[ClientResponse]


class PipelineResponse(BaseModel):
    """Воронка: count по статусам + сумма долга"""

    status: str
    count: int
    total_debt: float = 0.0
    clients: list[ClientResponse] | None = None


class ClientStatsResponse(BaseModel):
    """Статистика воронки"""

    total_clients: int
    by_status: dict[str, int]
    conversion_rates: dict[str, float]  # "contacted_to_consent": 0.38
    avg_cycle_days: float | None
    lost_reasons: dict[str, int]
    avg_debt_amount: Decimal | None


class ClientStatsAnonymizedResponse(BaseModel):
    """Анонимизированная статистика для методолога"""

    total_clients: int
    by_status: dict[str, int]
    conversion_rates: dict[str, float]
    avg_cycle_days: float | None
    lost_reasons_distribution: dict[str, float]  # Проценты, без ПДн


# ── Bulk операции ────────────────────────────────────────────────────────────


class BulkReassignRequest(BaseModel):
    """POST /api/clients/bulk/reassign"""

    client_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=100)
    new_manager_id: uuid.UUID


class BulkReassignResponse(BaseModel):
    reassigned: int
    errors: list[str]


class ClientMergeRequest(BaseModel):
    """POST /api/clients/{id}/merge — объединить дубли"""

    duplicate_id: uuid.UUID
    # ID дубля, который будет поглощён основной карточкой


# ── Consents ─────────────────────────────────────────────────────────────────


class ConsentCreateRequest(BaseModel):
    """POST /api/clients/{id}/consents — зафиксировать согласие"""

    consent_type: str = Field(..., max_length=50)
    channel: str = Field(..., max_length=20)
    legal_text_version: str | None = Field(None, max_length=20)
    evidence_url: str | None = Field(None, max_length=500)
    ip_address: str | None = None
    user_agent: str | None = None

    @field_validator("consent_type")
    @classmethod
    def validate_consent_type(cls, v: str) -> str:
        valid_types = {
            "data_processing", "contact_allowed",
            "consultation_agreed", "bfl_procedure", "marketing",
        }
        if v not in valid_types:
            raise ValueError(f"Недопустимый тип согласия: {v}")
        return v


class ConsentRevokeRequest(BaseModel):
    """POST /api/clients/{id}/consents/{cid}/revoke — отозвать"""

    reason: str = Field(..., min_length=1, max_length=500)


class ConsentResponse(BaseModel):
    """Ответ с данными согласия"""

    id: uuid.UUID
    client_id: uuid.UUID
    consent_type: str
    channel: str | None
    legal_text_version: str | None
    granted_at: datetime
    revoked_at: datetime | None
    revoked_reason: str | None
    recorded_by: uuid.UUID | None
    recorder_name: str | None = None
    evidence_url: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ConsentVerifyResponse(BaseModel):
    """Ответ на публичный эндпоинт верификации токена"""

    client_name: str
    consent_type: str
    legal_text: str
    status: str  # "pending", "confirmed", "expired", "used"


# ── Interactions ─────────────────────────────────────────────────────────────


class InteractionCreateRequest(BaseModel):
    """POST /api/clients/{id}/interactions — записать взаимодействие"""

    interaction_type: str = Field(..., max_length=50)
    content: str | None = None
    result: str | None = Field(None, max_length=200)
    duration_seconds: int | None = Field(None, ge=0)

    @field_validator("interaction_type")
    @classmethod
    def validate_interaction_type(cls, v: str) -> str:
        valid_types = {
            "outbound_call", "inbound_call", "sms_sent", "whatsapp_sent",
            "email_sent", "meeting", "note",
        }
        if v not in valid_types:
            raise ValueError(f"Недопустимый тип взаимодействия: {v}")
        return v


class InteractionResponse(BaseModel):
    """Ответ с данными взаимодействия"""

    id: uuid.UUID
    client_id: uuid.UUID
    manager_id: uuid.UUID | None
    manager_name: str | None = None
    interaction_type: str
    content: str | None
    result: str | None
    duration_seconds: int | None
    old_status: str | None
    new_status: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InteractionSummaryResponse(BaseModel):
    """Сводка по взаимодействиям"""

    total_calls: int
    total_meetings: int
    total_sms: int
    total_whatsapp: int
    total_emails: int
    total_notes: int
    days_in_funnel: int
    last_interaction_at: datetime | None


# ── Notifications ────────────────────────────────────────────────────────────


class NotificationResponse(BaseModel):
    """In-app уведомление"""

    id: uuid.UUID
    title: str
    body: str | None
    channel: str
    status: str
    client_id: uuid.UUID | None
    client_name: str | None = None
    read_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    unread_count: int


class SendNotificationRequest(BaseModel):
    """POST /api/clients/{id}/notify — отправить клиенту"""

    channel: str = Field(...)  # sms, whatsapp, email
    template_id: str | None = None
    custom_message: str | None = None

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: str) -> str:
        if v not in {"sms", "whatsapp", "email"}:
            raise ValueError("Канал: sms, whatsapp, email")
        return v


# ── Reminders ────────────────────────────────────────────────────────────────


class ReminderCreateRequest(BaseModel):
    """POST /api/reminders"""

    client_id: uuid.UUID
    remind_at: datetime
    message: str | None = Field(None, max_length=500)


class ReminderResponse(BaseModel):
    """Ответ с напоминанием"""

    id: uuid.UUID
    manager_id: uuid.UUID
    client_id: uuid.UUID
    client_name: str | None = None
    remind_at: datetime
    message: str | None
    is_completed: bool
    completed_at: datetime | None
    auto_generated: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Audit Log ────────────────────────────────────────────────────────────────


class AuditLogResponse(BaseModel):
    """Запись audit log (только для admin)"""

    id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_name: str | None = None
    actor_role: str | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    old_values: dict | None
    new_values: dict | None
    ip_address: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    per_page: int


# ── Duplicate warning in create response ─────────────────────────────────────


class ClientCreateResponse(BaseModel):
    """Ответ на создание клиента — может содержать предупреждение о дубле"""

    client: ClientResponse
    duplicate_warning: str | None = None
    duplicate_ids: list[uuid.UUID] | None = None
