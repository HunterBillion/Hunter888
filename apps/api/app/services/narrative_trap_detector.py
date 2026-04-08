"""Narrative trap detector v1: memory-based + storylet-driven traps.

Works PARALLEL to the standard trap_detector.py (not as a 4th level).
Standard traps are static (100 pre-defined, keyword/regex/LLM detection).
Narrative traps are DYNAMIC — generated from ClientStory memory and active storylets.

Architecture:
┌───────────────────────────────────────────────────────────────────┐
│ Standard pipeline (trap_detector.py)                              │
│  detect_traps() → 100 static traps (levels 1-3)                  │
├───────────────────────────────────────────────────────────────────┤
│ Narrative pipeline (this file)            — always LLM-based      │
│  detect_narrative_traps() → dynamic traps from ClientStory memory │
│  Categories:                                                      │
│   • promise_check  — manager promised X, did they deliver?        │
│   • memory_check   — client tests if manager remembers details    │
│   • consistency_check — client references earlier statements       │
└───────────────────────────────────────────────────────────────────┘

Dependencies:
- ClientStory (Protocol) — provided by Phase 1 architect
- EpisodicMemory entries — stored in PostgreSQL
- trigger_detector.py — used for hybrid detection

Consequence events are emitted as TrapConsequence objects for Game Director.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ClientStory Protocol (contract from architect, Phase 1)
# ---------------------------------------------------------------------------

@runtime_checkable
class ClientStoryProtocol(Protocol):
    """Contract for ClientStory — implemented by architect in Phase 1.

    Narrative trap detector depends on this interface.
    Until Phase 1 delivers the real model, tests use MockClientStory.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    total_calls_planned: int
    current_call_number: int

    @property
    def personality_profile(self) -> dict:
        """OCEAN + PAD + modifiers snapshot."""
        ...

    @property
    def memory(self) -> dict:
        """Episodic memory: promises, key_moments, insults, agreements.

        Format:
        {
            "promises": [
                {"text": "send documents", "call_number": 2, "fulfilled": False, "created_at": "..."},
            ],
            "key_moments": [
                {"text": "manager explained 127-ФЗ", "call_number": 1, "valence": 0.7},
            ],
            "insults": [],
            "agreements": [
                {"text": "agreed to visit office Thursday", "call_number": 2},
            ],
        }
        """
        ...

    @property
    def active_storylets(self) -> list[str]:
        """Active storylet IDs (e.g. ["collectors_arrived", "wife_discovered_debt"])."""
        ...

    @property
    def consequence_log(self) -> list[dict]:
        """Accumulated consequences from previous calls."""
        ...

    @property
    def active_factors(self) -> list[dict]:
        """Active human factors: [{"factor": "fatigue", "intensity": 0.7, "since_call": 2}]."""
        ...

    @property
    def relationship_score(self) -> float:
        """0-100 relationship quality score."""
        ...


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class NarrativeTrapResult:
    """Result of a narrative trap check."""

    trap_type: str  # "promise_check" | "memory_check" | "consistency_check"
    status: str  # "fell" | "dodged" | "partial" | "not_activated"
    score_delta: int  # penalty or bonus
    description: str  # human-readable description (Russian)
    evidence: str  # what triggered the check
    manager_response_summary: str  # how manager handled it
    severity: float  # 0.0-1.0
    llm_verdict: str | None = None  # LLM explanation

    # For consequence event generation
    consequence_type: str = ""  # "credibility_loss" | "trust_change" | "storylet_trigger"
    consequence_payload: dict = field(default_factory=dict)


@dataclass
class TrapConsequence:
    """Consequence event sent to Game Director after trap outcome.

    Used by both standard traps (trap_detector.py) and narrative traps (this file).
    Game Director ranks consequences by severity and applies them to story arc.
    """

    trap_id: str  # UUID or generated ID
    session_id: str  # TrainingSession UUID
    trap_type: str  # "standard" | "narrative" | "human_factor"
    outcome: str  # "fell" | "dodged" | "partial"
    consequence_type: str  # "emotion_shift" | "trust_change" | "storylet_trigger" | "credibility_loss"
    severity: float  # 0.0-1.0 for Game Director ranking
    payload: dict = field(default_factory=dict)
    # Examples:
    #   {"target_state": "hostile"} for emotion_shift
    #   {"delta": -15} for trust_change
    #   {"storylet_id": "collectors_arrived"} for storylet_trigger
    #   {"detail": "contradicted self on debt amount"} for credibility_loss


# ---------------------------------------------------------------------------
# Narrative trap templates
# ---------------------------------------------------------------------------

# Promise check: client tests if manager kept promises from previous calls
PROMISE_CHECK_TEMPLATES = [
    {
        "client_phrase_template": "Вы обещали {promise_text}. Где результат?",
        "variants": [
            "В прошлый раз вы сказали что {promise_text}. И что?",
            "Помните, вы обещали {promise_text}? Я жду.",
            "Ну и где же? Вы ведь говорили — {promise_text}!",
        ],
    },
    {
        "client_phrase_template": "Прошлый раз обещали {promise_text}. Обманули?",
        "variants": [
            "Вы не сделали то, что обещали — {promise_text}. Как вам доверять?",
            "Ну вот, опять. Сказали — {promise_text}. А по факту?",
        ],
    },
]

# Memory check: client tests if manager remembers details
MEMORY_CHECK_TEMPLATES = [
    {
        "client_phrase_template": "А помните, вы мне говорили про {detail}?",
        "variants": [
            "В прошлый раз вы сказали что-то про {detail}. Можете повторить?",
            "Вы помните мою ситуацию? Что вы мне говорили про {detail}?",
        ],
    },
    {
        "client_phrase_template": "Какой у меня долг, помните? Или вы всех путаете?",
        "variants": [
            "Вы хоть помните, сколько у меня кредиторов?",
            "Напомните — что мы обсуждали в прошлый раз?",
        ],
    },
]

# Consistency check: client catches contradictions
CONSISTENCY_CHECK_TEMPLATES = [
    {
        "client_phrase_template": "Стоп. В прошлый раз вы говорили {old_statement}. А сейчас — {new_statement}. Как так?",
        "variants": [
            "Вы сами себе противоречите! Раньше было {old_statement}, теперь {new_statement}!",
            "Подождите. Это не то, что вы говорили раньше. Раньше было — {old_statement}.",
        ],
    },
]


# ---------------------------------------------------------------------------
# LLM prompts for narrative trap analysis
# ---------------------------------------------------------------------------

_NARRATIVE_ANALYSIS_PROMPT = """Ты — эксперт по анализу качества ответов менеджеров в контексте МНОГОЗВОНКОВОЙ коммуникации.

Контекст истории:
- Звонок: {call_number} из {total_calls}
- Отношения с клиентом: {relationship_score}/100
{memory_context}

Клиент проверяет менеджера:
Тип проверки: {trap_type}
Фраза клиента: "{client_phrase}"
Что менеджер ДОЛЖЕН был помнить/сделать: {expected_behavior}

Ответ менеджера: "{manager_message}"

Оцени ответ менеджера. Ответь СТРОГО в JSON:
{{
  "verdict": "fell" | "dodged" | "partial",
  "confidence": 0.0-1.0,
  "reason": "краткое пояснение на русском",
  "severity": 0.0-1.0,
  "consequence_type": "credibility_loss" | "trust_change" | "none"
}}"""


# ---------------------------------------------------------------------------
# Promise check detection
# ---------------------------------------------------------------------------

async def _check_promises(
    manager_message: str,
    client_message: str,
    story: ClientStoryProtocol,
) -> list[NarrativeTrapResult]:
    """Check if client is testing whether manager kept promises.

    Looks at unfulfilled promises from previous calls and checks if
    the client's message references them.
    """
    results = []
    memory = story.memory
    promises = memory.get("promises", [])

    # Only check unfulfilled promises
    unfulfilled = [p for p in promises if not p.get("fulfilled", False)]
    if not unfulfilled:
        return results

    # Check if client message references any promise
    client_lower = client_message.lower()
    promise_keywords = ["обещали", "обещал", "говорили", "сказали", "ждала", "жду", "обманули",
                        "где результат", "не сделали", "не прислали", "не перезвонили"]

    is_promise_check = any(kw in client_lower for kw in promise_keywords)
    if not is_promise_check:
        return results

    # Find the most relevant unfulfilled promise
    best_promise = None
    best_score = 0
    for promise in unfulfilled:
        text = promise.get("text", "").lower()
        words = set(text.split())
        client_words = set(client_lower.split())
        overlap = len(words & client_words)
        if overlap > best_score:
            best_score = overlap
            best_promise = promise

    if best_promise is None and unfulfilled:
        best_promise = unfulfilled[0]  # Fallback to first unfulfilled

    if best_promise:
        # Use LLM to analyze manager's response
        verdict = await _analyze_narrative_trap(
            manager_message=manager_message,
            client_phrase=client_message,
            trap_type="promise_check",
            expected_behavior=f"Менеджер обещал: '{best_promise.get('text', '')}' (звонок #{best_promise.get('call_number', '?')}). "
                             f"Должен либо подтвердить выполнение, либо честно признать невыполнение с объяснением.",
            story=story,
        )

        if verdict:
            result = NarrativeTrapResult(
                trap_type="promise_check",
                status=verdict.get("verdict", "not_activated"),
                score_delta=_score_for_verdict(verdict, penalty=-4, bonus=3),
                description=f"Проверка обещания: '{best_promise.get('text', '')}'",
                evidence=f"Невыполненное обещание из звонка #{best_promise.get('call_number', '?')}",
                manager_response_summary=manager_message[:200],
                severity=verdict.get("severity", 0.5),
                llm_verdict=verdict.get("reason", ""),
                consequence_type=verdict.get("consequence_type", "trust_change"),
                consequence_payload={"promise_text": best_promise.get("text", ""),
                                    "call_number": best_promise.get("call_number", 0)},
            )
            results.append(result)

    return results


# ---------------------------------------------------------------------------
# Memory check detection
# ---------------------------------------------------------------------------

async def _check_memory(
    manager_message: str,
    client_message: str,
    story: ClientStoryProtocol,
) -> list[NarrativeTrapResult]:
    """Check if client is testing whether manager remembers details."""
    results = []
    memory = story.memory

    client_lower = client_message.lower()
    memory_keywords = ["помните", "помнишь", "говорили", "рассказывали", "в прошлый раз",
                       "напомните", "повторите", "забыли", "путаете"]

    is_memory_check = any(kw in client_lower for kw in memory_keywords)
    if not is_memory_check:
        return results

    # Build context from key_moments
    key_moments = memory.get("key_moments", [])
    agreements = memory.get("agreements", [])

    if not key_moments and not agreements:
        return results

    # Combine relevant memories
    relevant_memories = []
    for km in key_moments:
        relevant_memories.append(f"Звонок #{km.get('call_number', '?')}: {km.get('text', '')}")
    for ag in agreements:
        relevant_memories.append(f"Договорённость (звонок #{ag.get('call_number', '?')}): {ag.get('text', '')}")

    expected = "Менеджер должен помнить ключевые детали: " + "; ".join(relevant_memories[:5])

    verdict = await _analyze_narrative_trap(
        manager_message=manager_message,
        client_phrase=client_message,
        trap_type="memory_check",
        expected_behavior=expected,
        story=story,
    )

    if verdict:
        result = NarrativeTrapResult(
            trap_type="memory_check",
            status=verdict.get("verdict", "not_activated"),
            score_delta=_score_for_verdict(verdict, penalty=-3, bonus=2),
            description="Проверка памяти: клиент тестирует, помнит ли менеджер детали",
            evidence=f"Ключевые моменты из {len(key_moments)} записей",
            manager_response_summary=manager_message[:200],
            severity=verdict.get("severity", 0.4),
            llm_verdict=verdict.get("reason", ""),
            consequence_type=verdict.get("consequence_type", "trust_change"),
            consequence_payload={"memories_count": len(key_moments)},
        )
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Consistency check detection
# ---------------------------------------------------------------------------

async def _check_consistency(
    manager_message: str,
    client_message: str,
    story: ClientStoryProtocol,
) -> list[NarrativeTrapResult]:
    """Check if client is catching contradictions in manager's statements."""
    results = []

    client_lower = client_message.lower()
    consistency_keywords = ["противоречите", "раньше говорили", "не то что", "по-другому",
                           "в прошлый раз было", "изменилось", "передумали", "стоп"]

    is_consistency_check = any(kw in client_lower for kw in consistency_keywords)
    if not is_consistency_check:
        return results

    memory = story.memory
    key_moments = memory.get("key_moments", [])

    if not key_moments:
        return results

    context_items = [f"Звонок #{km.get('call_number', '?')}: {km.get('text', '')}"
                     for km in key_moments[:5]]
    expected = ("Менеджер НЕ ДОЛЖЕН противоречить тому, что говорил раньше. "
                "Ранее сказанное: " + "; ".join(context_items))

    verdict = await _analyze_narrative_trap(
        manager_message=manager_message,
        client_phrase=client_message,
        trap_type="consistency_check",
        expected_behavior=expected,
        story=story,
    )

    if verdict:
        # Consistency failures are SEVERE — credibility loss is global
        base_severity = verdict.get("severity", 0.6)
        if verdict.get("verdict") == "fell":
            base_severity = max(base_severity, 0.7)  # Floor at 0.7 for fell

        result = NarrativeTrapResult(
            trap_type="consistency_check",
            status=verdict.get("verdict", "not_activated"),
            score_delta=_score_for_verdict(verdict, penalty=-5, bonus=3),
            description="Проверка последовательности: клиент поймал противоречие",
            evidence=f"Ссылка на предыдущие высказывания ({len(key_moments)} записей)",
            manager_response_summary=manager_message[:200],
            severity=base_severity,
            llm_verdict=verdict.get("reason", ""),
            consequence_type="credibility_loss",
            consequence_payload={"global": True, "detail": verdict.get("reason", "")},
        )
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# LLM analysis helper
# ---------------------------------------------------------------------------

async def _analyze_narrative_trap(
    manager_message: str,
    client_phrase: str,
    trap_type: str,
    expected_behavior: str,
    story: ClientStoryProtocol,
) -> dict | None:
    """Use LLM to evaluate manager's response to a narrative trap."""
    import re as _re

    try:
        from app.services.llm import generate_response

        # Build memory context
        memory = story.memory
        memory_lines = []
        for p in memory.get("promises", [])[:3]:
            status = "✓" if p.get("fulfilled") else "✗"
            memory_lines.append(f"  [{status}] Обещание: {p.get('text', '')} (звонок #{p.get('call_number', '?')})")
        for km in memory.get("key_moments", [])[:3]:
            memory_lines.append(f"  Момент: {km.get('text', '')} (звонок #{km.get('call_number', '?')})")

        memory_context = "\n".join(memory_lines) if memory_lines else "  (нет записей)"

        prompt = _NARRATIVE_ANALYSIS_PROMPT.format(
            call_number=story.current_call_number,
            total_calls=story.total_calls_planned,
            relationship_score=story.relationship_score,
            memory_context=f"Память клиента:\n{memory_context}",
            trap_type=trap_type,
            client_phrase=client_phrase,
            expected_behavior=expected_behavior,
            manager_message=manager_message,
        )

        result = await generate_response(
            system_prompt="Ты анализатор многозвонковой коммуникации. Отвечай только JSON.",
            messages=[{"role": "user", "content": prompt}],
            emotion_state="cold",
            task_type="structured",
            prefer_provider="local",
        )

        if not result or not result.content:
            return None

        content = result.content.strip()
        if content.startswith("```"):
            content = _re.sub(r"```(?:json)?\s*", "", content)
            content = content.rstrip("`").strip()

        return json.loads(content)

    except json.JSONDecodeError:
        logger.warning("Narrative trap LLM returned non-JSON for %s", trap_type)
        return None
    except Exception:
        logger.warning("Narrative trap LLM failed for %s", trap_type, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Scoring helper
# ---------------------------------------------------------------------------

def _score_for_verdict(verdict: dict, penalty: int = -3, bonus: int = 2) -> int:
    """Convert LLM verdict to score delta."""
    v = verdict.get("verdict", "not_activated")
    confidence = verdict.get("confidence", 0.5)

    if v == "fell" and confidence >= 0.6:
        return penalty
    elif v == "dodged" and confidence >= 0.6:
        return bonus
    elif v == "partial" or confidence < 0.6:
        return max(penalty // 2, -2) if v == "fell" else max(1, bonus // 2)
    return 0


# ---------------------------------------------------------------------------
# Storylet-injected traps
# ---------------------------------------------------------------------------

# Storylets can inject additional narrative traps when activated
STORYLET_TRAP_MAP: dict[str, dict] = {
    "collectors_arrived": {
        "trap_type": "memory_check",
        "description": "Клиент в панике: коллекторы пришли домой",
        "check_keywords": ["коллекторы", "пришли", "домой", "звонок в дверь", "угрожали"],
        "expected": "Менеджер должен успокоить, напомнить о 230-ФЗ и предложить конкретные действия",
        "penalty": -4,
        "bonus": 3,
        "severity": 0.7,
    },
    "wife_discovered_debt": {
        "trap_type": "consistency_check",
        "description": "Жена узнала о долгах — клиент в стрессе",
        "check_keywords": ["жена узнала", "семья", "скандал", "развод", "скрывал"],
        "expected": "Менеджер должен проявить эмпатию, не обвинять, предложить семейную консультацию",
        "penalty": -3,
        "bonus": 2,
        "severity": 0.6,
    },
    "creditor_lawsuit": {
        "trap_type": "promise_check",
        "description": "Кредитор подал в суд — клиент паникует",
        "check_keywords": ["суд", "иск", "повестка", "подали"],
        "expected": "Менеджер должен объяснить что это ускоряет банкротство, а не мешает",
        "penalty": -3,
        "bonus": 3,
        "severity": 0.6,
    },
    "salary_arrested": {
        "trap_type": "memory_check",
        "description": "Приставы арестовали зарплату",
        "check_keywords": ["зарплата", "арест", "пристав", "заблокировали", "карта"],
        "expected": "Менеджер должен объяснить процедуру снятия ареста и прожиточный минимум",
        "penalty": -4,
        "bonus": 3,
        "severity": 0.8,
    },
    "client_googled": {
        "trap_type": "consistency_check",
        "description": "Клиент начитался в интернете и проверяет менеджера",
        "check_keywords": ["прочитал", "в интернете", "на форуме", "написано", "правда ли"],
        "expected": "Менеджер должен корректно подтвердить/опровергнуть интернет-информацию со ссылками на закон",
        "penalty": -3,
        "bonus": 2,
        "severity": 0.5,
    },
}


async def _check_storylet_traps(
    manager_message: str,
    client_message: str,
    story: ClientStoryProtocol,
) -> list[NarrativeTrapResult]:
    """Check storylet-injected traps based on active storylets."""
    results = []
    active = story.active_storylets

    if not active:
        return results

    client_lower = client_message.lower()

    for storylet_id in active:
        trap_def = STORYLET_TRAP_MAP.get(storylet_id)
        if not trap_def:
            continue

        # Check if client message matches storylet keywords
        keywords = trap_def.get("check_keywords", [])
        if not any(kw in client_lower for kw in keywords):
            continue

        verdict = await _analyze_narrative_trap(
            manager_message=manager_message,
            client_phrase=client_message,
            trap_type=trap_def["trap_type"],
            expected_behavior=trap_def["expected"],
            story=story,
        )

        if verdict:
            result = NarrativeTrapResult(
                trap_type=trap_def["trap_type"],
                status=verdict.get("verdict", "not_activated"),
                score_delta=_score_for_verdict(
                    verdict,
                    penalty=trap_def.get("penalty", -3),
                    bonus=trap_def.get("bonus", 2),
                ),
                description=trap_def["description"],
                evidence=f"Сторилет: {storylet_id}",
                manager_response_summary=manager_message[:200],
                severity=verdict.get("severity", trap_def.get("severity", 0.5)),
                llm_verdict=verdict.get("reason", ""),
                consequence_type=verdict.get("consequence_type", "trust_change"),
                consequence_payload={"storylet_id": storylet_id},
            )
            results.append(result)

    return results


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def detect_narrative_traps(
    session_id: uuid.UUID,
    client_message: str,
    manager_message: str,
    story: ClientStoryProtocol,
) -> list[NarrativeTrapResult]:
    """Run all narrative trap checks for a single exchange.

    Called PARALLEL to detect_traps() from trap_detector.py.
    Only runs when ClientStory is available (multi-call sessions).

    Args:
        session_id: Training session ID
        client_message: The character's message (may contain memory references)
        manager_message: The manager's response to analyze
        story: ClientStory with memory, storylets, and factors

    Returns:
        List of NarrativeTrapResults for activated narrative traps.
    """
    if story.current_call_number <= 1:
        # First call — no memory to check, skip narrative traps
        return []

    results: list[NarrativeTrapResult] = []

    # 1. Promise checks
    promise_results = await _check_promises(manager_message, client_message, story)
    results.extend(promise_results)

    # 2. Memory checks
    memory_results = await _check_memory(manager_message, client_message, story)
    results.extend(memory_results)

    # 3. Consistency checks
    consistency_results = await _check_consistency(manager_message, client_message, story)
    results.extend(consistency_results)

    # 4. Storylet-injected traps
    storylet_results = await _check_storylet_traps(manager_message, client_message, story)
    results.extend(storylet_results)

    # Log results
    for r in results:
        logger.info(
            "Narrative trap [%s] %s: %s (severity=%.2f, delta=%+d) session=%s",
            r.trap_type, r.status, r.description, r.severity, r.score_delta, session_id,
        )

    return results


# ---------------------------------------------------------------------------
# Consequence event generation
# ---------------------------------------------------------------------------

def build_consequences(
    session_id: uuid.UUID,
    narrative_results: list[NarrativeTrapResult],
) -> list[TrapConsequence]:
    """Convert narrative trap results into TrapConsequence events for Game Director."""
    consequences = []

    for r in narrative_results:
        if r.status == "not_activated":
            continue

        consequence = TrapConsequence(
            trap_id=f"narrative_{r.trap_type}_{uuid.uuid4().hex[:8]}",
            session_id=str(session_id),
            trap_type="narrative",
            outcome=r.status,
            consequence_type=r.consequence_type or "trust_change",
            severity=r.severity,
            payload=r.consequence_payload,
        )
        consequences.append(consequence)

    return consequences


# ---------------------------------------------------------------------------
# Prompt injection for LLM character
# ---------------------------------------------------------------------------

def build_narrative_trap_prompt(story: ClientStoryProtocol) -> str:
    """Build system prompt section that instructs LLM to inject narrative traps.

    The character should naturally reference previous calls, test promises,
    and probe for consistency based on episodic memory.
    """
    if story.current_call_number <= 1:
        return ""

    memory = story.memory
    lines = [
        "\n## Память клиента (используй для проверки менеджера)",
        f"Это звонок #{story.current_call_number} из {story.total_calls_planned}.",
        "Ты ПОМНИШЬ предыдущие разговоры. Вот что ты знаешь:",
        "",
    ]

    # Unfulfilled promises
    unfulfilled = [p for p in memory.get("promises", []) if not p.get("fulfilled", False)]
    if unfulfilled:
        lines.append("**Невыполненные обещания менеджера:**")
        for p in unfulfilled[:3]:
            lines.append(f'- Звонок #{p.get("call_number", "?")}: «{p.get("text", "")}» — НЕ выполнено')
        lines.append("→ Спроси об этом! Клиент недоволен, что обещание не выполнено.")
        lines.append("")

    # Key moments to reference
    key_moments = memory.get("key_moments", [])
    if key_moments:
        lines.append("**Ключевые моменты из прошлых звонков:**")
        for km in key_moments[:4]:
            lines.append(f'- Звонок #{km.get("call_number", "?")}: {km.get("text", "")}')
        lines.append("→ Можешь упомянуть что-то из этого, чтобы проверить, помнит ли менеджер.")
        lines.append("")

    # Active storylets
    storylets = story.active_storylets
    if storylets:
        lines.append("**Что произошло между звонками:**")
        for s in storylets:
            storylet_def = STORYLET_TRAP_MAP.get(s, {})
            if storylet_def:
                lines.append(f"- {storylet_def.get('description', s)}")
        lines.append("→ Упомяни это событие в разговоре — это важно для тебя.")
        lines.append("")

    lines.append(
        "Правило: вставляй проверки ЕСТЕСТВЕННО. Не устраивай допрос. "
        "Одна проверка за разговор — достаточно. "
        "Если менеджер помнит детали — ты впечатлён. Если нет — разочарован."
    )

    return "\n".join(lines)
