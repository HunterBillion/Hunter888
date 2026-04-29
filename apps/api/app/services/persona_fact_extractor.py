"""TZ-4.5 PR 2 — extract persona facts from a manager turn.

The TZ-4 D3 ``persona_memory.lock_slot`` writer has lived as dead code
since April 2026 because nothing in the runtime called it after each
manager turn. This module is the missing caller's brain — it asks the
LLM "did the manager just reveal new info about himself?" and returns
a structured list of facts ready for ``lock_slot`` to commit.

Why a separate LLM call (not a side-effect of the main one)
-----------------------------------------------------------

The character-response LLM call (``generate_response`` in llm.py) has
its own attention budget — system prompt, character lore, scenario
prompt, last 20 turns of history. Adding "and also extract any new
facts about the manager into JSON" to that prompt:

  1. Costs the model attention it should spend on the actual reply.
  2. Mixes prose-mode and structured-mode outputs in one response,
     which every provider handles differently and unreliably.
  3. Couples extraction to the same provider/model the character is
     using — the character may be Gemma local (8K ctx, no JSON-mode);
     extraction wants Haiku/Flash with proper JSON support.

So extraction is a separate, smaller, cheaper LLM call. It fires AFTER
the character reply is sent (asyncio.create_task in PR 3), so the
manager-perceived turn latency is unaffected.

Why JSON via the structured-output prompt, not tool-use
-------------------------------------------------------

Anthropic and OpenAI both have native tool-use / structured-output
APIs that produce JSON without parsing. We don't use them here on
purpose:

  • Tool-use API requires defining a JSON Schema and the SDK bumps
    cost on every call. We only need a flat list of {slot, value,
    confidence, quote} — overkill.
  • A vanilla "respond ONLY with JSON" prompt + json.loads + validation
    works on every provider (Haiku, Flash, GPT-mini). Provider-agnostic
    matters because we want fallback chain support.

The validation gate (rejects malformed / low-confidence / non-quoted
extractions) compensates for the looser contract.

Why we don't trust the LLM
--------------------------

Three guards:

  1. **Schema-shape validation** — every fact MUST be a dict with
     exactly four keys. Drop everything else.
  2. **Slot whitelist** — slot_code MUST exist in PERSONA_SLOTS. No
     "the model invented a new slot" path.
  3. **Confidence threshold** — < 0.7 facts are dropped. < 0.9 facts
     can't overwrite an existing stable=True slot (anti-flip-flop).
  4. **Quote-must-be-substring** — the ``quote`` field MUST be a
     literal substring of the manager's message. Stops the LLM from
     fabricating a quote like "the manager said his name is Vasya"
     when the manager said no such thing.

Design budget
-------------

Target latency: ~600ms p95 (Haiku is fast). Target tokens: ~300 in
+ ~200 out. ~$0.0003 per call at Haiku pricing — order of magnitude
lower than the character-response call.

Best-effort guarantee
---------------------

Any failure (timeout, rate limit, malformed JSON, network) returns
an empty list with a logged warning. Extraction is bonus, not gating.
PR 3 caller will treat empty result the same as "no new facts" and
move on.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.services.persona_slots import PERSONA_SLOTS, all_slot_codes, get_slot

logger = logging.getLogger(__name__)


# ─── Public dataclass ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExtractedFact:
    """One fact the extractor wants to commit. Caller decides if the
    confidence threshold for this slot passes (depends on
    slot.stable + whether the slot is already populated).

    Frozen — caller iterates and calls lock_slot per fact, no mutation.
    """

    slot_code: str
    value: Any
    confidence: float
    quote: str

    def __post_init__(self) -> None:  # pragma: no cover — dataclass guard
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0,1], got {self.confidence}")


# ─── Prompts ────────────────────────────────────────────────────────────────


# Note: we DON'T use str.format() on this template — the literal JSON
# braces inside would collide with format-string placeholders. Instead
# we concat: head + slot_codes_line + middle + slot_descriptions + tail.

_SYSTEM_PROMPT_HEAD = """\
Ты — извлекатель фактов о ЧЕЛОВЕКЕ, который сейчас разговаривает с AI-клиентом
по телефону. Этот человек — менеджер по продажам услуг банкротства.

ВАЖНО: ты НЕ извлекаешь факты о клиенте (AI). Ты извлекаешь факты, которые
МЕНЕДЖЕР сказал О СЕБЕ или о своей компании. Например:
  - «меня зовут Дмитрий»          → slot=full_name, value="Дмитрий"
  - «я из Москвы»                  → slot=city, value="Москва"
  - «у меня компания Альфа»        → slot=company_name, value="Альфа"
  - «мы занимаемся стройкой»       → slot=industry, value="строительство"
  - «у меня двое детей»            → slot=children_count, value=2

Если менеджер задал вопрос или ничего о себе не сказал — верни пустой
список. НЕ ИЗВЛЕКАЙ факты "по логике" — нужна явная фраза в реплике.

ФОРМАТ ОТВЕТА: ТОЛЬКО JSON-массив, без лишнего текста до или после:

[
  {
    "slot_code": "<один из перечисленных ниже>",
    "value": "<извлечённое значение, тип см. ниже>",
    "confidence": 0.0..1.0,
    "quote": "<точная подстрока из реплики менеджера, доказывающая факт>"
  }
]

Если ничего не извлекается → верни []

ДОПУСТИМЫЕ slot_code: """

_SYSTEM_PROMPT_MIDDLE = """

ТИПЫ ЗНАЧЕНИЙ ПО СЛОТАМ:
"""

_SYSTEM_PROMPT_TAIL = """

ПРАВИЛА УВЕРЕННОСТИ (confidence):
  • 0.9-1.0 — менеджер сказал прямо и недвусмысленно («меня зовут Иван»)
  • 0.7-0.9 — следует из контекста, но не дословно («я из строительной компании»
    → industry=строительство c 0.8)
  • <0.7 — не извлекай вообще, возможны ошибки. НЕ возвращай их.

КРИТИЧЕСКИ ВАЖНО:
  • quote ОБЯЗАН быть точной подстрокой реплики менеджера. НЕ перефразируй.
  • Если менеджер ОПРОВЕРГАЕТ предыдущий факт («не Альфа, я там больше не работаю»)
    — извлеки ОПРОВЕРЖЕНИЕ как новый факт, в quote — фразу опровержения.
  • Один и тот же slot_code может встретиться только ОДИН раз в ответе.
"""


def _render_user_prompt(manager_message: str, known_facts_text: str) -> str:
    return (
        "Реплика менеджера:\n\"\"\"\n"
        + manager_message
        + "\n\"\"\"\n\n"
        "Уже известно о менеджере (для контекста, чтобы не извлекать повторно):\n"
        + known_facts_text
        + "\n\nОтвет — JSON-массив (или [] если ничего нового):"
    )


def _build_slot_descriptions() -> str:
    """One line per slot for the system prompt."""
    lines: list[str] = []
    for slot in PERSONA_SLOTS.values():
        type_hint = {
            int: "число",
            str: "строка",
            bool: "да/нет",
            list: "список строк",
        }.get(slot.value_type, "строка")
        lines.append(f"  • {slot.code} ({type_hint}) — {slot.extractor_hint}")
    return "\n".join(lines)


def _format_known_facts(confirmed_facts: dict[str, Any] | None) -> str:
    if not confirmed_facts:
        return "(пока ничего не известно)"
    lines: list[str] = []
    for code, fact in confirmed_facts.items():
        slot = get_slot(code)
        if slot is None or not isinstance(fact, dict) or "value" not in fact:
            continue
        lines.append(f"  • {slot.label_ru}: {fact['value']}")
    return "\n".join(lines) if lines else "(пока ничего не известно)"


def _render_system_prompt() -> str:
    return (
        _SYSTEM_PROMPT_HEAD
        + ", ".join(sorted(all_slot_codes()))
        + _SYSTEM_PROMPT_MIDDLE
        + _build_slot_descriptions()
        + _SYSTEM_PROMPT_TAIL
    )


# ─── Validation ─────────────────────────────────────────────────────────────


_REQUIRED_KEYS = frozenset({"slot_code", "value", "confidence", "quote"})


def _validate_one(item: Any, manager_message: str) -> ExtractedFact | None:
    """Strict validation: drop any item that doesn't pass.

    Returns ``None`` if invalid; logs at DEBUG (not warning — these
    are routine LLM imperfections, not errors).
    """
    if not isinstance(item, dict):
        logger.debug("fact-extractor: item is not a dict — drop")
        return None
    if set(item.keys()) != _REQUIRED_KEYS:
        # Allow extra keys, but require all four. Strict-equality would
        # fail on any extra (some LLMs add "reason" or "explanation").
        if not _REQUIRED_KEYS.issubset(item.keys()):
            logger.debug("fact-extractor: item missing required keys — drop %s", item.keys())
            return None

    slot_code = item.get("slot_code")
    if not isinstance(slot_code, str):
        return None
    slot = get_slot(slot_code)
    if slot is None:
        logger.debug("fact-extractor: slot_code=%r not in registry — drop", slot_code)
        return None

    value = item.get("value")
    # Coerce to declared type if possible
    if slot.value_type is int:
        try:
            value = int(value)
        except (TypeError, ValueError):
            return None
    elif slot.value_type is bool:
        if not isinstance(value, bool):
            return None
    elif slot.value_type is list:
        if not isinstance(value, list):
            return None
        value = [str(v).strip() for v in value if v]
        if not value:
            return None
    else:  # str
        if not isinstance(value, str):
            return None
        value = value.strip()
        if not value:
            return None

    confidence = item.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        return None
    if not (0.0 <= confidence <= 1.0):
        return None

    quote = item.get("quote")
    if not isinstance(quote, str) or not quote.strip():
        return None
    quote = quote.strip()

    # Quote-must-be-substring guard. Normalise both sides (lowercase,
    # collapse whitespace) so trivial diffs don't reject legitimate
    # extractions.
    normalised_msg = re.sub(r"\s+", " ", manager_message.lower()).strip()
    normalised_quote = re.sub(r"\s+", " ", quote.lower()).strip()
    if normalised_quote not in normalised_msg:
        logger.debug(
            "fact-extractor: quote %r not in manager message — drop (LLM hallucinated quote)",
            quote,
        )
        return None

    return ExtractedFact(
        slot_code=slot_code,
        value=value,
        confidence=confidence,
        quote=quote,
    )


def _parse_response(raw: str, manager_message: str) -> list[ExtractedFact]:
    """Tolerant JSON parser. Strips markdown fences, tolerates trailing
    text after the JSON array.
    """
    text = raw.strip()
    # Strip ```json ... ``` fence if present
    if text.startswith("```"):
        # Drop opening fence and language tag
        lines = text.split("\n", 1)
        text = lines[1] if len(lines) > 1 else ""
        # Drop trailing fence
        if "```" in text:
            text = text.rsplit("```", 1)[0]
    text = text.strip()

    if not text:
        return []

    # Find the first [ ... ] balanced array
    start = text.find("[")
    if start < 0:
        return []
    # Naive but works for our tiny payloads — find matching close
    # bracket by counting depth.
    depth = 0
    end = -1
    for i in range(start, len(text)):
        c = text[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        return []

    json_str = text[start:end]
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        logger.debug("fact-extractor: JSON parse failed — drop everything")
        return []
    if not isinstance(parsed, list):
        return []

    facts: list[ExtractedFact] = []
    seen_codes: set[str] = set()
    for item in parsed:
        validated = _validate_one(item, manager_message)
        if validated is None:
            continue
        if validated.slot_code in seen_codes:
            # Dedup — keep the first; LLM occasionally double-emits.
            continue
        seen_codes.add(validated.slot_code)
        facts.append(validated)
    return facts


# ─── Public API ─────────────────────────────────────────────────────────────


async def extract_facts_from_turn(
    *,
    manager_message: str,
    confirmed_facts: dict[str, Any] | None = None,
    timeout_s: float = 5.0,
    model_override: str | None = None,
) -> list[ExtractedFact]:
    """Extract persona facts from one manager turn.

    Best-effort: returns empty list on any failure (timeout, rate
    limit, no LLM client, malformed JSON, validation rejection).
    Caller in PR 3 doesn't need to handle errors — just iterates the
    result.

    ``confirmed_facts`` is the persona's existing facts dict — passed
    only as context to the LLM ("don't extract things you already
    know"). Saves prompt tokens; the validation gate doesn't consult
    it.
    """
    msg = (manager_message or "").strip()
    # Skip vacuous turns — saves a round-trip and tokens.
    if len(msg) < 6:
        return []

    # Lazy import to avoid bringing the anthropic SDK in at module-load
    # time when the API key isn't configured.
    from app.services.llm import _get_claude_client  # noqa: PLC0415

    client = _get_claude_client()
    if client is None:
        logger.info("fact-extractor: no Claude client configured — skipping")
        return []

    system_prompt = _render_system_prompt()
    user_prompt = _render_user_prompt(msg, _format_known_facts(confirmed_facts))

    # Haiku is the right speed/cost tradeoff for a per-turn classifier.
    # Override-able for tests / experiments.
    model = model_override or getattr(
        settings, "persona_extractor_model", "claude-haiku-4-5",
    )

    try:
        async with asyncio.timeout(timeout_s):
            response = await client.messages.create(
                model=model,
                max_tokens=400,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
    except asyncio.TimeoutError:
        logger.warning("fact-extractor: %.1fs timeout — skipping turn", timeout_s)
        return []
    except Exception as exc:
        logger.warning("fact-extractor: LLM call failed: %s", exc)
        return []

    # Anthropic SDK response.content is a list of content blocks.
    raw = ""
    try:
        for block in response.content:
            block_text = getattr(block, "text", None)
            if block_text:
                raw += block_text
    except Exception:
        return []

    if not raw.strip():
        return []

    return _parse_response(raw, manager_message=msg)


# ─── Public end-to-end wrapper (PR 3 wiring point) ──────────────────────────


# Confidence floors for the commit-or-drop decision. The extractor
# guarantees ≥ 0.7 already (anything lower it didn't return). We add a
# stricter ceiling for stable=True slots: rewriting "this person's
# name" should require near-certainty.
_OVERWRITE_STABLE_MIN_CONFIDENCE = 0.9
_OVERWRITE_VOLATILE_MIN_CONFIDENCE = 0.7
_NEW_FACT_MIN_CONFIDENCE = 0.7


def _should_commit(
    fact: ExtractedFact,
    *,
    persona_facts: dict[str, Any],
) -> bool:
    """Decide if an extracted fact should call lock_slot.

    Three rules:

      1. Slot must exist in the registry (already enforced by
         _validate_one — but defensive cheap re-check).
      2. New fact (slot empty in persona_facts) → confidence ≥ 0.7.
      3. Overwrite (slot already populated) →
         - stable=True slots need ≥ 0.9 (anti-flip-flop)
         - stable=False slots need ≥ 0.7 (free evolution)
    """
    from app.services.persona_slots import get_slot  # noqa: PLC0415

    slot = get_slot(fact.slot_code)
    if slot is None:
        return False

    existing = persona_facts.get(fact.slot_code)
    has_existing_value = (
        isinstance(existing, dict) and existing.get("value") is not None
    )

    if not has_existing_value:
        return fact.confidence >= _NEW_FACT_MIN_CONFIDENCE

    floor = (
        _OVERWRITE_STABLE_MIN_CONFIDENCE
        if slot.stable
        else _OVERWRITE_VOLATILE_MIN_CONFIDENCE
    )
    return fact.confidence >= floor


async def extract_and_commit_facts_for_turn(
    db,
    *,
    session_id,
    user_id,
    manager_message: str,
    persona,
) -> int:
    """End-to-end wrapper for the call-flow caller (PR 3 wiring point).

    1. Run :func:`extract_facts_from_turn` with the persona's current
       confirmed_facts as context.
    2. For each fact that passes :func:`_should_commit`, call
       ``persona_memory.lock_slot``.
    3. Returns the number of facts successfully committed.

    Never raises. Failures (no LLM, optimistic-concurrency conflict,
    DB error) are logged and counted as zero. The audit-hook contract:
    fact extraction is best-effort, the call must continue regardless.

    The caller (``ws/training.py``) is responsible for awaiting this
    function inside its existing post-reply ``async with async_session``
    block — same pattern as ``audit_and_publish_assistant_reply``.
    """
    if persona is None:
        return 0

    persona_facts: dict[str, Any] = dict(getattr(persona, "confirmed_facts", None) or {})

    try:
        candidates = await extract_facts_from_turn(
            manager_message=manager_message,
            confirmed_facts=persona_facts,
        )
    except Exception:  # pragma: no cover — extractor is already best-effort
        logger.exception(
            "fact-extractor: extract_facts_from_turn raised — session=%s",
            session_id,
        )
        return 0

    if not candidates:
        return 0

    # Lazy import to avoid a top-level cycle (persona_memory imports
    # nothing from us, but keeping the import inside the function
    # makes accidental future cycles obvious in stack traces).
    from app.services import persona_memory  # noqa: PLC0415

    committed = 0
    for fact in candidates:
        if not _should_commit(fact, persona_facts=persona_facts):
            logger.debug(
                "fact-extractor: %s skipped (confidence=%.2f, has_existing=%s)",
                fact.slot_code,
                fact.confidence,
                fact.slot_code in persona_facts,
            )
            continue

        try:
            await persona_memory.lock_slot(
                db,
                persona=persona,
                slot_code=fact.slot_code,
                fact_value=fact.value,
                expected_version=persona.version,
                session_id=session_id,
                source_ref=f"extractor:{fact.quote[:60]}",
                actor_id=user_id,
                source="ws.training.fact_extractor",
            )
        except persona_memory.PersonaConflict:
            # Another writer raced us. Log at info, not error — the
            # next manager turn will re-extract the same fact (since
            # confirmed_facts will then be up-to-date) and either
            # accept it or skip as already-locked.
            logger.info(
                "fact-extractor: PersonaConflict on slot=%s — re-extract on next turn",
                fact.slot_code,
            )
            continue
        except Exception:
            logger.exception(
                "fact-extractor: lock_slot raised on slot=%s — swallowing",
                fact.slot_code,
            )
            continue

        # Update local view so subsequent facts in the same batch
        # see the new value (else stable=True overwrite check would
        # use stale data within one turn).
        persona_facts[fact.slot_code] = {"value": fact.value}
        committed += 1

    if committed:
        logger.info(
            "fact-extractor: committed %d facts in session=%s lead=%s",
            committed,
            session_id,
            getattr(persona, "lead_client_id", None),
        )
    return committed
