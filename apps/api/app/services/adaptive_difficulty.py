"""
ТЗ-06: Intra-session адаптивная сложность.

Управляет динамической подстройкой сложности ВНУТРИ одной тренировочной сессии
на основе streak-анализа ответов менеджера.

Redis-ключ: session:{session_id}:adaptive → JSON (IntraSessionState)
"""
from __future__ import annotations

import json
import math
import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
#  Константы
# ──────────────────────────────────────────────────────────────────────

MIN_MODIFIER = -3
MAX_MODIFIER = 3

# Mood buffer
BASE_THRESHOLD_POS = 0.30
DIFFICULTY_FACTOR_POS = 0.05
BASE_THRESHOLD_NEG = -0.25
DIFFICULTY_FACTOR_NEG = 0.03

# Decay
BASE_DECAY = 0.04
DECAY_FACTOR = 0.02

# Traps
BASE_TRAP_PROB = 0.05
TRAP_PROB_FACTOR = 0.03

# Time
BASE_TIME_LIMIT = 45  # секунд
TIME_REDUCTION = 2

# Мягкий старт (первые 5 ходов)
SOFT_START_TURNS = 5
SOFT_START_MODIFIER_FACTOR = 0.5

# Coaching mode (чередование good/bad)
COACHING_MODE_THRESHOLD = 10  # ходов
COACHING_MODE_RATIO_RANGE = (0.4, 0.6)

# Камбэк
COMEBACK_BAD_STREAK_THRESHOLD = 5
COMEBACK_GOOD_STREAK_NEEDED = 3
COMEBACK_MODIFIER_BOOST = 1.5
COMEBACK_XP_BONUS = 15

REDIS_TTL = 86400  # 24 часа


# ──────────────────────────────────────────────────────────────────────
#  Phase 3.1 (2026-04-19) — DIFFICULTY_PARAMS table
#
#  Problem: scenarios at difficulty=1 and difficulty=10 previously felt
#  equally hard because there was no monotonic ramp for OCEAN shift, LLM
#  temperature, script-matcher threshold, agreement probability, etc.
#
#  Solution: a single authoritative table indexed by level 1..10. Every
#  consumer (scenario_engine, llm.py, script_checker, game_director) reads
#  through ``resolve_params(level)`` so the ramp is uniform.
#
#  Values designed so that:
#    - L1 is forgiving (high agreeableness shift, low temp, easy threshold,
#      hint coverage = all)
#    - L5 is neutral baseline
#    - L10 is brutal (low agreeableness, high neuroticism, high temp,
#      tight threshold, no hints)
#
#  Changes here are backward-compatible with the mood-buffer machine
#  above; those constants remain in effect as a parallel axis (streak
#  adaptation), not replaced.
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OceanShift:
    """Additive delta applied to archetype OCEAN baseline for a difficulty.

    All fields in [-1.0, +1.0]. Semantics match
    ``client_generator.ARCHETYPE_OCEAN`` single-letter keys.
    """

    O: float = 0.0
    C: float = 0.0
    E: float = 0.0
    A: float = 0.0
    N: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {"O": self.O, "C": self.C, "E": self.E, "A": self.A, "N": self.N}


@dataclass(frozen=True)
class DifficultyParams:
    """Parameters applied uniformly across the training pipeline per level.

    Read only through ``resolve_params()``; the dataclass is frozen so
    accidental mutation raises.
    """

    level: int
    """1..10 — the ordinal surfaced to the user."""

    llm_temperature: float
    """Base temperature for the client LLM. Monotonic 0.30 → 0.85."""

    script_similarity_threshold: float
    """``script_checker.check_checkpoint_match`` threshold. 0.45 → 0.68."""

    coaching_hints: str
    """One of ``"all" | "half" | "crisis_only" | "none"`` — what the
    ``WhisperPanel``/coach surfaces to the manager on this level."""

    agreement_base_probability: float
    """Rough prior probability the client will soften on a well-played
    turn. 0.80 (L1) → 0.12 (L10). Referenced by game_director when
    deciding ``relationship_score`` deltas."""

    gd_relationship_gain_per_turn: int
    """How fast ``relationship_score`` rises on positive turns. 5 → 1."""

    gd_relationship_loss_multiplier: float
    """Penalty multiplier on bad turns. 0.5 (soft) → 1.8 (harsh)."""

    objection_density: float
    """Expected density of client objections per turn. 0.2 → 0.9."""

    interrupt_probability: float
    """P(client interrupts manager's long explanation). 0.0 → 0.35."""

    ocean_shift: OceanShift
    """Additive shift to archetype OCEAN baseline for this level."""


DIFFICULTY_PARAMS: dict[int, DifficultyParams] = {
    1: DifficultyParams(
        level=1,
        llm_temperature=0.30,
        script_similarity_threshold=0.45,
        coaching_hints="all",
        agreement_base_probability=0.80,
        gd_relationship_gain_per_turn=5,
        gd_relationship_loss_multiplier=0.5,
        objection_density=0.20,
        interrupt_probability=0.00,
        ocean_shift=OceanShift(A=+0.15, N=-0.15),
    ),
    2: DifficultyParams(
        level=2,
        llm_temperature=0.35,
        script_similarity_threshold=0.47,
        coaching_hints="all",
        agreement_base_probability=0.72,
        gd_relationship_gain_per_turn=4,
        gd_relationship_loss_multiplier=0.6,
        objection_density=0.28,
        interrupt_probability=0.03,
        ocean_shift=OceanShift(A=+0.10, N=-0.10),
    ),
    3: DifficultyParams(
        level=3,
        llm_temperature=0.40,
        script_similarity_threshold=0.50,
        coaching_hints="half",
        agreement_base_probability=0.62,
        gd_relationship_gain_per_turn=4,
        gd_relationship_loss_multiplier=0.7,
        objection_density=0.35,
        interrupt_probability=0.05,
        ocean_shift=OceanShift(A=+0.05, N=-0.05),
    ),
    4: DifficultyParams(
        level=4,
        llm_temperature=0.45,
        script_similarity_threshold=0.52,
        coaching_hints="half",
        agreement_base_probability=0.55,
        gd_relationship_gain_per_turn=3,
        gd_relationship_loss_multiplier=0.9,
        objection_density=0.42,
        interrupt_probability=0.08,
        ocean_shift=OceanShift(),
    ),
    5: DifficultyParams(
        level=5,
        llm_temperature=0.50,
        script_similarity_threshold=0.55,
        coaching_hints="half",
        agreement_base_probability=0.48,
        gd_relationship_gain_per_turn=3,
        gd_relationship_loss_multiplier=1.0,
        objection_density=0.50,
        interrupt_probability=0.12,
        ocean_shift=OceanShift(),
    ),
    6: DifficultyParams(
        level=6,
        llm_temperature=0.55,
        script_similarity_threshold=0.58,
        coaching_hints="crisis_only",
        agreement_base_probability=0.40,
        gd_relationship_gain_per_turn=2,
        gd_relationship_loss_multiplier=1.15,
        objection_density=0.58,
        interrupt_probability=0.17,
        ocean_shift=OceanShift(A=-0.05, N=+0.05),
    ),
    7: DifficultyParams(
        level=7,
        llm_temperature=0.60,
        script_similarity_threshold=0.60,
        coaching_hints="crisis_only",
        agreement_base_probability=0.32,
        gd_relationship_gain_per_turn=2,
        gd_relationship_loss_multiplier=1.30,
        objection_density=0.65,
        interrupt_probability=0.22,
        ocean_shift=OceanShift(A=-0.10, N=+0.10),
    ),
    8: DifficultyParams(
        level=8,
        llm_temperature=0.70,
        script_similarity_threshold=0.63,
        coaching_hints="crisis_only",
        agreement_base_probability=0.25,
        gd_relationship_gain_per_turn=1,
        gd_relationship_loss_multiplier=1.45,
        objection_density=0.72,
        interrupt_probability=0.27,
        ocean_shift=OceanShift(A=-0.12, N=+0.15),
    ),
    9: DifficultyParams(
        level=9,
        llm_temperature=0.78,
        script_similarity_threshold=0.65,
        coaching_hints="none",
        agreement_base_probability=0.18,
        gd_relationship_gain_per_turn=1,
        gd_relationship_loss_multiplier=1.65,
        objection_density=0.82,
        interrupt_probability=0.32,
        ocean_shift=OceanShift(A=-0.15, N=+0.20),
    ),
    10: DifficultyParams(
        level=10,
        llm_temperature=0.85,
        script_similarity_threshold=0.68,
        coaching_hints="none",
        agreement_base_probability=0.12,
        gd_relationship_gain_per_turn=1,
        gd_relationship_loss_multiplier=1.80,
        objection_density=0.90,
        interrupt_probability=0.35,
        ocean_shift=OceanShift(O=-0.10, A=-0.20, N=+0.25),
    ),
}


def resolve_params(level: int | float | None) -> DifficultyParams:
    """Return the ``DifficultyParams`` for ``level`` (clamped to [1..10]).

    Accepts float (e.g. scenario.difficulty may be 6.5 after modifier) —
    rounds to nearest integer. ``None`` / garbage → level 5 (neutral).

    The return value is always a real entry from ``DIFFICULTY_PARAMS``;
    callers never need to None-check.
    """

    if level is None:
        return DIFFICULTY_PARAMS[5]
    try:
        lvl = int(round(float(level)))
    except (TypeError, ValueError):
        return DIFFICULTY_PARAMS[5]
    lvl = max(1, min(10, lvl))
    return DIFFICULTY_PARAMS[lvl]


# ──────────────────────────────────────────────────────────────────────
#  Reply Quality
# ──────────────────────────────────────────────────────────────────────

class ReplyQuality(str, Enum):
    GOOD = "good"
    BAD = "bad"
    NEUTRAL = "neutral"


# ──────────────────────────────────────────────────────────────────────
#  Streak Effect — описание эффекта
# ──────────────────────────────────────────────────────────────────────

@dataclass
class StreakEffect:
    """Описание эффекта, вызванного streak."""

    code: str                        # e.g. "inject_extra_trap", "difficulty_up_1"
    description: str                 # человеко-читаемое описание
    modifier_delta: int = 0          # изменение difficulty_modifier
    inject_trap: bool = False        # инжектить ловушку?
    trap_difficulty_bonus: int = 0   # бонус к сложности ловушки
    cascade: bool = False            # каскадная ловушка?
    fake_transition: bool = False    # fake transition?
    challenge_mode: bool = False     # включить challenge mode?
    challenge_turns: int = 0         # сколько ходов challenge
    hint: bool = False               # дать подсказку?
    direct_hint: bool = False        # прямая подсказка?
    disable_traps: bool = False      # отключить ловушки?
    disable_traps_turns: int = 0     # на сколько ходов
    mercy_deal: bool = False         # mercy (спасение от hangup)?
    emotional_spike: bool = False    # резкая смена эмоции?
    boss_mode: bool = False          # boss mode?
    safe_mode: bool = False          # safe mode (минимальная сложность)?
    coaching_mode: bool = False      # coaching mode?
    emotional_opening: bool = False  # клиент раскрывается?
    slow_down: bool = False          # замедление?
    explicit_request: bool = False   # клиент сам просит рассказать?
    auto_qualify: bool = False       # клиент сам называет данные?


# ──────────────────────────────────────────────────────────────────────
#  Таблица good_streak эффектов (1-15)
# ──────────────────────────────────────────────────────────────────────

GOOD_STREAK_EFFECTS: dict[int, StreakEffect] = {
    3: StreakEffect(
        code="inject_extra_trap",
        description="Дополнительная ловушка (сложность base+1)",
        inject_trap=True, trap_difficulty_bonus=1,
    ),
    4: StreakEffect(
        code="increase_decay",
        description="Decay ускоряется на 20%",
    ),
    5: StreakEffect(
        code="difficulty_up_1",
        description="difficulty_modifier += 1",
        modifier_delta=1,
    ),
    6: StreakEffect(
        code="inject_harder_trap",
        description="Сложная ловушка (сложность base+2)",
        inject_trap=True, trap_difficulty_bonus=2,
    ),
    7: StreakEffect(
        code="inject_cascade_trap",
        description="Каскадная ловушка (2-3 связанные)",
        cascade=True,
    ),
    8: StreakEffect(
        code="difficulty_up_2",
        description="difficulty_modifier += 1 (итого +2)",
        modifier_delta=1,
    ),
    9: StreakEffect(
        code="inject_fake_transition",
        description="Fake transition: клиент «согласился» и передумал",
        fake_transition=True,
    ),
    10: StreakEffect(
        code="challenge_mode_on",
        description="Challenge mode: testing на 2 хода",
        challenge_mode=True, challenge_turns=2,
    ),
    11: StreakEffect(
        code="emotional_spike",
        description="Резкая смена эмоционального состояния",
        emotional_spike=True,
    ),
    12: StreakEffect(
        code="difficulty_up_3",
        description="difficulty_modifier += 1 (итого +3 MAX)",
        modifier_delta=1,
    ),
    13: StreakEffect(
        code="inject_ultimate_trap",
        description="Ультимативная ловушка (максимальная для архетипа)",
        inject_trap=True, trap_difficulty_bonus=4,
    ),
    14: StreakEffect(
        code="combined_attack",
        description="Комбинированная атака: эмоция + факт + ультиматум",
        inject_trap=True, trap_difficulty_bonus=3, emotional_spike=True,
    ),
    15: StreakEffect(
        code="boss_mode",
        description="Boss mode: максимальная вариативность до конца сессии",
        boss_mode=True,
    ),
}

# ──────────────────────────────────────────────────────────────────────
#  Таблица bad_streak эффектов (1-15)
# ──────────────────────────────────────────────────────────────────────

BAD_STREAK_EFFECTS: dict[int, StreakEffect] = {
    2: StreakEffect(
        code="micro_hint",
        description="Клиент повторяет мысль проще",
        hint=True,
    ),
    3: StreakEffect(
        code="difficulty_down_1",
        description="difficulty_modifier -= 1",
        modifier_delta=-1,
    ),
    4: StreakEffect(
        code="decrease_decay",
        description="Decay замедляется на 25%",
    ),
    5: StreakEffect(
        code="hint",
        description="Клиент «наводит» на правильное действие",
        hint=True,
    ),
    6: StreakEffect(
        code="difficulty_down_2",
        description="difficulty_modifier -= 1 (итого -2)",
        modifier_delta=-1,
    ),
    7: StreakEffect(
        code="direct_hint",
        description="Клиент сам спрашивает то, что менеджер должен был спросить",
        direct_hint=True,
    ),
    8: StreakEffect(
        code="disable_traps",
        description="Ловушки отключены на 3 хода",
        disable_traps=True, disable_traps_turns=3,
    ),
    9: StreakEffect(
        code="difficulty_down_3",
        description="difficulty_modifier -= 1 (итого -3 MAX)",
        modifier_delta=-1,
    ),
    10: StreakEffect(
        code="mercy_deal",
        description="Mercy: callback вместо hangup",
        mercy_deal=True,
    ),
    11: StreakEffect(
        code="emotional_opening",
        description="Клиент сам рассказывает о ситуации",
        emotional_opening=True,
    ),
    12: StreakEffect(
        code="global_slowdown",
        description="Все таймеры увеличены на 50%",
        slow_down=True,
    ),
    13: StreakEffect(
        code="explicit_request",
        description="Клиент сам просит рассказать про банкротство",
        explicit_request=True,
    ),
    14: StreakEffect(
        code="auto_qualify",
        description="Клиент сам называет ключевые данные",
        auto_qualify=True,
    ),
    15: StreakEffect(
        code="safe_mode",
        description="Safe mode: минимальная сложность, ловушки отключены",
        safe_mode=True, disable_traps=True,
    ),
}


# ──────────────────────────────────────────────────────────────────────
#  IntraSessionState — состояние адаптации внутри сессии
# ──────────────────────────────────────────────────────────────────────

@dataclass
class IntraSessionState:
    good_streak: int = 0
    bad_streak: int = 0
    total_good: int = 0
    total_bad: int = 0
    total_neutral: int = 0
    difficulty_modifier: int = 0
    extra_traps_injected: int = 0
    softened: bool = False
    challenge_mode: bool = False
    challenge_turns_left: int = 0
    mercy_activated: bool = False
    hints_given: int = 0
    last_action: str = ""
    modifier_history: list[dict] = field(default_factory=list)
    coaching_mode: bool = False
    onboarding_mode: bool = False
    safe_mode: bool = False
    boss_mode: bool = False
    traps_disabled: bool = False
    traps_disabled_turns: int = 0
    slow_mode: bool = False
    # Камбэк-трекинг
    max_bad_streak_before_recovery: int = 0
    recovery_good_streak: int = 0
    had_comeback: bool = False
    # Turn counter
    current_turn: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "IntraSessionState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ──────────────────────────────────────────────────────────────────────
#  AdaptiveAction — результат адаптации (отправляется в LLM/клиент)
# ──────────────────────────────────────────────────────────────────────

@dataclass
class AdaptiveAction:
    """Инструкция для LLM-клиента, сформированная адаптивной системой."""

    effect_code: str = "none"
    description: str = ""
    difficulty_modifier: int = 0
    effective_difficulty: int = 0

    # Инструкции для LLM
    inject_trap: bool = False
    trap_difficulty: int = 0
    cascade_trap: bool = False
    fake_transition: bool = False
    challenge_mode: bool = False
    challenge_turns: int = 0
    give_hint: bool = False
    hint_type: str = ""  # "micro", "standard", "direct"
    disable_traps: bool = False
    mercy_deal: bool = False
    emotional_spike: bool = False
    boss_mode: bool = False
    safe_mode: bool = False
    emotional_opening: bool = False
    slow_down: bool = False
    explicit_request: bool = False
    auto_qualify: bool = False
    coaching_mode: bool = False

    # Метрики для фронтенда
    threshold_positive: float = 0.55
    threshold_negative: float = -0.40
    decay_rate: float = 0.14
    max_trap_difficulty: int = 7
    trap_injection_probability: float = 0.20
    max_active_traps: int = 2
    reply_time_limit: int = 35


# ──────────────────────────────────────────────────────────────────────
#  IntraSessionAdapter — основной сервис
# ──────────────────────────────────────────────────────────────────────

class IntraSessionAdapter:
    """Управляет внутрисессионной адаптацией сложности."""

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}:adaptive"

    # ── Redis I/O ──

    async def get_state(self, session_id: str) -> IntraSessionState:
        """Загружает состояние из Redis (или создаёт новое)."""
        raw = await self._redis.get(self._key(session_id))
        if raw:
            return IntraSessionState.from_dict(json.loads(raw))
        return IntraSessionState()

    async def save_state(self, session_id: str, state: IntraSessionState) -> None:
        """Сохраняет состояние в Redis (atomic SET with TTL)."""
        await self._redis.set(
            self._key(session_id),
            json.dumps(state.to_dict(), ensure_ascii=False),
            ex=REDIS_TTL,
        )

    async def _atomic_process(self, session_id: str, quality: "ReplyQuality", base_difficulty: int) -> "AdaptiveAction":
        """Process reply with Redis WATCH for CAS (compare-and-swap) safety.

        Retries up to 3 times if the key was modified between read and write.
        """
        key = self._key(session_id)
        for attempt in range(3):
            try:
                async with self._redis.pipeline(transaction=True) as pipe:
                    await pipe.watch(key)
                    raw = await pipe.get(key)
                    state = IntraSessionState.from_dict(json.loads(raw)) if raw else IntraSessionState()

                    state.current_turn += 1
                    self._update_streak(state, quality)
                    self._check_comeback(state)
                    self._check_coaching_mode(state)
                    self._check_onboarding_mode(state)
                    effect = self._get_streak_effect(state)
                    self._apply_effect(state, effect, base_difficulty)

                    if state.challenge_mode and state.challenge_turns_left > 0:
                        state.challenge_turns_left -= 1
                        if state.challenge_turns_left <= 0:
                            state.challenge_mode = False
                    if state.traps_disabled and state.traps_disabled_turns > 0:
                        state.traps_disabled_turns -= 1
                        if state.traps_disabled_turns <= 0:
                            state.traps_disabled = False

                    eff_diff = self._effective_difficulty(base_difficulty, state.difficulty_modifier)
                    action = self._build_action(state, effect, eff_diff, base_difficulty)

                    pipe.multi()
                    pipe.set(key, json.dumps(state.to_dict(), ensure_ascii=False), ex=REDIS_TTL)
                    await pipe.execute()

                    logger.info(
                        "Adaptive [%s] turn=%d quality=%s streak=+%d/-%d mod=%d eff=%d action=%s",
                        session_id[:8], state.current_turn, quality.value,
                        state.good_streak, state.bad_streak,
                        state.difficulty_modifier, eff_diff,
                        effect.code if effect else "none",
                    )
                    return action
            except Exception as e:
                if "WATCH" in str(type(e).__name__).upper() or "WatchError" in str(type(e).__name__):
                    logger.debug("Adaptive CAS retry %d for session %s", attempt + 1, session_id[:8])
                    continue
                raise
        # Fallback: non-atomic path after 3 retries
        return await self.process_reply(session_id, quality, base_difficulty)

    async def delete_state(self, session_id: str) -> None:
        """Удаляет состояние из Redis (при завершении сессии)."""
        await self._redis.delete(self._key(session_id))

    # ── Основной метод: обработка ответа менеджера ──

    async def process_reply(
        self,
        session_id: str,
        quality: ReplyQuality,
        base_difficulty: int,
    ) -> AdaptiveAction:
        """
        Обрабатывает ответ менеджера и возвращает адаптивное действие.

        Args:
            session_id: ID тренировочной сессии
            quality: оценка качества ответа ("good" / "bad" / "neutral")
            base_difficulty: базовая сложность сессии (1-10)

        Returns:
            AdaptiveAction с инструкциями для LLM и метриками
        """
        # Use atomic CAS (WATCH/MULTI/EXEC) to prevent lost updates
        try:
            return await self._atomic_process(session_id, quality, base_difficulty)
        except Exception:
            # Graceful fallback: non-atomic path if Redis doesn't support WATCH
            logger.debug("Atomic process unavailable, using non-atomic fallback for %s", session_id[:8])

        state = await self.get_state(session_id)
        state.current_turn += 1

        self._update_streak(state, quality)
        self._check_comeback(state)
        self._check_coaching_mode(state)
        self._check_onboarding_mode(state)
        effect = self._get_streak_effect(state)
        self._apply_effect(state, effect, base_difficulty)

        if state.challenge_mode and state.challenge_turns_left > 0:
            state.challenge_turns_left -= 1
            if state.challenge_turns_left <= 0:
                state.challenge_mode = False

        if state.traps_disabled and state.traps_disabled_turns > 0:
            state.traps_disabled_turns -= 1
            if state.traps_disabled_turns <= 0:
                state.traps_disabled = False

        eff_diff = self._effective_difficulty(base_difficulty, state.difficulty_modifier)
        action = self._build_action(state, effect, eff_diff, base_difficulty)

        await self.save_state(session_id, state)

        logger.info(
            "Adaptive [%s] turn=%d quality=%s streak=+%d/-%d mod=%d eff=%d action=%s",
            session_id[:8], state.current_turn, quality.value,
            state.good_streak, state.bad_streak,
            state.difficulty_modifier, eff_diff,
            effect.code if effect else "none",
        )

        return action

    # ── Шорткат для получения текущей effective difficulty ──

    async def get_effective_difficulty(self, session_id: str, base_difficulty: int) -> int:
        state = await self.get_state(session_id)
        return self._effective_difficulty(base_difficulty, state.difficulty_modifier)

    # ── Определение тренда сложности ──

    @staticmethod
    def get_difficulty_trend(state: IntraSessionState) -> str:
        """Вычисляет тренд сложности на основе последних 3 записей modifier_history.

        Returns:
            "rising" | "falling" | "stable"
        """
        history = state.modifier_history
        if len(history) < 2:
            return "stable"

        recent = history[-3:] if len(history) >= 3 else history[-2:]
        values = [entry.get("new", 0) for entry in recent]

        if all(values[i] < values[i + 1] for i in range(len(values) - 1)):
            return "rising"
        elif all(values[i] > values[i + 1] for i in range(len(values) - 1)):
            return "falling"
        return "stable"

    # ── Проверка необходимости hangup ──

    @staticmethod
    def should_hangup(state: IntraSessionState) -> bool:
        """Проверяет, нужен ли hangup: bad_streak >= 15 И mercy уже был И всё ещё bad.

        Логика:
        1. bad_streak >= 10 → mercy_deal (шанс спасти)
        2. bad_streak >= 15 И mercy_activated → hangup
        """
        return (
            state.bad_streak >= 15
            and state.mercy_activated
            and not state.had_comeback
        )

    # ── Определение текущего mode ──

    @staticmethod
    def get_current_mode(state: IntraSessionState) -> str:
        """Возвращает текущий mode (один, по приоритету)."""
        if state.boss_mode:
            return "boss"
        if state.safe_mode:
            return "safe"
        if state.challenge_mode:
            return "challenge"
        if state.coaching_mode:
            return "coaching"
        if state.onboarding_mode:
            return "onboarding"
        return "normal"

    # ── Построить WS payload для difficulty.update ──

    def build_ws_payload(
        self, state: IntraSessionState, base_difficulty: int,
    ) -> dict[str, Any]:
        """Формирует данные для WS-события difficulty.update."""
        return {
            "effective_difficulty": self._effective_difficulty(
                base_difficulty, state.difficulty_modifier,
            ),
            "modifier": state.difficulty_modifier,
            "mode": self.get_current_mode(state),
            "good_streak": state.good_streak,
            "bad_streak": state.bad_streak,
            "had_comeback": state.had_comeback,
            "trend": self.get_difficulty_trend(state),
        }

    # ── Финализация сессии (получить итоговые данные) ──

    async def finalize_session(self, session_id: str) -> dict[str, Any]:
        """Возвращает итоговые данные адаптации для записи в SessionHistory."""
        state = await self.get_state(session_id)
        result = {
            "max_good_streak": max(
                (h.get("new", 0) for h in state.modifier_history if h.get("new", 0) > 0),
                default=state.good_streak,
            ),
            "max_bad_streak": state.max_bad_streak_before_recovery or state.bad_streak,
            "final_difficulty_modifier": state.difficulty_modifier,
            "had_comeback": state.had_comeback,
            "mercy_activated": state.mercy_activated,
            "extra_traps_injected": state.extra_traps_injected,
        }
        # Пересчитать max streaks из истории
        max_gs = state.good_streak
        max_bs = state.bad_streak
        for entry in state.modifier_history:
            r = entry.get("reason", "")
            if "good_streak" in r:
                try:
                    streak_val = int(r.split("_")[-1])
                    max_gs = max(max_gs, streak_val)
                except ValueError:
                    pass
        result["max_good_streak"] = max_gs

        await self.delete_state(session_id)
        return result

    # ──────────────────────────────────────────────────────────────────
    #  Внутренние методы
    # ──────────────────────────────────────────────────────────────────

    def _update_streak(self, state: IntraSessionState, quality: ReplyQuality) -> None:
        if quality == ReplyQuality.GOOD:
            state.good_streak += 1
            state.bad_streak = 0
            state.total_good += 1
        elif quality == ReplyQuality.BAD:
            state.bad_streak += 1
            state.good_streak = 0
            state.total_bad += 1
        else:  # neutral
            state.total_neutral += 1
            # Neutral НЕ сбрасывает streak

    def _check_comeback(self, state: IntraSessionState) -> None:
        """Трекинг камбэка: bad_streak ≥ 5, затем good_streak ≥ 3."""
        if state.bad_streak >= COMEBACK_BAD_STREAK_THRESHOLD:
            state.max_bad_streak_before_recovery = max(
                state.max_bad_streak_before_recovery, state.bad_streak,
            )
        if (
            state.max_bad_streak_before_recovery >= COMEBACK_BAD_STREAK_THRESHOLD
            and state.good_streak >= COMEBACK_GOOD_STREAK_NEEDED
            and not state.had_comeback
        ):
            state.had_comeback = True
            logger.info("Comeback detected! max_bad=%d", state.max_bad_streak_before_recovery)

    def _check_coaching_mode(self, state: IntraSessionState) -> None:
        total = state.total_good + state.total_bad
        if total >= COACHING_MODE_THRESHOLD and not state.coaching_mode:
            ratio = state.total_good / total if total > 0 else 0.5
            if COACHING_MODE_RATIO_RANGE[0] <= ratio <= COACHING_MODE_RATIO_RANGE[1]:
                state.coaching_mode = True

    def _check_onboarding_mode(self, state: IntraSessionState) -> None:
        if (
            state.current_turn <= SOFT_START_TURNS
            and state.bad_streak >= SOFT_START_TURNS
            and not state.onboarding_mode
        ):
            state.onboarding_mode = True
            state.difficulty_modifier = MIN_MODIFIER
            state.traps_disabled = True
            state.safe_mode = True

    def _get_streak_effect(self, state: IntraSessionState) -> StreakEffect | None:
        """Определяет эффект по текущему streak."""
        # Boss mode / safe mode: уже активированы, не повторять
        if state.boss_mode or state.safe_mode or state.onboarding_mode:
            return None

        # Good streak эффекты
        if state.good_streak > 0 and state.good_streak in GOOD_STREAK_EFFECTS:
            return GOOD_STREAK_EFFECTS[state.good_streak]

        # Bad streak эффекты
        if state.bad_streak > 0 and state.bad_streak in BAD_STREAK_EFFECTS:
            effect = BAD_STREAK_EFFECTS[state.bad_streak]
            # Мягкий старт: ослабляем bad эффекты в первые N ходов
            if state.current_turn <= SOFT_START_TURNS and effect.modifier_delta < 0:
                effect = StreakEffect(
                    code=effect.code + "_soft",
                    description=effect.description + " (ослабленный)",
                    modifier_delta=0,  # Не снижаем modifier на soft start
                    hint=effect.hint,
                    direct_hint=effect.direct_hint,
                )
            return effect

        return None

    def _apply_effect(
        self,
        state: IntraSessionState,
        effect: StreakEffect | None,
        base_difficulty: int,
    ) -> None:
        if effect is None:
            state.last_action = "none"
            return

        old_modifier = state.difficulty_modifier

        # Применить modifier delta
        if effect.modifier_delta != 0:
            state.difficulty_modifier = max(
                MIN_MODIFIER,
                min(MAX_MODIFIER, state.difficulty_modifier + effect.modifier_delta),
            )

        # Обновить флаги
        if effect.challenge_mode:
            state.challenge_mode = True
            state.challenge_turns_left = effect.challenge_turns

        if effect.disable_traps:
            state.traps_disabled = True
            state.traps_disabled_turns = effect.disable_traps_turns or 999

        if effect.mercy_deal:
            state.mercy_activated = True

        if effect.boss_mode:
            state.boss_mode = True

        if effect.safe_mode:
            state.safe_mode = True

        if effect.hint or effect.direct_hint:
            state.hints_given += 1

        if effect.inject_trap:
            state.extra_traps_injected += 1

        state.softened = state.difficulty_modifier < 0
        state.last_action = effect.code

        # Записать историю
        if state.difficulty_modifier != old_modifier:
            state.modifier_history.append({
                "turn": state.current_turn,
                "old": old_modifier,
                "new": state.difficulty_modifier,
                "reason": f"{effect.code}_streak_{state.good_streak or state.bad_streak}",
            })

    @staticmethod
    def _effective_difficulty(base: int, modifier: int, chapter_ceiling: int = 10) -> int:
        """Effective difficulty clamped to [1, chapter_ceiling]."""
        return max(1, min(chapter_ceiling, base + modifier))

    def _build_action(
        self,
        state: IntraSessionState,
        effect: StreakEffect | None,
        eff_diff: int,
        base_difficulty: int,
    ) -> AdaptiveAction:
        """Строит AdaptiveAction со всеми метриками."""
        action = AdaptiveAction(
            difficulty_modifier=state.difficulty_modifier,
            effective_difficulty=eff_diff,
        )

        # Метрики, зависящие от effective_difficulty
        action.threshold_positive = BASE_THRESHOLD_POS + eff_diff * DIFFICULTY_FACTOR_POS
        action.threshold_negative = BASE_THRESHOLD_NEG - eff_diff * DIFFICULTY_FACTOR_NEG

        decay = BASE_DECAY + eff_diff * DECAY_FACTOR
        # Модификаторы decay от streak
        if state.good_streak >= 4:
            decay *= 1.2
        if state.bad_streak >= 4:
            decay *= 0.75
        if state.slow_mode:
            decay *= 0.5
        action.decay_rate = round(decay, 4)

        action.max_trap_difficulty = min(10, eff_diff + 2)
        action.trap_injection_probability = round(
            BASE_TRAP_PROB + eff_diff * TRAP_PROB_FACTOR, 3,
        )
        action.max_active_traps = 1 + eff_diff // 3

        time_limit = BASE_TIME_LIMIT - eff_diff * TIME_REDUCTION
        if state.slow_mode:
            time_limit = int(time_limit * 1.5)
        action.reply_time_limit = time_limit

        # Флаги от эффекта
        if effect:
            action.effect_code = effect.code
            action.description = effect.description
            action.inject_trap = effect.inject_trap and not state.traps_disabled
            action.trap_difficulty = min(
                action.max_trap_difficulty,
                base_difficulty + effect.trap_difficulty_bonus,
            )
            action.cascade_trap = effect.cascade
            action.fake_transition = effect.fake_transition
            action.challenge_mode = effect.challenge_mode or state.challenge_mode
            action.challenge_turns = state.challenge_turns_left
            action.give_hint = effect.hint or effect.direct_hint
            action.hint_type = (
                "direct" if effect.direct_hint
                else "standard" if effect.hint
                else ""
            )
            action.disable_traps = state.traps_disabled
            action.mercy_deal = effect.mercy_deal
            action.emotional_spike = effect.emotional_spike
            action.boss_mode = state.boss_mode
            action.safe_mode = state.safe_mode
            action.emotional_opening = effect.emotional_opening
            action.slow_down = state.slow_mode or effect.slow_down
            action.explicit_request = effect.explicit_request
            action.auto_qualify = effect.auto_qualify
            action.coaching_mode = state.coaching_mode
        else:
            action.effect_code = "none"
            action.boss_mode = state.boss_mode
            action.safe_mode = state.safe_mode
            action.coaching_mode = state.coaching_mode
            action.disable_traps = state.traps_disabled

        return action


# ──────────────────────────────────────────────────────────────────────
#  Вспомогательные функции для других модулей
# ──────────────────────────────────────────────────────────────────────

def compute_mood_thresholds(effective_difficulty: int) -> dict[str, float]:
    """Возвращает пороги Mood Buffer для данной effective_difficulty."""
    return {
        "threshold_positive": BASE_THRESHOLD_POS + effective_difficulty * DIFFICULTY_FACTOR_POS,
        "threshold_negative": BASE_THRESHOLD_NEG - effective_difficulty * DIFFICULTY_FACTOR_NEG,
        "decay_rate": BASE_DECAY + effective_difficulty * DECAY_FACTOR,
    }


def compute_trap_params(effective_difficulty: int) -> dict[str, Any]:
    """Возвращает параметры ловушек для данной effective_difficulty."""
    return {
        "max_trap_difficulty": min(10, effective_difficulty + 2),
        "trap_probability": BASE_TRAP_PROB + effective_difficulty * TRAP_PROB_FACTOR,
        "max_active_traps": 1 + effective_difficulty // 3,
    }


def compute_counter_gates(effective_difficulty: int) -> dict[str, int]:
    """Возвращает пороги counter-gate для данной effective_difficulty."""
    return {
        "skeptic_facts_required": 2 + effective_difficulty // 4,
        "empathy_signals_required": 1 + effective_difficulty // 3,
        "trust_specifics_required": 1 + effective_difficulty // 5,
    }


def compute_voice_params(effective_difficulty: int) -> dict[str, float]:
    """Возвращает параметры голоса для данной effective_difficulty."""
    return {
        "voice_variation": 0.05 + effective_difficulty * 0.03,
        "speech_rate_min": 1.0 - effective_difficulty * 0.02,
        "speech_rate_max": 1.0 + effective_difficulty * 0.03,
        "hesitation_probability": max(0.05, 0.30 - effective_difficulty * 0.025),
        "emotional_intensity": 0.3 + effective_difficulty * 0.07,
    }
