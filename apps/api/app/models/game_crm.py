"""
AI continuity models for the unified Clients domain.

GameClientEvent остаётся отдельной таблицей от ClientInteraction:
- не хранит реальные ПДн
- обслуживает AI continuity / training слой
- должен быть логически совместим с общим путём клиента, а не жить как отдельная CRM
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GameEventType(str, enum.Enum):
    """6 типов событий таймлайна (ТЗ 10.1)."""
    call = "call"                    # Звонок (из TrainingSession)
    message = "message"              # Сообщение в панели
    consequence = "consequence"      # Последствие (от Game Director)
    storylet = "storylet"            # Сюжетное событие
    status_change = "status_change"  # Смена статуса игрового клиента
    callback = "callback"            # Запланированный обратный звонок


class GameClientStatus(str, enum.Enum):
    """Статусы игрового клиента (зеркало реального CRM, упрощённый)."""
    new = "new"
    contacted = "contacted"
    interested = "interested"
    thinking = "thinking"
    consent_given = "consent_given"
    documents = "documents"
    contract_signed = "contract_signed"
    in_process = "in_process"
    completed = "completed"
    lost = "lost"


class GameClientEvent(Base):
    """
    Событие таймлайна игрового клиента.

    Отдельная от ClientInteraction таблица:
    - Не содержит реальных ПДн
    - Привязана к ClientStory (AI-клиент), а не к RealClient
    - Соответствует TimelineEvent(timestamp, type, source, payload)
    """
    __tablename__ = "game_client_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    story_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_stories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Тип события
    event_type: Mapped[GameEventType] = mapped_column(
        Enum(GameEventType, name="game_event_type", create_constraint=True),
        nullable=False,
    )

    # Источник события
    source: Mapped[str] = mapped_column(
        String(100), nullable=False, default="system",
        comment="Источник: system, manager, game_director, scheduler",
    )

    # Нарративная дата (игровое время, не реальное)
    narrative_date: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Дата в игровом мире, e.g. '15 марта 2024'",
    )

    # Основной контент
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Привязка к сессии (для event_type=call)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Привязка к обратному звонку (для event_type=callback)
    reminder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )

    # Payload для специфичных данных
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Примеры payload:
    # call: {"score": 78, "duration_sec": 180, "emotion_final": "considering"}
    # consequence: {"severity": 0.8, "type": "trust_broken", "detail": "..."}
    # storylet: {"storylet_id": "collectors_arrived", "impact": "anxiety+30"}
    # status_change: {"old_status": "new", "new_status": "contacted"}
    # callback: {"scheduled_for": "2024-03-17", "reminder_type": "game_callback"}

    # Метаданные
    severity: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Важность события 0.0-1.0 (для сортировки/фильтрации)",
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_game_events_story_created", "story_id", "created_at"),
        Index("ix_game_events_user_type", "user_id", "event_type"),
    )

    def to_timeline_dict(self) -> dict:
        """Сериализация для TimelineEvent формата."""
        return {
            "id": str(self.id),
            "timestamp": self.created_at.isoformat() if self.created_at else None,
            "type": self.event_type.value,
            "source": self.source,
            "narrative_date": self.narrative_date,
            "title": self.title,
            "content": self.content,
            "payload": self.payload or {},
            "severity": self.severity,
            "is_read": self.is_read,
            "session_id": str(self.session_id) if self.session_id else None,
        }
