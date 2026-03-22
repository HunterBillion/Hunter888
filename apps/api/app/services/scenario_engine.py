"""Scenario engine v5 — scenario selection, session config, prompt building, stage directions.

Functions (v2 original):
- select_scenario: pick scenario template by manager level + preferences
- generate_session_config: build full session config (archetype, chain, traps, difficulty)
- build_scenario_prompt: inject scenario/stage/awareness into LLM system prompt
- track_stage_progress: determine current conversation stage from message index

Functions (v5 new):
- parse_stage_directions_v2: two-pass parser for v1+v2 stage direction tags
- apply_between_calls_context: generate CRM events between calls
- generate_session_report: auto-generate post-call report via small LLM
- generate_pre_call_brief: build manager-facing pre-call brief

Uses canonical lists:
- 25 archetypes (see ArchetypeCode in models/roleplay.py)
- 15 scenarios (see ScenarioCode in models/scenario.py)
- 10 emotion states: cold, guarded, curious, considering, negotiating, deal, testing, callback, hostile, hangup
"""

import logging
import random
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scenario import ScenarioCode, ScenarioTemplate
from app.models.reputation import ReputationTier, TIER_MIN_DIFFICULTY
from app.services.reputation import (
    calculate_emotion_weight_shift,
    shift_emotion_weights,
    _score_to_tier,
)

logger = logging.getLogger(__name__)


# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class SessionConfig:
    """Full configuration for a training session generated from a scenario template."""
    scenario_code: str
    scenario_name: str
    template_id: uuid.UUID
    # Selected client profile params
    archetype: str
    initial_emotion: str
    client_awareness: str
    client_motivation: str
    # Chains and traps
    recommended_chains: list[dict] = field(default_factory=list)
    active_traps: list[str] = field(default_factory=list)
    traps_count: int = 1
    cascades_count: int = 0
    # Stages
    stages: list[dict] = field(default_factory=list)
    # Scoring
    scoring_modifiers: list[dict] = field(default_factory=list)
    difficulty: int = 5
    # Prompts
    awareness_prompt: str = ""
    stage_skip_reactions: dict = field(default_factory=dict)
    client_prompt_template: str = ""
    # Duration
    target_outcome: str = "meeting"
    typical_duration_minutes: int = 8
    max_duration_minutes: int = 15


@dataclass
class StageInfo:
    """Current stage info returned by track_stage_progress."""
    order: int
    name: str
    description: str
    manager_goals: list[str]
    manager_mistakes: list[str]
    expected_emotion_range: list[str]
    emotion_red_flag: str
    is_required: bool
    is_final: bool


# ─── Difficulty → scenario group mapping ─────────────────────────────────────

# Manager level 1-3 → easier scenarios, 4-7 → medium, 8-10 → hard + special
_LEVEL_SCENARIO_GROUPS: dict[str, list[str]] = {
    "beginner": [
        ScenarioCode.cold_ad.value,
        ScenarioCode.warm_callback.value,
        ScenarioCode.in_website.value,
        ScenarioCode.in_hotline.value,
    ],
    "intermediate": [
        ScenarioCode.cold_ad.value,
        ScenarioCode.cold_base.value,
        ScenarioCode.cold_referral.value,
        ScenarioCode.warm_callback.value,
        ScenarioCode.warm_noanswer.value,
        ScenarioCode.warm_refused.value,
        ScenarioCode.in_website.value,
        ScenarioCode.in_hotline.value,
        ScenarioCode.in_social.value,
    ],
    "advanced": [v.value for v in ScenarioCode],  # All 15
}

# Difficulty thresholds for manager levels 1-10
_LEVEL_TO_GROUP = {
    1: "beginner", 2: "beginner", 3: "beginner",
    4: "intermediate", 5: "intermediate", 6: "intermediate", 7: "intermediate",
    8: "advanced", 9: "advanced", 10: "advanced",
}


# ─── Core functions ──────────────────────────────────────────────────────────

async def select_scenario(
    db: AsyncSession,
    manager_level: int = 5,
    preferences: Optional[dict] = None,
    reputation_score: Optional[float] = None,
) -> ScenarioTemplate:
    """Select a scenario template based on manager level, reputation, and preferences.

    Args:
        db: Database session
        manager_level: Manager skill level 1-10
        preferences: Optional dict with keys:
            - scenario_code: str — force specific scenario
            - group: str — filter by group (A_outbound_cold, B_outbound_warm, etc.)
            - exclude_codes: list[str] — recently played scenarios to avoid
            - difficulty_range: tuple[int, int] — min/max difficulty
        reputation_score: Manager reputation score 0-100 (if available).
            Used to enforce minimum difficulty by reputation tier:
            Стажёр(0-20)→min 1, Менеджер(21-40)→min 2, Старший(41-60)→min 3,
            Эксперт(61-80)→min 5, Хантер(81-100)→min 6.

    Returns:
        ScenarioTemplate object

    Raises:
        ValueError: if no matching scenario found
    """
    preferences = preferences or {}

    # Force specific scenario code
    if forced_code := preferences.get("scenario_code"):
        result = await db.execute(
            select(ScenarioTemplate).where(
                ScenarioTemplate.code == forced_code,
                ScenarioTemplate.is_active == True,  # noqa: E712
            )
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise ValueError(f"Scenario '{forced_code}' not found or inactive")
        return template

    # Build query with filters
    query = select(ScenarioTemplate).where(ScenarioTemplate.is_active == True)  # noqa: E712

    # Filter by manager-level appropriate scenarios
    level_clamped = max(1, min(10, manager_level))
    group_key = _LEVEL_TO_GROUP[level_clamped]
    allowed_codes = _LEVEL_SCENARIO_GROUPS[group_key]
    query = query.where(ScenarioTemplate.code.in_(allowed_codes))

    # ── Reputation-based minimum difficulty ──
    if reputation_score is not None:
        tier = _score_to_tier(reputation_score)
        min_diff = TIER_MIN_DIFFICULTY.get(tier, 1)
        query = query.where(ScenarioTemplate.difficulty >= min_diff)
        logger.debug("Reputation %.1f → tier=%s → min_difficulty=%d",
                      reputation_score, tier.value, min_diff)

    # Filter by scenario group if specified
    if group_filter := preferences.get("group"):
        query = query.where(ScenarioTemplate.group_name == group_filter)

    # Exclude recently played
    if exclude_codes := preferences.get("exclude_codes"):
        query = query.where(ScenarioTemplate.code.notin_(exclude_codes))

    # Difficulty range (explicit override takes precedence)
    if diff_range := preferences.get("difficulty_range"):
        d_min, d_max = diff_range
        query = query.where(
            ScenarioTemplate.difficulty >= d_min,
            ScenarioTemplate.difficulty <= d_max,
        )

    result = await db.execute(query)
    templates = list(result.scalars().all())

    if not templates:
        # Fallback: any active scenario (ignore reputation filter)
        logger.warning("No scenario matched filters, falling back to any active")
        result = await db.execute(
            select(ScenarioTemplate).where(ScenarioTemplate.is_active == True)  # noqa: E712
        )
        templates = list(result.scalars().all())

    if not templates:
        raise ValueError("No active scenario templates found in database")

    # Weighted random selection by difficulty proximity to manager level
    weights = []
    for t in templates:
        diff_delta = abs(t.difficulty - level_clamped)
        w = max(1.0, 10.0 - diff_delta * 2)
        weights.append(w)

    return random.choices(templates, weights=weights, k=1)[0]


def generate_session_config(
    template: ScenarioTemplate,
    manager_level: int = 5,
    reputation_score: Optional[float] = None,
) -> SessionConfig:
    """Generate a full session configuration from a scenario template.

    Randomly selects:
    - Client archetype (weighted by template.archetype_weights)
    - Initial emotion variant (weighted by template.initial_emotion_variants,
      shifted by reputation if available)
    - Number of traps (within template range)
    - Active trap categories

    Args:
        template: ScenarioTemplate from database
        manager_level: Manager skill level 1-10 (adjusts difficulty)
        reputation_score: Manager reputation 0-100. If provided, shifts initial
            emotion weights: high reputation → clients start warmer,
            low reputation → clients start colder.

    Returns:
        SessionConfig ready for session creation
    """
    # ── Select archetype (weighted random) ──
    weights_dict: dict = template.archetype_weights or {}
    archetypes = [k for k, v in weights_dict.items() if v > 0]
    arch_weights = [weights_dict[k] for k in archetypes]

    if archetypes:
        archetype = random.choices(archetypes, weights=arch_weights, k=1)[0]
    else:
        archetype = "skeptic"  # fallback

    # ── Select initial emotion (with reputation-based weight shifting) ──
    emotion_variants: dict = template.initial_emotion_variants or {}
    if emotion_variants:
        # Apply reputation shift if available
        if reputation_score is not None:
            modifier = calculate_emotion_weight_shift(reputation_score)
            shifted = shift_emotion_weights(emotion_variants, modifier)
            logger.debug("Emotion weights shifted: reputation=%.1f modifier=%.2f "
                         "original=%s shifted=%s",
                         reputation_score, modifier, emotion_variants, shifted)
        else:
            shifted = emotion_variants

        emotions = list(shifted.keys())
        emo_weights = list(shifted.values())
        initial_emotion = random.choices(emotions, weights=emo_weights, k=1)[0]
    else:
        initial_emotion = template.initial_emotion or "cold"

    # ── Select trap count and categories ──
    traps_min = template.traps_count_min or 1
    traps_max = template.traps_count_max or 2
    # Higher manager level → more traps
    level_bonus = max(0, (manager_level - 5) // 2)
    trap_count = min(traps_max, random.randint(traps_min, traps_max) + level_bonus)

    trap_pool: list = template.trap_pool_categories or []
    active_traps = random.sample(trap_pool, min(trap_count, len(trap_pool))) if trap_pool else []

    # ── Difficulty adjustment ──
    base_difficulty = template.difficulty or 5
    adjusted_difficulty = max(1, min(10, base_difficulty + (manager_level - 5) // 3))

    # ── Build config ──
    return SessionConfig(
        scenario_code=template.code,
        scenario_name=template.name,
        template_id=template.id,
        archetype=archetype,
        initial_emotion=initial_emotion,
        client_awareness=template.client_awareness or "zero",
        client_motivation=template.client_motivation or "none",
        recommended_chains=template.recommended_chains or [],
        active_traps=active_traps,
        traps_count=trap_count,
        cascades_count=template.cascades_count or 0,
        stages=template.stages or [],
        scoring_modifiers=template.scoring_modifiers or [],
        difficulty=adjusted_difficulty,
        awareness_prompt=template.awareness_prompt or "",
        stage_skip_reactions=template.stage_skip_reactions or {},
        client_prompt_template=template.client_prompt_template or "",
        target_outcome=template.target_outcome or "meeting",
        typical_duration_minutes=template.typical_duration_minutes or 8,
        max_duration_minutes=template.max_duration_minutes or 15,
    )


def build_scenario_prompt(config: SessionConfig, current_stage_order: int = 1) -> str:
    """Build scenario-specific prompt sections for LLM system prompt injection.

    Returns a string with three sections:
    - ## Сценарий — call type, context, and target
    - ## Текущий этап разговора — goals, mistakes, emotion range
    - ## Осведомлённость клиента — awareness level and behavioral instructions

    Args:
        config: SessionConfig from generate_session_config
        current_stage_order: 1-based stage index

    Returns:
        Formatted prompt string to append to system prompt
    """
    parts = []

    # ── Section 1: Scenario overview ──
    parts.append(
        f"## Сценарий: {config.scenario_name}\n"
        f"Код сценария: {config.scenario_code}\n"
        f"Целевой результат: {_outcome_label(config.target_outcome)}\n"
        f"Сложность: {config.difficulty}/10\n"
        f"Максимальная длительность: {config.max_duration_minutes} мин."
    )

    # ── Section 2: Current stage ──
    stage = _find_stage(config.stages, current_stage_order)
    if stage:
        goals_text = "\n".join(f"  • {g}" for g in stage.get("manager_goals", []))
        mistakes_text = "\n".join(f"  ✗ {m}" for m in stage.get("manager_mistakes", []))
        emotions = ", ".join(stage.get("expected_emotion_range", []))

        parts.append(
            f"## Текущий этап разговора: {stage['name']} (этап {current_stage_order})\n"
            f"{stage.get('description', '')}\n\n"
            f"Цели менеджера на этом этапе:\n{goals_text}\n\n"
            f"Типичные ошибки менеджера:\n{mistakes_text}\n\n"
            f"Ожидаемый диапазон эмоций клиента: {emotions}\n"
            f"Красный флаг (критическая эмоция): {stage.get('emotion_red_flag', 'hangup')}"
        )
    else:
        parts.append(
            "## Текущий этап: свободная беседа\n"
            "Все основные этапы пройдены. Веди разговор естественно."
        )

    # ── Section 3: Client awareness ──
    awareness_text = _awareness_description(config.client_awareness)
    parts.append(
        f"## Осведомлённость клиента: {config.client_awareness}\n"
        f"{awareness_text}"
    )

    # ── Section 4: Awareness prompt (scenario-specific) ──
    if config.awareness_prompt:
        parts.append(
            f"## Дополнительные инструкции по сценарию\n"
            f"{config.awareness_prompt}"
        )

    # ── Section 5: Stage-skip reactions ──
    if config.stage_skip_reactions:
        skip_lines = []
        for skip_key, reaction in config.stage_skip_reactions.items():
            skip_lines.append(f"  — Если менеджер пропустил «{skip_key}»: \"{reaction}\"")
        parts.append(
            "## Реакции на пропуск этапов\n"
            "Если менеджер пропускает важный этап разговора, используй эти реплики:\n"
            + "\n".join(skip_lines)
        )

    # ── Section 6: Client prompt template (if set) ──
    if config.client_prompt_template:
        parts.append(
            "## Шаблон поведения клиента\n"
            + config.client_prompt_template
        )

    return "\n\n---\n\n".join(parts)


def track_stage_progress(
    stages: list[dict],
    message_index: int,
    total_expected_messages: int = 12,
) -> StageInfo:
    """Determine the current conversation stage based on message index.

    Uses proportional mapping: each stage occupies a fraction of total messages
    based on its duration_min/duration_max relative to total conversation time.

    Args:
        stages: List of stage dicts from SessionConfig.stages
        message_index: 0-based index of the current message pair (user + assistant = 1)
        total_expected_messages: Expected total message pairs for the conversation

    Returns:
        StageInfo for the current stage
    """
    if not stages:
        return StageInfo(
            order=1, name="Свободная беседа", description="Нет этапов",
            manager_goals=[], manager_mistakes=[],
            expected_emotion_range=["cold"], emotion_red_flag="hangup",
            is_required=False, is_final=True,
        )

    sorted_stages = sorted(stages, key=lambda s: s.get("order", 0))

    # Calculate proportional boundaries
    total_duration = sum(
        (s.get("duration_min", 1) + s.get("duration_max", 2)) / 2
        for s in sorted_stages
    )
    if total_duration == 0:
        total_duration = len(sorted_stages)

    # Map message index to a stage
    cumulative = 0.0
    progress = message_index / max(1, total_expected_messages)

    for i, stage in enumerate(sorted_stages):
        avg_dur = (stage.get("duration_min", 1) + stage.get("duration_max", 2)) / 2
        stage_fraction = avg_dur / total_duration
        cumulative += stage_fraction

        if progress < cumulative or i == len(sorted_stages) - 1:
            return StageInfo(
                order=stage.get("order", i + 1),
                name=stage.get("name", f"Этап {i + 1}"),
                description=stage.get("description", ""),
                manager_goals=stage.get("manager_goals", []),
                manager_mistakes=stage.get("manager_mistakes", []),
                expected_emotion_range=stage.get("expected_emotion_range", ["cold"]),
                emotion_red_flag=stage.get("emotion_red_flag", "hangup"),
                is_required=stage.get("required", True),
                is_final=(i == len(sorted_stages) - 1),
            )

    # Fallback (should not reach here)
    last = sorted_stages[-1]
    return StageInfo(
        order=last.get("order", len(sorted_stages)),
        name=last.get("name", "Последний этап"),
        description=last.get("description", ""),
        manager_goals=last.get("manager_goals", []),
        manager_mistakes=last.get("manager_mistakes", []),
        expected_emotion_range=last.get("expected_emotion_range", []),
        emotion_red_flag=last.get("emotion_red_flag", "hangup"),
        is_required=last.get("required", True),
        is_final=True,
    )


# ─── Internal helpers ────────────────────────────────────────────────────────

def _find_stage(stages: list[dict], order: int) -> Optional[dict]:
    """Find stage by order number."""
    for s in stages:
        if s.get("order") == order:
            return s
    return None


def _outcome_label(outcome: str) -> str:
    """Russian label for target outcome."""
    labels = {
        "meeting": "Записать на консультацию",
        "callback": "Договориться о перезвоне",
        "payment": "Получить оплату",
        "qualification": "Квалифицировать клиента",
        "retention": "Удержать клиента",
        "upsell": "Продать доп. услугу",
    }
    return labels.get(outcome, outcome)


def _awareness_description(level: str) -> str:
    """Return behavioral description for client awareness level."""
    descriptions = {
        "zero": (
            "Клиент НЕ знает что такое банкротство физических лиц.\n"
            "Поведение: задаёт базовые вопросы (\"а что это?\", \"как это работает?\"), "
            "путает с банкротством юрлиц, боится слова \"банкрот\", думает что это позор.\n"
            "НЕ используй профессиональные термины без пояснения."
        ),
        "low": (
            "Клиент слышал о банкротстве, но имеет неполную/искажённую информацию.\n"
            "Поведение: \"Я читал в интернете...\", ссылается на мифы (заберут квартиру, "
            "не выпустят за границу навсегда, испортят кредитную историю навечно).\n"
            "Корректируй мифы мягко, ссылайся на 127-ФЗ."
        ),
        "medium": (
            "Клиент уже консультировался или читал про 127-ФЗ.\n"
            "Поведение: знает про реструктуризацию и реализацию, задаёт конкретные вопросы "
            "про сроки и стоимость, может сравнивать с другими компаниями.\n"
            "Общайся как с подготовленным клиентом, не объясняй базу."
        ),
        "high": (
            "Клиент глубоко разбирается, возможно консультировался с юристом.\n"
            "Поведение: оперирует статьями закона, знает про ст. 446 ГПК РФ, "
            "задаёт сложные вопросы про практику, может ловить на некомпетентности.\n"
            "Будь точен в цифрах и ссылках на закон."
        ),
        "mixed": (
            "Знания клиента неравномерны — в чём-то разбирается, в чём-то полный ноль.\n"
            "Поведение: может задать сложный вопрос, а затем примитивный, "
            "путается в терминах, но требует подробностей.\n"
            "Адаптируй уровень объяснений по ходу разговора."
        ),
    }
    return descriptions.get(level, descriptions["zero"])


def get_stage_skip_reaction(config: SessionConfig, skipped_stage: str) -> Optional[str]:
    """Get client's reaction phrase when manager skips a stage.

    Args:
        config: Current session config
        skipped_stage: Stage key that was skipped (e.g., 'greeting_skip', 'qualification_skip')

    Returns:
        Reaction phrase or None if no reaction configured
    """
    return config.stage_skip_reactions.get(skipped_stage)


def estimate_total_messages(config: SessionConfig) -> int:
    """Estimate the total expected message pairs for the session.

    Uses typical_reply_count_min/max from template or derives from stage durations.
    """
    stages = config.stages or []
    if not stages:
        return 10

    # Sum average durations, assume ~1.5 message pairs per minute
    total_min_time = sum(s.get("duration_min", 1) for s in stages)
    total_max_time = sum(s.get("duration_max", 2) for s in stages)
    avg_time = (total_min_time + total_max_time) / 2
    return max(6, int(avg_time * 1.5))


# ===========================================================================
# v5: Stage direction parsing — two-pass with fuzzy fallback
# ===========================================================================

@dataclass
class ParsedStageDirection:
    """Result of parsing a single stage direction tag."""
    direction_type: str        # "emotion_trigger", "trap", "memory", "storylet", "consequence", "factor"
    raw_tag: str               # Original text: "[MEMORY:Обещал скидку]"
    payload: dict              # Parsed payload: {"content": "Обещал скидку", "salience": 5}
    confidence: float = 1.0    # 1.0 for exact match, <1.0 for fuzzy

# v1 tag patterns (existing)
_V1_PATTERNS = {
    "emotion_trigger": re.compile(r"\[emotion_trigger:([^\]]+)\]", re.IGNORECASE),
    "trap": re.compile(r"\[trap:([^\]]+)\]", re.IGNORECASE),
    "action": re.compile(r"\*([^*]+)\*"),
}

# v2 tag patterns (new)
_V2_PATTERNS = {
    "memory": re.compile(
        r"\[MEMORY:([^\]]+)\]", re.IGNORECASE
    ),
    "storylet": re.compile(
        r"\[STORYLET:([^\]]+)\]", re.IGNORECASE
    ),
    "consequence": re.compile(
        r"\[CONSEQUENCE:([^\]]+)\]", re.IGNORECASE
    ),
    "factor": re.compile(
        r"\[FACTOR:([^\]]+)\]", re.IGNORECASE
    ),
}

# Fuzzy fallback patterns for when LLM outputs imperfect tags
_FUZZY_PATTERNS = {
    "memory": re.compile(
        r"\[(?:MEMO(?:RY)?|ПАМЯТЬ|ЗАПОМН)[:\s]([^\]]+)\]", re.IGNORECASE
    ),
    "storylet": re.compile(
        r"\[(?:STORY(?:LET)?|СЮЖЕТ|ИСТОРИЯ)[:\s]([^\]]+)\]", re.IGNORECASE
    ),
    "consequence": re.compile(
        r"\[(?:CONSEQ(?:UENCE)?|ПОСЛЕДСТВ)[:\s]([^\]]+)\]", re.IGNORECASE
    ),
    "factor": re.compile(
        r"\[(?:FACT(?:OR)?|ФАКТОР)[:\s]([^\]]+)\]", re.IGNORECASE
    ),
}


def parse_stage_directions_v2(text: str) -> tuple[str, list[ParsedStageDirection]]:
    """Two-pass stage direction parser.

    Pass 1: Exact pattern matching (v1 + v2 tags)
    Pass 2: Fuzzy fallback for imperfect LLM outputs

    Returns:
        (clean_text, directions) — text with all stage directions stripped,
        and list of parsed direction objects.
    """
    directions: list[ParsedStageDirection] = []
    found_spans: list[tuple[int, int]] = []  # Track matched spans to avoid double-match

    # ── Pass 1: Exact matching ──
    # v1 tags
    for dtype, pattern in _V1_PATTERNS.items():
        for match in pattern.finditer(text):
            payload = _parse_v1_payload(dtype, match.group(1).strip())
            directions.append(ParsedStageDirection(
                direction_type=dtype,
                raw_tag=match.group(0),
                payload=payload,
                confidence=1.0,
            ))
            found_spans.append((match.start(), match.end()))

    # v2 tags
    for dtype, pattern in _V2_PATTERNS.items():
        for match in pattern.finditer(text):
            payload = _parse_v2_payload(dtype, match.group(1).strip())
            directions.append(ParsedStageDirection(
                direction_type=dtype,
                raw_tag=match.group(0),
                payload=payload,
                confidence=1.0,
            ))
            found_spans.append((match.start(), match.end()))

    # ── Pass 2: Fuzzy fallback ──
    for dtype, pattern in _FUZZY_PATTERNS.items():
        for match in pattern.finditer(text):
            # Skip if already matched in pass 1
            span = (match.start(), match.end())
            if any(_spans_overlap(span, fs) for fs in found_spans):
                continue
            payload = _parse_v2_payload(dtype, match.group(1).strip())
            directions.append(ParsedStageDirection(
                direction_type=dtype,
                raw_tag=match.group(0),
                payload=payload,
                confidence=0.7,  # Lower confidence for fuzzy match
            ))
            found_spans.append(span)
            logger.info("Fuzzy match for %s: '%s'", dtype, match.group(0))

    # ── Strip all matched tags from text ──
    clean_text = text
    # Sort spans in reverse order to avoid offset shifts
    for start, end in sorted(found_spans, reverse=True):
        clean_text = clean_text[:start] + clean_text[end:]

    # Clean up extra whitespace left by stripping
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()

    return clean_text, directions


def _spans_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _parse_v1_payload(dtype: str, content: str) -> dict:
    """Parse payload for v1 stage direction types."""
    if dtype == "emotion_trigger":
        return {"target_emotion": content}
    elif dtype == "trap":
        return {"trap_name": content}
    elif dtype == "action":
        return {"description": content}
    return {"raw": content}


def _parse_v2_payload(dtype: str, content: str) -> dict:
    """Parse payload for v2 stage direction types.

    Supports structured content with optional key=value pairs:
    [MEMORY:Обещал скидку|salience=8|type=promise]
    [CONSEQUENCE:trust_broken|severity=0.8]
    [FACTOR:fatigue|intensity=0.7]
    [STORYLET:creditor_pressure|trigger=anxiety]
    """
    parts = content.split("|")
    main_content = parts[0].strip()
    kwargs = {}

    for part in parts[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip()
            v = v.strip()
            # Try to parse numeric values
            try:
                v = float(v) if "." in v else int(v)
            except ValueError:
                pass
            kwargs[k] = v

    if dtype == "memory":
        return {
            "content": main_content,
            "salience": kwargs.get("salience", 5),
            "type": kwargs.get("type", "fact"),
            "valence": kwargs.get("valence", 0.0),
        }
    elif dtype == "storylet":
        return {
            "storylet_id": main_content,
            "trigger": kwargs.get("trigger", ""),
            "description": kwargs.get("desc", main_content),
        }
    elif dtype == "consequence":
        return {
            "type": main_content,
            "severity": kwargs.get("severity", 0.5),
            "detail": kwargs.get("detail", ""),
        }
    elif dtype == "factor":
        return {
            "factor": main_content,
            "intensity": kwargs.get("intensity", 0.5),
            "duration": kwargs.get("duration", "call"),  # "call" | "story"
        }
    return {"raw": content}


# ===========================================================================
# v5: Between-call context — CRM event simulation
# ===========================================================================

# Pool of possible between-call CRM events
_BETWEEN_CALL_EVENTS = {
    "creditor_called": {
        "description": "Кредитор позвонил клиенту с угрозами",
        "impact": "increased_anxiety",
        "emotion_shift": {"N": 0.1, "P": -0.2, "A": 0.15},
        "probability_by_call": {2: 0.4, 3: 0.5, 4: 0.6},
    },
    "client_googled_bankruptcy": {
        "description": "Клиент загуглил информацию о банкротстве",
        "impact": "increased_knowledge",
        "emotion_shift": {"O": 0.1, "P": 0.05},
        "probability_by_call": {2: 0.6, 3: 0.3, 4: 0.1},
    },
    "family_discussion": {
        "description": "Клиент обсудил ситуацию с семьёй",
        "impact": "family_pressure",
        "emotion_shift": {"A": 0.1, "N": 0.05},
        "probability_by_call": {2: 0.5, 3: 0.4, 4: 0.3},
    },
    "salary_delayed": {
        "description": "Задержка зарплаты — финансовое давление усилилось",
        "impact": "increased_desperation",
        "emotion_shift": {"N": 0.15, "P": -0.15, "D": -0.1},
        "probability_by_call": {2: 0.2, 3: 0.25, 4: 0.3},
    },
    "found_competitor": {
        "description": "Клиент нашёл предложение от конкурента",
        "impact": "comparison_shopping",
        "emotion_shift": {"O": 0.05, "A": -0.1},
        "probability_by_call": {2: 0.3, 3: 0.4, 4: 0.3},
    },
    "positive_review_seen": {
        "description": "Клиент прочитал положительный отзыв о компании",
        "impact": "increased_trust",
        "emotion_shift": {"P": 0.1, "A": -0.05},
        "probability_by_call": {2: 0.2, 3: 0.3, 4: 0.2},
    },
    "collector_visit": {
        "description": "Коллекторы пришли к клиенту домой",
        "impact": "panic",
        "emotion_shift": {"N": 0.2, "P": -0.3, "A": 0.2, "D": -0.2},
        "probability_by_call": {2: 0.1, 3: 0.15, 4: 0.2},
    },
    "court_letter": {
        "description": "Получил письмо из суда о задолженности",
        "impact": "fear_and_urgency",
        "emotion_shift": {"N": 0.15, "P": -0.2, "A": 0.15},
        "probability_by_call": {3: 0.2, 4: 0.3},
    },
    "friend_went_through": {
        "description": "Знакомый клиента успешно прошёл банкротство",
        "impact": "social_proof",
        "emotion_shift": {"P": 0.15, "O": 0.1, "A": -0.05},
        "probability_by_call": {2: 0.15, 3: 0.2, 4: 0.15},
    },
    "nothing_happened": {
        "description": "Ничего значимого не произошло",
        "impact": "time_decay",
        "emotion_shift": {},
        "probability_by_call": {2: 0.3, 3: 0.2, 4: 0.15},
    },
}


def apply_between_calls_context(
    call_number: int,
    archetype_code: str,
    previous_outcome: str | None = None,
    previous_emotion: str = "cold",
    existing_events: list[dict] | None = None,
) -> list[dict]:
    """Generate simulated CRM events that happened between calls.

    Events are selected probabilistically based on:
    - Call number (more dramatic events in later calls)
    - Archetype (anxious clients more likely to get creditor events)
    - Previous call outcome (positive outcomes reduce negative events)

    Args:
        call_number: The upcoming call number (2, 3, etc.)
        archetype_code: Client's archetype
        previous_outcome: How the last call ended
        previous_emotion: Last emotion state from previous call
        existing_events: Already generated events from earlier calls

    Returns:
        List of new event dicts: [{"event": "...", "impact": "...", "description": "..."}]
    """
    existing_events = existing_events or []
    existing_event_types = {e["event"] for e in existing_events}
    new_events = []

    # Archetype modifiers — increase/decrease probability of certain events
    archetype_modifiers = {
        "anxious": {"creditor_called": 1.5, "collector_visit": 1.3, "court_letter": 1.3},
        "paranoid": {"found_competitor": 1.5, "client_googled_bankruptcy": 1.5},
        "pragmatic": {"client_googled_bankruptcy": 1.5, "found_competitor": 1.3},
        "desperate": {"creditor_called": 1.4, "salary_delayed": 1.5, "collector_visit": 1.5},
        "passive": {"nothing_happened": 1.5, "family_discussion": 0.5},
        "manipulator": {"found_competitor": 1.5, "client_googled_bankruptcy": 1.3},
    }
    arch_mod = archetype_modifiers.get(archetype_code, {})

    # Previous outcome modifiers
    outcome_mod = 1.0
    if previous_outcome in ("deal", "scheduled_meeting"):
        outcome_mod = 0.5  # Good outcomes reduce bad events
    elif previous_outcome in ("hangup", "hostile"):
        outcome_mod = 1.3  # Bad outcomes increase dramatic events

    # Select 1-3 events
    num_events = random.choices([1, 2, 3], weights=[0.4, 0.4, 0.2], k=1)[0]

    candidates = []
    for event_key, event_data in _BETWEEN_CALL_EVENTS.items():
        if event_key in existing_event_types and event_key != "nothing_happened":
            continue  # Don't repeat events
        base_prob = event_data["probability_by_call"].get(call_number, 0.1)
        prob = base_prob * arch_mod.get(event_key, 1.0) * outcome_mod
        candidates.append((event_key, event_data, min(1.0, prob)))

    # Weighted selection without replacement
    for _ in range(num_events):
        if not candidates:
            break
        keys, datas, probs = zip(*candidates)
        total = sum(probs)
        if total == 0:
            break
        normalized = [p / total for p in probs]
        chosen_idx = random.choices(range(len(candidates)), weights=normalized, k=1)[0]
        chosen_key, chosen_data, _ = candidates[chosen_idx]

        # Roll against probability
        if random.random() < probs[chosen_idx]:
            new_events.append({
                "event": chosen_key,
                "impact": chosen_data["impact"],
                "description": chosen_data["description"],
                "emotion_shift": chosen_data.get("emotion_shift", {}),
            })
        candidates.pop(chosen_idx)

    # Ensure at least one event
    if not new_events:
        nothing = _BETWEEN_CALL_EVENTS["nothing_happened"]
        new_events.append({
            "event": "nothing_happened",
            "impact": nothing["impact"],
            "description": nothing["description"],
            "emotion_shift": {},
        })

    return new_events


# ===========================================================================
# v5: Pre-call brief generation
# ===========================================================================

def generate_pre_call_brief(
    call_number: int,
    client_name: str,
    archetype_code: str,
    previous_outcome: str | None,
    previous_emotion: str,
    between_events: list[dict],
    key_memories: list[dict] | None = None,
) -> str:
    """Generate a pre-call brief for the manager before the next call.

    This is shown to the manager in the UI before the call starts,
    giving context about the client's history and what to expect.
    """
    parts = [f"## Бриф перед звонком #{call_number}"]
    parts.append(f"**Клиент:** {client_name} (архетип: {archetype_code})")

    if previous_outcome:
        outcome_labels = {
            "deal": "✅ Согласился на встречу",
            "callback": "📞 Попросил перезвонить",
            "hangup": "❌ Бросил трубку",
            "hostile": "⚠️ Был агрессивен",
            "considering": "🤔 Думает",
            "scheduled_meeting": "✅ Записан на консультацию",
        }
        parts.append(f"**Прошлый звонок:** {outcome_labels.get(previous_outcome, previous_outcome)}")
        parts.append(f"**Последняя эмоция:** {previous_emotion}")

    if between_events:
        parts.append("\n**Что произошло между звонками:**")
        for evt in between_events:
            parts.append(f"  • {evt.get('description', evt.get('event', '?'))}")

    if key_memories:
        parts.append("\n**Ключевые моменты из прошлых звонков:**")
        for mem in key_memories[:5]:  # Top 5 by salience
            parts.append(f"  • {mem.get('content', '?')}")

    # Tactical advice based on context
    parts.append("\n**Рекомендации:**")
    if previous_outcome == "hangup":
        parts.append("  • Начните мягко, извинитесь за предыдущий опыт")
        parts.append("  • Не давите, дайте клиенту высказаться")
    elif previous_outcome == "hostile":
        parts.append("  • Будьте готовы к агрессии, сохраняйте спокойствие")
        parts.append("  • Покажите понимание ситуации клиента")
    elif previous_outcome == "callback":
        parts.append("  • Напомните о предыдущей договорённости")
        parts.append("  • Подготовьте конкретное предложение")

    # Event-specific advice
    for evt in between_events:
        impact = evt.get("impact", "")
        if impact == "panic":
            parts.append("  • ⚠️ Клиент в панике — сначала успокойте, потом предлагайте")
        elif impact == "comparison_shopping":
            parts.append("  • Клиент сравнивает — подчеркните ваши преимущества")
        elif impact == "social_proof":
            parts.append("  • Используйте социальное доказательство — клиент уже слышал о успехе")

    return "\n".join(parts)


# ===========================================================================
# v5: Session report generation
# ===========================================================================

async def generate_session_report(
    messages: list[dict],
    config: SessionConfig,
    score_breakdown: dict | None = None,
    trap_results: list[dict] | None = None,
    emotion_trajectory: list[dict] | None = None,
    call_number: int = 1,
    is_story_final: bool = False,
) -> dict:
    """Generate a structured post-call report via small LLM.

    Args:
        messages: Full conversation history for this call
        config: Session config
        score_breakdown: Per-layer scores if available
        trap_results: List of trap fell/dodged results
        emotion_trajectory: Sequence of emotion state changes
        call_number: Call number within multi-call story
        is_story_final: Whether this is the last call in the story

    Returns:
        Report dict suitable for SessionReport.content JSONB
    """
    from app.services.llm import generate_response

    # Build analysis prompt
    conversation_text = "\n".join(
        f"{'Менеджер' if m['role'] == 'user' else 'Клиент'}: {m['content']}"
        for m in messages
    )

    report_prompt = (
        "Ты — опытный тренер по продажам услуг банкротства физических лиц (127-ФЗ). "
        "Проанализируй следующий разговор менеджера с клиентом и создай структурированный отчёт.\n\n"
        f"Сценарий: {config.scenario_name} (сложность: {config.difficulty}/10)\n"
        f"Архетип клиента: {config.archetype}\n"
        f"Звонок #{call_number}\n\n"
        f"Разговор:\n{conversation_text}\n\n"
        "Создай отчёт в формате JSON со следующими полями:\n"
        '- "summary": краткое описание звонка (2-3 предложения)\n'
        '- "strengths": массив сильных сторон менеджера (2-4 пункта)\n'
        '- "weaknesses": массив слабых сторон (2-4 пункта)\n'
        '- "missed_opportunities": что менеджер упустил (1-3 пункта)\n'
        '- "recommendations": рекомендации на следующий звонок (2-3 пункта)\n'
        '- "key_moments": ключевые моменты [{"seq": N, "type": "тип", "detail": "описание"}]\n'
        "Отвечай ТОЛЬКО JSON, без markdown и пояснений."
    )

    try:
        response = await generate_response(
            system_prompt=report_prompt,
            messages=[{"role": "user", "content": "Проанализируй разговор и создай отчёт."}],
            emotion_state="cold",
            user_id="system:reporter",
        )

        # Try to parse as JSON
        import json
        try:
            report_data = json.loads(response.content)
        except json.JSONDecodeError:
            # LLM didn't return valid JSON — wrap in basic structure
            report_data = {
                "summary": response.content[:500],
                "strengths": [],
                "weaknesses": [],
                "missed_opportunities": [],
                "recommendations": [],
                "key_moments": [],
            }

    except Exception as e:
        logger.error("Failed to generate session report: %s", e)
        report_data = {
            "summary": "Не удалось сгенерировать отчёт автоматически.",
            "strengths": [],
            "weaknesses": [],
            "missed_opportunities": [],
            "recommendations": [],
            "key_moments": [],
            "error": str(e),
        }

    # Enrich with mechanical data
    if score_breakdown:
        report_data["score_breakdown"] = score_breakdown
    if trap_results:
        report_data["trap_results"] = trap_results
    if emotion_trajectory:
        report_data["emotion_trajectory"] = emotion_trajectory

    report_data["call_number"] = call_number
    report_data["scenario"] = config.scenario_code
    report_data["archetype"] = config.archetype
    report_data["is_story_final"] = is_story_final
    report_data["generated_by"] = "llm_auto"

    return report_data
