"""Character emotion engine with Redis-backed state management.

States: cold -> warming -> open
Transitions depend on manager's communication quality.
Emotion state and timeline are stored in Redis per session for fast access.
"""

import json
import logging
import time
import uuid

import redis.asyncio as aioredis

from app.config import settings
from app.models.character import EmotionState

logger = logging.getLogger(__name__)

TRANSITIONS = {
    EmotionState.cold: {
        "good_response": EmotionState.warming,
        "bad_response": EmotionState.cold,
    },
    EmotionState.warming: {
        "good_response": EmotionState.open,
        "bad_response": EmotionState.cold,
    },
    EmotionState.open: {
        "good_response": EmotionState.open,
        "bad_response": EmotionState.warming,
    },
}

# Redis key patterns
_EMOTION_KEY = "session:{session_id}:emotion"
_TIMELINE_KEY = "session:{session_id}:emotion_timeline"
_KEY_TTL = 3600  # 1 hour TTL for session emotion data


def _redis() -> aioredis.Redis:
    """Create a Redis client from settings."""
    return aioredis.from_url(settings.redis_url, decode_responses=True)


def get_next_emotion(current: EmotionState, response_quality: str) -> EmotionState:
    """Compute the next emotion state given current state and response quality."""
    return TRANSITIONS.get(current, {}).get(response_quality, current)


async def get_emotion(session_id: uuid.UUID) -> EmotionState:
    """Get the current emotion state for a session from Redis.

    Returns EmotionState.cold as default if not found.
    """
    r = _redis()
    try:
        key = _EMOTION_KEY.format(session_id=session_id)
        value = await r.get(key)
        if value is None:
            return EmotionState.cold
        return EmotionState(value)
    except Exception:
        logger.warning("Failed to get emotion from Redis for session %s", session_id)
        return EmotionState.cold
    finally:
        await r.aclose()


async def set_emotion(session_id: uuid.UUID, state: EmotionState) -> None:
    """Set the current emotion state for a session in Redis and append to timeline."""
    r = _redis()
    try:
        key = _EMOTION_KEY.format(session_id=session_id)
        timeline_key = _TIMELINE_KEY.format(session_id=session_id)

        pipe = r.pipeline()
        pipe.set(key, state.value, ex=_KEY_TTL)

        # Append to emotion timeline
        entry = json.dumps({
            "state": state.value,
            "timestamp": time.time(),
        })
        pipe.rpush(timeline_key, entry)
        pipe.expire(timeline_key, _KEY_TTL)

        await pipe.execute()
    except Exception:
        logger.warning("Failed to set emotion in Redis for session %s", session_id)
    finally:
        await r.aclose()


async def get_emotion_timeline(session_id: uuid.UUID) -> list[dict]:
    """Get the full emotion timeline for a session.

    Returns a list of {"state": str, "timestamp": float} entries.
    """
    r = _redis()
    try:
        key = _TIMELINE_KEY.format(session_id=session_id)
        raw_entries = await r.lrange(key, 0, -1)
        return [json.loads(entry) for entry in raw_entries]
    except Exception:
        logger.warning("Failed to get emotion timeline from Redis for session %s", session_id)
        return []
    finally:
        await r.aclose()


async def init_emotion(session_id: uuid.UUID, initial_state: EmotionState) -> None:
    """Initialize emotion state for a new session."""
    await set_emotion(session_id, initial_state)


async def transition_emotion(
    session_id: uuid.UUID,
    response_quality: str,
) -> EmotionState:
    """Transition emotion based on response quality and persist to Redis.

    Args:
        session_id: The training session ID.
        response_quality: "good_response" or "bad_response".

    Returns:
        The new emotion state after transition.
    """
    current = await get_emotion(session_id)
    new_state = get_next_emotion(current, response_quality)
    if new_state != current:
        await set_emotion(session_id, new_state)
    return new_state


async def cleanup_emotion(session_id: uuid.UUID) -> list[dict]:
    """Clean up emotion data from Redis for a finished session.

    Returns the timeline before deletion (for persisting to DB).
    """
    timeline = await get_emotion_timeline(session_id)

    r = _redis()
    try:
        key = _EMOTION_KEY.format(session_id=session_id)
        timeline_key = _TIMELINE_KEY.format(session_id=session_id)
        await r.delete(key, timeline_key)
    except Exception:
        logger.warning("Failed to cleanup emotion in Redis for session %s", session_id)
    finally:
        await r.aclose()

    return timeline
