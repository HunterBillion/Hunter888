"""
Daily and weekly challenge generation by epoch (DOC_03 §28).

Challenges are generated based on the manager's current level/epoch.
Each challenge has: code, description, xp_reward, condition, epoch.
"""

from __future__ import annotations

from dataclasses import dataclass
from scripts.seed_levels import get_level_for_xp


@dataclass
class Challenge:
    code: str
    title: str
    description: str
    xp_reward: int
    condition: dict
    frequency: str  # "daily" | "weekly"


def get_epoch(level: int) -> int:
    """Return epoch number (1-4) for a given level."""
    if level <= 5:
        return 1
    if level <= 10:
        return 2
    if level <= 15:
        return 3
    return 4


# ─── Epoch I: Learning (Levels 1-5) ─────────────────────────────────────────

EPOCH_1_DAILY: list[Challenge] = [
    Challenge(
        code="e1_daily_variety", title="Разнообразие",
        description="Сыграйте 2 сессии с разными архетипами",
        xp_reward=30, condition={"type": "different_archetypes_today", "count": 2},
        frequency="daily",
    ),
    Challenge(
        code="e1_daily_score", title="Хороший результат",
        description="Получите score >= 60 хотя бы в 1 сессии",
        xp_reward=20, condition={"type": "min_score_today", "min_score": 60, "count": 1},
        frequency="daily",
    ),
    Challenge(
        code="e1_daily_new", title="Новый опыт",
        description="Попробуйте архетип, с которым ещё не играли",
        xp_reward=25, condition={"type": "new_archetype_played"},
        frequency="daily",
    ),
]

EPOCH_1_WEEKLY: list[Challenge] = [
    Challenge(
        code="e1_weekly_5arch", title="Пять характеров",
        description="Сыграйте 5 разных архетипов за неделю",
        xp_reward=100, condition={"type": "different_archetypes_week", "count": 5},
        frequency="weekly",
    ),
    Challenge(
        code="e1_weekly_3deals", title="Три сделки",
        description="Закройте 3 сделки за неделю",
        xp_reward=75, condition={"type": "deals_this_week", "count": 3},
        frequency="weekly",
    ),
    Challenge(
        code="e1_weekly_clean", title="Чистый звонок",
        description="Завершите 1 сессию с 0 антипаттернов",
        xp_reward=50, condition={"type": "zero_antipatterns_week", "count": 1},
        frequency="weekly",
    ),
]

# ─── Epoch II: Mastery (Levels 6-10) ────────────────────────────────────────

EPOCH_2_DAILY: list[Challenge] = [
    Challenge(
        code="e2_daily_t3", title="Сложный клиент",
        description="Сыграйте T3+ архетип с score >= 60",
        xp_reward=40, condition={"type": "t3_plus_min_score", "min_score": 60},
        frequency="daily",
    ),
    Challenge(
        code="e2_daily_traps", title="Ловкач",
        description="Обойдите 3 ловушки без попадания",
        xp_reward=30, condition={"type": "dodge_traps_today", "count": 3},
        frequency="daily",
    ),
    Challenge(
        code="e2_daily_diff6", title="Сложность 6+",
        description="Сыграйте сессию на сложности >= 6",
        xp_reward=25, condition={"type": "min_difficulty_today", "min_difficulty": 6},
        frequency="daily",
    ),
]

EPOCH_2_WEEKLY: list[Challenge] = [
    Challenge(
        code="e2_weekly_hybrids", title="Укротитель гибридов",
        description="Закройте сделку на 3 гибридных архетипах",
        xp_reward=120, condition={"type": "hybrid_deals_week", "count": 3},
        frequency="weekly",
    ),
    Challenge(
        code="e2_weekly_avg70", title="Стабильность",
        description="Средний score >= 70 за 5 сессий",
        xp_reward=100, condition={"type": "avg_score_week", "min_avg": 70, "min_sessions": 5},
        frequency="weekly",
    ),
    Challenge(
        code="e2_weekly_fakes", title="Детектор лжи",
        description="Распознайте 5 фейковых переходов",
        xp_reward=80, condition={"type": "detect_fakes_week", "count": 5},
        frequency="weekly",
    ),
    Challenge(
        code="e2_weekly_arena", title="Арена",
        description="Сыграйте 1 матч на арене",
        xp_reward=60, condition={"type": "arena_match_week", "count": 1},
        frequency="weekly",
    ),
]

# ─── Epoch III: Special Ops (Levels 11-15) ───────────────────────────────────

EPOCH_3_DAILY: list[Challenge] = [
    Challenge(
        code="e3_daily_special", title="Спецоперация",
        description="Завершите 1 спец-сценарий с score >= 55",
        xp_reward=50, condition={"type": "special_scenario_min_score", "min_score": 55},
        frequency="daily",
    ),
    Challenge(
        code="e3_daily_multi", title="Многосторонний",
        description="Закройте сделку в dual_client или multi_party",
        xp_reward=45, condition={"type": "deal_multi_party"},
        frequency="daily",
    ),
]

EPOCH_3_WEEKLY: list[Challenge] = [
    Challenge(
        code="e3_weekly_all_special", title="Все спецоперации",
        description="Пройдите все доступные спец-сценарии хотя бы 1 раз",
        xp_reward=150, condition={"type": "all_special_scenarios_week"},
        frequency="weekly",
    ),
    Challenge(
        code="e3_weekly_avg65", title="Спец-стабильность",
        description="Средний score >= 65 в спец-сценариях",
        xp_reward=120, condition={"type": "avg_special_score_week", "min_avg": 65},
        frequency="weekly",
    ),
    Challenge(
        code="e3_weekly_boss", title="Охотник на боссов",
        description="Закройте сделку с puppet_master или shifting",
        xp_reward=100, condition={"type": "deal_boss_archetype_week"},
        frequency="weekly",
    ),
]

# ─── Epoch IV: Legend (Levels 16-20) ─────────────────────────────────────────

EPOCH_4_DAILY: list[Challenge] = [
    Challenge(
        code="e4_daily_diff10", title="Максимум",
        description="Завершите 1 сессию на сложности 10",
        xp_reward=50, condition={"type": "difficulty_10_today"},
        frequency="daily",
    ),
    Challenge(
        code="e4_daily_t4", title="T4 сделка",
        description="Закройте сделку с T4 архетипом",
        xp_reward=45, condition={"type": "t4_deal_today"},
        frequency="daily",
    ),
]

EPOCH_4_WEEKLY: list[Challenge] = [
    Challenge(
        code="e4_weekly_marathon", title="Марафонец",
        description="Завершите random marathon (3 сессии)",
        xp_reward=200, condition={"type": "random_marathon_week"},
        frequency="weekly",
    ),
    Challenge(
        code="e4_weekly_stress", title="Несгибаемый",
        description="Завершите стресс-тест (5 сессий) со средним score >= 55",
        xp_reward=200, condition={"type": "stress_test_week", "min_avg": 55},
        frequency="weekly",
    ),
    Challenge(
        code="e4_weekly_mentor", title="Наставник",
        description="Проведите менторскую сессию",
        xp_reward=150, condition={"type": "mentoring_session_week"},
        frequency="weekly",
    ),
    Challenge(
        code="e4_weekly_ultimate", title="Легенда",
        description="Победите Абсолют в boss_fight",
        xp_reward=300, condition={"type": "defeat_ultimate_week"},
        frequency="weekly",
    ),
]

# ─── Public API ──────────────────────────────────────────────────────────────

EPOCH_CHALLENGES: dict[int, dict[str, list[Challenge]]] = {
    1: {"daily": EPOCH_1_DAILY, "weekly": EPOCH_1_WEEKLY},
    2: {"daily": EPOCH_2_DAILY, "weekly": EPOCH_2_WEEKLY},
    3: {"daily": EPOCH_3_DAILY, "weekly": EPOCH_3_WEEKLY},
    4: {"daily": EPOCH_4_DAILY, "weekly": EPOCH_4_WEEKLY},
}


def get_challenges_for_level(level: int) -> dict[str, list[Challenge]]:
    """Return daily + weekly challenges for the manager's current level."""
    epoch = get_epoch(level)
    return EPOCH_CHALLENGES.get(epoch, EPOCH_CHALLENGES[1])


def get_daily_challenges(level: int) -> list[Challenge]:
    """Return daily challenges for the level."""
    return get_challenges_for_level(level)["daily"]


def get_weekly_challenges(level: int) -> list[Challenge]:
    """Return weekly challenges for the level."""
    return get_challenges_for_level(level)["weekly"]
