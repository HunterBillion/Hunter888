"""Tier C case generation — full LLM generation with per-user Redis cache.

Produces a QuizCase entirely from LLM output. Each user gets a small pool of
~5 generated cases cached for 7 days (keyed on user_id + complexity). When
router picks Tier C:
  1. Check Redis cache for this user+complexity. If ≥ min_pool, pick random.
  2. Otherwise call LLM → validate JSON → add to pool.

Rate limit: 5 Tier-C generations per user per day (controls LLM cost).
After limit hits, router falls back to Tier B for that user.

Latency: 3-8s on cold generation (Claude Sonnet), ~0ms on cache hit.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
import uuid
from datetime import date
from typing import Literal

from app.services.quiz_v2.cases import QuizCase

logger = logging.getLogger(__name__)

# Redis key patterns
_CACHE_PREFIX = "quiz_v2:tier_c:cache"   # {prefix}:{user_id}:{complexity} → list of cases
_RATE_PREFIX = "quiz_v2:tier_c:rate"     # {prefix}:{user_id}:{YYYY-MM-DD} → count

CACHE_TTL_SECONDS = 7 * 24 * 60 * 60    # 7 days
DAILY_LIMIT = 5
MIN_POOL_FOR_REUSE = 3                   # reuse cached cases once pool has >=3


def _cache_key(user_id: str, complexity: str) -> str:
    return f"{_CACHE_PREFIX}:{user_id}:{complexity}"


def _rate_key(user_id: str) -> str:
    today = date.today().isoformat()
    return f"{_RATE_PREFIX}:{user_id}:{today}"


async def _get_cached_pool(user_id: str, complexity: str) -> list[QuizCase]:
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        raw = await r.get(_cache_key(user_id, complexity))
        if not raw:
            return []
        data = json.loads(raw)
        return [QuizCase.from_redis_json(c) for c in data]
    except Exception as exc:
        logger.warning("quiz_v2.tier_c: cache read failed: %s", exc)
        return []


async def _append_to_cache(user_id: str, complexity: str, case: QuizCase) -> None:
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        key = _cache_key(user_id, complexity)
        raw = await r.get(key)
        pool = json.loads(raw) if raw else []
        pool.append(case.to_redis_json())
        # Cap pool at 10 cases per complexity
        pool = pool[-10:]
        await r.setex(key, CACHE_TTL_SECONDS, json.dumps(pool, ensure_ascii=False))
    except Exception as exc:
        logger.warning("quiz_v2.tier_c: cache write failed: %s", exc)


async def _check_and_increment_rate(user_id: str) -> bool:
    """Atomic increment + check. Returns True if under limit."""
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        key = _rate_key(user_id)
        new_count = await r.incr(key)
        if new_count == 1:
            # First use today — set 24h TTL
            await r.expire(key, 24 * 60 * 60)
        return int(new_count) <= DAILY_LIMIT
    except Exception:
        # Fail-closed: deny if Redis broken (cheaper than unlimited LLM spend)
        return False


async def _llm_generate_case(complexity: str) -> tuple[dict | None, set[str]]:
    """Generate a fresh case JSON via RAG-grounded LLM.

    Returns (parsed_dict_or_None, allowed_articles_set). Second member used
    by the caller to post-validate article references.
    """
    from app.services.llm import generate_response
    from app.services.quiz_v2.rag_grounding import build_rag_grounded_prompt_suffix

    complexity_brief = {
        "simple":       "стандартное добросовестное банкротство физлица (порог, документы, освобождение)",
        "tangled":      "запутанное дело с 1-2 осложнениями (развод, созаёмщик, мошенники, ипотека, фрод)",
        "adversarial":  "сложное дело с оспариванием сделок, субсидиарной ответственностью или попыткой вывода активов",
    }.get(complexity, "стандартное дело")

    # Pull real 127-FZ snippets relevant to this complexity
    rag_suffix, allowed_articles = await build_rag_grounded_prompt_suffix(
        complexity, max_snippets=5, max_chars_per_snippet=280,
    )

    prompt = (
        f"Сгенерируй УНИКАЛЬНЫЙ учебный кейс банкротства физлица по 127-ФЗ.\n"
        f"Тип: {complexity_brief}.\n\n"
        f"Верни СТРОГО JSON (без markdown, без комментариев):\n"
        "{\n"
        '  "debtor_name": "Полное ФИО (рус., реалистичное, не клише)",\n'
        '  "debtor_age": число 28-65,\n'
        '  "debtor_occupation": "род занятий или бывшая профессия",\n'
        '  "debt_amount": число (500000-8000000, кратно 10000),\n'
        '  "creditors": ["Сбер (Х тыс.)", ...] — 2-4 элемента с суммами,\n'
        '  "trigger_event": "причина наступления неплатёжеспособности",\n'
        '  "complicating_factors": ["осложнение 1", ...] — 0 для simple, 1-3 для сложных,\n'
        '  "narrative_hook": "1-2 предложения — суть дела, почему это особый случай",\n'
        '  "expected_beats": {\n'
        '    "intake": ["ключевой факт 1", "..."],\n'
        '    "documents": [...],\n'
        '    "obstacles": [...],\n'
        '    "property": [...],\n'
        '    "outcome": [...]\n'
        "  }\n"
        "}\n\n"
        "КРИТИЧЕСКИ ВАЖНО: в expected_beats и narrative_hook ссылайся ТОЛЬКО "
        "на статьи из «Правового контекста» ниже. НЕ выдумывай номера статей, "
        "которых нет в контексте.\n"
        f"{rag_suffix}"
    )

    try:
        result = await generate_response(
            system_prompt=(
                "Ты эксперт по законодательству о банкротстве РФ (127-ФЗ). "
                "Генерируешь учебные кейсы для тренировки менеджеров, "
                "опираясь СТРОГО на предоставленный правовой контекст."
            ),
            messages=[{"role": "user", "content": prompt}],
            emotion_state="curious",
            task_type="structured",
            prefer_provider="cloud",
        )
        content = result.content.strip()
        # Extract JSON — may be wrapped in markdown
        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
            logger.warning("quiz_v2.tier_c: no JSON in LLM response")
            return None, allowed_articles
        parsed = json.loads(m.group(0))
        # Sanity validate
        required = ("debtor_name", "debtor_age", "debt_amount", "creditors", "trigger_event", "narrative_hook")
        if not all(k in parsed for k in required):
            logger.warning("quiz_v2.tier_c: missing required fields in LLM response")
            return None, allowed_articles
        return parsed, allowed_articles
    except Exception as exc:
        logger.warning("quiz_v2.tier_c: LLM generation failed: %s", exc)
        return None, allowed_articles


async def generate_tier_c_case(
    *,
    user_id: str,
    complexity: Literal["simple", "tangled", "adversarial"],
) -> QuizCase | None:
    """Return a QuizCase at tier C — cache-first, then LLM gen with rate-limit.

    Flow:
      1. Try cache (pool per user+complexity). If pool ≥ MIN_POOL_FOR_REUSE,
         return a random one (30% chance even if we could regenerate).
      2. Otherwise rate-check → LLM generate → cache → return.
      3. On any failure → return None (router falls back to Tier B or A).
    """
    # ── Step 1: cache lookup ───────────────────────────────────────────────
    pool = await _get_cached_pool(user_id, complexity)
    if len(pool) >= MIN_POOL_FOR_REUSE and random.random() < 0.7:
        # 70% reuse from cache when pool is healthy — saves LLM calls
        chosen = random.choice(pool)
        logger.info("quiz_v2.tier_c: cache hit user=%s complexity=%s pool=%d", user_id, complexity, len(pool))
        return chosen

    # ── Step 2: rate check before calling LLM ──────────────────────────────
    if not await _check_and_increment_rate(user_id):
        logger.info("quiz_v2.tier_c: daily rate limit hit for user=%s — fallback to cached pool", user_id)
        if pool:
            return random.choice(pool)
        return None

    # ── Step 3: LLM generation ─────────────────────────────────────────────
    t0 = time.monotonic()
    parsed, allowed_articles = await _llm_generate_case(complexity)
    if parsed is None:
        # Fallback to whatever's in the pool (may be empty — then None)
        if pool:
            return random.choice(pool)
        return None

    # ── Step 3b: anti-hallucination post-validation ────────────────────────
    try:
        from app.services.quiz_v2.rag_grounding import validate_case_articles
        parsed, removed_refs = validate_case_articles(parsed, allowed_articles)
        if removed_refs:
            logger.info(
                "quiz_v2.tier_c: stripped %d fabricated article refs from case: %s",
                len(removed_refs), removed_refs,
            )
    except Exception as _val_exc:
        logger.warning("quiz_v2.tier_c: article validation failed: %s", _val_exc)

    # Normalize + construct QuizCase
    try:
        debt_amount = int(parsed["debt_amount"])
        debt_amount = max(100_000, min(debt_amount, 20_000_000))  # guardrails
        age = int(parsed["debtor_age"])
        age = max(18, min(age, 85))

        case_id = f"C-{complexity[:3]}-{uuid.uuid4().hex[:8]}"
        case = QuizCase(
            case_id=case_id,
            complexity=complexity,
            debtor_name=str(parsed["debtor_name"])[:80],
            debtor_age=age,
            debtor_occupation=str(parsed.get("debtor_occupation", "не указано"))[:80],
            debt_amount=debt_amount,
            creditors=[str(c)[:120] for c in parsed.get("creditors", [])][:6],
            trigger_event=str(parsed["trigger_event"])[:200],
            complicating_factors=[str(f)[:150] for f in parsed.get("complicating_factors", [])][:4],
            narrative_hook=str(parsed["narrative_hook"])[:500],
            expected_beats=parsed.get("expected_beats", {}) if isinstance(parsed.get("expected_beats"), dict) else {},
            source_tier="C",
        )
    except Exception as exc:
        logger.warning("quiz_v2.tier_c: post-processing failed: %s", exc)
        return None

    dt_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "quiz_v2.tier_c: generated user=%s complexity=%s case=%s latency=%dms",
        user_id, complexity, case.case_id, dt_ms,
    )

    # Cache for later reuse
    await _append_to_cache(user_id, complexity, case)

    return case
