"""
TimelineAggregator — сервис агрегации таймлайна игрового клиента (ТЗ 10.1).

Adapter pattern: собирает события из нескольких источников и возвращает
единый отсортированный таймлайн в формате TimelineEvent.

Источники:
1. GameClientEvent (таблица game_client_events)
2. TrainingSession (звонки, привязанные к story)
3. EpisodicMemory (ключевые моменты из звонков)
4. ClientStory.between_call_events (CRM-симуляция)
5. ClientStory.consequences (накопленные последствия)
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game_crm import GameClientEvent, GameEventType
from app.models.roleplay import ClientStory, EpisodicMemory

logger = logging.getLogger(__name__)


@dataclass
class TimelineEvent:
    """Единый формат события таймлайна (ТЗ 10.1)."""
    timestamp: str
    type: str           # call | message | consequence | storylet | status_change | callback
    source: str         # system | manager | game_director | scheduler | memory
    title: str
    content: str | None = None
    payload: dict = field(default_factory=dict)
    severity: float | None = None
    narrative_date: str | None = None
    event_id: str | None = None
    session_id: str | None = None
    is_read: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.event_id,
            "timestamp": self.timestamp,
            "type": self.type,
            "source": self.source,
            "title": self.title,
            "content": self.content,
            "payload": self.payload,
            "severity": self.severity,
            "narrative_date": self.narrative_date,
            "session_id": self.session_id,
            "is_read": self.is_read,
        }


class TimelineAggregator:
    """
    Агрегатор таймлайна: собирает события из всех источников,
    объединяет и сортирует по timestamp (desc).

    Использование:
        aggregator = TimelineAggregator(db)
        timeline = await aggregator.get_timeline(story_id, limit=50)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_timeline(
        self,
        story_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        event_types: list[str] | None = None,
        include_memories: bool = False,
        include_between_events: bool = True,
    ) -> list[dict]:
        """
        Получить объединённый таймлайн для story.

        Args:
            story_id: ID клиентской истории
            limit: Макс. количество событий
            offset: Смещение для пагинации
            event_types: Фильтр по типам (None = все)
            include_memories: Включить эпизодические воспоминания
            include_between_events: Включить между-звонковые события из story

        Returns:
            Список TimelineEvent в формате dict, отсортированный по timestamp desc
        """
        events: list[TimelineEvent] = []

        # ── 1. GameClientEvent (основной источник) ──
        db_events = await self._fetch_game_events(story_id, event_types)
        events.extend(db_events)

        # ── 2. Between-call events из ClientStory JSONB ──
        if include_between_events:
            story_events = await self._fetch_between_call_events(story_id)
            events.extend(story_events)

        # ── 3. Consequences из ClientStory JSONB ──
        consequence_events = await self._fetch_story_consequences(story_id)
        events.extend(consequence_events)

        # ── 4. Episodic memories (опционально) ──
        if include_memories:
            memory_events = await self._fetch_episodic_memories(story_id)
            events.extend(memory_events)

        # ── Сортировка по timestamp (desc) и пагинация ──
        events.sort(key=lambda e: e.timestamp, reverse=True)

        # Фильтр по типам (если указаны)
        if event_types:
            events = [e for e in events if e.type in event_types]

        # Пагинация
        paginated = events[offset: offset + limit]

        return [e.to_dict() for e in paginated]

    async def get_timeline_count(
        self,
        story_id: uuid.UUID,
        event_types: list[str] | None = None,
    ) -> int:
        """Подсчёт общего количества событий (для пагинации)."""
        from sqlalchemy import func

        query = select(func.count()).where(GameClientEvent.story_id == story_id)
        if event_types:
            query = query.where(GameClientEvent.event_type.in_(event_types))
        result = await self.db.execute(query)
        return result.scalar() or 0

    # ══════════════════════════════════════════════════════════════════════════
    # Адаптеры источников
    # ══════════════════════════════════════════════════════════════════════════

    async def _fetch_game_events(
        self,
        story_id: uuid.UUID,
        event_types: list[str] | None = None,
    ) -> list[TimelineEvent]:
        """Адаптер: GameClientEvent → TimelineEvent."""
        query = (
            select(GameClientEvent)
            .where(GameClientEvent.story_id == story_id)
            .order_by(desc(GameClientEvent.created_at))
            .limit(200)  # Hard limit для безопасности
        )
        if event_types:
            query = query.where(GameClientEvent.event_type.in_(event_types))

        result = await self.db.execute(query)
        rows = result.scalars().all()

        return [
            TimelineEvent(
                event_id=str(row.id),
                timestamp=row.created_at.isoformat() if row.created_at else "",
                type=row.event_type.value,
                source=row.source,
                title=row.title,
                content=row.content,
                payload=row.payload or {},
                severity=row.severity,
                narrative_date=row.narrative_date,
                session_id=str(row.session_id) if row.session_id else None,
                is_read=row.is_read,
            )
            for row in rows
        ]

    async def _fetch_between_call_events(
        self,
        story_id: uuid.UUID,
    ) -> list[TimelineEvent]:
        """Адаптер: ClientStory.between_call_events JSONB → TimelineEvent."""
        result = await self.db.execute(
            select(ClientStory.between_call_events, ClientStory.created_at)
            .where(ClientStory.id == story_id)
        )
        row = result.one_or_none()
        if not row or not row[0]:
            return []

        events_json = row[0] if isinstance(row[0], list) else []
        story_created = row[1]

        timeline_events = []
        for i, evt in enumerate(events_json):
            if not isinstance(evt, dict):
                continue
            timeline_events.append(
                TimelineEvent(
                    event_id=f"between_{story_id}_{i}",
                    timestamp=story_created.isoformat() if story_created else "",
                    type="storylet",
                    source="game_director",
                    title=evt.get("event", "Событие между звонками"),
                    content=evt.get("impact", ""),
                    payload=evt,
                    narrative_date=evt.get("narrative_date"),
                    severity=evt.get("severity", 0.5),
                )
            )
        return timeline_events

    async def _fetch_story_consequences(
        self,
        story_id: uuid.UUID,
    ) -> list[TimelineEvent]:
        """Адаптер: ClientStory.consequences JSONB → TimelineEvent."""
        result = await self.db.execute(
            select(ClientStory.consequences, ClientStory.created_at)
            .where(ClientStory.id == story_id)
        )
        row = result.one_or_none()
        if not row or not row[0]:
            return []

        consequences = row[0] if isinstance(row[0], list) else []
        story_created = row[1]

        timeline_events = []
        for i, csq in enumerate(consequences):
            if not isinstance(csq, dict):
                continue
            timeline_events.append(
                TimelineEvent(
                    event_id=f"csq_{story_id}_{i}",
                    timestamp=story_created.isoformat() if story_created else "",
                    type="consequence",
                    source="game_director",
                    title=csq.get("type", "Последствие"),
                    content=csq.get("detail", ""),
                    payload=csq,
                    severity=csq.get("severity", 0.5),
                )
            )
        return timeline_events

    async def _fetch_episodic_memories(
        self,
        story_id: uuid.UUID,
    ) -> list[TimelineEvent]:
        """Адаптер: EpisodicMemory → TimelineEvent (высокая salience)."""
        result = await self.db.execute(
            select(EpisodicMemory)
            .where(
                EpisodicMemory.story_id == story_id,
                EpisodicMemory.salience >= 7,  # Только важные
                EpisodicMemory.is_compressed == False,  # noqa: E712
            )
            .order_by(desc(EpisodicMemory.created_at))
            .limit(20)
        )
        rows = result.scalars().all()

        return [
            TimelineEvent(
                event_id=f"mem_{row.id}",
                timestamp=row.created_at.isoformat() if row.created_at else "",
                type="message",
                source="memory",
                title=f"Воспоминание (звонок {row.call_number})",
                content=row.content,
                payload={
                    "memory_type": row.memory_type,
                    "salience": row.salience,
                    "valence": row.valence,
                    "call_number": row.call_number,
                },
                severity=row.salience / 10.0 if row.salience else 0.5,
            )
            for row in rows
        ]


# ══════════════════════════════════════════════════════════════════════════════
# Helper: создание событий
# ══════════════════════════════════════════════════════════════════════════════

async def create_game_event(
    db: AsyncSession,
    *,
    story_id: uuid.UUID,
    user_id: uuid.UUID,
    event_type: GameEventType,
    title: str,
    source: str = "system",
    content: str | None = None,
    narrative_date: str | None = None,
    session_id: uuid.UUID | None = None,
    payload: dict | None = None,
    severity: float | None = None,
) -> GameClientEvent:
    """Создать новое событие таймлайна и вернуть его.

    Side effect (TZ-1 §11.3): если ``story`` связана с реальным CRM-клиентом
    через хотя бы одну ``TrainingSession`` с ``real_client_id``, параллельно
    появится ``DomainEvent`` ``game.<event_type>``. Для чисто синтетических
    историй (нет real_client) продолжает работать только старый путь.
    """
    event = GameClientEvent(
        id=uuid.uuid4(),
        story_id=story_id,
        user_id=user_id,
        event_type=event_type,
        source=source,
        narrative_date=narrative_date,
        title=title,
        content=content,
        session_id=session_id,
        payload=payload,
        severity=severity,
    )
    db.add(event)
    await db.flush()

    try:
        story = await db.get(ClientStory, story_id)
        if story is not None:
            # Import inside function to avoid circular import at module load.
            from app.services.client_story_projector import record_story_game_event

            await record_story_game_event(
                db,
                story=story,
                game_event_type=event_type.value if hasattr(event_type, "value") else str(event_type),
                game_event_id=event.id,
                payload={
                    "title": title,
                    "content": content,
                    "narrative_date": narrative_date,
                    "session_id": str(session_id) if session_id else None,
                    "severity": severity,
                    "raw_payload": payload,
                },
                actor_id=user_id,
                source="timeline_aggregator",
            )
    except Exception:
        # Dual-write best-effort: never break game-event creation because
        # CRM mirror failed. Strict mode is available via config.
        logger.warning("create_game_event: domain mirror failed", exc_info=True)

    return event
