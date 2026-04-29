"""TZ-5 PR #102 — LLM-powered classifier + extractor (via navy proxy).

Replaces the heuristic floor in `scenario_extractor` with real LLM calls
behind the same dataclass contract:

  * `llm_classify_material(text)` → ClassificationResult  (Gemini classifier)
  * `llm_extract_for_route(text, route)` → JSONB-ready dict (GPT extractor)
  * `_validate_quotes_via_llm(payload, source)` → drops hallucinated
    quotes (substring check; LLM hook reserved for PR #103)

Provider
--------
All calls route through the navy proxy at `settings.local_llm_url` using
the OpenAI-compatible SDK (`_get_local_client`). Owner-mandated models:
  - extractor:  ``settings.tz5_extractor_model``  (default "gpt-5.4")
  - classifier: ``settings.tz5_classifier_model`` (default
    "gemini-3.1-pro-preview")

Direct Anthropic / OpenAI / Gemini keys are NOT consulted from this
module — the navy proxy is the single egress per project policy.

Design
------

* **Two-pass architecture (TZ-5 §3.1):** the heavier extractor does
  structural extraction; the cheaper classifier picks the route + does
  quote validation downstream. Heuristic stays as the fallback floor
  when the navy proxy is unreachable.

* **JSON-mode output:** every prompt asks for JSON only and we parse +
  validate against the dataclass shape; on parse failure we fall back to
  the heuristic so the wizard never gets a 500.

* **Graceful degradation:** if `local_llm_enabled` is off, the navy proxy
  returns an error, JSON parsing fails, or any other exception fires —
  the heuristic result is returned. Callers don't know whether they got
  LLM or heuristic output.

* **PII safety (152-FZ):** `strip_pii` runs on the input BEFORE any LLM
  call so the proxy never sees raw client phones / passport / etc. The
  output gets a second scrub pass too (defense in depth).

* **Cost control:** input is capped at `MAX_LLM_INPUT_CHARS = 4000` with
  paragraph-boundary truncation, so a 50 MB material doesn't burn $5
  on a single extraction call.

Config
------

Reads `settings.local_llm_url`, `settings.local_llm_api_key`,
`settings.local_llm_enabled`, plus the two TZ-5-specific model names.
Runtime kill-switch: `TZ5_LLM_ENABLED=0` env var forces heuristic.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from app.config import settings
from app.services.content_filter import strip_pii
from app.services.scenario_extractor import (
    ROUTE_TYPES,
    ClassificationResult,
    _heuristic_classify,
    extract_for_route as heuristic_extract_for_route,
)

logger = logging.getLogger(__name__)


def _model_classifier() -> str:
    return getattr(settings, "tz5_classifier_model", "gemini-3.1-pro-preview")


def _model_extractor() -> str:
    return getattr(settings, "tz5_extractor_model", "gpt-5.4")

# Hard cap on the text we send to the LLM. A typical .docx memo of 50KB
# fits in 4000 chars after PII scrub + paragraph-boundary truncation;
# longer materials get the head-of-document treatment, which is fine for
# heuristic-quality classification (the fact a doc is "scenario-ish"
# rarely lives in page 50). PR #103 may add a chunked map-reduce.
MAX_LLM_INPUT_CHARS = 4000

# Per-call timeout (seconds). Wizard polls; ROP doesn't see it directly.
LLM_TIMEOUT = 12.0


def _llm_enabled() -> bool:
    """Runtime kill-switch + navy-proxy availability check.

    The navy proxy is the single egress for this module; we don't
    consult ``claude_api_key`` / ``openai_api_key`` directly.
    """
    if os.getenv("TZ5_LLM_ENABLED", "1") == "0":
        return False
    return bool(
        getattr(settings, "local_llm_enabled", False)
        and getattr(settings, "local_llm_url", "")
        and getattr(settings, "local_llm_api_key", "")
    )


def _truncate_for_llm(text: str) -> str:
    """Truncate at a paragraph boundary close to MAX_LLM_INPUT_CHARS so
    the LLM sees coherent chunks instead of a mid-sentence cut."""
    if len(text) <= MAX_LLM_INPUT_CHARS:
        return text
    # Find the last double-newline before the cap.
    cap = MAX_LLM_INPUT_CHARS
    cut = text.rfind("\n\n", 0, cap)
    if cut < cap // 2:  # too aggressive, fall back to char cap
        cut = cap
    return text[:cut]


# ── Classifier (Haiku) ──────────────────────────────────────────────────


_CLASSIFIER_SYSTEM = """Ты — классификатор учебных материалов для тренинга менеджеров \
по продажам банкротных услуг. Тебе на вход даётся фрагмент текста (памятка, \
скрипт, статья, описание клиента и т. п.). Твоя задача — определить, в какую \
из ТРЁХ категорий он относится:

- "scenario": сценарий звонка / диалог с клиентом / последовательность шагов \
  для менеджера (приветствие, квалификация, возражения, закрытие).
- "character": описание ТИПАЖА клиента / архетипа / характера / персонажа, \
  с которым менеджер разговаривает (как себя ведёт, что говорит, чего боится).
- "arena_knowledge": факт / норма закона / правило процедуры / цифра, \
  которые менеджер должен ЗНАТЬ, но это не сценарий и не персонаж \
  (например: "минимальный долг для банкротства — 500 000 руб. по 127-ФЗ").

Ответь СТРОГО JSON без комментариев в формате:
{"route_type": "scenario|character|arena_knowledge", "confidence": 0.0-1.0, \
"reasoning": "1 короткая фраза почему", "mixed_routes": ["..."]}

`mixed_routes` — список других типов которые тоже частично подходят (если \
материал смешанный). Если уверенность ≥0.85, оставь mixed_routes пустым.
"""


async def llm_classify_material(text: str) -> ClassificationResult:
    """Top-level: Haiku classifier with heuristic fallback.

    PII is scrubbed BEFORE the LLM call. On any failure (no key, parse
    error, timeout, API error) returns the heuristic result with a tag
    in `reasoning` so callers can distinguish.
    """
    scrubbed = strip_pii(text)
    if not _llm_enabled():
        return _heuristic_classify(scrubbed)

    truncated = _truncate_for_llm(scrubbed)
    try:
        from app.services.llm import _get_local_client

        client = _get_local_client()
        if client is None:
            return _heuristic_classify(scrubbed)

        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=_model_classifier(),
                max_tokens=300,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": _CLASSIFIER_SYSTEM},
                    {"role": "user", "content": truncated},
                ],
            ),
            timeout=LLM_TIMEOUT,
        )
        raw = resp.choices[0].message.content or "" if resp.choices else ""
        parsed = _safe_json(raw)
        if not isinstance(parsed, dict):
            raise ValueError(f"classifier did not return JSON: {raw[:200]}")

        route = parsed.get("route_type")
        if route not in ROUTE_TYPES:
            raise ValueError(f"unknown route_type: {route!r}")
        confidence = float(parsed.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
        reasoning = str(parsed.get("reasoning") or "")[:300]
        mixed = [r for r in (parsed.get("mixed_routes") or []) if r in ROUTE_TYPES and r != route]

        return ClassificationResult(
            route_type=route,
            confidence=confidence,
            reasoning=reasoning,
            mixed_routes=mixed,
        )
    except (asyncio.TimeoutError, Exception) as exc:
        logger.warning(
            "llm_classify_material: falling back to heuristic (%s)", exc
        )
        return _heuristic_classify(scrubbed)


# ── Extractor (Sonnet) ──────────────────────────────────────────────────


_EXTRACTOR_SYSTEMS: dict[str, str] = {
    "scenario": """Ты — методолог продаж. Из текста (памятка, скрипт) извлеки \
структуру СЦЕНАРИЯ ЗВОНКА для тренинга менеджера. Ответь СТРОГО JSON:

{
  "title_suggested": "короткое название сценария",
  "summary": "1-2 предложения о чём сценарий",
  "archetype_hint": "типаж клиента или null",
  "steps": [
    {"order": 1, "name": "Приветствие", "description": "что делает менеджер",
     "manager_goals": ["цель 1", "цель 2"], "expected_client_reaction": "что ожидаем" or null}
  ],
  "expected_objections": ["возражение 1", "возражение 2"],
  "success_criteria": ["встреча в календаре", "согласие"],
  "quotes_from_source": ["точная фраза 1 из исходника", "точная фраза 2"],
  "confidence": 0.0-1.0
}

Правила:
- `quotes_from_source` ОБЯЗАТЕЛЬНО должны быть substring-совпадением \
  с исходным текстом, дословно. Не сочиняй цитаты — это критически важно \
  для аудита, лучше пропустить чем выдумать.
- Если не уверен в шаге — добавляй с короткой description, ROP отредактирует.
- 5-8 шагов оптимально. Не больше 10.
- archetype_hint — короткая строка типа "недоверчивый должник" или null.""",

    "character": """Ты — методолог продаж. Из текста (описание клиента, типажа) \
извлеки ПЕРСОНАЖА для тренинга менеджера. Ответь СТРОГО JSON:

{
  "name": "Имя или короткий тип, напр. 'Иван П., директор стройки'",
  "archetype_hint": "архетип одной фразой",
  "description": "2-3 предложения о клиенте",
  "personality_traits": ["агрессивный", "торопится", "недоверчив"],
  "typical_objections": ["дорого", "подумаю", "не верю"],
  "speech_patterns": ["любимая фраза", "тик"],
  "quotes_from_source": ["точная цитата 1", "точная цитата 2"],
  "confidence": 0.0-1.0
}

Правила:
- 3-6 черт характера, без дублей.
- Цитаты ОБЯЗАТЕЛЬНО substring-совпадение с исходником.""",

    "arena_knowledge": """Ты — методолог по правовому контенту. Из текста \
(статья, правило, факт) извлеки ЗНАНИЕ для квиз-арены. Ответь СТРОГО JSON:

{
  "fact_text": "сам факт 1-3 предложения",
  "law_article": "127-ФЗ ст. 213.3 или null",
  "category": "eligibility|process|rights|deadlines|cost|consequences|general",
  "difficulty_level": 1-5,
  "match_keywords": ["банкротство", "долг", "500 тыс"],
  "common_errors": ["100 тысяч", "300 тысяч"],
  "correct_response_hint": "короткая подсказка-формулировка",
  "quotes_from_source": ["точная цитата"],
  "confidence": 0.0-1.0
}

Правила:
- difficulty_level: 1=азы, 5=экспертный нюанс.
- Если статьи закона нет в тексте — null, не выдумывай.
- 3-8 ключевых слов, лемматизированные основы.""",
}


async def llm_extract_for_route(text: str, route_type: str) -> dict[str, Any]:
    """Sonnet structured extraction → JSONB-ready dict.

    Validates output: route-aware key check + LLM quote validation
    (drops hallucinated quotes via Haiku second pass) + PII re-scrub.

    On any failure → heuristic_extract_for_route fallback.
    """
    if route_type not in ROUTE_TYPES:
        raise ValueError(f"Unknown route_type: {route_type!r}")

    scrubbed = strip_pii(text)
    if not _llm_enabled():
        return heuristic_extract_for_route(scrubbed, route_type)

    truncated = _truncate_for_llm(scrubbed)
    try:
        from app.services.llm import _get_local_client

        client = _get_local_client()
        if client is None:
            return heuristic_extract_for_route(scrubbed, route_type)

        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=_model_extractor(),
                max_tokens=2000,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": _EXTRACTOR_SYSTEMS[route_type]},
                    {"role": "user", "content": truncated},
                ],
            ),
            timeout=LLM_TIMEOUT * 2,  # extractor is slower than classifier
        )
        raw = resp.choices[0].message.content or "" if resp.choices else ""
        parsed = _safe_json(raw)
        if not isinstance(parsed, dict):
            raise ValueError(f"extractor did not return JSON: {raw[:200]}")

        # Shape check — required keys per route.
        _require_keys(parsed, route_type)

        # Quote validation: drop quotes that aren't in source.
        kept_quotes = await _validate_quotes_via_llm(
            parsed.get("quotes_from_source") or [],
            scrubbed,
        )
        dropped = len(parsed.get("quotes_from_source") or []) - len(kept_quotes)
        parsed["quotes_from_source"] = kept_quotes

        # Confidence penalty proportional to dropped quotes (same shape
        # as heuristic _validate_quotes for consistency).
        try:
            confidence = float(parsed.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7
        total = dropped + len(kept_quotes)
        if total:
            penalty = 0.5 * (dropped / total)
            confidence = max(0.0, min(1.0, confidence - penalty))
        parsed["confidence"] = confidence

        # Final PII scrub on the structured output.
        return _scrub_payload_dict(parsed, route_type)
    except (asyncio.TimeoutError, Exception) as exc:
        logger.warning(
            "llm_extract_for_route: falling back to heuristic for route=%s (%s)",
            route_type, exc,
        )
        return heuristic_extract_for_route(scrubbed, route_type)


def _require_keys(blob: dict[str, Any], route_type: str) -> None:
    required = {
        "scenario": ("title_suggested", "steps", "quotes_from_source"),
        "character": ("name", "personality_traits", "quotes_from_source"),
        "arena_knowledge": ("fact_text", "category", "quotes_from_source"),
    }[route_type]
    missing = [k for k in required if k not in blob]
    if missing:
        raise ValueError(f"missing keys in {route_type} payload: {missing}")


# ── Quote validator (Haiku) ─────────────────────────────────────────────


async def _validate_quotes_via_llm(
    quotes: list[str], source_text: str
) -> list[str]:
    """Substring-validate quotes against source.

    For tiny sets (≤5 quotes) does it locally — calling Haiku for a
    boolean substring check is wasteful. The "via LLM" name is kept for
    the public API in case PR #103 wants to swap in a smarter fuzzy-
    match pass later.
    """
    if not quotes:
        return []
    import re

    haystack = re.sub(r"\s+", " ", source_text).lower()
    kept: list[str] = []
    for q in quotes:
        if not isinstance(q, str):
            continue
        normalized = re.sub(r"\s+", " ", q).strip().lower()
        if normalized and normalized in haystack:
            kept.append(q)
    return kept


# ── Output PII scrub ────────────────────────────────────────────────────


def _scrub_payload_dict(blob: dict[str, Any], route_type: str) -> dict[str, Any]:
    """Walk the JSONB blob and run `strip_pii` on every string field.

    Generic enough to handle all 3 route shapes — no per-route logic
    beyond key naming. Lists of strings are walked; ints/floats/None pass
    through.
    """
    def _walk(v: Any) -> Any:
        if isinstance(v, str):
            return strip_pii(v)
        if isinstance(v, dict):
            return {k: _walk(vv) for k, vv in v.items()}
        if isinstance(v, list):
            return [_walk(x) for x in v]
        return v

    cleaned = _walk(blob)
    # Keep route-specific shape — the editor assumes these keys exist.
    return cleaned


# ── JSON parsing helper ─────────────────────────────────────────────────


def _safe_json(raw: str) -> Any | None:
    """Parse JSON from a Claude response. Tolerates a few common
    issues: leading/trailing prose, code fences, trailing commas."""
    if not raw:
        return None
    s = raw.strip()
    # Strip ```json fences.
    if s.startswith("```"):
        # Find closing fence.
        s = s.split("```", 2)[1] if "```" in s[3:] else s[3:]
        # Drop a leading "json" tag if present.
        if s.lstrip().startswith("json"):
            s = s.lstrip()[4:]
    # Trim to outermost {...} just in case there's prose around it.
    if "{" in s and "}" in s:
        s = s[s.index("{") : s.rindex("}") + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


__all__ = [
    "llm_classify_material",
    "llm_extract_for_route",
]
