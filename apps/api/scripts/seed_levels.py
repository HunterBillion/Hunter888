"""
ТЗ-06: Seed-скрипт для 20 уровней и 35 достижений.

Использование:
    python -m scripts.seed_levels
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────
#  Данные: 20 уровней
# ──────────────────────────────────────────────────────────────────────

LEVELS: list[dict] = [
    {
        "level": 1,
        "name": "Стажёр",
        "description": "Первое знакомство с симулятором. Базовые клиенты, простые сценарии.",
        "xp_required": 0,
        "max_difficulty": 3,
        "unlocked_archetypes": ["skeptic", "anxious", "passive", "pragmatic", "desperate"],
        "unlocked_scenarios": ["in_website", "cold_ad", "cold_referral"],
        "unlocked_mechanics": ["basic_emotions", "factual_simple_traps"],
    },
    {
        "level": 2,
        "name": "Новичок",
        "description": "Больше разнообразия клиентов. Первые ловушки.",
        "xp_required": 200,
        "max_difficulty": 3,
        "unlocked_archetypes": ["avoidant", "delegator", "grateful"],
        "unlocked_scenarios": ["in_hotline"],
        "unlocked_mechanics": ["emotional_basic_traps"],
    },
    {
        "level": 3,
        "name": "Ученик",
        "description": "Первый серьёзный вызов: агрессивные и манипулятивные клиенты.",
        "xp_required": 500,
        "max_difficulty": 4,
        "unlocked_archetypes": ["aggressive", "negotiator", "blamer"],
        "unlocked_scenarios": ["warm_callback"],
        "unlocked_mechanics": ["factual_complex_traps", "intra_session_adaptive_lite"],
    },
    {
        "level": 4,
        "name": "Практикант",
        "description": "Манипулятивные клиенты и холодный обзвон.",
        "xp_required": 900,
        "max_difficulty": 5,
        "unlocked_archetypes": ["manipulator", "returner"],
        "unlocked_scenarios": ["cold_base"],
        "unlocked_mechanics": ["emotional_advanced_traps", "multi_stage_objections"],
    },
    {
        "level": 5,
        "name": "Менеджер",
        "description": "Все базовые архетипы доступны. Полная адаптивная система.",
        "xp_required": 1400,
        "max_difficulty": 5,
        "unlocked_archetypes": ["sarcastic", "shopper", "rushed", "overwhelmed"],
        "unlocked_scenarios": ["warm_noanswer", "in_social"],
        "unlocked_mechanics": ["full_intra_session_adaptive", "hints_system"],
    },
    {
        "level": 6,
        "name": "Продвинутый",
        "description": "Параноидальные и «всезнающие» клиенты. Первые гибриды.",
        "xp_required": 2000,
        "max_difficulty": 6,
        "unlocked_archetypes": ["paranoid", "know_it_all", "referred"],
        "unlocked_scenarios": ["warm_refused"],
        "unlocked_mechanics": ["simple_hybrids", "expert_reference_traps"],
    },
    {
        "level": 7,
        "name": "Опытный",
        "description": "Враждебные клиенты, пары. Каскадные ловушки.",
        "xp_required": 2700,
        "max_difficulty": 7,
        "unlocked_archetypes": ["hostile", "couple", "ashamed"],
        "unlocked_scenarios": ["upsell", "cold_partner"],
        "unlocked_mechanics": ["cascade_traps", "couple_call_mechanic", "full_chains"],
    },
    {
        "level": 8,
        "name": "Профи",
        "description": "Все архетипы разблокированы! Fake transitions, challenge mode.",
        "xp_required": 3500,
        "max_difficulty": 8,
        "unlocked_archetypes": ["lawyer_client", "crying"],
        "unlocked_scenarios": ["rescue", "couple_call"],
        "unlocked_mechanics": ["fake_transitions", "challenge_mode", "all_trap_types"],
    },
    {
        "level": 9,
        "name": "Эксперт",
        "description": "Все сценарии разблокированы! Сложные гибриды.",
        "xp_required": 4400,
        "max_difficulty": 9,
        "unlocked_archetypes": [],  # гибриды: aggressive+know_it_all, desperate+manipulator
        "unlocked_scenarios": ["vip_debtor", "warm_dropped"],
        "unlocked_mechanics": ["combined_attack", "emotional_spike", "complex_hybrids"],
    },
    {
        "level": 10,
        "name": "Мастер",
        "description": "Максимальная сложность разблокирована. Boss mode.",
        "xp_required": 5500,
        "max_difficulty": 10,
        "unlocked_archetypes": [],  # все гибриды (3+ компонентов)
        "unlocked_scenarios": [],  # спецмодификаторы
        "unlocked_mechanics": ["boss_mode", "ultimate_traps", "full_variability"],
    },
    {
        "level": 11,
        "name": "Старший мастер I",
        "description": "Клиент с юристом на проводе. Двойной клиент.",
        "xp_required": 7000,
        "max_difficulty": 10,
        "unlocked_archetypes": [],
        "unlocked_scenarios": ["special_lawyer_on_line"],
        "unlocked_mechanics": ["dual_client", "extended_randomization"],
    },
    {
        "level": 12,
        "name": "Старший мастер II",
        "description": "Повторное обращение после отказа. Кросс-сессионная память.",
        "xp_required": 8500,
        "max_difficulty": 10,
        "unlocked_archetypes": [],
        "unlocked_scenarios": ["special_re_engagement"],
        "unlocked_mechanics": ["cross_session_memory"],
    },
    {
        "level": 13,
        "name": "Старший мастер III",
        "description": "Три кредитора одновременно. Сложная квалификация.",
        "xp_required": 10000,
        "max_difficulty": 10,
        "unlocked_archetypes": [],
        "unlocked_scenarios": ["special_multi_creditor"],
        "unlocked_mechanics": ["multi_party_conversation"],
    },
    {
        "level": 14,
        "name": "Старший мастер IV",
        "description": "Конкурент уже работает. Переманивание клиента.",
        "xp_required": 11500,
        "max_difficulty": 10,
        "unlocked_archetypes": [],
        "unlocked_scenarios": ["special_competitor_active"],
        "unlocked_mechanics": ["competitor_scenario"],
    },
    {
        "level": 15,
        "name": "Старший мастер V",
        "description": "Срочное банкротство. Time-pressure mode.",
        "xp_required": 13000,
        "max_difficulty": 10,
        "unlocked_archetypes": [],
        "unlocked_scenarios": ["special_urgent_bankruptcy"],
        "unlocked_mechanics": ["time_pressure_mode"],
    },
    {
        "level": 16,
        "name": "Гроссмейстер I",
        "description": "Рандомный марафон: 3 сессии с рандомными параметрами.",
        "xp_required": 15000,
        "max_difficulty": 10,
        "unlocked_archetypes": [],
        "unlocked_scenarios": [],
        "unlocked_mechanics": ["random_marathon", "full_randomization"],
    },
    {
        "level": 17,
        "name": "Гроссмейстер II",
        "description": "Стресс-тест: 5 агрессивных клиентов подряд.",
        "xp_required": 17000,
        "max_difficulty": 10,
        "unlocked_archetypes": [],
        "unlocked_scenarios": [],
        "unlocked_mechanics": ["stress_test_series", "fatigue_mechanic"],
    },
    {
        "level": 18,
        "name": "Гроссмейстер III",
        "description": "Режим наставника: co-op обучение.",
        "xp_required": 19000,
        "max_difficulty": 10,
        "unlocked_archetypes": [],
        "unlocked_scenarios": [],
        "unlocked_mechanics": ["mentor_mode", "coop_mode"],
    },
    {
        "level": 19,
        "name": "Гроссмейстер IV",
        "description": "Босс-файт: мега-гибриды, смена архетипа каждые 3-4 хода.",
        "xp_required": 21000,
        "max_difficulty": 10,
        "unlocked_archetypes": [],
        "unlocked_scenarios": [],
        "unlocked_mechanics": ["boss_fight", "archetype_shifting"],
    },
    {
        "level": 20,
        "name": "Легенда",
        "description": "Вершина мастерства. Custom scenario builder, replay mode.",
        "xp_required": 23000,
        "max_difficulty": 10,
        "unlocked_archetypes": [],
        "unlocked_scenarios": [],
        "unlocked_mechanics": ["custom_scenario_builder", "replay_mode", "mentor_dashboard"],
    },
]


# ──────────────────────────────────────────────────────────────────────
#  Данные: 35 достижений
# ──────────────────────────────────────────────────────────────────────

ACHIEVEMENTS: list[dict] = [
    # ─── Категория: Результаты (results) ───
    {
        "code": "first_deal",
        "name": "Первая сделка",
        "description": "Закрыл первую сделку с ИИ-клиентом",
        "condition": {"type": "outcome_count", "outcome": "deal", "count": 1},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "results",
    },
    {
        "code": "first_perfect",
        "name": "Первый идеал",
        "description": "Первый score ≥ 90 за сессию",
        "condition": {"type": "score_threshold", "min_score": 90, "count": 1},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "results",
    },
    {
        "code": "streak_3",
        "name": "Серия побед",
        "description": "3 сделки подряд",
        "condition": {"type": "deal_streak", "count": 3},
        "xp_bonus": 30,
        "rarity": "common",
        "category": "results",
    },
    {
        "code": "streak_5",
        "name": "Неудержимый",
        "description": "5 сделок подряд",
        "condition": {"type": "deal_streak", "count": 5},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "results",
    },
    {
        "code": "streak_10",
        "name": "Непобедимый",
        "description": "10 сделок подряд",
        "condition": {"type": "deal_streak", "count": 10},
        "xp_bonus": 200,
        "rarity": "epic",
        "category": "results",
    },
    {
        "code": "perfect_score",
        "name": "Перфекционист",
        "description": "Набрал 95+ баллов за одну сессию",
        "condition": {"type": "score_threshold", "min_score": 95, "count": 1},
        "xp_bonus": 100,
        "rarity": "rare",
        "category": "results",
    },
    {
        "code": "century",
        "name": "Сотня",
        "description": "Завершил 100 тренировочных сессий",
        "condition": {"type": "total_sessions", "count": 100},
        "xp_bonus": 150,
        "rarity": "rare",
        "category": "results",
    },
    {
        "code": "marathon",
        "name": "Марафонец",
        "description": "Завершил 500 тренировочных сессий",
        "condition": {"type": "total_sessions", "count": 500},
        "xp_bonus": 500,
        "rarity": "legendary",
        "category": "results",
    },
    # ─── Категория: Навыки (skills) ───
    {
        "code": "trap_master",
        "name": "Мастер ловушек",
        "description": "Обработал 10 ловушек подряд без попадания",
        "condition": {"type": "trap_dodge_streak", "count": 10},
        "xp_bonus": 50,
        "rarity": "uncommon",
        "category": "skills",
    },
    {
        "code": "trap_god",
        "name": "Бог ловушек",
        "description": "Обработал 25 ловушек подряд без попадания",
        "condition": {"type": "trap_dodge_streak", "count": 25},
        "xp_bonus": 150,
        "rarity": "epic",
        "category": "skills",
    },
    {
        "code": "chain_master",
        "name": "Цепочечник",
        "description": "Завершил 10 цепочек разговора подряд",
        "condition": {"type": "chain_completion_streak", "count": 10},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "skills",
    },
    {
        "code": "zero_antipatterns",
        "name": "Чистый звонок",
        "description": "Сессия с 0 антипаттернов",
        "condition": {"type": "zero_antipatterns", "count": 1},
        "xp_bonus": 40,
        "rarity": "common",
        "category": "skills",
    },
    {
        "code": "clean_streak",
        "name": "Чистая серия",
        "description": "5 сессий подряд с 0 антипаттернов",
        "condition": {"type": "zero_antipatterns_streak", "count": 5},
        "xp_bonus": 100,
        "rarity": "rare",
        "category": "skills",
    },
    {
        "code": "empathy_master",
        "name": "Эмпат",
        "description": "Навык «Эмпатия» достиг 90+",
        "condition": {"type": "skill_threshold", "skill": "empathy", "min_value": 90},
        "xp_bonus": 75,
        "rarity": "rare",
        "category": "skills",
    },
    {
        "code": "knowledge_guru",
        "name": "Гуру",
        "description": "Навык «Знание продукта» достиг 90+",
        "condition": {"type": "skill_threshold", "skill": "knowledge", "min_value": 90},
        "xp_bonus": 75,
        "rarity": "rare",
        "category": "skills",
    },
    {
        "code": "objection_pro",
        "name": "Возражатель",
        "description": "Навык «Работа с возражениями» достиг 90+",
        "condition": {"type": "skill_threshold", "skill": "objection_handling", "min_value": 90},
        "xp_bonus": 75,
        "rarity": "rare",
        "category": "skills",
    },
    {
        "code": "stress_shield",
        "name": "Стальные нервы",
        "description": "Навык «Стрессоустойчивость» достиг 90+",
        "condition": {"type": "skill_threshold", "skill": "stress_resistance", "min_value": 90},
        "xp_bonus": 75,
        "rarity": "rare",
        "category": "skills",
    },
    {
        "code": "closer_elite",
        "name": "Элитный клозер",
        "description": "Навык «Закрытие» достиг 90+",
        "condition": {"type": "skill_threshold", "skill": "closing", "min_value": 90},
        "xp_bonus": 75,
        "rarity": "rare",
        "category": "skills",
    },
    {
        "code": "qualifier_pro",
        "name": "Квалификатор",
        "description": "Навык «Квалификация» достиг 90+",
        "condition": {"type": "skill_threshold", "skill": "qualification", "min_value": 90},
        "xp_bonus": 75,
        "rarity": "rare",
        "category": "skills",
    },
    {
        "code": "all_skills_80",
        "name": "Мастер на все руки",
        "description": "Все 6 навыков достигли 80+",
        "condition": {"type": "all_skills_threshold", "min_value": 80},
        "xp_bonus": 200,
        "rarity": "epic",
        "category": "skills",
    },
    # ─── Категория: Вызовы (challenges) ───
    {
        "code": "stress_test",
        "name": "Стрессоустойчивый",
        "description": "Закрыл сделку с hostile/aggressive при difficulty ≥ 5",
        "condition": {"type": "deal_with_archetype", "archetypes": ["hostile", "aggressive"], "min_difficulty": 5},
        "xp_bonus": 40,
        "rarity": "common",
        "category": "challenges",
    },
    {
        "code": "comeback",
        "name": "Камбэк",
        "description": "Закрыл сделку после серии из 5+ плохих ответов",
        "condition": {"type": "comeback", "min_bad_streak": 5},
        "xp_bonus": 60,
        "rarity": "uncommon",
        "category": "challenges",
    },
    {
        "code": "speedrun",
        "name": "Спринтер",
        "description": "Закрыл сделку менее чем за 5 минут",
        "condition": {"type": "deal_under_time", "max_seconds": 300},
        "xp_bonus": 30,
        "rarity": "common",
        "category": "challenges",
    },
    {
        "code": "expert_killer",
        "name": "Экспертоборец",
        "description": "Закрыл сделку с know_it_all при difficulty ≥ 8",
        "condition": {"type": "deal_with_archetype", "archetypes": ["know_it_all"], "min_difficulty": 8},
        "xp_bonus": 80,
        "rarity": "rare",
        "category": "challenges",
    },
    {
        "code": "rescue_hero",
        "name": "Спасатель",
        "description": "Закрыл сделку в сценарии rescue при difficulty ≥ 6",
        "condition": {"type": "deal_with_scenario", "scenarios": ["rescue"], "min_difficulty": 6},
        "xp_bonus": 100,
        "rarity": "rare",
        "category": "challenges",
    },
    {
        "code": "couple_tamer",
        "name": "Укротитель пар",
        "description": "Закрыл сделку в сценарии couple_call",
        "condition": {"type": "deal_with_scenario", "scenarios": ["couple_call"]},
        "xp_bonus": 80,
        "rarity": "rare",
        "category": "challenges",
    },
    {
        "code": "boss_slayer",
        "name": "Убийца боссов",
        "description": "Закрыл сделку при активном boss_mode (good_streak ≥ 15)",
        "condition": {"type": "deal_in_boss_mode", "min_good_streak": 15},
        "xp_bonus": 150,
        "rarity": "epic",
        "category": "challenges",
    },
    {
        "code": "mercy_to_deal",
        "name": "Из пепла",
        "description": "Закрыл сделку после активации mercy_deal",
        "condition": {"type": "deal_after_mercy"},
        "xp_bonus": 120,
        "rarity": "epic",
        "category": "challenges",
    },
    {
        "code": "difficulty_10_deal",
        "name": "Максимум",
        "description": "Закрыл сделку на difficulty 10",
        "condition": {"type": "deal_at_difficulty", "difficulty": 10},
        "xp_bonus": 100,
        "rarity": "rare",
        "category": "challenges",
    },
    {
        "code": "difficulty_10_perfect",
        "name": "Абсолют",
        "description": "Score ≥ 90 на difficulty 10",
        "condition": {"type": "score_at_difficulty", "min_score": 90, "difficulty": 10},
        "xp_bonus": 300,
        "rarity": "legendary",
        "category": "challenges",
    },
    # ─── Категория: Прогрессия (progression) ───
    {
        "code": "all_archetypes",
        "name": "Универсал",
        "description": "Сыграл все 25 базовых архетипов",
        "condition": {"type": "unique_archetypes_played", "count": 25},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "progression",
    },
    {
        "code": "all_scenarios",
        "name": "Путешественник",
        "description": "Сыграл все 15 базовых сценариев",
        "condition": {"type": "unique_scenarios_played", "count": 15},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "progression",
    },
    {
        "code": "weekly_warrior",
        "name": "Боец недели",
        "description": "20+ сессий за одну неделю",
        "condition": {"type": "weekly_sessions", "count": 20},
        "xp_bonus": 100,
        "rarity": "uncommon",
        "category": "progression",
    },
    {
        "code": "daily_grind",
        "name": "Ежедневная практика",
        "description": "7 дней подряд хотя бы по 1 сессии",
        "condition": {"type": "daily_streak", "count": 7},
        "xp_bonus": 60,
        "rarity": "common",
        "category": "progression",
    },
    {
        "code": "level_20",
        "name": "Легенда",
        "description": "Достиг максимального 20 уровня",
        "condition": {"type": "reach_level", "level": 20},
        "xp_bonus": 1000,
        "rarity": "legendary",
        "category": "progression",
    },
]


# ──────────────────────────────────────────────────────────────────────
#  Seed-функция
# ──────────────────────────────────────────────────────────────────────

async def seed_levels_and_achievements() -> None:
    """Заполняет level_definitions и achievement_definitions."""
    from sqlalchemy import select, text
    from app.database import async_session as async_session_factory
    from app.models.progress import LevelDefinition, AchievementDefinition

    async with async_session_factory() as session:
        async with session.begin():
            # ── Уровни ──
            existing_levels = (await session.execute(select(LevelDefinition.level))).scalars().all()
            for lvl in LEVELS:
                if lvl["level"] not in existing_levels:
                    session.add(LevelDefinition(**lvl))
                else:
                    # Upsert: обновляем существующие
                    await session.execute(
                        text("""
                            UPDATE level_definitions SET
                                name = :name,
                                description = :description,
                                xp_required = :xp_required,
                                max_difficulty = :max_difficulty,
                                unlocked_archetypes = :unlocked_archetypes::jsonb,
                                unlocked_scenarios = :unlocked_scenarios::jsonb,
                                unlocked_mechanics = :unlocked_mechanics::jsonb
                            WHERE level = :level
                        """),
                        {
                            **lvl,
                            "unlocked_archetypes": str(lvl["unlocked_archetypes"]).replace("'", '"'),
                            "unlocked_scenarios": str(lvl["unlocked_scenarios"]).replace("'", '"'),
                            "unlocked_mechanics": str(lvl["unlocked_mechanics"]).replace("'", '"'),
                        },
                    )

            # ── Достижения ──
            existing_codes = (
                await session.execute(select(AchievementDefinition.code))
            ).scalars().all()
            for ach in ACHIEVEMENTS:
                if ach["code"] not in existing_codes:
                    session.add(AchievementDefinition(**ach))

        await session.commit()
        print(f"✅ Seeded {len(LEVELS)} levels and {len(ACHIEVEMENTS)} achievements")


# ──────────────────────────────────────────────────────────────────────
#  Экспорт констант (для использования в других модулях)
# ──────────────────────────────────────────────────────────────────────

# XP-пороги по уровням (для быстрого доступа без БД)
LEVEL_XP_THRESHOLDS: dict[int, int] = {lvl["level"]: lvl["xp_required"] for lvl in LEVELS}

# Кумулятивные разблокировки (все архетипы доступные на уровне N)
def get_cumulative_archetypes(level: int) -> list[str]:
    """Возвращает ВСЕ архетипы, доступные на данном уровне."""
    result: list[str] = []
    for lvl in LEVELS:
        if lvl["level"] <= level:
            result.extend(lvl["unlocked_archetypes"])
    return result


def get_cumulative_scenarios(level: int) -> list[str]:
    """Возвращает ВСЕ сценарии, доступные на данном уровне."""
    result: list[str] = []
    for lvl in LEVELS:
        if lvl["level"] <= level:
            result.extend(lvl["unlocked_scenarios"])
    return result


def get_max_difficulty(level: int) -> int:
    """Возвращает максимальную доступную сложность для уровня."""
    for lvl in reversed(LEVELS):
        if lvl["level"] <= level:
            return lvl["max_difficulty"]
    return 3


def get_level_for_xp(total_xp: int) -> int:
    """Определяет уровень по общему количеству XP."""
    current_level = 1
    for lvl in LEVELS:
        if total_xp >= lvl["xp_required"]:
            current_level = lvl["level"]
        else:
            break
    return current_level


def get_level_name(level: int) -> str:
    """Возвращает русское название уровня."""
    for lvl in LEVELS:
        if lvl["level"] == level:
            return lvl["name"]
    return "Неизвестный"


# ──────────────────────────────────────────────────────────────────────
#  Entrypoint
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    asyncio.run(seed_levels_and_achievements())
