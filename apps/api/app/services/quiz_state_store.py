"""Redis-backed persistence for solo-quiz dedup + reconnect resilience.

Without this, `_SoloQuizState` lives only in the WebSocket handler's
process memory. A network blip, a tab reload, or any reconnect spins up a
fresh state — `asked_chunk_ids` empties, the same question can be served
twice in one quiz, the streak resets.

This module persists the *dedup-critical* slice of state per session, so
on WS reconnect we can rehydrate. Full session state (RAG context,
in-flight LLM stream) is intentionally NOT persisted — that's caller-
side and would balloon the payload.

Keys
----
    quiz:state:{session_id}      — JSON blob, TTL 2h
    quiz:question_hashes:{sid}   — Redis SET of sha256 prefixes, TTL 2h

Why two keys: the SET is hot path (`SISMEMBER` per question generation);
the JSON blob is cold path (rehydrate on connect). Splitting avoids
re-serializing the whole state on each new question.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from typing import Any

from app.core.redis_pool import get_redis

logger = logging.getLogger(__name__)

_TTL_SECONDS = 2 * 60 * 60  # 2h — covers a reasonable quiz session
_STATE_KEY = "quiz:state:{sid}"
_HASH_SET_KEY = "quiz:question_hashes:{sid}"

# Normalize question text before hashing so trivial whitespace/case
# variation across LLM regenerations dedups correctly.
_NORMALIZE_RE = re.compile(r"\s+")


def normalize_question(text: str) -> str:
    """Lowercase + collapse whitespace + strip. Stable across LLM jitter."""
    return _NORMALIZE_RE.sub(" ", text.strip().lower())


def question_hash(text: str) -> str:
    """16-char prefix of sha256(normalize(text)). Collision risk is
    cosmetic at this length for a single quiz session (≤50 questions)."""
    return hashlib.sha256(normalize_question(text).encode("utf-8")).hexdigest()[:16]


async def is_question_seen(session_id: uuid.UUID, text: str) -> bool:
    """True if this question text was already served in this session."""
    try:
        r = get_redis()
        return bool(await r.sismember(_HASH_SET_KEY.format(sid=session_id), question_hash(text)))
    except Exception as exc:
        logger.error("quiz_state_store.is_question_seen failed (Redis down?): %s", exc, exc_info=True)
        return False  # Fail-open — better to risk one repeat than to hang generation


async def mark_question_seen(session_id: uuid.UUID, text: str) -> None:
    """Add question to the seen-set. Idempotent."""
    try:
        r = get_redis()
        key = _HASH_SET_KEY.format(sid=session_id)
        pipe = r.pipeline()
        pipe.sadd(key, question_hash(text))
        pipe.expire(key, _TTL_SECONDS)
        await pipe.execute()
    except Exception as exc:
        logger.error(
            "quiz_state_store.mark_question_seen failed (Redis down?): %s",
            exc,
            exc_info=True,
        )


async def save_snapshot(session_id: uuid.UUID, snapshot: dict[str, Any]) -> None:
    """Persist a small state snapshot (counters + last seen). Cheap enough
    to call after every answer; on reconnect we can pick up the streak."""
    try:
        r = get_redis()
        await r.set(
            _STATE_KEY.format(sid=session_id),
            json.dumps(snapshot, default=str),
            ex=_TTL_SECONDS,
        )
    except Exception as exc:
        logger.warning("quiz_state_store.save_snapshot failed: %s", exc)


async def load_snapshot(session_id: uuid.UUID) -> dict[str, Any] | None:
    """Hydrate a previously-saved snapshot, or None if none exists or
    Redis is unreachable. Caller treats absence as 'fresh session'."""
    try:
        r = get_redis()
        raw = await r.get(_STATE_KEY.format(sid=session_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)
    except Exception as exc:
        logger.warning("quiz_state_store.load_snapshot failed: %s", exc)
        return None


async def clear_session(session_id: uuid.UUID) -> None:
    """Remove all session state (called on quiz finish/abandon)."""
    try:
        r = get_redis()
        pipe = r.pipeline()
        pipe.delete(_STATE_KEY.format(sid=session_id))
        pipe.delete(_HASH_SET_KEY.format(sid=session_id))
        await pipe.execute()
    except Exception as exc:
        logger.warning("quiz_state_store.clear_session failed: %s", exc)
