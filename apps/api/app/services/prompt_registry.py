"""
Prompt Registry — data-driven prompt management (DOC_16).

Loads prompts from DB (prompt_versions table) with Redis caching.
Supports runtime composition: archetype + scenario + emotion → final prompt.
Supports A/B testing via is_active + version fields.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── Prompt Types ────────────────────────────────────────────────────────────

PROMPT_TYPES = [
    "archetype",      # 100 archetype character prompts
    "scenario",       # 8 scenario modifier blocks
    "emotion",        # 30 emotion injections (10 × 3 intensities)
    "compound",       # 8 compound emotion prompts
    "judge",          # PvP judge evaluation prompt
    "personality",    # 6 Knowledge Arena examiners
    "bot",            # 10 PvE bot variants + base
    "template",       # Question generation + answer evaluation templates
]

# ─── Scenario Modifier Keys ──────────────────────────────────────────────────

SCENARIO_MODIFIERS: dict[str, dict[str, str]] = {
    "cold": {
        "key": "scenario_cold_modifier",
        "block": """[SCENARIO_COLD_MODIFIER]
Это ХОЛОДНЫЙ звонок. Клиент НЕ ожидал этого звонка.
ПРАВИЛА:
- Первые 30 секунд критичны — легитимируй звонок
- Клиент может бросить трубку в любой момент
- НЕ переходи к продаже до установления контакта
- Используй hook в первые 2-3 реплики
[/SCENARIO_COLD_MODIFIER]""",
    },
    "warm": {
        "key": "scenario_warm_modifier",
        "block": """[SCENARIO_WARM_MODIFIER]
Это ТЁПЛЫЙ контакт. Клиент уже знает о компании.
ПРАВИЛА:
- Напомни о предыдущем контакте
- Спроси об изменениях в ситуации
- Работай с новыми возражениями
- Двигай по воронке к следующему шагу
[/SCENARIO_WARM_MODIFIER]""",
    },
    "inbound": {
        "key": "scenario_inbound_modifier",
        "block": """[SCENARIO_INBOUND_MODIFIER]
Клиент сам обратился. Он ГОТОВ к разговору.
ПРАВИЛА:
- Быстрая квалификация (не трать время на warming)
- Клиент ожидает экспертизу
- Максимальная эффективность — ценi его время
- Закрытие на конкретное действие (встреча, документы)
[/SCENARIO_INBOUND_MODIFIER]""",
    },
    "crisis": {
        "key": "scenario_crisis_modifier",
        "block": """[SCENARIO_CRISIS_MODIFIER]
Клиент в КРИЗИСЕ. Эмоции на пределе.
ПРАВИЛА:
- СНАЧАЛА стабилизируй эмоциональное состояние
- НЕ продавай, пока клиент не успокоится
- Покажи что ты на его стороне
- Дай конкретный план из 1-2 шагов (не больше)
- Юридическая точность КРИТИЧНА (230-ФЗ, 127-ФЗ)
[/SCENARIO_CRISIS_MODIFIER]""",
    },
    "compliance": {
        "key": "scenario_compliance_modifier",
        "block": """[SCENARIO_COMPLIANCE_MODIFIER]
Клиент проверяет твою юридическую грамотность.
ПРАВИЛА:
- Каждая ссылка на закон должна быть ТОЧНОЙ
- Ошибка в статье = потеря доверия
- Будь готов к сложным вопросам
- НЕ обещай то, что не можешь гарантировать
- Legal accuracy — главный критерий оценки
[/SCENARIO_COMPLIANCE_MODIFIER]""",
    },
    "follow_up": {
        "key": "scenario_follow_up_modifier",
        "block": """[SCENARIO_FOLLOW_UP_MODIFIER]
Это ПОВТОРНЫЙ контакт. Клиент уже знает тебя.
ПРАВИЛА:
- Покажи что помнишь предыдущий разговор
- Предложи НОВУЮ ценность (не повторяй старое)
- Двигай по воронке: звонок→встреча→документы→сделка
- Фиксируй конкретные обязательства с датами
[/SCENARIO_FOLLOW_UP_MODIFIER]""",
    },
    "multi_party": {
        "key": "scenario_multi_party_modifier",
        "block": """[SCENARIO_MULTI_PARTY_MODIFIER]
На звонке НЕСКОЛЬКО участников.
ПРАВИЛА:
- Идентифицируй всех участников и их роли
- Адресуй каждого отдельно
- При разногласиях — медиация, не выбирай сторону
- Закрытие через КОНСЕНСУС, не давление
[/SCENARIO_MULTI_PARTY_MODIFIER]""",
    },
    "special": {
        "key": "scenario_special_modifier",
        "block": """[SCENARIO_SPECIAL_MODIFIER]
Особая ситуация с уникальными правилами.
ПРАВИЛА:
- Адаптируйся к нестандартной ситуации
- Будь гибким — стандартный скрипт может не работать
- Фокус на индивидуальном подходе
[/SCENARIO_SPECIAL_MODIFIER]""",
    },
}


def get_scenario_modifier(scenario_code: str) -> str:
    """Get scenario modifier block for prompt injection."""
    if scenario_code.startswith("cold"):
        return SCENARIO_MODIFIERS["cold"]["block"]
    if scenario_code.startswith("warm"):
        return SCENARIO_MODIFIERS["warm"]["block"]
    if scenario_code.startswith("in_"):
        return SCENARIO_MODIFIERS["inbound"]["block"]
    if scenario_code.startswith("crisis"):
        return SCENARIO_MODIFIERS["crisis"]["block"]
    if scenario_code.startswith("compliance"):
        return SCENARIO_MODIFIERS["compliance"]["block"]
    if scenario_code.startswith("follow_up"):
        return SCENARIO_MODIFIERS["follow_up"]["block"]
    if scenario_code.startswith("multi_party"):
        return SCENARIO_MODIFIERS["multi_party"]["block"]
    return SCENARIO_MODIFIERS["special"]["block"]


# ─── Emotion Injection Templates ─────────────────────────────────────────────

EMOTION_INJECTION_TEMPLATE = """[EMOTION_INJECTION]
Текущее эмоциональное состояние: {state} (интенсивность: {intensity})
{state_description}

Корректировка поведения:
- Голос: {voice_note}
- Реакции: {reaction_note}
[/EMOTION_INJECTION]"""


def build_emotion_injection(state: str, intensity: str, description: str) -> str:
    """Build emotion injection block for prompt."""
    voice_notes = {
        "low": "Спокойный, сдержанный тон",
        "medium": "Умеренно выраженные эмоции",
        "high": "Ярко выраженные эмоции, максимальная интенсивность",
    }
    reaction_notes = {
        "low": "Мягкие реакции, долгие паузы между ответами",
        "medium": "Стандартные реакции с эмоциональной окраской",
        "high": "Мгновенные, резкие реакции, короткие фразы",
    }
    return EMOTION_INJECTION_TEMPLATE.format(
        state=state,
        intensity=intensity,
        state_description=description,
        voice_note=voice_notes.get(intensity, voice_notes["medium"]),
        reaction_note=reaction_notes.get(intensity, reaction_notes["medium"]),
    )


# ─── Runtime Prompt Composition ──────────────────────────────────────────────

def compose_session_prompt(
    archetype_prompt: str,
    scenario_code: str,
    emotion_state: str | None = None,
    emotion_intensity: str | None = None,
    emotion_description: str | None = None,
) -> str:
    """Compose full session system prompt from components.

    Order: archetype_block + scenario_modifier + emotion_injection
    """
    parts = [archetype_prompt]

    # Scenario modifier
    modifier = get_scenario_modifier(scenario_code)
    parts.append(modifier)

    # Emotion injection (optional, added during session)
    if emotion_state and emotion_intensity:
        injection = build_emotion_injection(
            state=emotion_state,
            intensity=emotion_intensity,
            description=emotion_description or "",
        )
        parts.append(injection)

    return "\n\n".join(parts)


# ─── Prompt File Loader (Phase 1: file-based) ───────────────────────────────

PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts" / "characters"


async def load_archetype_prompt_db(
    archetype_code: str,
    version: str = "v2",
    db=None,
) -> str | None:
    """Load archetype prompt from DB (prompt_versions table), fall back to filesystem.

    Priority: DB (active, matching version) → DB (active, any version) → File → None.
    """
    if db is not None:
        try:
            from sqlalchemy import select
            from app.models.prompt_version import PromptVersion

            # Try exact version
            result = await db.execute(
                select(PromptVersion.content)
                .where(
                    PromptVersion.prompt_type == "archetype",
                    PromptVersion.prompt_key == archetype_code,
                    PromptVersion.version == version,
                    PromptVersion.is_active == True,  # noqa: E712
                )
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row:
                return row

            # Try any active version
            result = await db.execute(
                select(PromptVersion.content)
                .where(
                    PromptVersion.prompt_type == "archetype",
                    PromptVersion.prompt_key == archetype_code,
                    PromptVersion.is_active == True,  # noqa: E712
                )
                .order_by(PromptVersion.created_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row:
                return row
        except Exception as exc:
            logger.warning("DB prompt load failed for %s: %s — falling back to file", archetype_code, exc)

    # Fallback: filesystem
    return load_archetype_prompt(archetype_code, version)


def load_archetype_prompt(archetype_code: str, version: str = "v2") -> str | None:
    """Load archetype prompt from file system. Returns None if not found."""
    path = PROMPTS_DIR / f"{archetype_code}_{version}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None
