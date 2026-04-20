"""Arena TTS — arcade-voiced question narration for PvP/Duel rounds.

Phase 2.7 (2026-04-19). Users loved the arcade theming of the arena but
complained it was silent — quiz_v2 had audio for its case briefings, but
arena round questions were text-only. This module plugs that gap.

Design goals:
  - **Reuse quiz_v2/voice.py primitives.** Same navy.api OpenAI-compat TTS
    path, same ``_synthesize_navy`` helper — no new provider integration.
  - **Different voice.** Arena voice is snappier than quiz_v2 detective /
    professor. We use the ``shimmer`` voice at 1.05x speed to fit the
    "game show" vibe.
  - **Aggressive cache.** The same question can fire across many arena
    rounds and duels — we key by SHA-1 of the question text so repeats are
    ~free after first synthesis.
  - **Zero latency on miss.** The WS handler must not block waiting for
    TTS; it fires a background task and emits ``pvp.audio_ready`` when the
    audio is actually ready.
  - **Graceful degradation.** Any failure → ``None`` → frontend stays
    silent but functional.

Public API:
  - ``synth_question_audio(round_id, text)`` → ``str | None`` data-URL
  - ``schedule_round_audio(round_id, text, emit)`` — fire-and-forget task
    that calls synth and invokes ``emit(audio_url)`` when done
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# Arcade voice: shimmer is brighter/snappier than the detective/professor
# voices used in quiz_v2. Speed tick above 1.0 keeps the pace up.
_ARENA_VOICE = "shimmer"
_ARENA_SPEED = 1.05

# Cache TTL: long enough to survive an entire tournament. We key by text
# content so identical questions in different rounds share the same cache
# entry — a match can cycle through the same objection bank repeatedly.
_CACHE_TTL_S = 60 * 60 * 24  # 24h
_MAX_TEXT_CHARS = 2500

# Module-level in-process cache as a fallback when Redis is unavailable.
# Bounded so we don't leak memory on long-running dev processes.
_LOCAL_CACHE: dict[str, str] = {}
_LOCAL_CACHE_MAX = 256


def _cache_key(text: str) -> str:
    return "arena_audio:" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:24]


async def _cache_get(key: str) -> Optional[str]:
    try:
        from app.core.redis_pool import get_redis

        r = get_redis()
        data = await r.get(key)
        if data:
            # Redis returns bytes when binary, str for decoded — handle both.
            return data.decode() if isinstance(data, (bytes, bytearray)) else data
    except Exception as exc:  # noqa: BLE001
        logger.debug("arena.audio cache_get redis miss: %s", exc)
    return _LOCAL_CACHE.get(key)


async def _cache_set(key: str, value: str) -> None:
    try:
        from app.core.redis_pool import get_redis

        r = get_redis()
        await r.setex(key, _CACHE_TTL_S, value)
    except Exception as exc:  # noqa: BLE001
        logger.debug("arena.audio cache_set redis miss: %s", exc)
    if len(_LOCAL_CACHE) >= _LOCAL_CACHE_MAX:
        # Naive eviction — drop an arbitrary entry. 256 is enough that this
        # rarely fires in practice.
        _LOCAL_CACHE.pop(next(iter(_LOCAL_CACHE)))
    _LOCAL_CACHE[key] = value


async def synth_question_audio(text: str) -> Optional[str]:
    """Return a data-URL for ``text`` or ``None`` on failure.

    Checks cache first; on miss calls navy.api TTS and stores the result
    before returning.
    """

    from app.config import settings

    if not (settings.navy_tts_enabled and settings.local_llm_api_key):
        return None

    clean = (text or "").strip()
    if not clean:
        return None
    if len(clean) > _MAX_TEXT_CHARS:
        clean = clean[:_MAX_TEXT_CHARS]

    key = _cache_key(clean)
    cached = await _cache_get(key)
    if cached:
        logger.debug("arena.audio cache hit: %s", key)
        return cached

    try:
        from app.services.tts import _synthesize_navy

        audio_bytes = await _synthesize_navy(
            clean, voice=_ARENA_VOICE, speed=_ARENA_SPEED,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("arena.audio synth failed: %s", exc)
        return None

    if not audio_bytes or len(audio_bytes) < 200:
        return None

    b64 = base64.b64encode(audio_bytes).decode("ascii")
    url = f"data:audio/mpeg;base64,{b64}"
    try:
        await _cache_set(key, url)
    except Exception:  # noqa: BLE001
        pass

    logger.info(
        "arena.audio synthesized: chars=%d bytes=%d key=%s",
        len(clean), len(audio_bytes), key,
    )
    return url


def schedule_round_audio(
    *,
    round_id: str,
    text: str,
    emit: Callable[[dict], Awaitable[None]],
) -> asyncio.Task:
    """Fire-and-forget: synth audio and call ``emit({round_id, audio_url})``.

    Returning the Task lets caller keep a reference (so it isn't GC'd mid-
    flight, a subtle trap with ``asyncio.create_task``).
    """

    async def _run() -> None:
        try:
            audio_url = await synth_question_audio(text)
            if audio_url:
                await emit({"round_id": round_id, "audio_url": audio_url})
        except Exception:  # noqa: BLE001
            logger.exception("arena.audio schedule_round_audio failed")

    return asyncio.create_task(_run())
