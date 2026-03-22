"""Trap detection engine v2: 3-level analysis + cascades + emotion integration.

Architecture — 3-level detection pipeline:
┌─────────────────────────────────────────────────────────────────────┐
│ Level 1: Keyword matching (difficulty 1-3)    — <1ms per trap      │
│ Level 2: Regex pattern matching (difficulty 4-7) — <5ms per trap   │
│ Level 3: LLM semantic analysis (difficulty 8-10) — 500-1500ms      │
└─────────────────────────────────────────────────────────────────────┘

Cascade flow:
1. Manager FELL on trap A → check if trap A has triggers_trap_id
2. If yes → activate the harder trap B in the next exchange
3. Continue until cascade ends or manager DODGEs

Scoring integration:
- Traps contribute a 6th scoring layer: trap_handling (-10 to +10)
- Each FELL trap applies its penalty (-3 to -5)
- Each DODGED trap applies its bonus (+2 to +3)
- Capped at -10 (floor) and +10 (ceiling)

Emotion integration:
- On FELL → trigger fell_emotion_trigger (e.g. "hostile", "hangup")
- On DODGED → trigger dodged_emotion_trigger (e.g. "considering", "curious")
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass, field

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

# Redis keys
_TRAP_STATE_KEY = "session:{session_id}:traps"
_CASCADE_STATE_KEY = "session:{session_id}:cascades"
_TRAP_STATE_TTL = 7200  # 2 hours


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TrapResult:
    """Result of checking a single trap against manager's response."""

    trap_id: str
    trap_name: str
    category: str  # legal | emotional | manipulative | expert | price | provocative | professional | procedural
    subcategory: str = ""
    status: str = "not_activated"  # "fell" | "dodged" | "partial" | "not_activated"
    score_delta: int = 0  # negative = penalty, positive = bonus
    detection_level: str = "keyword"  # keyword | regex | llm
    wrong_keywords_found: list[str] = field(default_factory=list)
    correct_keywords_found: list[str] = field(default_factory=list)
    wrong_patterns_matched: list[str] = field(default_factory=list)
    correct_patterns_matched: list[str] = field(default_factory=list)
    llm_verdict: str | None = None  # LLM explanation for level 3
    client_phrase: str = ""
    correct_example: str = ""  # shown to manager in post-session review
    explanation: str = ""  # why wrong/right
    law_reference: str = ""
    # Emotion engine triggers
    fell_emotion_trigger: str | None = None
    dodged_emotion_trigger: str | None = None
    # Cascade
    triggers_trap_id: str | None = None  # Next trap to activate on FELL


@dataclass
class TrapSessionState:
    """Accumulated trap results for an entire session."""

    activated: list[TrapResult] = field(default_factory=list)
    total_penalty: int = 0
    total_bonus: int = 0
    net_score: int = 0  # clamped to [-10, +10]
    cascade_activated: list[str] = field(default_factory=list)  # trap IDs activated via cascades


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Normalize Russian text for keyword matching: lowercase, collapse spaces."""
    return re.sub(r"\s+", " ", text.lower().strip())


# ---------------------------------------------------------------------------
# Level 1: Keyword matching (difficulty 1-3, <1ms)
# ---------------------------------------------------------------------------

def _keyword_match(text: str, keywords: list[str]) -> list[str]:
    """Check which keywords appear in the text.

    Uses word-boundary-aware matching to avoid false positives.
    """
    text_norm = _normalize(text)
    found = []
    for kw in keywords:
        kw_norm = _normalize(kw)
        if not kw_norm:
            continue
        # Multi-word keywords: check as substring
        if " " in kw_norm:
            if kw_norm in text_norm:
                found.append(kw)
        else:
            # Single word: use word boundary regex
            pattern = rf"\b{re.escape(kw_norm)}\b"
            try:
                if re.search(pattern, text_norm):
                    found.append(kw)
            except re.error:
                # Fallback to substring
                if kw_norm in text_norm:
                    found.append(kw)
    return found


def _analyze_keywords(
    manager_message: str,
    wrong_keywords: list[str],
    correct_keywords: list[str],
) -> tuple[list[str], list[str]]:
    """Run keyword matching for wrong and correct keywords."""
    wrong_found = _keyword_match(manager_message, wrong_keywords)
    correct_found = _keyword_match(manager_message, correct_keywords)
    return wrong_found, correct_found


# ---------------------------------------------------------------------------
# Level 2: Regex matching (difficulty 4-7, <5ms)
# ---------------------------------------------------------------------------

def _regex_match(text: str, patterns: list[str]) -> list[str]:
    """Check which regex patterns match the text.

    Patterns are expected to be valid Python regex strings.
    Returns list of matched pattern strings.
    """
    text_norm = _normalize(text)
    matched = []
    for pat in patterns:
        if not pat:
            continue
        try:
            if re.search(pat, text_norm, re.IGNORECASE):
                matched.append(pat)
        except re.error:
            logger.warning("Invalid regex pattern: %s", pat)
            continue
    return matched


def _analyze_regex(
    manager_message: str,
    wrong_patterns: list[str],
    correct_patterns: list[str],
) -> tuple[list[str], list[str]]:
    """Run regex matching for wrong and correct response patterns."""
    wrong_matched = _regex_match(manager_message, wrong_patterns)
    correct_matched = _regex_match(manager_message, correct_patterns)
    return wrong_matched, correct_matched


# ---------------------------------------------------------------------------
# Level 3: LLM semantic analysis (difficulty 8-10, 500-1500ms)
# ---------------------------------------------------------------------------

_LLM_TRAP_PROMPT = """Ты — эксперт по анализу ответов менеджеров по продажам услуг банкротства физических лиц (127-ФЗ).

Клиент сказал (ловушка):
"{client_phrase}"

Менеджер ответил:
"{manager_message}"

Контекст ловушки:
- Категория: {category}
- Что НЕ должен говорить менеджер: {wrong_example}
- Что ДОЛЖЕН говорить менеджер: {correct_example}
- Пояснение: {explanation}
{law_ref_line}

Оцени ответ менеджера. Ответь СТРОГО в JSON:
{{
  "verdict": "fell" | "dodged" | "partial",
  "confidence": 0.0-1.0,
  "reason": "краткое пояснение на русском"
}}"""


async def _analyze_llm(
    manager_message: str,
    trap: dict,
) -> dict | None:
    """Use LLM to semantically evaluate manager's response.

    Returns dict with verdict/confidence/reason, or None on failure.
    This is the most expensive level — only used for difficulty 8-10 traps.
    """
    try:
        # Lazy import to avoid circular dependency
        from app.services.llm import generate_response

        client_phrase = trap.get("client_phrase", "")
        law_ref = trap.get("law_reference", "")
        law_ref_line = f"- Ссылка на закон: {law_ref}" if law_ref else ""

        prompt_text = _LLM_TRAP_PROMPT.format(
            client_phrase=client_phrase,
            manager_message=manager_message,
            category=trap.get("category", ""),
            wrong_example=trap.get("wrong_response_example", ""),
            correct_example=trap.get("correct_response_example", ""),
            explanation=trap.get("explanation", ""),
            law_ref_line=law_ref_line,
        )

        result = await generate_response(
            system_prompt="Ты анализатор качества ответов менеджеров. Отвечай только JSON.",
            messages=[{"role": "user", "content": prompt_text}],
            emotion_state="cold",
        )

        if not result or not result.content:
            return None

        # Extract JSON from response
        content = result.content.strip()
        # Handle markdown code blocks
        if content.startswith("```"):
            content = re.sub(r"```(?:json)?\s*", "", content)
            content = content.rstrip("`").strip()

        return json.loads(content)

    except json.JSONDecodeError:
        logger.warning("LLM trap analysis returned non-JSON for trap %s", trap.get("name"))
        return None
    except Exception:
        logger.warning("LLM trap analysis failed for trap %s", trap.get("name"), exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Trap activation detection
# ---------------------------------------------------------------------------

def _phrase_similarity(text: str, target_phrase: str) -> float:
    """Simple word-overlap similarity between text and target phrase.

    Returns 0.0-1.0. Used to detect if character actually delivered the trap phrase.
    """
    text_words = set(_normalize(text).split())
    phrase_words = set(_normalize(target_phrase).split())
    if not phrase_words:
        return 0.0
    overlap = text_words & phrase_words
    return len(overlap) / len(phrase_words)


def check_trap_activation(
    character_message: str,
    trap: dict,
    similarity_threshold: float = 0.35,
) -> bool:
    """Check if the character's message contains (or is close to) ANY trap phrase variant.

    Checks primary client_phrase and all client_phrase_variants.
    The LLM might rephrase the trap slightly, so we use word overlap + substring.
    """
    phrases = [trap.get("client_phrase", "")]
    variants = trap.get("client_phrase_variants", [])
    if isinstance(variants, list):
        phrases.extend(variants)

    char_norm = _normalize(character_message)

    for phrase in phrases:
        if not phrase:
            continue
        # Direct substring check (first 40 chars)
        phrase_norm = _normalize(phrase)
        if phrase_norm[:40] in char_norm:
            return True
        # Word overlap similarity
        sim = _phrase_similarity(character_message, phrase)
        if sim >= similarity_threshold:
            return True

    return False


# ---------------------------------------------------------------------------
# Main analysis: 3-level pipeline
# ---------------------------------------------------------------------------

def _determine_detection_level(trap: dict) -> str:
    """Determine detection level from trap difficulty or explicit field."""
    # Explicit field takes priority
    level = trap.get("detection_level")
    if level in ("keyword", "regex", "llm"):
        return level
    # Derive from difficulty
    difficulty = trap.get("difficulty", 5)
    if difficulty <= 3:
        return "keyword"
    elif difficulty <= 7:
        return "regex"
    else:
        return "llm"


def _decide_verdict(
    wrong_found: list,
    correct_found: list,
    trap: dict,
    detection_level: str,
) -> TrapResult:
    """Core decision logic: combine keyword + regex evidence into a verdict.

    Used for levels 1 and 2. Level 3 uses LLM verdict with this as fallback.
    """
    penalty = trap.get("penalty", -3)
    bonus = trap.get("bonus", 2)
    trap_id = str(trap.get("id", ""))
    trap_name = trap.get("name", "Unknown trap")
    category = trap.get("category", "unknown")
    subcategory = trap.get("subcategory", "")
    client_phrase = trap.get("client_phrase", "")
    correct_example = trap.get("correct_response_example", "")
    explanation = trap.get("explanation", "")
    law_reference = trap.get("law_reference", "")
    fell_trigger = trap.get("fell_emotion_trigger")
    dodged_trigger = trap.get("dodged_emotion_trigger")
    triggers_next = str(trap.get("triggers_trap_id", "")) or None

    base = dict(
        trap_id=trap_id,
        trap_name=trap_name,
        category=category,
        subcategory=subcategory,
        detection_level=detection_level,
        client_phrase=client_phrase,
        correct_example=correct_example,
        explanation=explanation,
        law_reference=law_reference,
        fell_emotion_trigger=fell_trigger,
        dodged_emotion_trigger=dodged_trigger,
        triggers_trap_id=triggers_next,
    )

    # Decision tree
    if wrong_found and not correct_found:
        return TrapResult(
            **base,
            status="fell",
            score_delta=penalty,
            wrong_keywords_found=[w for w in wrong_found if isinstance(w, str)],
            correct_keywords_found=[],
        )

    if correct_found and len(correct_found) >= 2 and not wrong_found:
        return TrapResult(
            **base,
            status="dodged",
            score_delta=bonus,
            wrong_keywords_found=[],
            correct_keywords_found=[c for c in correct_found if isinstance(c, str)],
        )

    if wrong_found and correct_found:
        return TrapResult(
            **base,
            status="partial",
            score_delta=max(penalty // 2, -2),
            wrong_keywords_found=[w for w in wrong_found if isinstance(w, str)],
            correct_keywords_found=[c for c in correct_found if isinstance(c, str)],
        )

    if correct_found and len(correct_found) == 1:
        return TrapResult(
            **base,
            status="dodged",
            score_delta=max(1, bonus // 2),
            wrong_keywords_found=[],
            correct_keywords_found=[c for c in correct_found if isinstance(c, str)],
        )

    # Inconclusive
    return TrapResult(
        **base,
        status="not_activated",
        score_delta=0,
    )


async def analyze_response(
    manager_message: str,
    trap: dict,
) -> TrapResult:
    """Analyze a manager's response against a specific activated trap.

    3-level pipeline:
    - Level 1 (keyword): always runs — fast baseline
    - Level 2 (regex): runs if trap has regex patterns (difficulty 4-7)
    - Level 3 (LLM): runs only for difficulty 8-10 traps
    """
    detection_level = _determine_detection_level(trap)

    # --- Level 1: Keywords (always) ---
    wrong_kw = trap.get("wrong_response_keywords", [])
    correct_kw = trap.get("correct_response_keywords", [])
    wrong_found_kw, correct_found_kw = _analyze_keywords(manager_message, wrong_kw, correct_kw)

    # For level 1 traps, keywords are sufficient
    if detection_level == "keyword":
        return _decide_verdict(wrong_found_kw, correct_found_kw, trap, "keyword")

    # --- Level 2: Regex (difficulty 4-7) ---
    wrong_patterns = trap.get("wrong_response_patterns", [])
    correct_patterns = trap.get("correct_response_patterns", [])
    wrong_found_rx, correct_found_rx = _analyze_regex(manager_message, wrong_patterns, correct_patterns)

    # Combine keyword + regex evidence
    all_wrong = list(set(wrong_found_kw + wrong_found_rx))
    all_correct = list(set(correct_found_kw + correct_found_rx))

    if detection_level == "regex":
        result = _decide_verdict(all_wrong, all_correct, trap, "regex")
        result.wrong_patterns_matched = wrong_found_rx
        result.correct_patterns_matched = correct_found_rx
        return result

    # --- Level 3: LLM (difficulty 8-10) ---
    # First check if keywords/regex already give a clear verdict
    if all_wrong and not all_correct:
        result = _decide_verdict(all_wrong, all_correct, trap, "regex+keyword")
        result.wrong_patterns_matched = wrong_found_rx
        result.correct_patterns_matched = correct_found_rx
        return result

    if all_correct and len(all_correct) >= 2 and not all_wrong:
        result = _decide_verdict(all_wrong, all_correct, trap, "regex+keyword")
        result.wrong_patterns_matched = wrong_found_rx
        result.correct_patterns_matched = correct_found_rx
        return result

    # Inconclusive from keywords/regex — invoke LLM
    llm_result = await _analyze_llm(manager_message, trap)

    if llm_result and "verdict" in llm_result:
        verdict = llm_result["verdict"]
        confidence = llm_result.get("confidence", 0.5)
        reason = llm_result.get("reason", "")

        penalty = trap.get("penalty", -3)
        bonus = trap.get("bonus", 2)

        # Map LLM verdict to TrapResult
        if verdict == "fell" and confidence >= 0.6:
            status = "fell"
            score_delta = penalty
        elif verdict == "dodged" and confidence >= 0.6:
            status = "dodged"
            score_delta = bonus
        elif verdict == "partial" or confidence < 0.6:
            status = "partial"
            score_delta = max(penalty // 2, -2) if verdict == "fell" else max(1, bonus // 2)
        else:
            status = "not_activated"
            score_delta = 0

        trap_id = str(trap.get("id", ""))
        return TrapResult(
            trap_id=trap_id,
            trap_name=trap.get("name", "Unknown"),
            category=trap.get("category", "unknown"),
            subcategory=trap.get("subcategory", ""),
            status=status,
            score_delta=score_delta,
            detection_level="llm",
            wrong_keywords_found=wrong_found_kw,
            correct_keywords_found=correct_found_kw,
            wrong_patterns_matched=wrong_found_rx,
            correct_patterns_matched=correct_found_rx,
            llm_verdict=f"{verdict} ({confidence:.0%}): {reason}",
            client_phrase=trap.get("client_phrase", ""),
            correct_example=trap.get("correct_response_example", ""),
            explanation=trap.get("explanation", ""),
            law_reference=trap.get("law_reference", ""),
            fell_emotion_trigger=trap.get("fell_emotion_trigger"),
            dodged_emotion_trigger=trap.get("dodged_emotion_trigger"),
            triggers_trap_id=str(trap.get("triggers_trap_id", "")) or None,
        )

    # LLM failed — fall back to keyword+regex verdict
    result = _decide_verdict(all_wrong, all_correct, trap, "llm_fallback")
    result.wrong_patterns_matched = wrong_found_rx
    result.correct_patterns_matched = correct_found_rx
    return result


# ---------------------------------------------------------------------------
# Cascade logic
# ---------------------------------------------------------------------------

async def _get_cascade_state(session_id: uuid.UUID) -> dict:
    """Get cascade state from Redis: which traps were triggered via cascades."""
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        key = _CASCADE_STATE_KEY.format(session_id=session_id)
        raw = await r.get(key)
        await r.aclose()
        if raw:
            return json.loads(raw)
    except Exception:
        logger.warning("Failed to load cascade state for session %s", session_id)
    return {"activated_trap_ids": [], "fell_trap_ids": [], "dodged_trap_ids": []}


async def _save_cascade_state(session_id: uuid.UUID, state: dict) -> None:
    """Save cascade state to Redis."""
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        key = _CASCADE_STATE_KEY.format(session_id=session_id)
        await r.set(key, json.dumps(state), ex=_TRAP_STATE_TTL)
        await r.aclose()
    except Exception:
        logger.warning("Failed to save cascade state for session %s", session_id)


async def _process_cascades(
    session_id: uuid.UUID,
    results: list[TrapResult],
    all_traps_by_id: dict[str, dict],
) -> list[str]:
    """Process cascade activations based on trap results.

    When a manager FELL on a trap that has triggers_trap_id,
    the next trap in the cascade is added to the activation queue.

    Returns list of newly activated trap IDs (for next exchange).
    """
    cascade_state = await _get_cascade_state(session_id)
    newly_activated: list[str] = []

    for result in results:
        if result.status == "fell" and result.triggers_trap_id:
            next_id = result.triggers_trap_id
            # Don't re-activate already processed traps
            if next_id not in cascade_state["activated_trap_ids"]:
                cascade_state["activated_trap_ids"].append(next_id)
                newly_activated.append(next_id)
                logger.info(
                    "Cascade: trap '%s' FELL → activating trap %s for session %s",
                    result.trap_name, next_id, session_id,
                )

        # Track fell/dodged for blocked_by_trap_id logic
        if result.status == "fell":
            if result.trap_id not in cascade_state["fell_trap_ids"]:
                cascade_state["fell_trap_ids"].append(result.trap_id)
        elif result.status == "dodged":
            if result.trap_id not in cascade_state["dodged_trap_ids"]:
                cascade_state["dodged_trap_ids"].append(result.trap_id)

    await _save_cascade_state(session_id, cascade_state)
    return newly_activated


def _is_trap_blocked(trap: dict, cascade_state: dict) -> bool:
    """Check if a trap is blocked by another trap that hasn't been dodged.

    A trap with blocked_by_trap_id only activates if the blocking trap was DODGED.
    If the blocking trap hasn't been encountered yet, the trap is blocked.
    """
    blocked_by = str(trap.get("blocked_by_trap_id", "")) or None
    if not blocked_by:
        return False  # Not blocked by anything
    return blocked_by not in cascade_state.get("dodged_trap_ids", [])


# ---------------------------------------------------------------------------
# Main detection entry point
# ---------------------------------------------------------------------------

async def detect_traps(
    session_id: uuid.UUID,
    character_message: str,
    manager_message: str,
    active_traps: list[dict],
    all_traps_by_id: dict[str, dict] | None = None,
) -> list[TrapResult]:
    """Run full trap detection pipeline for a single exchange.

    Args:
        session_id: Training session ID
        character_message: The last character reply (might contain trap phrases)
        manager_message: The manager's response to analyze
        active_traps: List of trap dicts from DB (loaded from ClientProfile.trap_ids)
        all_traps_by_id: Optional dict of ALL traps indexed by ID (for cascade lookups)

    Returns:
        List of TrapResults for any traps that were activated AND resolved in this exchange.
    """
    if all_traps_by_id is None:
        all_traps_by_id = {str(t.get("id", "")): t for t in active_traps}

    cascade_state = await _get_cascade_state(session_id)
    results: list[TrapResult] = []

    # Include cascade-activated traps in the check list
    cascade_trap_ids = cascade_state.get("activated_trap_ids", [])
    cascade_traps = [
        all_traps_by_id[tid] for tid in cascade_trap_ids
        if tid in all_traps_by_id
    ]
    # Merge active_traps + cascade_traps, deduplicate by ID
    seen_ids = set()
    check_traps = []
    for t in list(active_traps) + cascade_traps:
        tid = str(t.get("id", ""))
        if tid not in seen_ids:
            seen_ids.add(tid)
            check_traps.append(t)

    for trap in check_traps:
        # Check if trap is blocked by another trap
        if _is_trap_blocked(trap, cascade_state):
            continue

        # Step 1: Did the character deliver this trap?
        if not check_trap_activation(character_message, trap):
            continue

        # Step 2: How did the manager respond? (3-level analysis)
        result = await analyze_response(manager_message, trap)
        if result.status == "not_activated":
            continue

        results.append(result)
        logger.info(
            "Trap '%s' [%s/%s] L%s: %s (delta=%+d) for session %s",
            result.trap_name, result.category, result.subcategory,
            result.detection_level, result.status,
            result.score_delta, session_id,
        )

    # Process cascades (activate next traps for FELL results)
    if results:
        await _process_cascades(session_id, results, all_traps_by_id)
        await _persist_trap_results(session_id, results)

    return results


# ---------------------------------------------------------------------------
# Emotion trigger extraction
# ---------------------------------------------------------------------------

def get_emotion_triggers(results: list[TrapResult]) -> list[dict]:
    """Extract emotion state change triggers from trap results.

    Returns list of dicts: [{"trigger": "hostile", "source": "trap_name", "reason": "fell"}]
    Used by the emotion engine to apply state transitions.
    """
    triggers = []
    for r in results:
        if r.status == "fell" and r.fell_emotion_trigger:
            triggers.append({
                "trigger": r.fell_emotion_trigger,
                "source": r.trap_name,
                "reason": "fell",
            })
        elif r.status == "dodged" and r.dodged_emotion_trigger:
            triggers.append({
                "trigger": r.dodged_emotion_trigger,
                "source": r.trap_name,
                "reason": "dodged",
            })
    return triggers


# ---------------------------------------------------------------------------
# Redis persistence
# ---------------------------------------------------------------------------

async def _persist_trap_results(
    session_id: uuid.UUID,
    results: list[TrapResult],
) -> None:
    """Append trap results to Redis for session-level tracking."""
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        key = _TRAP_STATE_KEY.format(session_id=session_id)

        for result in results:
            entry = json.dumps({
                "trap_id": result.trap_id,
                "trap_name": result.trap_name,
                "category": result.category,
                "subcategory": result.subcategory,
                "status": result.status,
                "score_delta": result.score_delta,
                "detection_level": result.detection_level,
                "wrong_found": result.wrong_keywords_found,
                "correct_found": result.correct_keywords_found,
                "wrong_patterns": result.wrong_patterns_matched,
                "correct_patterns": result.correct_patterns_matched,
                "llm_verdict": result.llm_verdict,
                "explanation": result.explanation,
                "law_reference": result.law_reference,
                "fell_emotion_trigger": result.fell_emotion_trigger,
                "dodged_emotion_trigger": result.dodged_emotion_trigger,
                "triggers_trap_id": result.triggers_trap_id,
            })
            await r.rpush(key, entry)

        await r.expire(key, _TRAP_STATE_TTL)
        await r.aclose()
    except Exception:
        logger.warning("Failed to persist trap results for session %s", session_id)


async def get_session_trap_state(session_id: uuid.UUID) -> TrapSessionState:
    """Load accumulated trap results for a session from Redis.

    Used at session end for scoring.
    """
    state = TrapSessionState()

    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        key = _TRAP_STATE_KEY.format(session_id=session_id)
        entries = await r.lrange(key, 0, -1)

        # Also load cascade state
        cascade_key = _CASCADE_STATE_KEY.format(session_id=session_id)
        cascade_raw = await r.get(cascade_key)
        await r.aclose()

        if cascade_raw:
            cascade_data = json.loads(cascade_raw)
            state.cascade_activated = cascade_data.get("activated_trap_ids", [])
    except Exception:
        logger.warning("Failed to load trap state for session %s", session_id)
        return state

    for entry_str in entries:
        try:
            entry = json.loads(entry_str)
        except json.JSONDecodeError:
            continue

        result = TrapResult(
            trap_id=entry.get("trap_id", ""),
            trap_name=entry.get("trap_name", ""),
            category=entry.get("category", ""),
            subcategory=entry.get("subcategory", ""),
            status=entry.get("status", ""),
            score_delta=entry.get("score_delta", 0),
            detection_level=entry.get("detection_level", "keyword"),
            wrong_keywords_found=entry.get("wrong_found", []),
            correct_keywords_found=entry.get("correct_found", []),
            wrong_patterns_matched=entry.get("wrong_patterns", []),
            correct_patterns_matched=entry.get("correct_patterns", []),
            llm_verdict=entry.get("llm_verdict"),
            explanation=entry.get("explanation", ""),
            law_reference=entry.get("law_reference", ""),
            fell_emotion_trigger=entry.get("fell_emotion_trigger"),
            dodged_emotion_trigger=entry.get("dodged_emotion_trigger"),
            triggers_trap_id=entry.get("triggers_trap_id"),
        )
        state.activated.append(result)

        if result.score_delta < 0:
            state.total_penalty += result.score_delta
        else:
            state.total_bonus += result.score_delta

    # Clamp net score to [-10, +10]
    raw_net = state.total_penalty + state.total_bonus
    state.net_score = max(-10, min(10, raw_net))

    return state


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

async def cleanup_trap_state(session_id: uuid.UUID) -> None:
    """Remove trap state and cascade state from Redis (called at session end)."""
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        trap_key = _TRAP_STATE_KEY.format(session_id=session_id)
        cascade_key = _CASCADE_STATE_KEY.format(session_id=session_id)
        await r.delete(trap_key, cascade_key)
        await r.aclose()
    except Exception:
        logger.debug("Trap cleanup failed for session %s", session_id)


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

def build_trap_injection_prompt(traps: list[dict]) -> str:
    """Build system prompt section that instructs the LLM to inject trap phrases.

    The LLM should naturally weave these into conversation at appropriate moments,
    not dump them all at once. Uses client_phrase_variants for variety.
    """
    if not traps:
        return ""

    lines = [
        "\n## Ловушки для менеджера (используй в подходящий момент диалога)",
        "Ты должен ЕСТЕСТВЕННО вплести эти фразы в разговор — не все сразу, а когда тема подходит.",
        "Каждую ловушку используй МАКСИМУМ один раз. Не нумеруй их, просто вставь как обычную реплику клиента.",
        "Для каждой ловушки можешь использовать основную фразу ИЛИ любой из вариантов — на твой выбор.",
        "",
    ]

    for trap in traps:
        phrase = trap.get("client_phrase", "")
        category = trap.get("category", "")
        variants = trap.get("client_phrase_variants", [])
        difficulty = trap.get("difficulty", 5)

        line = f'- [{category}, сл.{difficulty}] "{phrase}"'
        if variants:
            alt_list = " | ".join(f'"{v}"' for v in variants[:2])
            line += f" (варианты: {alt_list})"
        lines.append(line)

    lines.append(
        "\nВажно: вставляй ловушки только когда контекст диалога позволяет. "
        "Если менеджер увёл разговор в другую сторону — не форсируй."
    )

    return "\n".join(lines)
