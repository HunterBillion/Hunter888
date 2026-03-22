"""
Game CRM Service — бизнес-логика игровой CRM (Agent 7, spec 10.1-10.3).

4 основных метода:
1. get_client_timeline(story_id) — таймлайн с агрегацией
2. get_portfolio_stats(user_id) — статистика портфеля с Redis cache (TTL 5min)
3. schedule_callback(story_id, scheduled_for, note) — через ReminderScheduler
4. send_game_message(story_id, content) — сообщение в панели CRM

Дополнительно:
- get_stories_list(user_id) — список всех историй менеджера
- get_story_detail(story_id) — детали конкретной истории
- change_game_status(story_id, new_status) — смена статуса игрового клиента
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.game_crm import GameClientEvent, GameClientStatus, GameEventType
from app.models.roleplay import ClientStory, EpisodicMemory
from app.models.training import TrainingSession
from app.models.user import User
from app.services.timeline_aggregator import TimelineAggregator, create_game_event

logger = logging.getLogger(__name__)

# Redis cache TTL
PORTFOLIO_CACHE_TTL = 300  # 5 минут


# ══════════════════════════════════════════════════════════════════════════════
# Redis helper (shared pool)
# ══════════════════════════════════════════════════════════════════════════════

_redis_pool: aioredis.ConnectionPool | None = None


def _get_redis() -> aioredis.Redis:
    """Get Redis client using shared pool (same pattern as deps.py)."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.ConnectionPool.from_url(
            settings.redis_url, decode_responses=True, max_connections=10,
        )
    return aioredis.Redis(connection_pool=_redis_pool)


async def _cache_get(key: str) -> dict | None:
    """Read from Redis cache, return None on miss or error."""
    try:
        redis = _get_redis()
        raw = await redis.get(key)
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.debug("Redis cache miss/error: %s", e)
    return None


async def _cache_set(key: str, data: dict, ttl: int = PORTFOLIO_CACHE_TTL) -> None:
    """Write to Redis cache (best-effort)."""
    try:
        redis = _get_redis()
        await redis.set(key, json.dumps(data, default=str), ex=ttl)
    except Exception as e:
        logger.debug("Redis cache set error: %s", e)


async def _cache_invalidate(pattern: str) -> None:
    """Invalidate keys by pattern (best-effort)."""
    try:
        redis = _get_redis()
        keys = []
        async for key in redis.scan_iter(match=pattern, count=100):
            keys.append(key)
        if keys:
            await redis.delete(*keys)
    except Exception as e:
        logger.debug("Redis cache invalidate error: %s", e)


class GameCRMService:
    """Сервис Game CRM — основная бизнес-логика."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.timeline = TimelineAggregator(db)

    # ══════════════════════════════════════════════════════════════════════════
    # 1. get_client_timeline — таймлайн истории
    # ══════════════════════════════════════════════════════════════════════════

    async def get_client_timeline(
        self,
        story_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        event_types: list[str] | None = None,
        include_memories: bool = False,
    ) -> dict:
        """
        Получить таймлайн игрового клиента.

        Returns:
            {"items": [...], "total": N, "limit": N, "offset": N}
        """
        items = await self.timeline.get_timeline(
            story_id,
            limit=limit,
            offset=offset,
            event_types=event_types,
            include_memories=include_memories,
        )
        total = await self.timeline.get_timeline_count(story_id, event_types)

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # 2. get_portfolio_stats — статистика портфеля с Redis cache
    # ══════════════════════════════════════════════════════════════════════════

    async def get_portfolio_stats(
        self,
        user_id: uuid.UUID,
        *,
        period: str = "all",  # "week" | "month" | "all"
    ) -> dict:
        """
        Статистика портфеля игровых клиентов менеджера.

        Кэшируется в Redis (TTL 5 мин).

        Returns:
            {
                "total_stories": N,
                "completed": N,
                "active": N,
                "avg_score": float,
                "total_calls": N,
                "avg_calls_per_story": float,
                "status_breakdown": {"new": N, "contacted": N, ...},
                "recent_events": [...],
                "trend": {"direction": "up"|"down"|"stable", "change_pct": float},
                "period": "week"|"month"|"all",
            }
        """
        cache_key = f"game_crm:portfolio:{user_id}:{period}"
        cached = await _cache_get(cache_key)
        if cached:
            return cached

        # ── Compute fresh stats ──
        stats = await self._compute_portfolio_stats(user_id, period)

        # Cache result
        await _cache_set(cache_key, stats)

        return stats

    async def _compute_portfolio_stats(
        self,
        user_id: uuid.UUID,
        period: str,
    ) -> dict:
        """Подсчёт статистики портфеля из БД."""
        now = datetime.now(timezone.utc)

        # Фильтр по периоду
        date_filter = None
        if period == "week":
            date_filter = now - timedelta(days=7)
        elif period == "month":
            date_filter = now - timedelta(days=30)

        # ── Основная выборка историй ──
        query = select(ClientStory).where(ClientStory.user_id == user_id)
        if date_filter:
            query = query.where(ClientStory.created_at >= date_filter)
        result = await self.db.execute(query)
        stories = list(result.scalars().all())

        total = len(stories)
        completed = sum(1 for s in stories if s.is_completed)
        active = total - completed

        # ── Средний балл из TrainingSession ──
        story_ids = [s.id for s in stories]
        avg_score = 0.0
        total_calls = 0

        if story_ids:
            score_query = select(
                func.avg(TrainingSession.score_total),
                func.count(TrainingSession.id),
            ).where(
                TrainingSession.client_story_id.in_(story_ids),
                TrainingSession.score_total.isnot(None),
            )
            score_result = await self.db.execute(score_query)
            row = score_result.one_or_none()
            if row:
                avg_score = round(float(row[0] or 0), 1)
                total_calls = int(row[1] or 0)

        # ── Status breakdown (из последних событий status_change) ──
        status_breakdown: dict[str, int] = {}
        for s in stories:
            # Используем director_state или дефолт "new"
            ds = s.director_state or {}
            current_status = ds.get("game_status", "new")
            status_breakdown[current_status] = status_breakdown.get(current_status, 0) + 1

        # ── Последние события ──
        recent_query = (
            select(GameClientEvent)
            .where(
                GameClientEvent.user_id == user_id,
            )
            .order_by(desc(GameClientEvent.created_at))
            .limit(5)
        )
        recent_result = await self.db.execute(recent_query)
        recent_events = [
            e.to_timeline_dict()
            for e in recent_result.scalars().all()
        ]

        # ── Trend (сравнение с предыдущим периодом) ──
        trend = await self._compute_trend(user_id, period, total_calls)

        return {
            "total_stories": total,
            "completed": completed,
            "active": active,
            "avg_score": avg_score,
            "total_calls": total_calls,
            "avg_calls_per_story": round(total_calls / max(total, 1), 1),
            "status_breakdown": status_breakdown,
            "recent_events": recent_events,
            "trend": trend,
            "period": period,
        }

    async def _compute_trend(
        self,
        user_id: uuid.UUID,
        period: str,
        current_calls: int,
    ) -> dict:
        """Подсчёт тренда: сравнение с предыдущим аналогичным периодом."""
        now = datetime.now(timezone.utc)

        if period == "week":
            prev_start = now - timedelta(days=14)
            prev_end = now - timedelta(days=7)
        elif period == "month":
            prev_start = now - timedelta(days=60)
            prev_end = now - timedelta(days=30)
        else:
            return {"direction": "stable", "change_pct": 0.0}

        # Подсчёт звонков за предыдущий период
        prev_stories = await self.db.execute(
            select(ClientStory.id).where(
                ClientStory.user_id == user_id,
                ClientStory.created_at >= prev_start,
                ClientStory.created_at < prev_end,
            )
        )
        prev_story_ids = [r[0] for r in prev_stories.all()]

        prev_calls = 0
        if prev_story_ids:
            result = await self.db.execute(
                select(func.count(TrainingSession.id)).where(
                    TrainingSession.client_story_id.in_(prev_story_ids),
                )
            )
            prev_calls = result.scalar() or 0

        if prev_calls == 0:
            direction = "up" if current_calls > 0 else "stable"
            return {"direction": direction, "change_pct": 100.0 if current_calls > 0 else 0.0}

        change_pct = round(((current_calls - prev_calls) / prev_calls) * 100, 1)
        if change_pct > 5:
            direction = "up"
        elif change_pct < -5:
            direction = "down"
        else:
            direction = "stable"

        return {"direction": direction, "change_pct": change_pct}

    # ══════════════════════════════════════════════════════════════════════════
    # 3. schedule_callback — планирование обратного звонка
    # ══════════════════════════════════════════════════════════════════════════

    async def schedule_callback(
        self,
        story_id: uuid.UUID,
        owner_id: uuid.UUID | None,
        actor_id: uuid.UUID,
        *,
        scheduled_for: str,
        note: str | None = None,
    ) -> dict:
        """
        Запланировать обратный звонок через ReminderScheduler.
        owner_id=None для admin (доступ ко всем), actor_id — кто выполнил действие.
        """
        story = await self._get_story(story_id, owner_id)

        event = await create_game_event(
            self.db,
            story_id=story_id,
            user_id=actor_id,
            event_type=GameEventType.callback,
            source="manager",
            title=f"Обратный звонок запланирован: {scheduled_for}",
            content=note,
            narrative_date=scheduled_for,
            payload={
                "scheduled_for": scheduled_for,
                "note": note,
                "reminder_type": "game_callback",
                "story_name": story.story_name,
            },
            severity=0.6,
        )

        # WS уведомление — владельцу истории (manager)
        try:
            from app.ws.notifications import send_ws_notification
            await send_ws_notification(
                str(story.user_id),
                event_type="game_crm.callback_scheduled",
                data={
                    "story_id": str(story_id),
                    "story_name": story.story_name,
                    "scheduled_for": scheduled_for,
                    "event_id": str(event.id),
                },
            )
        except Exception:
            logger.debug("WS notification failed for game callback")

        await _cache_invalidate(f"game_crm:portfolio:{story.user_id}:*")

        return {
            "event_id": str(event.id),
            "scheduled_for": scheduled_for,
            "note": note,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # 4. send_game_message — отправка сообщения в панели
    # ══════════════════════════════════════════════════════════════════════════

    async def send_game_message(
        self,
        story_id: uuid.UUID,
        owner_id: uuid.UUID | None,
        actor_id: uuid.UUID,
        *,
        content: str,
        narrative_date: str | None = None,
    ) -> dict:
        """
        Отправить сообщение игровому клиенту (запись в таймлайн).
        owner_id=None для admin, actor_id — кто отправил.
        """
        story = await self._get_story(story_id, owner_id)

        event = await create_game_event(
            self.db,
            story_id=story_id,
            user_id=actor_id,
            event_type=GameEventType.message,
            source="manager",
            title="Сообщение клиенту",
            content=content,
            narrative_date=narrative_date,
            payload={"story_name": story.story_name},
            severity=0.3,
        )

        try:
            from app.ws.notifications import send_ws_notification
            await send_ws_notification(
                str(story.user_id),
                event_type="game_crm.message_sent",
                data={
                    "story_id": str(story_id),
                    "event_id": str(event.id),
                    "content": content[:100],
                },
            )
        except Exception:
            logger.debug("WS notification failed for game message")

        return {
            "event_id": str(event.id),
            "content": content,
            "timestamp": event.created_at.isoformat() if event.created_at else None,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # Дополнительные методы
    # ══════════════════════════════════════════════════════════════════════════

    async def get_stories_list(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        completed: bool | None = None,
    ) -> dict:
        """
        Список игровых историй менеджера.

        Returns:
            {"items": [...], "total": N}
        """
        query = select(ClientStory).where(ClientStory.user_id == user_id)
        count_query = select(func.count()).where(ClientStory.user_id == user_id)

        if completed is not None:
            query = query.where(ClientStory.is_completed == completed)
            count_query = count_query.where(ClientStory.is_completed == completed)

        query = query.order_by(desc(ClientStory.created_at)).limit(limit).offset(offset)

        result = await self.db.execute(query)
        stories = result.scalars().all()

        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        items = []
        for s in stories:
            ds = s.director_state or {}
            session_stats_result = await self.db.execute(
                select(
                    func.count(TrainingSession.id),
                    func.avg(TrainingSession.score_total),
                    func.max(TrainingSession.score_total),
                ).where(TrainingSession.client_story_id == s.id)
            )
            calls_count, avg_score, best_score = session_stats_result.one()
            # Подсчёт событий для story
            event_count_result = await self.db.execute(
                select(func.count()).where(GameClientEvent.story_id == s.id)
            )
            event_count = event_count_result.scalar() or 0

            items.append({
                "id": str(s.id),
                "story_name": s.story_name,
                "total_calls_planned": s.total_calls_planned,
                "current_call_number": s.current_call_number,
                "is_completed": s.is_completed,
                "game_status": ds.get("game_status", "new"),
                "tension": ds.get("tension_curve", [0])[-1] if ds.get("tension_curve") else 0,
                "event_count": event_count,
                "calls_completed": int(calls_count or 0),
                "avg_score": round(float(avg_score), 1) if avg_score is not None else None,
                "best_score": round(float(best_score), 1) if best_score is not None else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "started_at": s.started_at.isoformat() if s.started_at else None,
            })

        return {"items": items, "total": total}

    async def get_story_detail(
        self,
        story_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> dict:
        """Детальная информация об игровой истории."""
        query = select(ClientStory).where(ClientStory.id == story_id)
        if user_id:
            query = query.where(ClientStory.user_id == user_id)

        result = await self.db.execute(query)
        story = result.scalar_one_or_none()

        if not story:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Story not found")

        ds = story.director_state or {}

        # Подсчёт событий
        event_count_result = await self.db.execute(
            select(func.count()).where(GameClientEvent.story_id == story_id)
        )
        session_stats_result = await self.db.execute(
            select(
                func.count(TrainingSession.id),
                func.avg(TrainingSession.score_total),
                func.max(TrainingSession.score_total),
            ).where(TrainingSession.client_story_id == story_id)
        )
        calls_count, avg_score, best_score = session_stats_result.one()

        return {
            "id": str(story.id),
            "user_id": str(story.user_id),
            "client_profile_id": str(story.client_profile_id) if story.client_profile_id else None,
            "story_name": story.story_name,
            "total_calls_planned": story.total_calls_planned,
            "current_call_number": story.current_call_number,
            "is_completed": story.is_completed,
            "game_status": ds.get("game_status", "new"),
            "tension_curve": ds.get("tension_curve", []),
            "pacing": ds.get("pacing", "normal"),
            "next_twist": ds.get("next_twist"),
            "active_factors": story.active_factors or [],
            "between_call_events": story.between_call_events or [],
            "consequences": story.consequences or [],
            "event_count": event_count_result.scalar() or 0,
            "calls_completed": int(calls_count or 0),
            "avg_score": round(float(avg_score), 1) if avg_score is not None else None,
            "best_score": round(float(best_score), 1) if best_score is not None else None,
            "personality_profile": story.personality_profile or {},
            "created_at": story.created_at.isoformat() if story.created_at else None,
            "started_at": story.started_at.isoformat() if story.started_at else None,
            "ended_at": story.ended_at.isoformat() if story.ended_at else None,
        }

    async def change_game_status(
        self,
        story_id: uuid.UUID,
        owner_id: uuid.UUID | None,
        actor_id: uuid.UUID,
        *,
        new_status: str,
        reason: str | None = None,
    ) -> dict:
        """Сменить игровой статус клиента. owner_id=None для admin."""
        story = await self._get_story(story_id, owner_id)
        ds = story.director_state or {}
        old_status = ds.get("game_status", "new")

        if old_status == new_status:
            return {"old_status": old_status, "new_status": new_status, "changed": False}

        # Обновляем director_state
        ds["game_status"] = new_status
        ds["last_status_change"] = datetime.now(timezone.utc).isoformat()
        story.director_state = ds
        # Force JSONB update detection
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(story, "director_state")

        await create_game_event(
            self.db,
            story_id=story_id,
            user_id=actor_id,
            event_type=GameEventType.status_change,
            source="manager",
            title=f"Статус: {old_status} → {new_status}",
            content=reason,
            payload={"old_status": old_status, "new_status": new_status, "reason": reason},
            severity=0.7,
        )

        try:
            from app.ws.notifications import send_ws_notification
            await send_ws_notification(
                str(story.user_id),
                event_type="game_crm.status_changed",
                data={
                    "story_id": str(story_id),
                    "old_status": old_status,
                    "new_status": new_status,
                },
            )
        except Exception:
            logger.debug("WS notification failed for game status change")

        await _cache_invalidate(f"game_crm:portfolio:{story.user_id}:*")

        return {"old_status": old_status, "new_status": new_status, "changed": True}

    async def mark_events_read(
        self,
        story_id: uuid.UUID,
        user_id: uuid.UUID,
        event_ids: list[str] | None = None,
    ) -> int:
        """Пометить события как прочитанные."""
        from sqlalchemy import update

        query = (
            update(GameClientEvent)
            .where(
                GameClientEvent.story_id == story_id,
                GameClientEvent.user_id == user_id,
                GameClientEvent.is_read == False,  # noqa: E712
            )
            .values(is_read=True)
        )
        if event_ids:
            parsed_ids = [uuid.UUID(eid) for eid in event_ids]
            query = query.where(GameClientEvent.id.in_(parsed_ids))

        result = await self.db.execute(query)
        return result.rowcount

    # ══════════════════════════════════════════════════════════════════════════
    # Internal helpers
    # ══════════════════════════════════════════════════════════════════════════

    async def _get_story(
        self, story_id: uuid.UUID, user_id: uuid.UUID | None
    ) -> ClientStory:
        """Получить story с проверкой доступа. user_id=None для admin (доступ ко всем)."""
        query = select(ClientStory).where(ClientStory.id == story_id)
        if user_id is not None:
            query = query.where(ClientStory.user_id == user_id)
        result = await self.db.execute(query)
        story = result.scalar_one_or_none()
        if not story:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Story not found or access denied")
        return story
