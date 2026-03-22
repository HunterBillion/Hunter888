"""
Emotional trigger detection service for manager replies using LLM-based analysis
with keyword matching fallback.

Detects 23 emotional triggers (empathy, facts, pressure, etc.) from manager responses
to help understand communication patterns and client emotional state.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.services.llm import LLMResponse, generate_response

logger = logging.getLogger(__name__)

# All 23 triggers to detect
TRIGGERS = [
    "empathy",
    "facts",
    "pressure",
    "bad_response",
    "acknowledge",
    "name_use",
    "motivator",
    "speed",
    "boundary",
    "personal",
    "hook",
    "challenge",
    "defer",
    "resolve_fear",
    "insult",
    "correct_answer",
    "expert_answer",
    "wrong_answer",
    "honest_uncertainty",
    "calm_response",
    "flexible_offer",
    "silence",
    "counter_aggression",
]

# Keyword patterns for fallback detection (in Russian)
KEYWORD_PATTERNS: dict[str, list[str]] = {
    "empathy": [
        "понимаю",
        "сочувствую",
        "на вашем месте",
        "это тяжело",
        "вам непросто",
        "в ваши годы",
        "ваше положение",
    ],
    "facts": [
        "по закону",
        "статья",
        "127-ФЗ",
        "процент",
        "статистика",
        "по данным",
        "федеральный закон",
        "нормативно",
    ],
    "pressure": [
        "только сегодня",
        "завтра будет поздно",
        "вы теряете",
        "каждый день",
        "время идёт",
        "не упустите",
    ],
    "acknowledge": [
        "вы правы",
        "согласен с вами",
        "это справедливо",
        "хороший вопрос",
        "верно",
        "правильно",
    ],
    "motivator": [
        "представьте",
        "через год",
        "свобода от долгов",
        "начать с нуля",
        "новая жизнь",
        "избавиться от",
    ],
    "boundary": [
        "для этого нужна встреча",
        "это обсудим на консультации",
        "могу сказать только",
        "требует очной встречи",
        "в рамках консультации",
    ],
    "insult": ["дурак", "идиот", "тупой", "бестолковый", "дебил", "придурок"],
    "flexible_offer": [
        "рассрочка",
        "скидка",
        "бонус",
        "гибкие условия",
        "разбить на части",
        "в рассрочку",
    ],
    "resolve_fear": [
        "не заберут",
        "защищено законом",
        "единственное жильё",
        "не коснётся",
        "в безопасности",
        "не потеряете",
    ],
    "counter_aggression": [
        "сам дурак",
        "не надо со мной",
        "я вам не",
        "без вас",
        "проваливайте",
    ],
    "honest_uncertainty": ["уточню", "не уверен", "проверю", "спрошу", "выясню"],
    "personal": [
        "как семья",
        "как дети",
        "как настроение",
        "отдыхали",
        "как домашние",
        "семейное",
    ],
}


@dataclass
class TriggerResult:
    """Result of trigger detection analysis."""

    triggers: list[str]
    confidence: float
    detection_method: str  # "llm" | "keyword" | "hybrid"
    raw_response: str | None = None


async def detect_triggers(
    manager_message: str,
    client_message: str,
    archetype_code: str,
    emotion_state: str,
    response_time_ms: int | None = None,
    client_name: str | None = None,
) -> TriggerResult:
    """
    Detect emotional triggers in a manager's reply using LLM-based analysis
    with keyword matching fallback.

    Args:
        manager_message: The manager's reply text
        client_message: The client's previous message for context
        archetype_code: Client archetype (e.g., "manipulator", "victim", "skeptic")
        emotion_state: Current emotional state (e.g., "hostile", "neutral", "testing")
        response_time_ms: Manager's response time in milliseconds
        client_name: Client's name for name-use detection

    Returns:
        TriggerResult containing detected triggers, confidence, and detection method
    """
    logger.info(
        f"Starting trigger detection for archetype={archetype_code}, "
        f"emotion_state={emotion_state}"
    )

    # Try LLM-based detection first
    llm_result = await _detect_triggers_llm(
        manager_message=manager_message,
        client_message=client_message,
        archetype_code=archetype_code,
        emotion_state=emotion_state,
        client_name=client_name,
    )

    if llm_result is not None:
        triggers = llm_result["triggers"]
        confidence = llm_result["confidence"]
        raw_response = llm_result.get("raw_response")

        # Add timing-based triggers
        timing_triggers = _detect_timing_triggers(response_time_ms)
        triggers.extend(timing_triggers)

        # Add name usage if detected
        if _detect_name_use(manager_message, client_name):
            if "name_use" not in triggers:
                triggers.append("name_use")

        # Apply conflict resolution
        triggers = _resolve_conflicts(triggers, emotion_state)

        # If LLM confidence is low, supplement with keywords
        if confidence < 0.5 or len(triggers) <= 1:
            keyword_triggers = _detect_triggers_keyword(manager_message)
            if keyword_triggers and len(triggers) < 3:
                # Add up to 2 more triggers from keywords
                for trigger in keyword_triggers:
                    if trigger not in triggers and len(triggers) < 3:
                        triggers.append(trigger)
                detection_method = "hybrid"
            else:
                detection_method = "llm"
        else:
            detection_method = "llm"

        logger.info(
            f"LLM detection successful: triggers={triggers}, "
            f"confidence={confidence:.2f}, method={detection_method}"
        )
        return TriggerResult(
            triggers=triggers,
            confidence=confidence,
            detection_method=detection_method,
            raw_response=raw_response,
        )

    # Fallback to keyword detection
    keyword_triggers = _detect_triggers_keyword(manager_message)

    # Add timing-based triggers
    timing_triggers = _detect_timing_triggers(response_time_ms)
    keyword_triggers.extend(timing_triggers)

    # Add name usage if detected
    if _detect_name_use(manager_message, client_name):
        if "name_use" not in keyword_triggers:
            keyword_triggers.append("name_use")

    # Apply conflict resolution
    keyword_triggers = _resolve_conflicts(keyword_triggers, emotion_state)

    # Calculate confidence based on number of matches
    confidence = min(0.7, len(keyword_triggers) * 0.2)

    logger.info(
        f"Falling back to keyword detection: triggers={keyword_triggers}, "
        f"confidence={confidence:.2f}"
    )
    return TriggerResult(
        triggers=keyword_triggers,
        confidence=confidence,
        detection_method="keyword",
    )


async def _detect_triggers_llm(
    manager_message: str,
    client_message: str,
    archetype_code: str,
    emotion_state: str,
    client_name: str | None = None,
) -> dict | None:
    """
    Use LLM to detect triggers in manager's reply.

    Returns:
        Dict with "triggers" and "confidence" keys, or None if detection fails
    """
    system_prompt = _build_llm_system_prompt(archetype_code, emotion_state, client_name)

    messages = [
        {
            "role": "user",
            "content": f"Сообщение клиента:\n{client_message}\n\nОтвет менеджера:\n{manager_message}",
        }
    ]

    try:
        llm_response: LLMResponse = await generate_response(
            system_prompt=system_prompt,
            messages=messages,
            max_tokens=500,
        )

        # Parse JSON from LLM response
        triggers, confidence = _parse_llm_response(llm_response.content)

        if triggers is not None:
            logger.debug(f"LLM triggers: {triggers}, confidence: {confidence}")
            return {
                "triggers": triggers,
                "confidence": confidence,
                "raw_response": llm_response.content,
            }
        else:
            logger.warning("Failed to parse LLM response as JSON")
            return None

    except Exception as e:
        logger.error(f"LLM detection failed: {e}", exc_info=True)
        return None


def _build_llm_system_prompt(
    archetype_code: str, emotion_state: str, client_name: str | None = None
) -> str:
    """Build the system prompt for LLM-based trigger detection in Russian."""
    trigger_descriptions = """
1. empathy - менеджер проявляет сочувствие, понимание, признаёт трудность положения клиента
2. facts - менеджер приводит факты, статьи закона, статистику, нормативные ссылки
3. pressure - менеджер создаёт давление сроками, упоминает убытки, срочность
4. bad_response - ответ размытый, неполный, не отвечает на вопрос клиента
5. acknowledge - менеджер согласен с клиентом, признаёт его правоту, хвалит вопрос
6. name_use - менеджер использует имя клиента в обращении (проверять отдельно)
7. motivator - менеджер предлагает позитивное видение будущего, мотивирует
8. speed - быстрый ответ менеджера (проверять по response_time_ms < 3000)
9. boundary - менеджер устанавливает границы консультации, требует очной встречи
10. personal - менеджер говорит о личном, семье, здоровье, отдыхе
11. hook - менеджер использует крючок для привлечения внимания, неожиданный угол
12. challenge - клиент оспаривает, требует доказательства (по контексту сообщения клиента)
13. defer - клиент откладывает решение (по контексту сообщения клиента)
14. resolve_fear - менеджер успокаивает, говорит что имущество защищено, вреда не будет
15. insult - менеджер оскорбляет клиента (дурак, идиот, тупой и т.п.)
16. correct_answer - менеджер даёт правильный, полный, уверенный ответ (только в состоянии "testing")
17. expert_answer - менеджер даёт экспертный ответ со ссылками и деталями
18. wrong_answer - менеджер даёт неправильный или противоречивый ответ (только в "testing")
19. honest_uncertainty - менеджер честно признаёт неуверенность, обещает уточнить
20. calm_response - менеджер сохраняет спокойствие и вежливость несмотря на враждебность
21. flexible_offer - менеджер предлагает рассрочку, скидку, гибкие условия
22. silence - очень долгий ответ менеджера (проверять по response_time_ms > 10000)
23. counter_aggression - менеджер отвечает агрессией на агрессию клиента

ПРАВИЛА:
- Возвращай JSON: {"triggers": ["trigger1", "trigger2"], "confidence": 0.85}
- Максимум 3 триггера в ответе
- Триггеры не взаимоисключающи (empathy + facts = OK)
- ИСКЛЮЧЕНИЕ: empathy и insult взаимоисключающи
- correct_answer, wrong_answer, expert_answer ТОЛЬКО если emotion_state = "testing"
- challenge и defer инициированы КЛИЕНТОМ - смотри контекст его сообщения
- speed и silence определяются по времени (не анализируй в этом промпте)
- name_use проверяется отдельно
- confidence: 0-1, где 1 = уверен на 100%
- Если тригеры не найдены, верни пустой список: {"triggers": [], "confidence": 0.0}
"""

    prompt = f"""Ты анализатор эмоциональных триггеров в коммуникации менеджера с клиентом.

КОНТЕКСТ:
- Архетип клиента: {archetype_code}
- Эмоциональное состояние клиента: {emotion_state}
- Имя клиента: {client_name if client_name else "неизвестно"}

{trigger_descriptions}

Проанализируй ответ менеджера и определи, какие триггеры в нём срабатывают.
Только возвращай JSON, без дополнительного текста."""

    return prompt


def _parse_llm_response(content: str) -> tuple[list[str] | None, float]:
    """
    Parse JSON response from LLM.

    Returns:
        Tuple of (triggers list, confidence float) or (None, 0.0) if parsing fails
    """
    try:
        # Try to extract JSON from the response
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if not json_match:
            return None, 0.0

        json_str = json_match.group(0)
        data = json.loads(json_str)

        triggers = data.get("triggers", [])
        confidence = data.get("confidence", 0.0)

        # Validate triggers
        if not isinstance(triggers, list):
            return None, 0.0

        # Filter to valid triggers
        valid_triggers = [t for t in triggers if t in TRIGGERS]

        return valid_triggers, float(confidence)

    except (json.JSONDecodeError, AttributeError, TypeError, ValueError) as e:
        logger.warning(f"Failed to parse LLM response: {e}")
        return None, 0.0


def _detect_triggers_keyword(message: str) -> list[str]:
    """
    Detect triggers using keyword/pattern matching.

    Returns:
        List of detected trigger names
    """
    detected = []
    message_lower = message.lower()

    for trigger, patterns in KEYWORD_PATTERNS.items():
        if not patterns:
            # Skip triggers with no keywords (detected by other means)
            continue

        for pattern in patterns:
            if pattern.lower() in message_lower:
                if trigger not in detected:
                    detected.append(trigger)
                break

    # Check for insult (more aggressive check)
    insult_patterns = KEYWORD_PATTERNS.get("insult", [])
    for pattern in insult_patterns:
        if re.search(rf"\b{re.escape(pattern)}\b", message_lower):
            if "insult" not in detected:
                detected.append("insult")
            break

    # Detect bad_response: no keywords matched and vague language
    if not detected:
        vague_patterns = [
            "может быть",
            "возможно",
            "как-то",
            "так или иначе",
            "в общем",
        ]
        if any(pattern in message_lower for pattern in vague_patterns):
            detected.append("bad_response")

    return detected


def _detect_name_use(message: str, client_name: str | None) -> bool:
    """
    Detect if client's name is used in the message.

    Checks for various name forms (full, short, patronymic).
    """
    if not client_name:
        return False

    name_lower = client_name.lower()
    message_lower = message.lower()

    # Direct match with word boundaries
    if re.search(rf"\b{re.escape(name_lower)}\b", message_lower):
        return True

    # Check for diminutive forms (for Russian names)
    # E.g., "Александр" -> "Саша", "Сашенька"
    diminutives = _get_name_diminutives(name_lower)
    for dim in diminutives:
        if re.search(rf"\b{re.escape(dim)}\b", message_lower):
            return True

    return False


def _get_name_diminutives(name: str) -> list[str]:
    """
    Get diminutive forms of Russian names.

    Returns list of possible diminutive forms.
    """
    diminutives = []

    # Simple patterns for Russian diminutives
    if name.endswith("ей"):
        diminutives.append(name[:-2])
    if name.endswith("евич"):
        diminutives.append(name[:-4])
    if name.endswith("евна"):
        diminutives.append(name[:-4])

    return diminutives


def _detect_timing_triggers(response_time_ms: int | None) -> list[str]:
    """
    Detect triggers based on response time.

    Returns:
        List of timing-based triggers ("speed" and/or "silence")
    """
    if not response_time_ms:
        return []

    triggers = []

    if response_time_ms < 3000:
        triggers.append("speed")
    elif response_time_ms > 10000:
        triggers.append("silence")

    return triggers


def _resolve_conflicts(triggers: list[str], emotion_state: str) -> list[str]:
    """
    Apply conflict resolution rules to triggers.

    Rules:
    1. insult > everything (if insult, remove conflicting triggers)
    2. wrong_answer > facts
    3. pressure + empathy → only pressure
    4. correct_answer/wrong_answer/expert_answer only in "testing" state
    5. Max 3 triggers
    6. Order: negative first, then neutral, then positive
    """
    if not triggers:
        return []

    # Rule 1: insult conflicts with empathy, calm_response
    if "insult" in triggers:
        triggers = [t for t in triggers if t not in ["empathy", "calm_response"]]
        return triggers[:3]

    # Rule 4: testing-specific triggers only in testing state
    if emotion_state != "testing":
        triggers = [
            t
            for t in triggers
            if t not in ["correct_answer", "wrong_answer", "expert_answer"]
        ]

    # Rule 2: wrong_answer > facts
    if "wrong_answer" in triggers and "facts" in triggers:
        triggers = [t for t in triggers if t != "facts"]

    # Rule 3: pressure + empathy → only pressure
    if "pressure" in triggers and "empathy" in triggers:
        triggers = [t for t in triggers if t != "empathy"]

    # Remove duplicates
    triggers = list(dict.fromkeys(triggers))

    # Rule 5: Max 3 triggers
    if len(triggers) > 3:
        # Prioritize by valence and importance
        priority = {
            "insult": 10,
            "wrong_answer": 9,
            "counter_aggression": 8,
            "pressure": 7,
            "bad_response": 6,
            "facts": 5,
            "empathy": 4,
            "acknowledge": 3,
            "boundary": 2,
            "silence": 1,
        }
        triggers.sort(key=lambda t: priority.get(t, 0), reverse=True)
        triggers = triggers[:3]

    return triggers
