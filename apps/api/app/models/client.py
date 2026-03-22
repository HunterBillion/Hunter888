"""
Модуль «Связь с клиентом» — Agent 7 / Task X
Модели данных: RealClient, ClientConsent, ClientInteraction,
ClientNotification, ManagerReminder, AuditLog

ТЗ v2: 152-ФЗ compliance, Numeric для денег, soft-delete,
дедупликация, audit trail, таймауты статусов.
"""

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ── Enums ────────────────────────────────────────────────────────────────────


class ClientStatus(str, enum.Enum):
    """Воронка из 12 статусов (ТЗ v2, раздел 3.1)"""

    new = "new"                        # Добавлен, контакт не состоялся
    contacted = "contacted"            # Первый разговор
    interested = "interested"          # Проявил интерес к БФЛ
    consultation = "consultation"      # Записан/пришёл на консультацию
    thinking = "thinking"              # Ушёл думать
    consent_given = "consent_given"    # Дал согласие на процедуру
    contract_signed = "contract_signed"  # Подписан договор
    in_process = "in_process"          # Процедура банкротства идёт
    paused = "paused"                  # Приостановил процесс
    completed = "completed"            # Долги списаны — ФИНАЛЬНЫЙ
    lost = "lost"                      # Отказ / недозвон
    consent_revoked = "consent_revoked"  # Передумал после согласия


class ConsentType(str, enum.Enum):
    """Типы согласий (ТЗ v2, раздел 3.5, 152-ФЗ)"""

    data_processing = "data_processing"        # Хранение ФИО, телефона, суммы долга
    contact_allowed = "contact_allowed"        # Звонки/сообщения от менеджера
    consultation_agreed = "consultation_agreed"  # Бесплатная консультация
    bfl_procedure = "bfl_procedure"            # Начало процедуры банкротства
    marketing = "marketing"                    # Информационные рассылки


class ConsentChannel(str, enum.Enum):
    """Каналы получения согласия"""

    phone_call = "phone_call"    # Устное по телефону
    sms_link = "sms_link"        # Клиент перешёл по ссылке из SMS
    web_form = "web_form"        # Заполнил форму на сайте
    whatsapp = "whatsapp"        # Подтвердил в WhatsApp
    in_person = "in_person"      # Лично в офисе
    email_link = "email_link"    # Перешёл по ссылке из email


class InteractionType(str, enum.Enum):
    """Типы взаимодействий менеджер ↔ клиент"""

    outbound_call = "outbound_call"    # Менеджер позвонил
    inbound_call = "inbound_call"      # Клиент позвонил
    sms_sent = "sms_sent"              # Отправлено SMS
    whatsapp_sent = "whatsapp_sent"    # Отправлено в WA
    email_sent = "email_sent"          # Отправлен email
    meeting = "meeting"                # Встреча / консультация
    status_change = "status_change"    # Смена статуса
    consent_event = "consent_event"    # Событие согласия
    note = "note"                      # Заметка менеджера
    system = "system"                  # Автоматическое событие


class NotificationChannel(str, enum.Enum):
    """Каналы уведомлений"""

    in_app = "in_app"        # Внутри приложения (WebSocket)
    push = "push"            # Web Push
    sms = "sms"              # SMS
    whatsapp = "whatsapp"    # WhatsApp
    email = "email"          # Email


class NotificationStatus(str, enum.Enum):
    """Статусы доставки уведомлений"""

    pending = "pending"
    sent = "sent"
    delivered = "delivered"
    read = "read"
    failed = "failed"


class AuditAction(str, enum.Enum):
    """Действия для audit_log (ТЗ v2, раздел 2.4)"""

    create_client = "create_client"
    update_client = "update_client"
    view_client = "view_client"
    delete_client = "delete_client"
    grant_consent = "grant_consent"
    revoke_consent = "revoke_consent"
    export_data = "export_data"
    send_notification = "send_notification"
    change_status = "change_status"
    merge_clients = "merge_clients"
    bulk_reassign = "bulk_reassign"


client_status_enum = PgEnum(ClientStatus, name="clientstatus", create_type=False)
consent_channel_enum = PgEnum(ConsentChannel, name="consentchannel", create_type=False)
interaction_type_enum = PgEnum(InteractionType, name="interactiontype", create_type=False)
notification_channel_enum = PgEnum(
    NotificationChannel, name="notificationchannel", create_type=False
)
notification_status_enum = PgEnum(
    NotificationStatus, name="notificationstatus", create_type=False
)


# ── Таблица допустимых переходов (ТЗ v2, раздел 3.1) ────────────────────────


ALLOWED_STATUS_TRANSITIONS: dict[ClientStatus, list[ClientStatus]] = {
    ClientStatus.new: [ClientStatus.contacted, ClientStatus.lost],
    ClientStatus.contacted: [ClientStatus.interested, ClientStatus.consultation, ClientStatus.lost],
    ClientStatus.interested: [ClientStatus.consultation, ClientStatus.lost],
    ClientStatus.consultation: [ClientStatus.consent_given, ClientStatus.thinking, ClientStatus.lost],
    ClientStatus.thinking: [ClientStatus.consent_given, ClientStatus.lost],
    ClientStatus.consent_given: [ClientStatus.contract_signed, ClientStatus.consent_revoked],
    ClientStatus.contract_signed: [ClientStatus.in_process, ClientStatus.consent_revoked],
    ClientStatus.in_process: [ClientStatus.completed, ClientStatus.paused],
    ClientStatus.paused: [ClientStatus.in_process, ClientStatus.lost],
    ClientStatus.completed: [],  # Финальный
    ClientStatus.lost: [ClientStatus.contacted],  # Повторная попытка (cooldown 3 дня, макс 3)
    ClientStatus.consent_revoked: [ClientStatus.thinking, ClientStatus.lost],
}

# Таймауты по статусам (дни → действие)
STATUS_TIMEOUTS: dict[ClientStatus, list[dict]] = {
    ClientStatus.new: [{"days": 3, "action": "remind_manager"}],
    ClientStatus.contacted: [{"days": 5, "action": "remind_manager_and_rop"}],
    ClientStatus.interested: [{"days": 7, "action": "remind_manager"}],
    ClientStatus.thinking: [
        {"days": 21, "action": "remind_manager"},
        {"days": 28, "action": "notify_rop"},
        {"days": 30, "action": "auto_lost"},
    ],
    ClientStatus.consent_given: [{"days": 5, "action": "remind_manager"}],
    ClientStatus.paused: [{"days": 14, "action": "remind_manager"}],
    ClientStatus.consent_revoked: [{"days": 7, "action": "remind_manager"}],
}


# ── Модели ───────────────────────────────────────────────────────────────────


class RealClient(Base):
    """
    Карточка реального клиента (ТЗ v2, раздел 4.1).
    Отдельно от AI-персонажа тренировки (ClientProfile).
    """

    __tablename__ = "real_clients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    manager_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[ClientStatus] = mapped_column(
        client_status_enum, default=ClientStatus.new, nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )

    # ТЗ v2: Numeric(12,2) вместо Float для денежных сумм
    debt_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    debt_details: Mapped[dict | None] = mapped_column(JSONB)
    # {creditors: [...], has_mortgage: bool, monthly_payment: ...}

    source: Mapped[str | None] = mapped_column(String(100))
    # cold_call, referral, website, social_media...

    notes: Mapped[str | None] = mapped_column(Text)
    next_contact_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    lost_reason: Mapped[str | None] = mapped_column(String(500))

    # ТЗ v2: счётчик повторных попыток (макс LOST_MAX_RETRIES=3)
    lost_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ТЗ v2: для автотаймаутов (сколько дней в текущем статусе)
    last_status_change_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ──
    manager: Mapped["User"] = relationship(
        "User", foreign_keys=[manager_id], lazy="selectin"
    )
    consents: Mapped[list["ClientConsent"]] = relationship(
        back_populates="client", lazy="selectin",
        order_by="ClientConsent.created_at.desc()"
    )
    interactions: Mapped[list["ClientInteraction"]] = relationship(
        back_populates="client", lazy="noload",
        order_by="ClientInteraction.created_at.desc()"
    )
    notifications: Mapped[list["ClientNotification"]] = relationship(
        back_populates="client", lazy="noload"
    )
    reminders: Mapped[list["ManagerReminder"]] = relationship(
        back_populates="client", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<RealClient {self.full_name} [{self.status.value}]>"


class ClientConsent(Base):
    """
    Согласия клиента (ТЗ v2, раздел 4.2).
    Каждое согласие — отдельная запись. Отзыв создаёт revoked_at.
    Все операции логируются в audit_log (152-ФЗ).
    """

    __tablename__ = "client_consents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("real_clients.id"), nullable=False, index=True
    )
    consent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    channel: Mapped[ConsentChannel | None] = mapped_column(consent_channel_enum)

    # ТЗ v2: версия юридического текста согласия
    legal_text_version: Mapped[str | None] = mapped_column(String(20))

    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(500))

    ip_address: Mapped[str | None] = mapped_column(String(45))
    # ТЗ v2: для аудита 152-ФЗ
    user_agent: Mapped[str | None] = mapped_column(String(500))

    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    evidence_url: Mapped[str | None] = mapped_column(String(500))

    # ТЗ v2: HMAC-SHA256 токен для SMS-подтверждения
    token: Mapped[str | None] = mapped_column(String(128), unique=True)
    token_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ──
    client: Mapped["RealClient"] = relationship(back_populates="consents")
    recorder: Mapped["User"] = relationship(
        "User", foreign_keys=[recorded_by], lazy="selectin"
    )

    # ── Constraints ──
    __table_args__ = (
        # Уникальность: один активный consent определённого типа на клиента
        Index(
            "uq_active_consent_per_type",
            "client_id", "consent_type",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    @property
    def is_active(self) -> bool:
        """Согласие действует, если не отозвано"""
        return self.revoked_at is None

    @property
    def is_token_valid(self) -> bool:
        """Токен валиден: не использован и не просрочен"""
        if not self.token or self.token_used_at is not None:
            return False
        if self.token_expires_at and datetime.now(timezone.utc) > self.token_expires_at:
            return False
        return True

    def __repr__(self) -> str:
        status = "active" if self.is_active else "revoked"
        return f"<ClientConsent {self.consent_type} [{status}]>"


class ClientInteraction(Base):
    """
    История взаимодействий менеджер ↔ клиент (ТЗ v2, раздел 4.3).
    Каждый звонок, встреча, заметка, смена статуса — отдельная запись.
    """

    __tablename__ = "client_interactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("real_clients.id"), nullable=False, index=True
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    interaction_type: Mapped[InteractionType] = mapped_column(
        interaction_type_enum, nullable=False
    )
    content: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str | None] = mapped_column(String(200))
    # "перезвонить", "записан на консультацию", "отказ"

    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    # Длительность звонка

    # Для status_change
    old_status: Mapped[str | None] = mapped_column(String(50))
    new_status: Mapped[str | None] = mapped_column(String(50))

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ──
    client: Mapped["RealClient"] = relationship(back_populates="interactions")
    manager: Mapped["User"] = relationship("User", foreign_keys=[manager_id], lazy="selectin")

    # ── Indexes ──
    __table_args__ = (
        Index("ix_client_interactions_timeline", "client_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ClientInteraction {self.interaction_type.value} for {self.client_id}>"


class ClientNotification(Base):
    """
    Уведомления менеджеру и клиенту (ТЗ v2, раздел 4.4).
    In-App (WebSocket), Push, SMS, WhatsApp, Email.
    """

    __tablename__ = "client_notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recipient_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "manager" или "client"
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("real_clients.id")
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        notification_channel_enum, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)

    # ТЗ v2: ID шаблона для переиспользования
    template_id: Mapped[str | None] = mapped_column(String(50))

    status: Mapped[NotificationStatus] = mapped_column(
        notification_status_enum, default=NotificationStatus.pending, nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # ТЗ v2: delivered отдельно от sent
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ТЗ v2: причина ошибки доставки
    failed_reason: Mapped[str | None] = mapped_column(String(500))
    # ТЗ v2: retry counter
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ──
    client: Mapped["RealClient"] = relationship(back_populates="notifications")

    # ── Indexes ──
    __table_args__ = (
        Index("ix_notifications_recipient", "recipient_type", "recipient_id"),
        Index("ix_notifications_status", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ClientNotification [{self.channel.value}] → {self.recipient_type}>"


class ManagerReminder(Base):
    """
    Напоминания менеджеру (ТЗ v2, раздел 4.5).
    Ручные и автоматически сгенерированные (cron).
    """

    __tablename__ = "manager_reminders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    manager_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("real_clients.id"), nullable=False
    )
    remind_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    message: Mapped[str | None] = mapped_column(String(500))
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auto_generated: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ──
    manager: Mapped["User"] = relationship("User", foreign_keys=[manager_id], lazy="selectin")
    client: Mapped["RealClient"] = relationship(back_populates="reminders")

    # ── Indexes ──
    __table_args__ = (
        Index("ix_reminders_pending", "manager_id", "is_completed", "remind_at"),
    )

    def __repr__(self) -> str:
        status = "done" if self.is_completed else "pending"
        return f"<ManagerReminder [{status}] {self.remind_at}>"


class AuditLog(Base):
    """
    Audit Trail — 152-ФЗ compliance (ТЗ v2, раздел 2.4).
    APPEND-ONLY: только INSERT, без UPDATE/DELETE.
    Логирует все действия с ПДн клиентов.
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    actor_role: Mapped[str | None] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    # create_client, update_client, view_client, grant_consent, etc.

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # real_clients, client_consents, client_interactions
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    old_values: Mapped[dict | None] = mapped_column(JSONB)
    new_values: Mapped[dict | None] = mapped_column(JSONB)

    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Relationships ──
    actor: Mapped["User"] = relationship("User", foreign_keys=[actor_id], lazy="selectin")

    # ── Indexes ──
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_actor", "actor_id"),
        Index("ix_audit_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} on {self.entity_type}/{self.entity_id}>"


# ── Forward ref import для User relationship ─────────────────────────────────
# Импортируется в __init__.py — SQLAlchemy resolved через string refs
from app.models.user import User  # noqa: E402, F811
