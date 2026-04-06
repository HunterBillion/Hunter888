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

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.core import errors as err
from app.core.redis_pool import get_redis
from app.models.game_crm import GameClientEvent, GameClientStatus, GameEventType
from app.models.roleplay import ClientProfile, ClientStory, EpisodicMemory, ObjectionChain, Trap
from app.models.training import TrainingSession
from app.models.user import User
from app.services.llm import generate_response
from app.services.rag_legal import retrieve_legal_context
from app.services.objection_chain import build_chain_system_prompt
from app.services.timeline_aggregator import TimelineAggregator, create_game_event
from app.services.trap_detector import build_trap_injection_prompt

logger = logging.getLogger(__name__)

# Redis cache TTL
PORTFOLIO_CACHE_TTL = 300  # 5 минут

MAX_CHAT_HISTORY_EVENTS = 12
MAX_MEMORY_ITEMS = 8


# ══════════════════════════════════════════════════════════════════════════════
# Redis helper (uses centralized pool from app.core.redis_pool)
# ══════════════════════════════════════════════════════════════════════════════

def _get_redis() -> aioredis.Redis:
    """Get Redis client from centralized shared pool."""
    return get_redis()


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
        user_id: uuid.UUID | None = None,
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
        await self._get_story(story_id, user_id)
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

        manager_event = await create_game_event(
            self.db,
            story_id=story_id,
            user_id=actor_id,
            event_type=GameEventType.message,
            source="manager",
            title="Сообщение клиенту",
            content=content,
            narrative_date=narrative_date,
            payload={"story_name": story.story_name, "role": "manager"},
            severity=0.3,
        )

        ai_reply_text = await self._safe_generate_ai_client_reply(
            story,
            actor_id=actor_id,
            manager_message=content,
        )
        ai_event = await create_game_event(
            self.db,
            story_id=story_id,
            user_id=story.user_id,
            event_type=GameEventType.message,
            source="ai_client",
            title="Ответ AI-клиента",
            content=ai_reply_text,
            narrative_date=narrative_date,
            payload={
                "story_name": story.story_name,
                "role": "ai_client",
                "reply_to_event_id": str(manager_event.id),
            },
            severity=0.55,
        )

        try:
            from app.ws.notifications import send_ws_notification
            await send_ws_notification(
                str(story.user_id),
                event_type="game_crm.message_sent",
                data={
                    "story_id": str(story_id),
                    "event_id": str(manager_event.id),
                    "content": content[:100],
                    "reply_event_id": str(ai_event.id),
                    "reply_preview": ai_reply_text[:140],
                },
            )
        except Exception:
            logger.debug("WS notification failed for game message")

        return {
            "event_id": str(manager_event.id),
            "content": content,
            "timestamp": manager_event.created_at.isoformat() if manager_event.created_at else None,
            "event": manager_event.to_timeline_dict(),
            "reply": {
                "event_id": str(ai_event.id),
                "content": ai_reply_text,
                "timestamp": ai_event.created_at.isoformat() if ai_event.created_at else None,
                "event": ai_event.to_timeline_dict(),
            },
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
            raise HTTPException(status_code=404, detail=err.STORY_NOT_FOUND)

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
            raise HTTPException(status_code=404, detail=err.STORY_NOT_FOUND_OR_ACCESS_DENIED)
        return story

    async def _generate_ai_client_reply(
        self,
        story: ClientStory,
        *,
        actor_id: uuid.UUID,
        manager_message: str,
    ) -> str:
        # Step 1: fetch recent chat history first — needed to build the RAG query
        recent_messages = await self._get_recent_chat_history(story.id)

        # Step 2: kick off the RAG lookup in the background using its own DB
        # session so it can run concurrently with the sequential self.db queries
        # below (SQLAlchemy async sessions hold a single connection — concurrent
        # queries on the same session are not safe).
        _legal_query = "\n".join(
            [msg.get("content", "") for msg in recent_messages[-6:]] + [manager_message]
        )

        async def _fetch_legal_isolated():
            from app.database import async_session as _make_session
            async with _make_session() as rag_db:
                return await retrieve_legal_context(_legal_query, rag_db, top_k=6)

        legal_task = asyncio.create_task(_fetch_legal_isolated())

        # Step 3: sequential self.db queries (single connection, cannot parallelize)
        memories = await self._get_story_memories(story.id)
        manager_skill = await self._get_manager_skill_profile(actor_id)
        traps = await self._get_story_traps(story)
        chain_prompt = await self._get_story_chain_prompt(story)

        profile = None
        if story.client_profile_id:
            profile_result = await self.db.execute(
                select(ClientProfile).where(ClientProfile.id == story.client_profile_id)
            )
            profile = profile_result.scalar_one_or_none()

        # Step 4: await the RAG result (likely already done by the time we get here)
        try:
            legal_context = await legal_task
        except Exception as exc:
            logger.warning("Legal context fetch failed, proceeding without RAG: %s", exc)
            from app.services.rag_legal import RAGContext
            legal_context = RAGContext(results=[], query=_legal_query)

        system_prompt = self._build_ai_client_system_prompt(
            story,
            profile=profile,
            memories=memories,
            traps=traps,
            chain_prompt=chain_prompt,
            manager_skill=manager_skill,
            legal_context=legal_context.to_prompt_context() if legal_context.has_results else "",
        )
        messages = list(recent_messages)
        if not (
            messages
            and messages[-1].get("role") == "user"
            and messages[-1].get("content", "").strip() == manager_message.strip()
        ):
            messages.append({"role": "user", "content": manager_message})

        response = await generate_response(
            system_prompt=system_prompt,
            messages=messages,
            emotion_state=self._resolve_story_emotion(story),
            user_id=str(story.user_id),
        )
        reply_text = response.content.strip()
        await self._update_story_legal_memory(
            story,
            manager_message=manager_message,
            legal_context=legal_context,
            manager_skill=manager_skill,
        )
        return reply_text
        
    async def _safe_generate_ai_client_reply(
        self,
        story: ClientStory,
        *,
        actor_id: uuid.UUID,
        manager_message: str,
    ) -> str:
        try:
            return await self._generate_ai_client_reply(story, actor_id=actor_id, manager_message=manager_message)
        except Exception as exc:
            logger.warning("Game CRM AI reply fallback: story=%s error=%s", story.id, exc)
            return (
                "Я вас услышал, но у меня пока слишком много сомнений. "
                "Объясните проще: почему в моей ситуации это вообще законно и что со мной реально будет дальше?"
            )

    async def _get_recent_chat_history(self, story_id: uuid.UUID) -> list[dict[str, str]]:
        result = await self.db.execute(
            select(GameClientEvent)
            .where(
                GameClientEvent.story_id == story_id,
                GameClientEvent.event_type == GameEventType.message,
            )
            .order_by(desc(GameClientEvent.created_at))
            .limit(MAX_CHAT_HISTORY_EVENTS)
        )
        rows = list(reversed(result.scalars().all()))
        messages: list[dict[str, str]] = []
        for row in rows:
            if not row.content:
                continue
            role = "assistant" if row.source == "ai_client" else "user"
            messages.append({"role": role, "content": row.content})
        return messages

    async def _get_story_memories(self, story_id: uuid.UUID) -> list[EpisodicMemory]:
        result = await self.db.execute(
            select(EpisodicMemory)
            .where(EpisodicMemory.story_id == story_id)
            .order_by(EpisodicMemory.salience.desc(), desc(EpisodicMemory.created_at))
            .limit(MAX_MEMORY_ITEMS)
        )
        return list(result.scalars().all())

    async def _get_story_traps(self, story: ClientStory) -> list[dict[str, Any]]:
        if not story.client_profile_id:
            return []

        profile_result = await self.db.execute(
            select(ClientProfile).where(ClientProfile.id == story.client_profile_id)
        )
        profile = profile_result.scalar_one_or_none()
        if not profile or not profile.trap_ids:
            return []

        trap_ids: list[uuid.UUID] = []
        for trap_id in profile.trap_ids:
            try:
                trap_ids.append(uuid.UUID(str(trap_id)))
            except (TypeError, ValueError):
                continue

        if not trap_ids:
            return []

        result = await self.db.execute(
            select(Trap).where(Trap.id.in_(trap_ids), Trap.is_active.is_(True))
        )
        traps = result.scalars().all()
        return [
            {
                "id": str(trap.id),
                "name": trap.name,
                "category": trap.category,
                "subcategory": trap.subcategory,
                "difficulty": trap.difficulty,
                "client_phrase": trap.client_phrase,
                "client_phrase_variants": trap.client_phrase_variants or [],
                "wrong_response_example": trap.wrong_response_example,
                "correct_response_example": trap.correct_response_example,
                "explanation": trap.explanation,
                "law_reference": trap.law_reference,
            }
            for trap in traps
        ]

    async def _get_story_chain_prompt(self, story: ClientStory) -> str:
        if not story.client_profile_id:
            return ""

        profile_result = await self.db.execute(
            select(ClientProfile).where(ClientProfile.id == story.client_profile_id)
        )
        profile = profile_result.scalar_one_or_none()
        if not profile or not profile.chain_id:
            return ""

        chain_result = await self.db.execute(
            select(ObjectionChain).where(ObjectionChain.id == profile.chain_id, ObjectionChain.is_active.is_(True))
        )
        chain = chain_result.scalar_one_or_none()
        if not chain or not isinstance(chain.steps, list):
            return ""

        return build_chain_system_prompt(chain.steps)

    async def _get_manager_skill_profile(self, actor_id: uuid.UUID) -> dict[str, Any]:
        stats = await self.db.execute(
            select(
                func.avg(TrainingSession.score_total),
                func.max(TrainingSession.score_total),
                func.count(TrainingSession.id),
            ).where(
                TrainingSession.user_id == actor_id,
                TrainingSession.score_total.isnot(None),
            )
        )
        avg_score, best_score, total_sessions = stats.one()
        avg_score = float(avg_score or 0.0)
        best_score = float(best_score or 0.0)
        total_sessions = int(total_sessions or 0)

        if total_sessions < 3 or avg_score < 60:
            tier = "novice"
            cunning_level = 0.45
        elif avg_score < 78:
            tier = "balanced"
            cunning_level = 0.62
        elif avg_score < 88:
            tier = "strong"
            cunning_level = 0.78
        else:
            tier = "expert"
            cunning_level = 0.9

        return {
            "avg_score": round(avg_score, 1),
            "best_score": round(best_score, 1),
            "total_sessions": total_sessions,
            "tier": tier,
            "cunning_level": cunning_level,
        }

    async def _update_story_legal_memory(
        self,
        story: ClientStory,
        *,
        manager_message: str,
        legal_context: Any,
        manager_skill: dict[str, Any],
    ) -> None:
        ds = story.director_state or {}
        existing_memory = ds.get("legal_memory") or []
        updated = list(existing_memory)

        for result in getattr(legal_context, "results", [])[:4]:
            updated.append(f"{result.law_article}: {result.fact_text}")
            if result.common_errors:
                updated.extend(
                    f"Ошибка/спорная тема: {item}" for item in result.common_errors[:2]
                )
            if result.correct_response_hint:
                updated.append(f"Корректный вектор ответа: {result.correct_response_hint}")

        if "127-фз" in manager_message.lower() or "ст." in manager_message.lower():
            updated.append(f"Менеджер ссылался на право: {manager_message[:220]}")

        # Preserve insertion order while deduplicating.
        deduped = list(dict.fromkeys(item for item in updated if item))[-12:]
        ds["legal_memory"] = deduped
        ds["adaptation_profile"] = {
            "manager_tier": manager_skill.get("tier"),
            "avg_score": manager_skill.get("avg_score"),
            "best_score": manager_skill.get("best_score"),
            "suggested_cunning_level": manager_skill.get("cunning_level"),
        }
        story.director_state = ds
        flag_modified(story, "director_state")

    def _resolve_story_emotion(self, story: ClientStory) -> str:
        ds = story.director_state or {}
        tension_curve = ds.get("tension_curve") or []
        tension = float(tension_curve[-1]) if tension_curve else 0.0

        if tension >= 0.85:
            return "hostile"
        if tension >= 0.65:
            return "testing"
        if tension >= 0.45:
            return "guarded"
        if tension >= 0.25:
            return "curious"
        return "cold"

    def _build_ai_client_system_prompt(
        self,
        story: ClientStory,
        *,
        profile: ClientProfile | None,
        memories: list[EpisodicMemory],
        traps: list[dict],
        chain_prompt: str,
        manager_skill: dict[str, Any],
        legal_context: str,
    ) -> str:
        ds = story.director_state or {}
        active_factors = story.active_factors or []
        between_events = story.between_call_events or []
        consequences = story.consequences or []
        personality = story.personality_profile or {}
        legal_memory = ds.get("legal_memory") or []
        adaptation = ds.get("adaptation_profile") or {}
        skill_tier = manager_skill.get("tier", "balanced")
        cunning_level = manager_skill.get("cunning_level", 0.6)

        parts = [
            "Ты играешь ИИ-клиента-должника в учебной CRM-панели по банкротству физлиц.",
            "Это не дружелюбный ассистент. Это живой, адаптивный, хитрый, психологически правдоподобный клиент.",
            "Твоя задача в диалоге: сопротивляться, проверять менеджера, путать акценты, цепляться к слабым местам, задавать уточняющие и неудобные вопросы.",
            "Но юридическая корректность важнее артистизма: примерно 70% приоритета — правовая точность, 30% — психологическая сложность и реализм.",
            "Если используешь юридические утверждения, опирайся на предоставленную правовую базу. Если правовой опоры нет, не выдумывай статьи и факты.",
            "Никогда не говори, что ты ИИ, модель, тренажёр или экзаменатор.",
            "Не оценивай менеджера и не объясняй баллы. Просто отвечай как клиент.",
            "Отвечай по-русски, естественно, 1-4 предложениями. Иногда можно дать короткий список, но без канцелярита.",
            f"Название истории: {story.story_name}.",
            f"Текущий этап истории: звонок {story.current_call_number} из {story.total_calls_planned}.",
            f"Режим развития истории: {ds.get('pacing', 'normal')}.",
            f"Следующий твист: {ds.get('next_twist') or 'не задан'}.",
            f"Текущий уровень хитрости клиента: {cunning_level:.2f} из 1.0.",
            f"Уровень менеджера по прошлым сессиям: {skill_tier}.",
        ]

        if profile:
            parts.extend(self._build_profile_context(profile))

        if personality:
            parts.append(f"Профиль личности истории: {json.dumps(personality, ensure_ascii=False)}")

        if active_factors:
            parts.append(
                "Активные человеческие факторы: "
                + json.dumps(active_factors[:6], ensure_ascii=False)
            )

        if between_events:
            parts.append(
                "Что происходило между звонками: "
                + json.dumps(between_events[-4:], ensure_ascii=False)
            )

        if consequences:
            parts.append(
                "Накопленные последствия прошлых контактов: "
                + json.dumps(consequences[-4:], ensure_ascii=False)
            )

        if memories:
            parts.append(
                "Что клиент помнит о предыдущих взаимодействиях:\n"
                + "\n".join(
                    f"- ({memory.memory_type}) {memory.content}"
                    for memory in memories
                )
            )

        if legal_memory:
            parts.append(
                "Жёсткая юридическая память клиента: ранее спорные или важные правовые темы, к которым он будет возвращаться:\n"
                + "\n".join(f"- {item}" for item in legal_memory[:8])
            )

        if adaptation:
            parts.append(
                "Профиль адаптации под менеджера: "
                + json.dumps(adaptation, ensure_ascii=False)
            )

        if legal_context:
            parts.append(legal_context)

        if traps:
            parts.append(build_trap_injection_prompt(traps))

        if chain_prompt:
            parts.append(chain_prompt)

        parts.append(
            "Поведенческие правила:\n"
            "- если менеджер поверхностен, усиливай недоверие и дроби разговор на неудобные уточнения;\n"
            "- если менеджер юридически точен, спорь умно, а не абсурдно;\n"
            "- можешь быть эмоциональным, но не ломай правдоподобие;\n"
            "- не соглашайся слишком быстро;\n"
            "- если менеджер задел важный страх или мягкую точку, можешь немного смягчиться;\n"
            "- если менеджер слабый, не раскрывай все возражения сразу — дави простыми, но болезненными сомнениями;\n"
            "- если менеджер сильный, используй более тонкие юридические, эмоциональные и procedural-вопросы."
        )

        return "\n\n".join(parts)

    def _build_profile_context(self, profile: ClientProfile) -> list[str]:
        parts = [
            (
                "Скрытый профиль клиента: "
                f"{profile.full_name}, {profile.age} лет, {profile.city}, "
                f"архетип={profile.archetype_code}, долг={profile.total_debt}."
            ),
            (
                "Уровни доверия/сопротивления: "
                f"trust={profile.trust_level}/10, resistance={profile.resistance_level}/10."
            ),
        ]

        if profile.fears:
            parts.append("Главные страхи: " + ", ".join(str(item) for item in profile.fears[:5]))
        if profile.soft_spot:
            parts.append(f"Мягкая точка: {profile.soft_spot}.")
        if profile.breaking_point:
            parts.append(f"Точка перелома: {profile.breaking_point}.")
        if profile.hidden_objections:
            parts.append(
                "Скрытые возражения: "
                + ", ".join(str(item) for item in profile.hidden_objections[:5])
            )
        if profile.creditors:
            parts.append(
                "Кредиторы: "
                + json.dumps(profile.creditors[:4], ensure_ascii=False)
            )
        if profile.property_list:
            parts.append(
                "Имущество: "
                + json.dumps(profile.property_list[:4], ensure_ascii=False)
            )
        if profile.income:
            parts.append(
                f"Доход: {profile.income} руб/мес, тип дохода: {profile.income_type or 'unknown'}."
            )

        return parts
