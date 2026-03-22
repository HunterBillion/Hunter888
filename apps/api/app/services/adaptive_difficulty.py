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
        """Сохраняет состояние в Redis."""
        await self._redis.set(
            self._key(session_id),
            json.dumps(state.to_dict(), ensure_ascii=False),
            ex=REDIS_TTL,
        )

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
        state = await self.get_state(session_id)
        state.current_turn += 1

        # ── Шаг 1: Обновить streak ──
        self._update_streak(state, quality)

        # ── Шаг 2: Проверить камбэк ──
        self._check_comeback(state)

        # ── Шаг 3: Проверить coaching mode (чередование) ──
        self._check_coaching_mode(state)

        # ── Шаг 4: Проверить onboarding mode (5 bad подряд в начале) ──
        self._check_onboarding_mode(state)

        # ── Шаг 5: Получить streak effect ──
        effect = self._get_streak_effect(state)

        # ── Шаг 6: Применить effect к state ──
        self._apply_effect(state, effect, base_difficulty)

        # ── Шаг 7: Обновить challenge mode countdown ──
        if state.challenge_mode and state.challenge_turns_left > 0:
            state.challenge_turns_left -= 1
            if state.challenge_turns_left <= 0:
                state.challenge_mode = False

        # ── Шаг 8: Обновить traps disabled countdown ──
        if state.traps_disabled and state.traps_disabled_turns > 0:
            state.traps_disabled_turns -= 1
            if state.traps_disabled_turns <= 0:
                state.traps_disabled = False

        # ── Шаг 9: Вычислить effective difficulty и метрики ──
        eff_diff = self._effective_difficulty(base_difficulty, state.difficulty_modifier)
        action = self._build_action(state, effect, eff_diff, base_difficulty)

        # ── Шаг 10: Сохранить ──
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
    def _effective_difficulty(base: int, modifier: int) -> int:
        return max(1, min(10, base + modifier))

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
