"""Session manager: create, track, and finalize training sessions.

Responsibilities:
- Start session: create in DB + Redis
- Store message history in Redis (fast access) + PostgreSQL (persistence)
- Track session state: active messages count, duration, emotion timeline
- End session: calculate duration, cleanup Redis, update DB
- Rate limiting: max N sessions/day per user, max N messages/session
"""

import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.character import EmotionState
from app.models.training import Message, MessageRole, SessionStatus, TrainingSession
from app.services.emotion import cleanup_emotion, init_emotion

logger = logging.getLogger(__name__)

# Redis key patterns
_SESSION_KEY = "session:{session_id}:state"
_MESSAGES_KEY = "session:{session_id}:messages"
_KEY_TTL = 3600  # 1 hour


class SessionError(Exception):
    """Base error for session operations."""


class RateLimitError(SessionError):
    """User has exceeded their daily session or per-session message limit."""


class SessionNotFoundError(SessionError):
    """Session does not exist or is not active."""


import asyncio as _asyncio

_pool: aioredis.ConnectionPool | None = None
_pool_lock = _asyncio.Lock()


async def _ensure_pool() -> aioredis.ConnectionPool:
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                _pool = aioredis.ConnectionPool.from_url(
                    settings.redis_url, decode_responses=True, max_connections=20
                )
    return _pool


def _redis() -> aioredis.Redis:
    """Get a Redis client using a shared connection pool.

    Note: call _ensure_pool() at startup or first use to initialize safely.
    """
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(
            settings.redis_url, decode_responses=True, max_connections=20
        )
    return aioredis.Redis(connection_pool=_pool)


async def check_rate_limit(user_id: uuid.UUID, db: AsyncSession) -> None:
    """Check if the user can start a new session today.

    Raises RateLimitError if they've exceeded max_sessions_per_day.
    """
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(TrainingSession.id)).where(
            TrainingSession.user_id == user_id,
            TrainingSession.started_at >= day_start,
        )
    )
    count = result.scalar() or 0
    if count >= settings.max_sessions_per_day:
        raise RateLimitError(
            f"Daily session limit reached ({settings.max_sessions_per_day}). Try again tomorrow."
        )


async def start_session(
    user_id: uuid.UUID,
    scenario_id: uuid.UUID,
    initial_emotion: EmotionState,
    db: AsyncSession,
) -> TrainingSession:
    """Create a new training session in DB and initialize Redis state.

    Args:
        user_id: The user starting the session.
        scenario_id: The scenario being trained.
        initial_emotion: Starting emotion state from character config.
        db: Database session.

    Returns:
        The created TrainingSession ORM object.

    Raises:
        RateLimitError: If daily session limit exceeded.
    """
    await check_rate_limit(user_id, db)

    session = TrainingSession(
        user_id=user_id,
        scenario_id=scenario_id,
        status=SessionStatus.active,
    )
    db.add(session)
    await db.flush()

    # Initialize Redis state
    r = _redis()
    try:
        state_key = _SESSION_KEY.format(session_id=session.id)
        state = {
            "user_id": str(user_id),
            "scenario_id": str(scenario_id),
            "status": "active",
            "started_at": time.time(),
            "message_count": 0,
            "last_activity": time.time(),
        }
        await r.set(state_key, json.dumps(state), ex=_KEY_TTL)
    except Exception:
        logger.warning("Failed to init Redis state for session %s", session.id)

    # Initialize emotion in Redis
    await init_emotion(session.id, initial_emotion)

    return session


async def get_session_state(session_id: uuid.UUID) -> dict | None:
    """Get session state from Redis. Returns None if not found."""
    r = _redis()
    try:
        key = _SESSION_KEY.format(session_id=session_id)
        raw = await r.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        logger.warning("Failed to get session state from Redis for %s", session_id)
        return None


async def update_activity(session_id: uuid.UUID) -> None:
    """Update last_activity timestamp in Redis (for silence detection)."""
    r = _redis()
    try:
        key = _SESSION_KEY.format(session_id=session_id)
        raw = await r.get(key)
        if raw:
            state = json.loads(raw)
            state["last_activity"] = time.time()
            await r.set(key, json.dumps(state), ex=_KEY_TTL)
    except Exception:
        logger.warning("Failed to update activity for session %s", session_id)


async def check_silence_timeout(session_id: uuid.UUID, timeout_sec: int = 30) -> bool:
    """Check if the session has been silent for longer than timeout_sec.

    Returns True if timed out (no activity for > timeout_sec).
    """
    state = await get_session_state(session_id)
    if state is None:
        return True
    last_activity = state.get("last_activity", 0)
    return (time.time() - last_activity) > timeout_sec


async def get_last_activity_time(session_id: uuid.UUID) -> float | None:
    """Get the last activity timestamp for a session from Redis."""
    state = await get_session_state(session_id)
    if state is None:
        return None
    return state.get("last_activity")


async def check_message_limit(session_id: uuid.UUID) -> None:
    """Check if the session has reached its message limit.

    Raises RateLimitError if limit exceeded.
    """
    state = await get_session_state(session_id)
    if state is None:
        raise SessionNotFoundError(f"Session {session_id} not found in Redis")
    msg_count = state.get("message_count", 0)
    if msg_count >= settings.max_messages_per_session:
        raise RateLimitError(
            f"Message limit reached ({settings.max_messages_per_session} per session)"
        )


async def add_message(
    session_id: uuid.UUID,
    role: MessageRole,
    content: str,
    db: AsyncSession,
    *,
    audio_duration_ms: int | None = None,
    stt_confidence: float | None = None,
    emotion_state: str | None = None,
    llm_model: str | None = None,
    llm_latency_ms: int | None = None,
) -> Message:
    """Add a message to both Redis (for fast access) and PostgreSQL (persistence).

    Also increments the session message counter and updates last_activity.
    """
    # Atomic message counter via Redis INCR (prevents race conditions)
    r = _redis()
    counter_key = f"session:{session_id}:msg_count"
    try:
        seq = await r.incr(counter_key)
        await r.expire(counter_key, _KEY_TTL)
        # Update last_activity in session state
        state_key = _SESSION_KEY.format(session_id=session_id)
        raw = await r.get(state_key)
        if raw:
            state = json.loads(raw)
            state["message_count"] = seq
            state["last_activity"] = time.time()
            await r.set(state_key, json.dumps(state), ex=_KEY_TTL)
    except Exception:
        logger.warning("Failed to update message count in Redis for session %s", session_id)
        seq = 1

    # Save to DB
    msg = Message(
        session_id=session_id,
        role=role,
        content=content,
        audio_duration_ms=audio_duration_ms,
        stt_confidence=stt_confidence,
        emotion_state=emotion_state,
        sequence_number=seq,
        llm_model=llm_model,
        llm_latency_ms=llm_latency_ms,
    )
    db.add(msg)
    await db.flush()

    # Cache message in Redis for fast history retrieval
    r2 = _redis()
    try:
        messages_key = _MESSAGES_KEY.format(session_id=session_id)
        entry = json.dumps({
            "role": role.value,
            "content": content,
            "emotion_state": emotion_state,
            "sequence_number": seq,
            "timestamp": time.time(),
        })
        pipe = r2.pipeline()
        pipe.rpush(messages_key, entry)
        pipe.expire(messages_key, _KEY_TTL)
        await pipe.execute()
    except Exception:
        logger.warning("Failed to cache message in Redis for session %s", session_id)

    return msg


async def get_message_history(session_id: uuid.UUID) -> list[dict]:
    """Get message history from Redis (fast path).

    Returns list of {"role": str, "content": str, ...} dicts.
    """
    r = _redis()
    try:
        key = _MESSAGES_KEY.format(session_id=session_id)
        raw_entries = await r.lrange(key, 0, -1)
        return [json.loads(entry) for entry in raw_entries]
    except Exception:
        logger.warning("Failed to get message history from Redis for session %s", session_id)
        return []


async def end_session(
    session_id: uuid.UUID,
    db: AsyncSession,
    *,
    status: SessionStatus = SessionStatus.completed,
) -> TrainingSession | None:
    """Finalize a training session.

    - Calculate duration
    - Retrieve and persist emotion timeline
    - Clean up Redis data
    - Update DB record
    """
    # Get the DB session record
    result = await db.execute(
        select(TrainingSession).where(TrainingSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        logger.error("Session %s not found in DB during end_session", session_id)
        return None

    # Calculate duration
    now = datetime.now(timezone.utc)
    if session.started_at:
        started = session.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        duration = int((now - started).total_seconds())
    else:
        duration = 0

    # Get emotion timeline before cleanup
    emotion_timeline = await cleanup_emotion(session_id)

    # Update DB
    session.status = status
    session.ended_at = now
    session.duration_seconds = duration
    session.emotion_timeline = emotion_timeline
    db.add(session)

    # Cleanup Redis session state and messages
    r = _redis()
    try:
        state_key = _SESSION_KEY.format(session_id=session_id)
        messages_key = _MESSAGES_KEY.format(session_id=session_id)
        await r.delete(state_key, messages_key)
    except Exception:
        logger.warning("Failed to cleanup Redis for session %s", session_id)

    return session
