"""LLM-backed grader for morning warm-up answers.

Uses the navy.api gateway (OpenAI-compatible, see .env: LOCAL_LLM_URL /
LOCAL_LLM_API_KEY) with model gpt-5.4.

Contract:
    grade(question, user_answer, hint) -> WarmupGrade | None

Returns None on any failure (network, parse, rate-limit) — callers are
EXPECTED to fall back to the keyword-match heuristic that ships with
`morning_drill.py`. This service is a PURE enhancement: if navy is down,
the warm-up still works, just with a cheaper signal.

Caching: results are cached in Redis under
    warmup:grade:v1:{sha1(model|question_id|normalized_answer)}
with a 7-day TTL. The same (question, answer) pair — even with different
users — always gets the same grade, which is the entire point.

Token budget: system prompt ~180 tokens, payload ~60, response capped at
150 tokens → ~400 tokens per call. With the 5-question warm-up that's
~2K tokens/day/user. Cheap.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Model name as configured by the user (gpt-5.4 via navy.api). We avoid
# hardcoding this into callers so swapping models is a one-line change.
WARMUP_GRADER_MODEL = "gpt-5.4"

# Redis key prefix / TTL for cache.
_CACHE_PREFIX = "warmup:grade:v1:"
_CACHE_TTL_SECONDS = 7 * 24 * 3600

# Whole-request timeout (navy.api normally responds in 1-3s).
_REQUEST_TIMEOUT = 12.0

# System prompt — trainer-style, strict JSON output.
_SYSTEM_PROMPT = (
    "Ты — строгий, но доброжелательный тренер по банкротству физлиц (ФЗ-127) "
    "и навыкам продаж. Тебе дают вопрос разминки, эталон (ожидаемый смысл) и "
    "ответ обучающегося. Оцени ответ по смыслу (не по словам). Учитывай "
    "сокращённую форму: это РАЗМИНКА, а не экзамен. Верни строго JSON без "
    "комментариев и без markdown:\n"
    '{"score":0..100,"ok":true|false,"covered":[<что раскрыто>],'
    '"missed":[<что упущено>],"feedback":"<1-2 фразы практической подсказки>"}'
)


@dataclass(frozen=True)
class WarmupGrade:
    score: int             # 0..100
    ok: bool               # True when score >= 60 (tunable inside grader)
    covered: list[str]
    missed: list[str]
    feedback: str
    model: str = WARMUP_GRADER_MODEL
    cached: bool = False


# ── helpers ──────────────────────────────────────────────────────────────


def _normalize_answer(answer: str) -> str:
    """Collapse whitespace and lowercase so cache keys are stable."""
    return re.sub(r"\s+", " ", answer.strip().lower())


def _cache_key(question_id: str, answer: str, model: str = WARMUP_GRADER_MODEL) -> str:
    raw = f"{model}|{question_id}|{_normalize_answer(answer)}"
    return _CACHE_PREFIX + hashlib.sha1(raw.encode("utf-8")).hexdigest()


async def _redis_get(key: str) -> str | None:
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        val = await r.get(key)
        if isinstance(val, bytes):
            return val.decode("utf-8")
        return val
    except Exception as e:  # redis down — just skip cache
        logger.debug("warmup_grader cache get skipped: %s", e)
        return None


async def _redis_set(key: str, payload: str) -> None:
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        await r.set(key, payload, ex=_CACHE_TTL_SECONDS)
    except Exception as e:
        logger.debug("warmup_grader cache set skipped: %s", e)


def _parse_llm_json(raw: str) -> dict[str, Any] | None:
    """Strict JSON first, then best-effort substring extraction."""
    text = raw.strip()
    # Strip ```json fences if the model adds them despite instructions.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _coerce(data: dict[str, Any]) -> WarmupGrade | None:
    try:
        score_raw = data.get("score", 0)
        try:
            score = int(float(score_raw))
        except (TypeError, ValueError):
            score = 0
        score = max(0, min(100, score))
        ok = bool(data.get("ok", score >= 60))
        covered = [str(x) for x in (data.get("covered") or []) if str(x).strip()]
        missed = [str(x) for x in (data.get("missed") or []) if str(x).strip()]
        feedback = str(data.get("feedback") or "").strip()
        return WarmupGrade(
            score=score,
            ok=ok,
            covered=covered[:6],
            missed=missed[:6],
            feedback=feedback[:400],
        )
    except Exception as e:
        logger.warning("warmup_grader coerce failed: %s", e)
        return None


# ── public API ───────────────────────────────────────────────────────────


async def grade(
    question_id: str,
    question_text: str,
    user_answer: str,
    hint: str | None,
    law_article: str | None = None,
    kind: str = "legal",
) -> WarmupGrade | None:
    """Grade a single warm-up answer. Returns None on any failure."""
    answer = (user_answer or "").strip()
    if not answer:
        return None
    if not settings.local_llm_api_key or not settings.local_llm_url:
        return None  # navy not configured — caller falls back to heuristic

    # 1) Cache lookup.
    key = _cache_key(question_id, answer)
    cached = await _redis_get(key)
    if cached:
        data = _parse_llm_json(cached)
        grade_obj = _coerce(data) if data else None
        if grade_obj:
            return WarmupGrade(
                score=grade_obj.score,
                ok=grade_obj.ok,
                covered=grade_obj.covered,
                missed=grade_obj.missed,
                feedback=grade_obj.feedback,
                model=grade_obj.model,
                cached=True,
            )

    # 2) Build messages.
    user_payload_lines = [
        f"ВОПРОС: {question_text}",
        f"ТИП: {kind}",
    ]
    if law_article:
        user_payload_lines.append(f"СТАТЬЯ: {law_article}")
    if hint:
        user_payload_lines.append(f"ЭТАЛОН: {hint}")
    user_payload_lines.append(f"ОТВЕТ ОБУЧАЮЩЕГОСЯ: {answer}")
    user_payload = "\n".join(user_payload_lines)

    url = settings.local_llm_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.local_llm_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": WARMUP_GRADER_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_payload},
        ],
        "temperature": 0.2,
        "max_tokens": 220,
        "response_format": {"type": "json_object"},
    }

    # 3) Call navy.
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=body)
    except (httpx.TimeoutException, httpx.HTTPError) as e:
        logger.info("warmup_grader network error: %s", e)
        return None

    if resp.status_code >= 400:
        # 429 / 5xx — don't poison the cache. Caller uses heuristic.
        logger.info("warmup_grader upstream %d: %s", resp.status_code, resp.text[:200])
        return None

    try:
        body_json = resp.json()
        raw_content = body_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        logger.warning("warmup_grader malformed response: %s", e)
        return None

    data = _parse_llm_json(raw_content)
    if not data:
        logger.warning("warmup_grader non-JSON content: %r", raw_content[:200])
        return None

    grade_obj = _coerce(data)
    if not grade_obj:
        return None

    # 4) Cache raw JSON (compact) for 7 days.
    try:
        await _redis_set(
            key,
            json.dumps(
                {
                    "score": grade_obj.score,
                    "ok": grade_obj.ok,
                    "covered": grade_obj.covered,
                    "missed": grade_obj.missed,
                    "feedback": grade_obj.feedback,
                },
                ensure_ascii=False,
            ),
        )
    except Exception as e:
        logger.debug("warmup_grader cache write failed: %s", e)

    return grade_obj
