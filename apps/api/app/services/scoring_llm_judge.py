"""LLM-as-judge layer over the rule-based scoring engine.

This is a NEW SCORING LAYER that runs ONCE at session-finalize time over the
full transcript and produces a small structured verdict. The verdict nudges
the rule-based score (range [-8, +5]) and surfaces an explainable
Russian-language summary on the results page.

Design notes
------------
* Single-shot: one LLM call per session-finalize, never per-turn.
* Fail-soft: any LLM error → judge contributes 0, rationale becomes
  "оценка LLM-судьи временно недоступна".
* Latency budget: 8s timeout via ``asyncio.wait_for``.
* Cost guard: caller (``scoring.calculate_scores``) skips the judge entirely
  when ``len(user_messages) < 4`` — too short to score meaningfully.
* Cache: per-session Redis cache keyed on
  ``session_id + sha1(transcript)[:12]``, TTL 24h, so re-renders of the
  results page don't re-call the LLM.

The judge does NOT replace any rule-based layer; it only adds a sibling
``judge_score`` term to the final sum in ``scoring.calculate_scores``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# Hard caps on the prompt payload — see module docstring.
_MAX_TURNS = 30
_MAX_CHARS = 8000

# Score nudge envelope. Read by tests.
_SCORE_ADJUST_MIN = -8
_SCORE_ADJUST_MAX = 5

# 8s blocking budget for the judge.
_JUDGE_TIMEOUT_S = 8.0

# Cache TTL — 24h. Same transcript hash means same verdict, no point re-asking.
_CACHE_TTL_S = 86_400

# Russian fail-soft rationale for surface on the results page.
_FAIL_SOFT_RATIONALE = "оценка LLM-судьи временно недоступна"
_PARSE_FAIL_RATIONALE = "не удалось разобрать ответ судьи"


class JudgeFlagItem(BaseModel):
    """A single red_flag with anchor info — P4 (2026-05-04).

    The trainee sees a chip; clicking it scrolls to the cited message
    in the transcript pane and shows ``fix_example`` as a tooltip.
    """

    label: str = Field(..., max_length=80)
    message_index: int = Field(..., ge=-1)  # -1 allowed for generic
    excerpt: str = Field(default="", max_length=120)
    fix_example: str = Field(default="", max_length=200)


class JudgeStrengthItem(BaseModel):
    """A single strength with optional anchor — P4."""

    label: str = Field(..., max_length=80)
    message_index: int = Field(default=-1, ge=-1)
    excerpt: str = Field(default="", max_length=120)


class JudgeVerdict(BaseModel):
    """Structured verdict from the LLM judge.

    Fields are intentionally narrow so the schema can be enforced via
    ``model_validate_json`` without leaving room for the LLM to drift.

    P4 (2026-05-04): ``red_flags`` and ``strengths`` upgraded from
    ``list[str]`` to lists of structured items anchored to the transcript.
    Old-shape verdicts (already cached as list-of-string) are normalised
    on read by ``_normalize_judge_dict`` — backwards-compatible.
    """

    verdict: Literal["excellent", "good", "mixed", "poor", "red_flag"]
    score_adjust: int = Field(..., ge=_SCORE_ADJUST_MIN, le=_SCORE_ADJUST_MAX)
    rationale_ru: str
    red_flags: list[JudgeFlagItem] = Field(default_factory=list)
    strengths: list[JudgeStrengthItem] = Field(default_factory=list)
    model_used: str = ""
    latency_ms: int = 0


def _normalize_judge_dict(raw: dict | None) -> dict | None:
    """Convert legacy list-of-string judge dicts into the P4 anchored shape.

    Sessions stored before P4 have ``red_flags: list[str]`` and
    ``strengths: list[str]``. The FE expects the new object shape. This
    helper is idempotent — it walks the lists and wraps any bare strings
    as ``{label, message_index=-1, excerpt="", fix_example=""}``.

    Returns None when ``raw`` is None so the caller can fall through.
    """
    if not raw or not isinstance(raw, dict):
        return raw

    def _wrap_flag(x: Any) -> dict:
        if isinstance(x, str):
            return {"label": x, "message_index": -1, "excerpt": "", "fix_example": ""}
        if isinstance(x, dict):
            return {
                "label": str(x.get("label") or "")[:80],
                "message_index": int(x.get("message_index", -1)),
                "excerpt": str(x.get("excerpt") or "")[:120],
                "fix_example": str(x.get("fix_example") or "")[:200],
            }
        return {"label": str(x)[:80], "message_index": -1, "excerpt": "", "fix_example": ""}

    def _wrap_strength(x: Any) -> dict:
        if isinstance(x, str):
            return {"label": x, "message_index": -1, "excerpt": ""}
        if isinstance(x, dict):
            return {
                "label": str(x.get("label") or "")[:80],
                "message_index": int(x.get("message_index", -1)),
                "excerpt": str(x.get("excerpt") or "")[:120],
            }
        return {"label": str(x)[:80], "message_index": -1, "excerpt": ""}

    out = dict(raw)
    if "red_flags" in out and isinstance(out["red_flags"], list):
        out["red_flags"] = [_wrap_flag(x) for x in out["red_flags"]]
    if "strengths" in out and isinstance(out["strengths"], list):
        out["strengths"] = [_wrap_strength(x) for x in out["strengths"]]
    return out


def _default_verdict(rationale: str, *, model_used: str = "fallback", latency_ms: int = 0) -> JudgeVerdict:
    """Construct the neutral fallback verdict used on errors / parse failures."""
    return JudgeVerdict(
        verdict="mixed",
        score_adjust=0,
        rationale_ru=rationale,
        red_flags=[],
        strengths=[],
        model_used=model_used,
        latency_ms=latency_ms,
    )


def _format_transcript(
    user_messages: list[str],
    assistant_messages: list[str],
) -> str:
    """Interleave user/assistant turns into a M[i]:/К: transcript, capped.

    P4 (2026-05-04): user turns now carry an INDEX prefix ``M[i]`` so the
    LLM can reference them by index in the structured red_flags/strengths
    output. The index matches the position in ``user_messages`` (0-based).
    Assistant turns stay unindexed — the trainee is the one being judged.

    Keeps the LAST ``_MAX_TURNS`` turns and at most ``_MAX_CHARS`` characters
    (whichever bound is tighter). The cap is taken from the END so the
    closing of the call (where the verdict matters most) is preserved.
    """
    pairs: list[str] = []
    n = max(len(user_messages), len(assistant_messages))
    for i in range(n):
        if i < len(user_messages):
            pairs.append(f"M[{i}]: {user_messages[i]}")
        if i < len(assistant_messages):
            pairs.append(f"К: {assistant_messages[i]}")

    # Cap to last _MAX_TURNS lines.
    if len(pairs) > _MAX_TURNS:
        pairs = pairs[-_MAX_TURNS:]

    transcript = "\n".join(pairs)

    # Cap by chars (preserve the tail).
    if len(transcript) > _MAX_CHARS:
        transcript = transcript[-_MAX_CHARS:]

    return transcript


def _build_user_prompt(
    *,
    transcript: str,
    archetype: str | None,
    emotion_arc: list[str],
    call_outcome: str,
) -> str:
    """Build the Russian-language judge prompt body."""
    arch = archetype or "не указан"
    arc = ", ".join([e for e in emotion_arc if e]) or "не зафиксирована"
    outcome = call_outcome or "unknown"

    return (
        "Контекст звонка:\n"
        f"- Архетип клиента: {arch}\n"
        f"- Эмоциональная дуга: {arc}\n"
        f"- Исход звонка: {outcome}\n\n"
        "Транскрипт (M[i] = i-я реплика менеджера, К = реплика клиента):\n"
        "---\n"
        f"{transcript}\n"
        "---\n\n"
        "Задание: оцени работу менеджера и верни СТРОГО валидный JSON со следующими полями:\n"
        '  "verdict"       — одно из: "excellent", "good", "mixed", "poor", "red_flag"\n'
        f'  "score_adjust"  — целое число в диапазоне [{_SCORE_ADJUST_MIN}, {_SCORE_ADJUST_MAX}]\n'
        '  "rationale_ru"  — 1-2 предложения по-русски, чему равен этот вердикт\n'
        '  "red_flags"     — список ОБЪЕКТОВ. Каждый объект:\n'
        '                       {"label": <короткое название проблемы>,\n'
        '                        "message_index": <индекс из M[i]>,\n'
        '                        "excerpt": <цитата из M[i] до 100 символов>,\n'
        '                        "fix_example": <как лучше было сказать, до 160 символов>}\n'
        '                    Каждый red_flag ОБЯЗАН ссылаться на конкретный M[i].\n'
        '                    Используй -1 в message_index ТОЛЬКО если проблема разлита по всему звонку.\n'
        '  "strengths"     — список ОБЪЕКТОВ. Каждый объект:\n'
        '                       {"label": <короткая похвала>,\n'
        '                        "message_index": <индекс M[i] или -1 если общая>,\n'
        '                        "excerpt": <цитата из M[i] до 100 символов или пустая строка>}\n\n'
        "Пример red_flag:\n"
        '  {"label": "Оскорбление клиента",\n'
        '   "message_index": 4,\n'
        '   "excerpt": "вы что, идиот?",\n'
        '   "fix_example": "Давайте я объясню по-другому, чтобы стало понятно."}\n\n'
        "Никакого текста ВНЕ JSON. Никаких markdown-обёрток. Только сам JSON-объект."
    )


_SYSTEM_PROMPT = (
    "Ты — наставник для менеджера холодных звонков по теме банкротства физических лиц "
    "(127-ФЗ). Ты получаешь полный транскрипт одного звонка и оцениваешь работу менеджера: "
    "выявил ли он потребность, грамотно ли работал с возражениями, не нарушал ли законов и "
    "профессиональной этики, удержал ли клиента до закрытия. Отвечай ТОЛЬКО JSON по "
    "указанной схеме, без пояснений вне JSON."
)


def _strip_code_fence(content: str) -> str:
    """LLMs sometimes wrap JSON in ```json ... ``` despite instructions.

    Strip the fence (and an optional language tag) before parsing.
    """
    s = content.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = s.rstrip("`").strip()
    return s


def _clamp_score_adjust(raw: Any) -> int:
    """Coerce the LLM's reported adjust into the legal int range.

    Out-of-range values are clamped (not rejected) — the verdict is still
    useful even if the LLM tried to over-reward / over-penalise.
    """
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return 0
    return max(_SCORE_ADJUST_MIN, min(_SCORE_ADJUST_MAX, v))


def _clamp_message_index(payload: dict, max_index: int) -> None:
    """In-place clamp `message_index` to [-1, max_index]. P4 guard.

    LLM may hallucinate `message_index=99` when only 5 user messages
    exist. Rather than rejecting the whole verdict, we clamp to -1
    (generic flag) and log so we can dashboard the rate.
    """
    for key in ("red_flags", "strengths"):
        items = payload.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get("message_index", -1))
            except (TypeError, ValueError):
                idx = -1
            if idx < -1 or idx > max_index:
                logger.debug(
                    "judge: clamped %s.message_index %d → -1 (max=%d)",
                    key, idx, max_index,
                )
                item["message_index"] = -1
            else:
                item["message_index"] = idx


def _parse_verdict(
    raw_content: str,
    *,
    model_used: str,
    latency_ms: int,
    user_messages_count: int = 0,
) -> JudgeVerdict:
    """Parse the LLM's reply into a ``JudgeVerdict`` or return the fallback."""
    if not raw_content:
        return _default_verdict(_PARSE_FAIL_RATIONALE, model_used=model_used, latency_ms=latency_ms)

    text = _strip_code_fence(raw_content)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("LLM judge returned non-JSON: %r", text[:200])
        return _default_verdict(_PARSE_FAIL_RATIONALE, model_used=model_used, latency_ms=latency_ms)

    if not isinstance(payload, dict):
        return _default_verdict(_PARSE_FAIL_RATIONALE, model_used=model_used, latency_ms=latency_ms)

    # Pre-clamp score_adjust BEFORE pydantic validation so the LLM's
    # off-by-one doesn't sink the whole verdict.
    if "score_adjust" in payload:
        payload["score_adjust"] = _clamp_score_adjust(payload["score_adjust"])

    payload.setdefault("red_flags", [])
    payload.setdefault("strengths", [])
    payload["model_used"] = model_used
    payload["latency_ms"] = latency_ms

    # P4: normalise legacy list[str] flags + clamp out-of-range indices.
    payload = _normalize_judge_dict(payload) or payload
    if user_messages_count > 0:
        _clamp_message_index(payload, max_index=user_messages_count - 1)

    try:
        return JudgeVerdict.model_validate(payload)
    except ValidationError as e:
        logger.warning("LLM judge JSON failed schema: %s | payload=%r", e, payload)
        return _default_verdict(_PARSE_FAIL_RATIONALE, model_used=model_used, latency_ms=latency_ms)


def _make_cache_key(session_id: str, transcript: str) -> str:
    digest = hashlib.sha1(transcript.encode("utf-8")).hexdigest()[:12]
    return f"scoring:judge:{session_id}:{digest}"


async def _cache_get(redis_client, key: str) -> JudgeVerdict | None:
    if redis_client is None:
        return None
    try:
        raw = await redis_client.get(key)
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return JudgeVerdict.model_validate_json(raw)
    except Exception:
        logger.debug("Judge cache read failed for %s", key, exc_info=True)
        return None


async def _cache_set(redis_client, key: str, verdict: JudgeVerdict) -> None:
    if redis_client is None:
        return
    try:
        await redis_client.set(key, verdict.model_dump_json(), ex=_CACHE_TTL_S)
    except Exception:
        logger.debug("Judge cache write failed for %s", key, exc_info=True)


async def _invoke_llm(transcript_prompt: str) -> tuple[str, str, int]:
    """Call the secondary LLM, return (content, model_used, latency_ms).

    Reuses ``app.services.llm.generate_response`` so we route through the
    same provider chain as everything else. ``task_type="judge"`` and
    ``temperature=0.2`` keep the output deterministic.
    """
    # Lazy import — avoids a heavy import chain at module load and
    # lets tests stub ``generate_response`` via ``monkeypatch.setattr``.
    from app.services.llm import generate_response

    start = time.monotonic()
    response = await generate_response(
        system_prompt=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": transcript_prompt}],
        emotion_state="cold",
        task_type="judge",
        # Prefer local (navy.api / Haiku-class) so we don't burn cloud budget
        # on every session-finalize. The fallback chain handles outages.
        prefer_provider="local",
        temperature=0.2,
        max_tokens=600,
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    content = (response.content if response and response.content else "") or ""
    model_used = (response.model if response and response.model else "unknown") or "unknown"
    return content, model_used, latency_ms


async def judge_transcript(
    *,
    session_id: str,
    user_messages: list[str],
    assistant_messages: list[str],
    archetype: str | None,
    emotion_arc: list[str],
    call_outcome: str,
    redis_client: Any = None,
) -> JudgeVerdict:
    """Run the LLM judge over a full transcript and return a structured verdict.

    Fail-soft contract:
      - Any LLM error / timeout / parse failure → returns a neutral verdict
        with ``score_adjust=0`` and a Russian rationale describing the
        degradation. NEVER raises to the caller.

    Caching:
      - When ``redis_client`` is provided, the verdict is cached under
        ``scoring:judge:{session_id}:{sha1(transcript)[:12]}`` for 24h.
        Re-reads of the results page will hit the cache and skip the LLM.
    """
    transcript = _format_transcript(user_messages, assistant_messages)
    cache_key = _make_cache_key(session_id, transcript)

    cached = await _cache_get(redis_client, cache_key)
    if cached is not None:
        return cached

    user_prompt = _build_user_prompt(
        transcript=transcript,
        archetype=archetype,
        emotion_arc=emotion_arc,
        call_outcome=call_outcome,
    )

    try:
        content, model_used, latency_ms = await asyncio.wait_for(
            _invoke_llm(user_prompt),
            timeout=_JUDGE_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "LLM judge timed out after %.1fs for session %s — fail-soft",
            _JUDGE_TIMEOUT_S, session_id,
        )
        return _default_verdict(_FAIL_SOFT_RATIONALE, model_used="timeout", latency_ms=int(_JUDGE_TIMEOUT_S * 1000))
    except Exception:
        logger.warning("LLM judge call failed for session %s — fail-soft", session_id, exc_info=True)
        return _default_verdict(_FAIL_SOFT_RATIONALE, model_used="error", latency_ms=0)

    verdict = _parse_verdict(
        content,
        model_used=model_used,
        latency_ms=latency_ms,
        user_messages_count=len(user_messages),
    )

    # Cache only successful, non-fallback verdicts so transient errors don't
    # stick for 24h. The two fallback rationales are the only signal of a
    # degraded path.
    if verdict.rationale_ru not in (_FAIL_SOFT_RATIONALE, _PARSE_FAIL_RATIONALE):
        await _cache_set(redis_client, cache_key, verdict)

    return verdict
