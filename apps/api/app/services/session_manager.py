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
from app.core.redis_pool import get_redis as _redis
from app.models.character import EmotionState
from app.models.training import Message, MessageRole, SessionStatus, TrainingSession
from app.services.emotion import cleanup_emotion, init_emotion

logger = logging.getLogger(__name__)

# Redis key patterns
_SESSION_KEY = "session:{session_id}:state"
_MESSAGES_KEY = "session:{session_id}:messages"
_KEY_TTL = 7200  # 2 hours (allows session resume after network drops)


class SessionError(Exception):
    """Base error for session operations."""


class RateLimitError(SessionError):
    """User has exceeded their daily session or per-session message limit."""


class SessionNotFoundError(SessionError):
    """Session does not exist or is not active."""


async def check_rate_limit(user_id: uuid.UUID, db: AsyncSession) -> None:
    """Check if the user can start a new session today.

    Uses Redis atomic INCR with daily TTL to prevent TOCTOU race conditions
    where two concurrent requests both pass the DB count check.
    Falls back to DB count if Redis is unavailable.

    Raises RateLimitError if they've exceeded max_sessions_per_day.
    """
    limit = settings.max_sessions_per_day

    # ── Primary: atomic Redis counter (race-safe) ──
    r = _redis()
    try:
        day_key = f"rate:sessions:{user_id}:{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        current = await r.incr(day_key)
        if current == 1:
            # First session today — set TTL to expire at end of UTC day
            await r.expire(day_key, 86400)
        if current > limit:
            raise RateLimitError(
                f"Daily session limit reached ({limit}). Try again tomorrow."
            )
        return  # Under limit
    except RateLimitError:
        raise
    except Exception:
        logger.warning("Redis rate limit check failed for user %s, falling back to DB", user_id)

    # ── Fallback: DB count (still has TOCTOU window but better than nothing) ──
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(TrainingSession.id)).where(
            TrainingSession.user_id == user_id,
            TrainingSession.started_at >= day_start,
        )
    )
    count = result.scalar() or 0
    if count >= limit:
        raise RateLimitError(
            f"Daily session limit reached ({limit}). Try again tomorrow."
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

    # Initialize Redis state — required for WS to find the session.
    # BUG-8 fix: if Redis init fails, expunge session from DB to prevent
    # orphaned DB records that WS reconnect can't find in Redis.
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
        logger.error("Failed to init Redis state for session %s — rolling back DB", session.id)
        await db.rollback()
        raise RuntimeError("Cannot start session: Redis unavailable")

    # Initialize emotion in Redis
    try:
        await init_emotion(session.id, initial_emotion)
    except Exception:
        logger.warning("Failed to init emotion for session %s (non-critical)", session.id)

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
    """Update last_activity timestamp in Redis atomically via Lua script.

    Previous implementation used GET → modify → SET which is a race condition
    under concurrent WebSocket messages.
    """
    r = _redis()
    try:
        key = _SESSION_KEY.format(session_id=session_id)
        # Atomic Lua: decode JSON, update field, re-encode, reset TTL
        lua = """
        local raw = redis.call('GET', KEYS[1])
        if not raw then return 0 end
        local state = cjson.decode(raw)
        state['last_activity'] = tonumber(ARGV[1])
        redis.call('SET', KEYS[1], cjson.encode(state), 'EX', tonumber(ARGV[2]))
        return 1
        """
        await r.eval(lua, 1, key, str(time.time()), str(_KEY_TTL))
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
    """Atomically check if the session has reached its message limit.

    Uses Redis INCR for atomic check-and-reserve: increments a shadow counter
    and checks if it exceeds the limit. If over, decrements back.
    This prevents the TOCTOU race where two concurrent messages both pass the check.

    Raises RateLimitError if limit exceeded.
    """
    r = _redis()
    limit = settings.max_messages_per_session
    shadow_key = f"session:{session_id}:msg_limit_guard"
    try:
        current = await r.incr(shadow_key)
        if current == 1:
            await r.expire(shadow_key, _KEY_TTL)
        if current > limit:
            await r.decr(shadow_key)  # Release the slot
            raise RateLimitError(
                f"Message limit reached ({limit} per session)"
            )
        # Under limit — slot reserved
        return
    except RateLimitError:
        raise
    except Exception:
        logger.warning("Redis msg limit check failed for %s, falling back to state check", session_id)

    # Fallback: non-atomic check from session state (still has TOCTOU window)
    state = await get_session_state(session_id)
    if state is None:
        raise SessionNotFoundError(f"Session {session_id} not found in Redis")
    msg_count = state.get("message_count", 0)
    if msg_count >= limit:
        raise RateLimitError(
            f"Message limit reached ({limit} per session)"
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

    # Refresh TTL on all session keys to prevent expiry during active sessions
    await refresh_session_ttl(session_id)

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


async def refresh_session_ttl(session_id: uuid.UUID) -> None:
    """Refresh TTL on all Redis keys for a session (call on add_message, resume, etc.)."""
    r = _redis()
    try:
        keys = [
            _SESSION_KEY.format(session_id=session_id),
            _MESSAGES_KEY.format(session_id=session_id),
            f"session:{session_id}:msg_count",
            f"session:{session_id}:emotion",
            f"session:{session_id}:emotion_timeline",
            f"session:{session_id}:mood_buffer",
            f"session:{session_id}:interaction_memory",
            f"session:{session_id}:fake_transition",
            f"session:{session_id}:message_index",
        ]
        pipe = r.pipeline()
        for key in keys:
            pipe.expire(key, _KEY_TTL)
        await pipe.execute()
    except Exception:
        logger.warning("Failed to refresh TTL for session %s", session_id)


async def get_message_history_db(
    session_id: uuid.UUID, db: AsyncSession
) -> list[dict]:
    """Fallback: get message history from PostgreSQL when Redis is empty."""
    try:
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.sequence_number.asc())
        )
        messages = result.scalars().all()
        return [
            {
                "role": msg.role.value,
                "content": msg.content,
                "emotion_state": msg.emotion_state,
                "sequence_number": msg.sequence_number,
                "timestamp": msg.created_at.timestamp() if msg.created_at else 0,
            }
            for msg in messages
        ]
    except Exception:
        logger.warning("Failed to get message history from DB for session %s", session_id)
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

    # ── Idempotency guard: prevent double-end corruption ──
    # If session is already finalized (completed/abandoned/error), return as-is.
    # This prevents watchdog + main handler racing to end the same session.
    if session.status != SessionStatus.active:
        logger.warning(
            "end_session called on non-active session %s (status=%s), skipping",
            session_id, session.status.value if hasattr(session.status, 'value') else session.status,
        )
        return session

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

    # ── Cleanup ALL Redis keys for this session ──
    # Previously only deleted 2 keys — left 7+ orphaned keys per session
    # which caused unbounded Redis memory growth in production.
    r = _redis()
    try:
        keys_to_delete = [
            _SESSION_KEY.format(session_id=session_id),
            _MESSAGES_KEY.format(session_id=session_id),
            f"session:{session_id}:msg_count",
            f"session:{session_id}:emotion",
            f"session:{session_id}:emotion_timeline",
            f"session:{session_id}:mood_buffer",
            f"session:{session_id}:interaction_memory",
            f"session:{session_id}:fake_transition",
            f"session:{session_id}:message_index",
            f"session:{session_id}:msg_limit_guard",
        ]
        await r.delete(*keys_to_delete)
        # Also clean up trigger_counter:* keys via scan
        cursor = 0
        pattern = f"session:{session_id}:trigger_counter:*"
        while True:
            cursor, keys = await r.scan(cursor, match=pattern, count=200)
            if keys:
                await r.delete(*keys)
            if cursor == 0:
                break
    except Exception:
        logger.warning("Failed to cleanup Redis for session %s", session_id)

    return session
