"""TZ-8 P0 #2 — per-session RAG cache for call-mode LLM calls.

Closes the gap audit-call-mode-rag-missing: ``ws/training.py`` builds
``extra_system`` from a dozen sources (scenario, client_profile,
manager_profile, persona_facts, …) but never calls
:func:`app.services.rag_unified.retrieve_all_context`. As a result
the AI-client in a live phone-call sees neither team methodology
playbooks (TZ-8 PR-A..E), nor the manager's auto-wiki, nor the legal
knowledge base. Coach (REST) wired RAG correctly; call mode (WS)
never did.

The naive fix — call ``retrieve_all_context`` on every WS message —
is the wrong shape for two reasons:

  1. **Cost.** A call session emits 30-60 user turns. Four-source
     RAG fanout per turn = 120-240 retrieval queries per call,
     each issuing one embedding lookup + four cosine searches. On a
     pilot of 15 testers running 10 calls/day each that's ~30k
     extra retrievals daily. Most return the same chunks because
     the call topic doesn't shift between the user's "понял" and
     "как лучше сказать?" turns.

  2. **Latency.** Streaming TTS depends on first-token latency
     (the user is on a phone — they hear silence while the LLM
     thinks). Adding ~250-400ms of RAG fanout to every turn
     visibly degrades the UX *exactly* in the surface where it
     hurts most.

This module solves both with a per-session TTL cache stored in
``state`` (the in-memory + Redis-backed session dict that
``ws/training.py`` already threads through every handler).

Public surface
--------------

* :func:`get_call_rag_block` — returns the formatted RAG prompt
  block for the current turn. Cache hit → returns the cached
  string in microseconds; cache miss → fanout + format + cache.
  Failure-mode: returns ``""`` and logs at DEBUG, never raises
  upward (the call must continue even if RAG is down).

Cache shape on ``state``
------------------------

``state["_call_rag_cache"] = {
    "ts": float,            # monotonic timestamp of last refresh
    "prompt": str,          # formatted block (may be empty)
    "team_id": str | None,  # resolved once per session
    "query_sig": str,       # last query's first 60 chars (debug)
}``

The ``team_id`` is resolved once on the first call (one
``SELECT users.team_id`` round-trip) and pinned for the rest of
the session. Re-resolving every turn would defeat the point of the
cache.

Why TTL is config-driven
------------------------

Default 60 seconds is the call-pace sweet spot — methodology
chunks rarely become relevant or irrelevant inside a one-minute
window, and 60s gives the operations team enough room to push a
new playbook and see it picked up by the next call session
without hot-reloading. Operators can tune via
``settings.call_rag_cache_ttl_seconds``.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Config defaults ─────────────────────────────────────────────────────


DEFAULT_TTL_SECONDS = 60.0
"""Cache lifetime per session. Keep aligned with how often a ROP
might push a new playbook + want it visible to in-flight calls.
Operations team overrides via settings.call_rag_cache_ttl_seconds."""


_QUERY_SIG_LEN = 60
"""Debug-only: how many leading characters of the query we stash on
the cache row so a log line tells the operator what query last
triggered a refresh."""


# ── Public API ──────────────────────────────────────────────────────────


async def get_call_rag_block(
    *,
    state: dict[str, Any],
    user_id: uuid.UUID | str,
    query: str,
    db: AsyncSession,
    context_type: str = "training",
    archetype_code: str | None = None,
    emotion_state: str = "cold",
    ttl_seconds: float | None = None,
) -> str:
    """Return the unified RAG prompt block for this turn.

    The block is the output of
    :meth:`UnifiedRAGResult.to_prompt` — already wrapped in
    ``[DATA_START]/[DATA_END]`` markers (TZ-8 §3.6.1) and already
    sanitised (``filter_methodology_context`` /
    ``filter_wiki_context`` ran upstream). Callers can append it
    verbatim to ``extra_system``.

    On cache hit the function is a dictionary lookup. On cache miss
    it issues:
      * one ``SELECT users.team_id`` (only on the very first call
        of the session)
      * one ``retrieve_all_context`` fanout (legal + wiki + methodology
        + personality, each in its own short-lived async session
        per ``rag_unified.py``)

    Failure-mode: any exception is swallowed. The call must
    continue even if RAG is down. Caller gets ``""`` and the
    surrounding ``extra_system`` is built without RAG context.

    Args:
        state: session_state dict from ws/training.py. Used as the
            cache backing store. The function mutates
            ``state["_call_rag_cache"]`` in place.
        user_id: UUID of the manager driving the call. Forwarded to
            ``retrieve_all_context`` for wiki personalisation and
            methodology team-resolution.
        query: latest user (manager) message. Used as the embedding
            query for the four retrievers. Truncated to 500 chars
            inside ``retrieve_all_context``.
        db: AsyncSession. Used only for the one-time
            ``SELECT users.team_id`` lookup. The actual RAG fanout
            opens its own short-lived sessions per
            ``rag_unified.retrieve_all_context``.
        context_type: ``"training"`` / ``"coach"`` / ``"quiz"`` —
            chooses the budget split. Defaults to ``"training"``
            (call mode runs through the training WS path).
        archetype_code: forwarded to personality RAG.
        emotion_state: forwarded to personality RAG.
        ttl_seconds: cache lifetime override. ``None`` =
            :data:`DEFAULT_TTL_SECONDS`. Pass ``0.0`` to bypass the
            cache (used by tests).

    Returns:
        Formatted prompt block ending in a newline, or ``""`` if
        nothing relevant was retrieved or RAG failed.
    """
    ttl = (
        DEFAULT_TTL_SECONDS
        if ttl_seconds is None
        else max(0.0, float(ttl_seconds))
    )
    now = time.monotonic()

    cache = state.get("_call_rag_cache") or {}
    cache_ts = cache.get("ts", 0.0)
    cache_prompt = cache.get("prompt", "")

    # Cache hit — TTL not elapsed.
    if ttl > 0 and (now - cache_ts) < ttl and cache:
        return cache_prompt or ""

    # Resolve team_id once per session. Reuse on subsequent misses.
    team_id = cache.get("team_id_resolved")
    if team_id is False:
        # Sentinel: previous call resolved it as None (manager has
        # no team). Don't keep re-querying.
        team_id_for_call = None
    elif team_id is None:
        # Truly unresolved. Run the lookup once.
        team_id_for_call = await _resolve_team_id(user_id, db)
        # Cache: ``False`` means "looked up, came back None"; UUID
        # means "looked up, found team". Distinct states so we
        # don't re-query on every miss.
        cache["team_id_resolved"] = team_id_for_call or False
    else:
        team_id_for_call = team_id

    # Fanout the four-source RAG. Failures are swallowed — the
    # caller must continue without RAG context, never crash a call.
    try:
        from app.services.rag_unified import retrieve_all_context

        result = await retrieve_all_context(
            query=query,
            user_id=_coerce_uuid(user_id),
            db=db,
            context_type=context_type,
            archetype_code=archetype_code,
            emotion_state=emotion_state,
            team_id=team_id_for_call,
        )
        prompt = result.to_prompt() or ""
    except Exception:
        logger.debug(
            "call_rag_cache: retrieve_all_context failed for session "
            "user %s — proceeding without RAG block",
            user_id, exc_info=True,
        )
        prompt = ""

    # Update the cache regardless of outcome — empty string on
    # failure prevents a thundering-herd of retries on the same
    # turn (the next refresh happens after TTL).
    cache.update(
        {
            "ts": now,
            "prompt": prompt,
            "query_sig": (query or "")[:_QUERY_SIG_LEN],
        }
    )
    state["_call_rag_cache"] = cache

    return prompt


# ── Internals ───────────────────────────────────────────────────────────


async def _resolve_team_id(
    user_id: uuid.UUID | str,
    db: AsyncSession,
) -> uuid.UUID | None:
    """One-shot ``SELECT users.team_id`` mirroring the P0 #1 pattern in
    :func:`app.services.ai_coach.generate_coaching_response`.

    Returns ``None`` for managers without a team — the caller treats
    that as "skip methodology RAG" (see TZ-8 §1: methodology has no
    global fallback). Failure to query also returns ``None`` —
    fail-open so a transient DB hiccup doesn't kill the call.
    """
    try:
        from sqlalchemy import select

        from app.models.user import User

        return (
            await db.execute(
                select(User.team_id).where(User.id == _coerce_uuid(user_id))
            )
        ).scalar_one_or_none()
    except Exception:
        logger.debug(
            "call_rag_cache: team_id lookup failed for user %s "
            "(non-critical, fall through with team_id=None)",
            user_id, exc_info=True,
        )
        return None


def _coerce_uuid(user_id: uuid.UUID | str) -> uuid.UUID:
    """``state["user_id"]`` is sometimes a string (Redis-restored
    sessions) and sometimes a UUID (fresh DB-loaded). Normalise so
    the SELECT and the downstream RAG calls are both happy."""
    if isinstance(user_id, uuid.UUID):
        return user_id
    return uuid.UUID(str(user_id))


def reset_cache(state: dict[str, Any]) -> None:
    """Clear the per-session cache. Useful for tests + for a future
    "playbook hot-reload" notification consumer that wants every
    in-flight call to re-fanout immediately when a ROP saves a new
    chunk."""
    state.pop("_call_rag_cache", None)


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "get_call_rag_block",
    "reset_cache",
]
