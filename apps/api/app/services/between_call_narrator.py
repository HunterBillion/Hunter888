"""Between-Call Intelligence: LLM-powered narrative generation.

Replaces hardcoded random.choice() messages with contextual,
AI-generated content for multi-call story arcs.

Three main capabilities:
1. Dynamic client messages — state/relationship/memory-aware
2. Pre-call coaching tips — manager-weakness-targeted advice
3. Between-call narrative — what happened in the "time gap" between calls

All LLM calls are optional and fallback to template-based generation
if LLM is unavailable or rate-limited.
"""

import logging
import random
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class NarratorContext:
    """All context needed to generate between-call content."""
    # Story state
    lifecycle_state: str = "FIRST_CONTACT"
    relationship_score: float = 50.0
    call_number: int = 1
    total_calls: int = 3

    # Character
    archetype_code: str = "skeptic"
    client_name: str = "Клиент"
    # H4 (Roadmap Phase 0 §5.1): gender-aware persona label. "unknown"
    # (a.k.a. data we haven't collected) falls back to a neutral noun
    # phrase so the prompt doesn't mix masculine and feminine forms.
    gender: str = "unknown"  # "male" | "female" | "unknown"

    # Previous call
    last_outcome: str = "unknown"
    last_emotion: str = "cold"
    last_score: float = 0.0

    # Memories and events
    key_memories: list[dict] = field(default_factory=list)
    active_storylets: list[str] = field(default_factory=list)
    active_consequences: list[dict] = field(default_factory=list)
    between_events: list[dict] = field(default_factory=list)

    # Manager data (for coaching)
    manager_weak_points: list[str] = field(default_factory=list)
    manager_strong_points: list[str] = field(default_factory=list)

    # Story chapter context (Путь Охотника)
    chapter_id: int = 1
    chapter_name: str = ""
    epoch_name: str = ""


@dataclass
class NarratorResult:
    """Output from the narrator."""
    client_message: str | None = None
    coaching_tips: list[str] = field(default_factory=list)
    narrative_summary: str = ""
    emotional_forecast: str = ""
    suggested_opener: str = ""
    source: str = "template"  # "llm" or "template"


# ---------------------------------------------------------------------------
# Archetype personality hints for LLM prompt
# ---------------------------------------------------------------------------

# H4 (Roadmap Phase 0 §5.1): grammatical gender matters in Russian —
# ``agrsеsивн[ый/ая]`` differs by ending, and an AI client labelled with
# the wrong one breaks immersion immediately. Store the root adjective
# per archetype plus the gendered agreement; ``trait_for`` stitches them
# at render time. ``unknown`` gender uses a noun-phrase fallback
# ("клиент с <свойство>") that works regardless of grammatical gender.
_ARCHETYPE_TRAITS: dict[str, dict[str, str]] = {
    "skeptic": {
        "male": "скептичный, требует доказательств, не верит на слово",
        "female": "скептичная, требует доказательств, не верит на слово",
        "neutral": "клиент со скептическим настроем, требует доказательств, не верит на слово",
    },
    "anxious": {
        "male": "тревожный, боится последствий, нервничает при упоминании суда",
        "female": "тревожная, боится последствий, нервничает при упоминании суда",
        "neutral": "клиент с тревожностью, боится последствий, нервничает при упоминании суда",
    },
    "aggressive": {
        "male": "агрессивный, давит, перебивает, повышает голос",
        "female": "агрессивная, давит, перебивает, повышает голос",
        "neutral": "клиент с агрессивным настроем, давит, перебивает, повышает голос",
    },
    "passive": {
        "male": "пассивный, молчит, отвечает односложно, не инициирует",
        "female": "пассивная, молчит, отвечает односложно, не инициирует",
        "neutral": "клиент пассивного склада, молчит, отвечает односложно, не инициирует",
    },
    "pragmatic": {
        "male": "прагматичный, считает деньги, сравнивает варианты",
        "female": "прагматичная, считает деньги, сравнивает варианты",
        "neutral": "клиент с прагматичным подходом, считает деньги, сравнивает варианты",
    },
    "manipulator": {
        "male": "манипулятивный, давит на жалость, перекручивает слова",
        "female": "манипулятивная, давит на жалость, перекручивает слова",
        "neutral": "клиент со склонностью к манипуляции, давит на жалость, перекручивает слова",
    },
    "paranoid": {
        "male": "параноидальный, подозревает мошенничество, не доверяет",
        "female": "параноидальная, подозревает мошенничество, не доверяет",
        "neutral": "клиент с параноидальным настроем, подозревает мошенничество, не доверяет",
    },
    "ashamed": {
        "male": "стыдится ситуации, избегает темы долгов",
        "female": "стыдится ситуации, избегает темы долгов",
        "neutral": "клиент стыдится ситуации, избегает темы долгов",
    },
    "desperate": {
        "male": "отчаянный, готов на всё, торопит процесс",
        "female": "отчаянная, готова на всё, торопит процесс",
        "neutral": "клиент в отчаянии, готов на всё, торопит процесс",
    },
    "sarcastic": {
        "male": "саркастичный, язвит, провоцирует, подшучивает",
        "female": "саркастичная, язвит, провоцирует, подшучивает",
        "neutral": "клиент с саркастичной подачей, язвит, провоцирует, подшучивает",
    },
    "know_it_all": {
        "male": "всезнайка, читал в интернете, спорит с юристом",
        "female": "всезнайка, читала в интернете, спорит с юристом",
        "neutral": "клиент-всезнайка, читал в интернете, спорит с юристом",
    },
    "negotiator": {
        "male": "переговорщик, торгуется по каждому пункту",
        "female": "переговорщица, торгуется по каждому пункту",
        "neutral": "клиент-переговорщик, торгуется по каждому пункту",
    },
    "overwhelmed": {
        "male": "подавленный, растерянный, не может сосредоточиться",
        "female": "подавленная, растерянная, не может сосредоточиться",
        "neutral": "клиент в подавленном состоянии, растерян, не может сосредоточиться",
    },
    "hostile": {
        "male": "враждебный, озлоблен, обвиняет менеджера",
        "female": "враждебная, озлоблена, обвиняет менеджера",
        "neutral": "клиент с враждебным настроем, озлоблен, обвиняет менеджера",
    },
    "grateful": {
        "male": "благодарный, вежливый, ценит помощь",
        "female": "благодарная, вежливая, ценит помощь",
        "neutral": "клиент благодарного склада, вежливый, ценит помощь",
    },
}

_NEUTRAL_FALLBACK = "клиент с нейтральной подачей"


def trait_for(archetype_code: str, gender: str | None = None) -> str:
    """Return the gender-agreed trait string for ``archetype_code``.

    ``gender`` accepts ``"male"``/``"female"``; any other value (including
    ``None``, ``"unknown"``) maps to the gender-neutral noun-phrase
    variant so the output never mixes forms.
    """
    variants = _ARCHETYPE_TRAITS.get(archetype_code)
    if not variants:
        return _NEUTRAL_FALLBACK
    key = gender if gender in ("male", "female") else "neutral"
    return variants.get(key) or variants.get("neutral") or _NEUTRAL_FALLBACK

# Storylet narrative hints for context enrichment
_STORYLET_CONTEXT: dict[str, str] = {
    "wife_found_out": "Жена клиента узнала о долгах. Семейное давление.",
    "collectors_arrived": "К клиенту приходили коллекторы. Клиент напуган.",
    "court_order_received": "Клиент получил судебный приказ. Срочность выросла.",
    "salary_garnishment": "Из зарплаты удерживают средства. Финансовое давление.",
    "positive_precedent": "Клиент узнал об успешном банкротстве знакомого.",
    "friend_recommended_lawyer": "Другу порекомендовали другого юриста.",
    "debt_penalty_increase": "Пени по долгу выросли. Ситуация ухудшается.",
    "job_loss": "Клиент потерял работу. Финансовое положение критическое.",
    "manager_empathy_detected": "Клиент почувствовал искреннюю заботу менеджера.",
    "bank_restructuring_offer": "Банк предложил реструктуризацию долга.",
}


# ---------------------------------------------------------------------------
# LLM-based generation
# ---------------------------------------------------------------------------

async def generate_client_message_llm(ctx: NarratorContext) -> str | None:
    """Generate a contextual client message via LLM.

    Returns None if LLM is unavailable — caller should fallback to template.
    """
    try:
        from app.services.llm import generate_response
    except ImportError:
        return None

    # Build compact system prompt
    trait = trait_for(ctx.archetype_code, ctx.gender)
    storylet_hints = " ".join(
        _STORYLET_CONTEXT.get(s, "") for s in ctx.active_storylets[:3]
    ).strip()

    memory_context = ""
    if ctx.key_memories:
        mem_items = [m.get("content", "") for m in ctx.key_memories[:3] if m.get("content")]
        if mem_items:
            memory_context = f"Клиент помнит: {'; '.join(mem_items)}."

    event_context = ""
    if ctx.between_events:
        evt_items = [e.get("description", e.get("event", "")) for e in ctx.between_events[:3]]
        if evt_items:
            event_context = f"Между звонками произошло: {'; '.join(evt_items)}."

    system_prompt = f"""Ты — {ctx.client_name}, клиент с долгами, обдумывающий банкротство.
Характер: {trait}.
Состояние: {ctx.lifecycle_state}. Доверие к менеджеру: {ctx.relationship_score:.0f}/100.
Это после звонка #{ctx.call_number} из {ctx.total_calls}. Предыдущий звонок закончился: {ctx.last_emotion}.
{memory_context}
{event_context}
{storylet_hints}

Напиши ОДНО короткое сообщение (1-3 предложения, как в мессенджере) менеджеру между звонками.
Стиль: разговорный, как реальный человек пишет в WhatsApp/Telegram.
НЕ используй формальные обороты. НЕ используй «Уважаемый». Пиши как живой человек.
Отрази своё текущее эмоциональное состояние и уровень доверия."""

    try:
        response = await generate_response(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": "Напиши сообщение менеджеру."}],
            emotion_state=ctx.last_emotion,
            task_type="simple",
            prefer_provider="local",
        )
        text = response.content.strip()
        # Clean up: remove quotes, limit length
        text = text.strip('"«»""\'')
        if len(text) > 500:
            text = text[:497] + "..."
        return text if text else None
    except Exception as e:
        logger.debug("LLM client message generation failed: %s", e)
        return None


async def generate_coaching_tips_llm(ctx: NarratorContext) -> list[str] | None:
    """Generate personalized coaching tips for the manager before next call.

    Returns None if LLM unavailable.
    """
    try:
        from app.services.llm import generate_response
    except ImportError:
        return None

    if not ctx.manager_weak_points and ctx.relationship_score >= 70:
        # S3-10: No weak points and doing well — return None (not []).
        # Empty list [] is falsy in Python, so the fallback at the call site
        # would incorrectly trigger template generation. None signals "skip coaching"
        # explicitly, while [] meant "LLM returned nothing" → should fall back.
        return None

    weak_str = ", ".join(ctx.manager_weak_points[:3]) if ctx.manager_weak_points else "не определены"
    trait = trait_for(ctx.archetype_code, ctx.gender)

    system_prompt = f"""Ты — AI-коуч для менеджеров по банкротству.
Менеджер готовится к звонку #{ctx.call_number + 1} с клиентом ({trait}).
Доверие: {ctx.relationship_score:.0f}/100. Состояние клиента: {ctx.lifecycle_state}.
Предыдущий звонок: эмоция = {ctx.last_emotion}, результат = {ctx.last_outcome}, балл = {ctx.last_score:.0f}.
Слабые стороны менеджера: {weak_str}.

Дай 2-3 КОНКРЕТНЫХ совета для следующего звонка.
Каждый совет — 1 предложение. Формат: пронумерованный список.
Советы должны быть практичными и учитывать конкретную ситуацию.
НЕ давай общих советов типа "будьте вежливы". Давай конкретику."""

    try:
        response = await generate_response(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": "Дай советы для следующего звонка."}],
            task_type="coach",
            prefer_provider="cloud",
        )
        text = response.content.strip()
        # Parse numbered list
        tips = []
        for line in text.split("\n"):
            line = line.strip()
            cleaned = re.sub(r"^\d+[.)]\s*", "", line).strip()
            if cleaned and len(cleaned) > 10:
                tips.append(cleaned)
        return tips[:3] if tips else None
    except Exception as e:
        logger.debug("LLM coaching tips generation failed: %s", e)
        return None


async def generate_narrative_summary_llm(ctx: NarratorContext) -> str | None:
    """Generate a narrative summary of what happened between calls.

    Creates an immersive "time gap" description for the frontend.
    """
    try:
        from app.services.llm import generate_response
    except ImportError:
        return None

    if not ctx.between_events and not ctx.active_storylets:
        return None

    event_descs = [
        e.get("description", e.get("event", "")) for e in ctx.between_events[:4]
    ]
    storylet_descs = [
        _STORYLET_CONTEXT.get(s, s) for s in ctx.active_storylets[:2]
    ]
    all_events = [d for d in event_descs + storylet_descs if d]

    if not all_events:
        return None

    chapter_line = ""
    if ctx.chapter_name and ctx.epoch_name:
        chapter_line = f"\nМенеджер на Главе {ctx.chapter_id}: '{ctx.chapter_name}' (Эпоха: {ctx.epoch_name}). Учитывай это в тоне повествования.\n"

    system_prompt = f"""Ты — нарратор игры-тренажёра по банкротству.
Между звонками с клиентом прошло время. Произошли события:
{chr(10).join(f'- {e}' for e in all_events)}

Клиент: {ctx.client_name}, {trait_for(ctx.archetype_code, ctx.gender)}.
Доверие: {ctx.relationship_score:.0f}/100.
{chapter_line}
Напиши КРАТКОЕ (2-3 предложения) повествование от третьего лица о том,
что происходило с клиентом между звонками.
Стиль: нарративный, как в игре. НЕ используй списки. Создай атмосферу."""

    try:
        response = await generate_response(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": "Что произошло между звонками?"}],
            task_type="simple",
            prefer_provider="local",
        )
        text = response.content.strip()
        if len(text) > 800:
            text = text[:797] + "..."
        return text if text else None
    except Exception as e:
        logger.debug("LLM narrative summary generation failed: %s", e)
        return None


async def generate_suggested_opener_llm(ctx: NarratorContext) -> str | None:
    """Suggest an opening phrase for the manager to start the next call.

    Based on previous call outcome and current client state.
    """
    try:
        from app.services.llm import generate_response
    except ImportError:
        return None

    trait = trait_for(ctx.archetype_code, ctx.gender)

    system_prompt = f"""Ты — AI-коуч. Менеджер начинает звонок #{ctx.call_number + 1} с клиентом.
Клиент: {trait}. Доверие: {ctx.relationship_score:.0f}/100.
Предыдущий звонок закончился: {ctx.last_emotion}.
Текущий этап: {ctx.lifecycle_state}.

Предложи ОДНУ фразу-открывашку (1-2 предложения), с которой менеджер может начать звонок.
Фраза должна учитывать предыдущий контекст и быть естественной."""

    try:
        response = await generate_response(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": "Как лучше начать звонок?"}],
            task_type="simple",
            prefer_provider="local",
        )
        text = response.content.strip().strip('"«»""\'')
        return text[:300] if text else None
    except Exception as e:
        logger.debug("LLM suggested opener generation failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Template-based fallback (no LLM needed)
# ---------------------------------------------------------------------------

def generate_coaching_tips_template(ctx: NarratorContext) -> list[str]:
    """Generate coaching tips from templates when LLM is unavailable."""
    tips = []

    # Emotion-specific advice
    if ctx.last_emotion in ("hostile", "hangup"):
        tips.append(
            "Клиент был враждебен. Начните с извинения за неудобства "
            "и покажите, что вы на его стороне."
        )
    elif ctx.last_emotion == "cold":
        tips.append(
            "Клиент ещё не заинтересован. Задайте открытый вопрос о его "
            "ситуации, не давите с решением."
        )
    elif ctx.last_emotion in ("curious", "considering"):
        tips.append(
            "Клиент проявляет интерес. Предложите конкретный следующий шаг "
            "(документы, расчёт, встреча)."
        )

    # Relationship-specific
    if ctx.relationship_score < 30:
        tips.append(
            "Доверие очень низкое. Сфокусируйтесь на эмпатии, не на продаже. "
            "Покажите, что понимаете его ситуацию."
        )
    elif ctx.relationship_score > 75:
        tips.append(
            "Доверие высокое. Можно переходить к конкретным действиям: "
            "сбору документов и началу процедуры."
        )

    # Weak-point advice
    _weak_advice = {
        "objection_handling": "Подготовьте ответы на типичные возражения: цена, сроки, последствия.",
        "closing": "Не забудьте предложить конкретный следующий шаг в конце звонка.",
        "legal_knowledge": "Освежите знание статей 127-ФЗ, клиент может задать юридические вопросы.",
        "communication": "Слушайте больше, чем говорите. Задавайте уточняющие вопросы.",
        "empathy": "Начните с вопроса «Как у вас дела?» и дайте клиенту выговориться.",
    }
    for wp in ctx.manager_weak_points[:2]:
        advice = _weak_advice.get(wp)
        if advice and advice not in tips:
            tips.append(advice)

    # Storylet-specific
    for s in ctx.active_storylets[:1]:
        if s == "wife_found_out":
            tips.append("Жена узнала о долгах. Предложите семейную консультацию.")
        elif s == "collectors_arrived":
            tips.append("Были коллекторы. Объясните, что банкротство останавливает взыскание.")
        elif s == "court_order_received":
            tips.append("Есть судебный приказ. Это срочно — объясните механизм его отмены.")

    return tips[:3]


def generate_emotional_forecast(ctx: NarratorContext) -> str:
    """Predict likely client emotional state for next call."""
    if ctx.last_emotion in ("hostile", "hangup"):
        if ctx.relationship_score > 50:
            return "guarded"  # Recovery possible
        return "hostile"  # Still angry

    if ctx.last_emotion in ("deal", "negotiating"):
        return "considering"  # Progressing

    if ctx.last_emotion in ("curious", "considering"):
        if ctx.relationship_score > 60:
            return "negotiating"  # Ready to move forward
        return "curious"  # Still exploring

    # Default: slightly warmer than last time if relationship improved
    emotion_progression = {
        "cold": "guarded",
        "guarded": "curious",
        "testing": "guarded",
        "callback": "curious",
    }
    return emotion_progression.get(ctx.last_emotion, ctx.last_emotion)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def generate_between_call_content(ctx: NarratorContext) -> NarratorResult:
    """Main entry point: generate all between-call content.

    Tries LLM first, falls back to templates if unavailable.
    Uses concurrent generation for speed.
    """
    result = NarratorResult()
    result.emotional_forecast = generate_emotional_forecast(ctx)

    # Only generate content for call 2+
    if ctx.call_number < 1:
        result.source = "template"
        return result

    # Try LLM-based generation (fire all in parallel for speed)
    import asyncio

    llm_msg, llm_tips, llm_narrative, llm_opener = await asyncio.gather(
        generate_client_message_llm(ctx),
        generate_coaching_tips_llm(ctx),
        generate_narrative_summary_llm(ctx),
        generate_suggested_opener_llm(ctx),
        return_exceptions=True,
    )

    # Client message
    if isinstance(llm_msg, str) and llm_msg:
        result.client_message = llm_msg
        result.source = "llm"
    # (template fallback handled by game_director._generate_client_message)

    # S3-10: Coaching tips — handle None (skip) vs Exception vs list vs empty
    # FIX-4 (v13): asyncio.gather(return_exceptions=True) returns Exception
    # objects as values — handle them explicitly before the type checks.
    if isinstance(llm_tips, BaseException):
        logger.debug("LLM coaching tips raised: %s", llm_tips)
        llm_tips = None  # Treat as LLM failure → template fallback

    if llm_tips is None:
        # LLM decided to skip coaching (high score, no weak points) — no tips
        result.coaching_tips = []
    elif isinstance(llm_tips, list) and len(llm_tips) > 0:
        result.coaching_tips = llm_tips
        result.source = "llm"
    else:
        # LLM returned empty — fall back to templates
        result.coaching_tips = generate_coaching_tips_template(ctx)

    # Narrative summary
    if isinstance(llm_narrative, str) and llm_narrative:
        result.narrative_summary = llm_narrative
        result.source = "llm"

    # Suggested opener
    if isinstance(llm_opener, str) and llm_opener:
        result.suggested_opener = llm_opener

    return result
