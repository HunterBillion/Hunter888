"""Arena lifelines — hint / skip / 50-50.

Sprint 4 (2026-04-20). The three lifelines give players a controlled
escape hatch per match:

  * **hint**  — returns a single RAG-grounded pointer ("Смотри ст. 213.3,
                 абзац 2"). Costs one hint token.
  * **skip**  — mark the current round as skipped (no score + no penalty).
                 Costs one skip token.
  * **fifty** — for multiple-choice rounds, returns two distractor keys
                 to dim. Costs one fifty token.

Quotas per mode:
  arena      — 2 hints, 1 skip,  1 fifty
  duel       — 0 hints, 1 skip,  0 fifty  (pure head-to-head)
  rapid      — 1 hint,  0 skip,  0 fifty  (speed matters)
  pve        — 3 hints, 2 skips, 1 fifty  (practice-friendly)
  tournament — 0 hints, 0 skip,  0 fifty  (no help on the road to glory)

State is kept in Redis under ``lifelines:{session_id}:{user_id}`` with
the match's TTL. Counters only go down; refilling requires a new match.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal, Optional

logger = logging.getLogger(__name__)

Mode = Literal["arena", "duel", "rapid", "pve", "tournament"]


@dataclass(frozen=True)
class LifelineQuota:
    hints: int
    skips: int
    fiftys: int


DEFAULT_QUOTAS: dict[Mode, LifelineQuota] = {
    "arena":      LifelineQuota(hints=2, skips=1, fiftys=1),
    "duel":       LifelineQuota(hints=0, skips=1, fiftys=0),
    "rapid":      LifelineQuota(hints=1, skips=0, fiftys=0),
    "pve":        LifelineQuota(hints=3, skips=2, fiftys=1),
    "tournament": LifelineQuota(hints=0, skips=0, fiftys=0),
}

REDIS_TTL_SECONDS = 60 * 60 * 2  # 2h — longer than any match


def _key(session_id: str, user_id: str) -> str:
    return f"lifelines:{session_id}:{user_id}"


async def init_for_match(
    *, session_id: str, user_id: str, mode: Mode,
) -> LifelineQuota:
    """Create the lifeline counters for this (session, user, mode). Idempotent."""

    quota = DEFAULT_QUOTAS.get(mode, DEFAULT_QUOTAS["arena"])
    try:
        from app.core.redis_pool import get_redis

        r = get_redis()
        key = _key(session_id, user_id)
        # SETNX so re-init doesn't overwrite consumed counters.
        existing = await r.get(key)
        if not existing:
            await r.setex(
                key, REDIS_TTL_SECONDS,
                json.dumps({"hints": quota.hints, "skips": quota.skips, "fiftys": quota.fiftys}),
            )
    except Exception:  # noqa: BLE001 — fail-open
        logger.debug("lifelines.init_for_match redis miss", exc_info=True)
    return quota


async def get_remaining(
    *, session_id: str, user_id: str,
) -> dict[str, int]:
    """Return the remaining counts — all zero on Redis miss / fresh user."""

    try:
        from app.core.redis_pool import get_redis

        r = get_redis()
        raw = await r.get(_key(session_id, user_id))
        if not raw:
            return {"hints": 0, "skips": 0, "fiftys": 0}
        data = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode())
        return {
            "hints": int(data.get("hints", 0)),
            "skips": int(data.get("skips", 0)),
            "fiftys": int(data.get("fiftys", 0)),
        }
    except Exception:
        logger.debug("lifelines.get_remaining redis miss", exc_info=True)
        return {"hints": 0, "skips": 0, "fiftys": 0}


async def consume(
    *, session_id: str, user_id: str, kind: Literal["hint", "skip", "fifty"],
) -> bool:
    """Atomically decrement the counter for ``kind``. Returns True if consumed,
    False if no tokens left (or Redis down)."""

    field = {"hint": "hints", "skip": "skips", "fifty": "fiftys"}[kind]
    try:
        from app.core.redis_pool import get_redis

        r = get_redis()
        key = _key(session_id, user_id)
        raw = await r.get(key)
        if not raw:
            return False
        data = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode())
        if int(data.get(field, 0)) <= 0:
            return False
        data[field] = int(data[field]) - 1
        await r.setex(key, REDIS_TTL_SECONDS, json.dumps(data))
        return True
    except Exception:
        logger.debug("lifelines.consume redis error", exc_info=True)
        return False


# ────────────────────────────────────────────────────────────────────
# Hint generation — pulls the top-1 RAG result and returns a short hint
# ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HintPayload:
    text: str
    article: Optional[str]
    confidence: float


async def generate_hint(*, question_text: str) -> HintPayload:
    """Return a 1-line RAG-grounded hint for the manager.

    Never raises — if RAG is unavailable, returns a generic nudge.
    """

    try:
        from app.services.rag_legal import retrieve_legal_context
        from app.database import async_session

        async with async_session() as db:
            ctx = await retrieve_legal_context(question_text, db, top_k=1)
        if ctx.has_results:
            top = ctx.results[0]
            hint = (
                top.correct_response_hint
                or top.fact_text[:160]
                or "Смотри правовой контекст."
            )
            return HintPayload(
                text=hint[:200],
                article=top.law_article,
                confidence=float(getattr(top, "relevance_score", 0.0) or 0.0),
            )
    except Exception:
        logger.debug("lifelines.generate_hint rag failure", exc_info=True)

    return HintPayload(
        text="Опирайся на 127-ФЗ: статьи 213.3 (порог), 213.4 (заявление), 213.9 (управляющий).",
        article=None,
        confidence=0.0,
    )
