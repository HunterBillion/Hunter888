"""
Emotion system v6 extensions (DOC_08).

New features layered ON TOP of existing emotion.py:
- IntensityLevel (3 levels per state → 30 sub-states)
- CompoundEmotions (8 display-only overlays)
- MicroExpressions (6 transient flashes, 1-2 messages)
- GraphVariants (10 archetype-group-specific transition graphs)
- 17 new triggers (23→40)

ALL backward-compatible: existing EmotionState enum, MoodBuffer, and
ALLOWED_TRANSITIONS unchanged. New features are optional overlays.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any, Optional


# ═══════════════════════════════════════════════════════════════════════
#  1. INTENSITY SYSTEM
# ═══════════════════════════════════════════════════════════════════════

class IntensityLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def compute_intensity(
    current_energy: float,
    threshold_pos: float,
    threshold_neg: float,
) -> tuple[IntensityLevel, float]:
    """Compute intensity from MoodBuffer energy. Returns (level, normalized 0-1)."""
    active_threshold = threshold_pos if current_energy >= 0 else abs(threshold_neg)
    if active_threshold == 0:
        return IntensityLevel.MEDIUM, 0.5

    normalized = min(1.0, abs(current_energy) / active_threshold)

    if normalized < 0.33:
        return IntensityLevel.LOW, normalized
    elif normalized < 0.66:
        return IntensityLevel.MEDIUM, normalized
    else:
        return IntensityLevel.HIGH, normalized


# Transition threshold jitter by intensity
TRANSITION_JITTER: dict[IntensityLevel, float] = {
    IntensityLevel.LOW: 0.0,
    IntensityLevel.MEDIUM: 0.05,
    IntensityLevel.HIGH: 0.10,
}

# 30 sub-state descriptions (state × intensity)
INTENSITY_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "cold": {"low": "Вялый холод", "medium": "Стена", "high": "Ледяное отвержение"},
    "guarded": {"low": "Лёгкая настороженность", "medium": "Щит поднят", "high": "Полная оборона"},
    "curious": {"low": "Мягкий интерес", "medium": "Активное любопытство", "high": "Горящий интерес"},
    "considering": {"low": "Фоновое обдумывание", "medium": "Активный анализ", "high": "На грани решения"},
    "negotiating": {"low": "Прощупывание", "medium": "Активный торг", "high": "Жёсткие переговоры"},
    "deal": {"low": "Условное согласие", "medium": "Твёрдое решение", "high": "Полная готовность"},
    "testing": {"low": "Мягкая проверка", "medium": "Тест на прочность", "high": "Экзамен"},
    "callback": {"low": "Вежливый уход", "medium": "Реальный интерес к перезвону", "high": "Нетерпеливое ожидание"},
    "hostile": {"low": "Раздражение", "medium": "Открытая враждебность", "high": "Ярость"},
    "hangup": {"low": "Тихий уход", "medium": "Демонстративный бросок", "high": "Скандальный разрыв"},
}


# ═══════════════════════════════════════════════════════════════════════
#  2. COMPOUND EMOTIONS (8 display-only overlays)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class CompoundEmotion:
    code: str
    display_name_ru: str
    base_state: str
    pad_shift: dict[str, float]   # {"P": delta, "A": delta, "D": delta}
    tts_overrides: dict[str, float]
    avatar_animation: str
    priority: int  # 1-9, higher wins


COMPOUND_EMOTIONS: list[CompoundEmotion] = [
    CompoundEmotion("cold_curiosity", "Холодное любопытство", "cold", {"P": 0.1, "A": 0.05, "D": 0}, {"style": -0.05}, "slight_head_tilt", 2),
    CompoundEmotion("resigned_acceptance", "Смирение", "deal", {"P": -0.1, "A": -0.1, "D": -0.2}, {"speed": -0.05, "stability": 0.05}, "slow_nod", 3),
    CompoundEmotion("desperate_hope", "Отчаянная надежда", "callback", {"P": 0.2, "A": 0.15, "D": -0.1}, {"stability": -0.10}, "leaning_forward", 4),
    CompoundEmotion("cautious_interest", "Осторожный интерес", "curious", {"P": 0.05, "A": 0.1, "D": 0.05}, {"speed": -0.03}, "lean_back_crossed_arms", 5),
    CompoundEmotion("grudging_respect", "Вынужденное уважение", "considering", {"P": -0.05, "A": 0.05, "D": 0.1}, {"stability": 0.05}, "nod_with_frown", 6),
    CompoundEmotion("hopeful_anxiety", "Надежда с тревогой", "considering", {"P": 0.1, "A": 0.2, "D": -0.15}, {"stability": -0.10, "speed": 0.05}, "fidgeting", 7),
    CompoundEmotion("fake_warmth", "Притворное тепло", "negotiating", {"P": 0.15, "A": 0, "D": 0.1}, {"style": 0.15, "similarity": 0.05}, "forced_smile", 8),
    CompoundEmotion("volatile_anger", "Взрывная злость", "hostile", {"P": -0.2, "A": 0.3, "D": 0.2}, {"stability": -0.20, "speed": 0.15}, "aggressive_gesture", 9),
]

COMPOUND_MAP: dict[str, CompoundEmotion] = {c.code: c for c in COMPOUND_EMOTIONS}


def detect_compound_emotion(
    current_state: str,
    intensity: IntensityLevel,
    intensity_value: float,
    recent_states: list[str],
    fake_active: bool,
    ocean_profile: dict[str, float] | None = None,
    recent_triggers: list[str] | None = None,
) -> CompoundEmotion | None:
    """Detect if a compound emotion is active. Returns highest-priority match."""
    ocean = ocean_profile or {}
    triggers = recent_triggers or []
    candidates: list[CompoundEmotion] = []

    # cold_curiosity: cold + high Openness
    if current_state == "cold" and ocean.get("O", 0) >= 0.7:
        candidates.append(COMPOUND_MAP["cold_curiosity"])

    # resigned_acceptance: deal + LOW intensity
    if current_state == "deal" and intensity == IntensityLevel.LOW:
        candidates.append(COMPOUND_MAP["resigned_acceptance"])

    # desperate_hope: callback + positive triggers recent
    if current_state == "callback" and sum(1 for t in triggers[-5:] if t in ("empathy", "resolve_fear", "hook")) >= 2:
        candidates.append(COMPOUND_MAP["desperate_hope"])

    # cautious_interest: curious + recent negative trigger
    if current_state == "curious" and any(t in ("pressure", "bad_response") for t in triggers[-3:]):
        candidates.append(COMPOUND_MAP["cautious_interest"])

    # grudging_respect: considering + hostile in recent states + HIGH intensity
    if current_state == "considering" and intensity == IntensityLevel.HIGH and "hostile" in recent_states[-3:]:
        candidates.append(COMPOUND_MAP["grudging_respect"])

    # hopeful_anxiety: considering + high Neuroticism
    if current_state == "considering" and ocean.get("N", 0) >= 0.6 and intensity_value > 0:
        candidates.append(COMPOUND_MAP["hopeful_anxiety"])

    # fake_warmth: negotiating + FakeTransition active
    if current_state == "negotiating" and fake_active:
        candidates.append(COMPOUND_MAP["fake_warmth"])

    # volatile_anger: hostile + oscillation (state changed 3+ times in last 5)
    if current_state == "hostile" and len(set(recent_states[-5:])) >= 3:
        candidates.append(COMPOUND_MAP["volatile_anger"])

    if not candidates:
        return None

    return max(candidates, key=lambda c: c.priority)


# ═══════════════════════════════════════════════════════════════════════
#  3. MICRO-EXPRESSIONS (6 transient flashes)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class MicroExpression:
    code: str
    display_name_ru: str
    trigger_condition: str
    duration_messages: int
    tts_override: dict[str, float]
    avatar_animation: str
    pad_shift: dict[str, float]
    cooldown_messages: int


MICRO_EXPRESSIONS: dict[str, MicroExpression] = {
    "surprise_flash": MicroExpression("surprise_flash", "Вспышка удивления", "hook|facts + energy_delta > 0.3", 1, {"stability": -0.15, "speed": 0.10}, "eyebrow_raise", {"A": 0.2}, 5),
    "anger_spike": MicroExpression("anger_spike", "Вспышка злости", "insult|pressure", 1, {"stability": -0.25, "speed": 0.15, "style": 0.20}, "jaw_clench_flash", {"P": -0.3, "A": 0.2}, 3),
    "relief_moment": MicroExpression("relief_moment", "Момент облегчения", "resolve_fear", 2, {"stability": 0.10, "speed": -0.05}, "exhale_shoulders_drop", {"P": 0.2, "A": -0.1}, 4),
    "humor_break": MicroExpression("humor_break", "Момент юмора", "humor", 1, {"stability": 0.05, "style": -0.10}, "brief_smile", {"P": 0.15}, 6),
    "shame_flash": MicroExpression("shame_flash", "Вспышка стыда", "boundary + avoidance_archetype", 1, {"stability": 0.05, "speed": -0.10}, "look_away", {"P": -0.1, "D": -0.15}, 5),
    "doubt_flicker": MicroExpression("doubt_flicker", "Мерцание сомнения", "facts|expert_answer vs hostile|testing", 1, {"stability": -0.05}, "micro_frown", {"A": 0.05}, 4),
}


@dataclass
class ActiveMicroExpression:
    expression: MicroExpression
    remaining_messages: int
    triggered_at_message: int


class MicroExpressionQueue:
    """Manages micro-expression lifecycle: trigger → active → cooldown."""

    def __init__(self) -> None:
        self.active: ActiveMicroExpression | None = None
        self.cooldowns: dict[str, int] = {}

    def try_trigger(self, code: str, current_message: int) -> bool:
        """Try to trigger a micro-expression. Returns True if activated."""
        if self.active is not None:
            return False  # already one active
        if code not in MICRO_EXPRESSIONS:
            return False
        if self.cooldowns.get(code, 0) > 0:
            return False  # in cooldown

        expr = MICRO_EXPRESSIONS[code]
        self.active = ActiveMicroExpression(
            expression=expr,
            remaining_messages=expr.duration_messages,
            triggered_at_message=current_message,
        )
        return True

    def tick(self) -> ActiveMicroExpression | None:
        """Called every message. Decrements timers and returns active micro if any."""
        # Decrement cooldowns
        for code in list(self.cooldowns):
            self.cooldowns[code] -= 1
            if self.cooldowns[code] <= 0:
                del self.cooldowns[code]

        # Check active
        if self.active:
            self.active.remaining_messages -= 1
            if self.active.remaining_messages <= 0:
                # Enter cooldown
                self.cooldowns[self.active.expression.code] = self.active.expression.cooldown_messages
                result = self.active
                self.active = None
                return result
            return self.active
        return None

    def to_dict(self) -> dict:
        return {
            "active": {
                "code": self.active.expression.code,
                "remaining": self.active.remaining_messages,
                "triggered_at": self.active.triggered_at_message,
            } if self.active else None,
            "cooldowns": dict(self.cooldowns),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MicroExpressionQueue":
        q = cls()
        if data.get("active"):
            code = data["active"]["code"]
            if code in MICRO_EXPRESSIONS:
                q.active = ActiveMicroExpression(
                    expression=MICRO_EXPRESSIONS[code],
                    remaining_messages=data["active"]["remaining"],
                    triggered_at_message=data["active"]["triggered_at"],
                )
        q.cooldowns = data.get("cooldowns", {})
        return q


# ═══════════════════════════════════════════════════════════════════════
#  4. GRAPH VARIANTS (10 archetype-group-specific transition mods)
# ═══════════════════════════════════════════════════════════════════════

class GraphVariant(str, enum.Enum):
    STANDARD = "standard"
    RESISTANCE = "resistance"
    EMOTIONAL = "emotional"
    AVOIDANCE = "avoidance"
    CONTROL = "control"
    COGNITIVE = "cognitive"
    SOCIAL = "social"
    TEMPORAL = "temporal"
    PROFESSIONAL = "professional"
    SPECIAL = "special"


# Modifications: {variant: {"add": [(from, to)], "remove": [(from, to)], "priority": [(from, to)]}}
GRAPH_MODIFICATIONS: dict[GraphVariant, dict[str, list[tuple[str, str]]]] = {
    GraphVariant.STANDARD: {"add": [], "remove": [], "priority": []},
    GraphVariant.RESISTANCE: {
        "add": [("cold", "testing")],  # testing_early — resistance clients test immediately
        "remove": [],
        "priority": [("cold", "testing")],
    },
    GraphVariant.EMOTIONAL: {
        "add": [("considering", "deal")],  # skip negotiating for emotional climax
        "remove": [],
        "priority": [("considering", "deal")],
    },
    GraphVariant.AVOIDANCE: {
        "add": [("cold", "callback")],  # callback_attempt — avoidance tries to leave early
        "remove": [],
        "priority": [("cold", "callback")],
    },
    GraphVariant.CONTROL: {
        "add": [],
        "remove": [],
        "priority": [("guarded", "testing")],  # testing BEFORE considering
    },
    GraphVariant.COGNITIVE: {
        "add": [("curious", "testing")],  # extended testing phase
        "remove": [],
        "priority": [("curious", "testing")],
    },
    GraphVariant.SOCIAL: {
        "add": [("cold", "curious")],  # warmup — personal connection skips guarded
        "remove": [],
        "priority": [("cold", "curious")],
    },
    GraphVariant.TEMPORAL: {
        "add": [
            ("guarded", "callback"), ("curious", "callback"),
            ("considering", "callback"), ("negotiating", "callback"),
        ],  # callback available from every state
        "remove": [],
        "priority": [],
    },
    GraphVariant.PROFESSIONAL: {
        "add": [("curious", "negotiating")],  # fast-track via expert_answer
        "remove": [],
        "priority": [("curious", "negotiating")],
    },
    GraphVariant.SPECIAL: {
        "add": [],
        "remove": [],
        "priority": [],
    },
}

# Archetype → GraphVariant mapping (by group)
ARCHETYPE_GRAPH_VARIANT: dict[str, GraphVariant] = {}

_GROUP_VARIANT_MAP = {
    "resistance": GraphVariant.RESISTANCE,
    "emotional": GraphVariant.EMOTIONAL,
    "avoidance": GraphVariant.AVOIDANCE,
    "control": GraphVariant.CONTROL,
    "cognitive": GraphVariant.COGNITIVE,
    "social": GraphVariant.SOCIAL,
    "temporal": GraphVariant.TEMPORAL,
    "professional": GraphVariant.PROFESSIONAL,
    "special": GraphVariant.SPECIAL,
    "compound": GraphVariant.STANDARD,  # compounds use standard graph
}

# Populate from archetype_blender metadata
try:
    from app.services.archetype_blender import ARCHETYPE_META
    for code, (group, _tier) in ARCHETYPE_META.items():
        ARCHETYPE_GRAPH_VARIANT[code] = _GROUP_VARIANT_MAP.get(group, GraphVariant.STANDARD)
except ImportError:
    pass  # fallback: all STANDARD


def get_transitions_for_archetype(archetype_code: str) -> dict[str, set[str]]:
    """Get modified transition graph for an archetype's group variant."""
    from app.services.emotion import ALLOWED_TRANSITIONS

    variant = ARCHETYPE_GRAPH_VARIANT.get(archetype_code, GraphVariant.STANDARD)
    mods = GRAPH_MODIFICATIONS.get(variant, GRAPH_MODIFICATIONS[GraphVariant.STANDARD])

    # Deep copy base transitions
    transitions = {state: set(targets) for state, targets in ALLOWED_TRANSITIONS.items()}

    # Apply additions
    for from_state, to_state in mods.get("add", []):
        if from_state in transitions:
            transitions[from_state].add(to_state)

    # Apply removals
    for from_state, to_state in mods.get("remove", []):
        if from_state in transitions:
            transitions[from_state].discard(to_state)

    return transitions


# ═══════════════════════════════════════════════════════════════════════
#  5. NEW TRIGGERS (17 new, 23→40)
# ═══════════════════════════════════════════════════════════════════════

NEW_TRIGGERS: list[str] = [
    "personal_story", "concrete_plan", "legal_citation", "humor",
    "patience_demonstrated", "boundary_set", "family_mention",
    "deadline_reminder", "jargon", "repetition", "interruption",
    "false_empathy", "script_detected", "competitor_mention",
    "time_respect", "silence_comfortable", "social_proof",
    # v6.1: "Stupid question dilemma" — human-like interaction triggers
    "off_topic_reaction",   # Client reacts to manager's off-topic/stupid question
    "human_tangent",        # Client goes on a brief human tangent (then returns to topic)
    "typo_confusion",       # Client confused by manager's typo/gibberish
    "curiosity_personal",   # Client asks a personal/tangential question about manager
    "self_correction",      # Client corrects themselves mid-sentence (human imperfection)
]

NEW_TRIGGER_ENERGY: dict[str, float] = {
    "personal_story": 0.35,
    "concrete_plan": 0.40,
    "legal_citation": 0.45,
    "humor": 0.20,
    "patience_demonstrated": 0.30,
    "boundary_set": 0.35,
    "family_mention": 0.40,
    "deadline_reminder": 0.20,   # dual: depends on archetype group
    "jargon": -0.25,
    "repetition": -0.15,
    "interruption": -0.35,
    "false_empathy": -0.30,
    "script_detected": -0.25,
    "competitor_mention": -0.20,
    "time_respect": 0.20,
    "silence_comfortable": 0.15,
    "social_proof": 0.30,
    # v6.1: Human-like interaction — NEUTRAL energy (don't penalize, don't reward)
    "off_topic_reaction": 0.0,    # Client reacting to stupid question = neutral (not a penalty)
    "human_tangent": 0.0,         # Brief tangent = neutral (preserves current emotion)
    "typo_confusion": -0.05,      # Slight annoyance from gibberish, but NOT a real penalty
    "curiosity_personal": 0.05,   # Slight positive — client is engaging as human
    "self_correction": 0.0,       # Neutral — natural speech pattern
}

# Trigger conflict rules: if both detected, winner takes precedence
TRIGGER_CONFLICTS: dict[str, str] = {
    "empathy": "false_empathy",          # false_empathy wins over empathy
    "facts": "legal_citation",            # legal_citation wins (more specific)
    "patience_demonstrated": "interruption",  # interruption wins
    "personal_story": "script_detected",      # script_detected wins
    "concrete_plan": "repetition",            # repetition wins
}

# Keyword patterns for new trigger detection
NEW_TRIGGER_PATTERNS: dict[str, list[str]] = {
    "personal_story": [r"у\s+меня\s+был\s+(?:клиент|случай)", r"например.*один\s+(?:человек|клиент)", r"расскажу.*случай"],
    "concrete_plan": [r"(?:шаг|этап)\s+(?:первый|1|один)", r"план\s+(?:действий|такой)", r"давайте\s+по\s+порядку"],
    "legal_citation": [r"(?:статья|ст\.)\s+\d+", r"127[\s-]*ФЗ", r"(?:закон|кодекс).*(?:от|о)", r"пленум"],
    "humor": [r"(?:шучу|шутк)", r"(?:хаха|ахах|😄|😂)"],
    "patience_demonstrated": [],  # detected by silence duration > 8 sec
    "boundary_set": [r"не\s+могу\s+(?:это|так)", r"давайте\s+(?:вернёмся|по\s+делу)", r"это\s+не\s+в\s+моей\s+компетенции"],
    "family_mention": [r"(?:дети|ребён|семь|жен|муж|родител|мам|пап)", r"(?:сын|дочь|внук)"],
    "deadline_reminder": [r"(?:срок|дедлайн|осталось)\s+\d+", r"через\s+\d+\s+(?:дней|месяц)", r"(?:истекает|заканчивается)"],
    "jargon": [r"арбитражн", r"реструктуризац", r"конкурсн.*масс", r"финансов.*управляющ"],
    "repetition": [],  # detected by cosine similarity > 0.8 with previous response
    "interruption": [],  # detected by message length < 50% of client's and overlapping timing
    "false_empathy": [r"я\s+(?:вас|тебя)\s+(?:прекрасно|полностью)\s+понимаю", r"многие\s+в\s+(?:вашей|такой)\s+ситуации"],
    "script_detected": [],  # detected by template matching / low variability
    "competitor_mention": [r"(?:другая|конкурент|они|компания\s+\w+)\s+(?:хуже|дороже|мошенник)", r"не\s+советую.*(?:их|другую)"],
    "time_respect": [r"(?:не\s+буду|не\s+стану)\s+(?:задерживать|отнимать)", r"понимаю.*(?:торопитесь|заняты|время)"],
    "silence_comfortable": [],  # detected by manager waiting > 5 sec without panic
    "social_proof": [r"\d+\s*(?:тысяч|клиент|человек|семей)", r"(?:статистика|исследован|опрос)", r"(?:90|95|98|99)\s*%"],
    # v6.1: Human-like interaction detection patterns
    "off_topic_reaction": [],    # detected by semantic analysis: manager msg has low relevance to bankruptcy/sales
    "human_tangent": [],         # detected by AI output containing tangent markers (injected via prompt)
    "typo_confusion": [],        # detected by high gibberish ratio in manager message
    "curiosity_personal": [r"(?:вы\s+давно|сколько\s+вам|а\s+вы\s+сами|где\s+вы\s+(?:работ|учил))", r"(?:а\s+у\s+вас|вам\s+нравится|вы\s+женат|у\s+вас\s+дети)"],
    "self_correction": [],       # detected by AI output patterns (injected via prompt)
}

# Deadline_reminder dual-energy by archetype group
DEADLINE_DUAL_ENERGY: dict[str, float] = {
    "emotional": -0.20,   # fear
    "temporal": 0.30,     # motivation
    "avoidance": 0.30,    # motivation
    # others default to 0.05 (neutral)
}


# ═══════════════════════════════════════════════════════════════════════
#  6. TRAP INTENSITY MULTIPLIER
# ═══════════════════════════════════════════════════════════════════════

TRAP_INTENSITY_MULTIPLIER: dict[IntensityLevel, float] = {
    IntensityLevel.LOW: 0.5,
    IntensityLevel.MEDIUM: 1.0,
    IntensityLevel.HIGH: 1.5,
}


# ═══════════════════════════════════════════════════════════════════════
#  7. L11 EMOTION AWARENESS BONUS
# ═══════════════════════════════════════════════════════════════════════

def score_emotion_awareness(
    current_state: str,
    intensity: IntensityLevel,
    compound: CompoundEmotion | None,
    micro: ActiveMicroExpression | None,
    manager_triggers: list[str],
    archetype_group: str | None = None,
) -> float:
    """Calculate L11 bonus for emotion-aware responses. Max +1.25."""
    bonus = 0.0

    # +0.25 for intensity-appropriate response
    if intensity == IntensityLevel.HIGH:
        calming = {"empathy", "patience_demonstrated", "calm_response", "silence_comfortable"}
        if any(t in calming for t in manager_triggers):
            bonus += 0.25
    elif intensity == IntensityLevel.LOW:
        engaging = {"hook", "facts", "challenge", "social_proof", "concrete_plan"}
        if any(t in engaging for t in manager_triggers):
            bonus += 0.25

    # +0.25 for compound-appropriate response
    if compound:
        if compound.code == "hopeful_anxiety" and "concrete_plan" in manager_triggers:
            bonus += 0.25
        elif compound.code == "volatile_anger" and "calm_response" in manager_triggers:
            bonus += 0.25
        elif compound.code == "cautious_interest" and "facts" in manager_triggers:
            bonus += 0.25

    # +0.25 for micro-expression response
    if micro and micro.expression.code == "surprise_flash" and "hook" in manager_triggers:
        bonus += 0.25

    # +0.50 for graph-variant-appropriate triggers
    variant_triggers: dict[str, set[str]] = {
        "resistance": {"facts", "legal_citation", "boundary_set"},
        "emotional": {"empathy", "patience_demonstrated", "personal_story"},
        "avoidance": {"concrete_plan", "deadline_reminder"},
        "control": {"expert_answer", "legal_citation", "facts"},
        "cognitive": {"concrete_plan", "facts"},
        "social": {"family_mention", "personal_story", "social_proof"},
        "temporal": {"deadline_reminder", "concrete_plan", "time_respect"},
        "professional": {"legal_citation", "expert_answer"},
    }
    if archetype_group and archetype_group in variant_triggers:
        good = variant_triggers[archetype_group]
        if any(t in good for t in manager_triggers):
            bonus += 0.50

    return min(1.25, bonus)


# ═══════════════════════════════════════════════════════════════════════
#  8. HUMAN MOMENT DETECTION (v6.1 — "Stupid Question Dilemma")
# ═══════════════════════════════════════════════════════════════════════

# Bankruptcy/sales domain keywords — if a message contains NONE of these,
# it's likely off-topic or a "stupid question"
_DOMAIN_KEYWORDS = {
    "долг", "кредит", "банк", "банкротств", "процедур", "суд", "арбитраж",
    "управляющ", "реструктуриз", "списан", "имуществ", "квартир", "ипотек",
    "платёж", "платеж", "просрочк", "коллектор", "пристав", "исполнительн",
    "127-фз", "закон", "статья", "встреч", "консультац", "услуг", "стоим",
    "цен", "оплат", "рассрочк", "гарантир", "документ", "справк", "заявлен",
    "кредитор", "задолженност", "займ", "микрозайм", "мфо", "пенсия",
    "зарплат", "прожиточн", "алимент", "жильё", "жилье", "машин", "авто",
    "депозит", "вклад", "счёт", "счет", "карт", "финанс", "юрист",
    "здравствуйте", "добрый", "меня зовут", "компания", "звоню",
    "понимаю", "сочувствую", "ситуация", "помощь", "помочь", "решение",
    "предлагаю", "давайте", "расскажите", "могу", "опасения", "боитесь",
    "переживаете", "тревожит", "страх", "последств", "кредитная история",
}


def detect_human_moment(
    manager_message: str,
    *,
    min_words: int = 3,
    gibberish_ratio_threshold: float = 0.6,
) -> str | None:
    """Detect if manager's message is a "human moment" — off-topic, typo, or gibberish.

    Returns trigger name or None:
      - "typo_confusion" — message is mostly gibberish/typos (>60% non-dictionary words)
      - "off_topic_reaction" — message has NO domain keywords (off-topic)
      - "curiosity_personal" — message asks personal question about the manager
      - None — normal message, no special handling needed
    """
    import re

    text = manager_message.strip()
    if not text:
        return None

    words = text.lower().split()
    word_count = len(words)

    # Very short messages (1-2 words) — could be valid ("нет", "да", "слушаю")
    if word_count < min_words:
        # Check if it's pure gibberish (no real Russian words)
        cyrillic_count = sum(1 for w in words if re.search(r"[а-яё]{2,}", w))
        if cyrillic_count == 0 and word_count >= 1:
            return "typo_confusion"
        return None

    text_lower = text.lower()

    # 1. Gibberish detection: count words that look like Russian
    real_words = sum(1 for w in words if re.search(r"^[а-яё]{2,}$", w))
    if word_count >= 3 and real_words / word_count < (1.0 - gibberish_ratio_threshold):
        return "typo_confusion"

    # 2. Personal curiosity detection (before domain check)
    curiosity_patterns = NEW_TRIGGER_PATTERNS.get("curiosity_personal", [])
    for pattern in curiosity_patterns:
        if re.search(pattern, text_lower):
            return "curiosity_personal"

    # 3. Domain relevance check: does message contain ANY bankruptcy/sales keywords?
    has_domain_word = any(kw in text_lower for kw in _DOMAIN_KEYWORDS)
    if not has_domain_word:
        return "off_topic_reaction"

    return None


def should_ai_add_human_tangent(
    emotion_state: str,
    message_index: int,
    archetype_code: str,
    *,
    tangent_cooldown: int = 8,
    last_tangent_at: int = -99,
) -> bool:
    """Decide if AI client should insert a brief human tangent in this response.

    Rules:
      - Only in certain emotion states (curious, considering, callback, deal)
      - Not too early (message_index >= 6) and not too often (cooldown 8 messages)
      - Probability varies by archetype personality type
      - Never during hostile/hangup/cold (would break immersion)
    """
    # States where human tangent feels natural
    tangent_friendly_states = {"curious", "considering", "callback", "deal", "negotiating"}
    if emotion_state not in tangent_friendly_states:
        return False

    # Not too early in conversation
    if message_index < 6:
        return False

    # Cooldown between tangents
    if message_index - last_tangent_at < tangent_cooldown:
        return False

    # Archetype-specific probability (some characters tangent more)
    _TANGENT_PRONE = {
        "anxious", "crying", "desperate", "hysteric", "mood_swinger",
        "overwhelmed", "couple", "grateful", "sarcastic", "psychologist",
    }
    _TANGENT_RARE = {
        "aggressive", "hostile", "power_player", "strategist", "auditor",
        "know_it_all", "litigious", "pragmatic",
    }

    # Simple deterministic check based on message_index parity
    # This avoids randomness (reproducible) while still feeling organic
    if archetype_code in _TANGENT_PRONE:
        # Every ~8 messages in tangent-friendly state
        return message_index % 8 == 0
    elif archetype_code in _TANGENT_RARE:
        # Every ~16 messages
        return message_index % 16 == 0
    else:
        # Default: every ~12 messages
        return message_index % 12 == 0
