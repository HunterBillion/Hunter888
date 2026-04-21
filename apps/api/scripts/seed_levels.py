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
    # ═══ EPOCH I: ОБУЧЕНИЕ (Levels 1-5) ═══
    {
        "level": 1, "name": "Новобранец", "xp_required": 0, "max_difficulty": 3,
        "description": "Первое знакомство с симулятором. Безопасная среда: простые клиенты из 4 базовых групп, без ловушек и обманных переходов.",
        "unlocked_archetypes": ["skeptic", "anxious", "passive", "pragmatic", "desperate", "concrete", "procrastinator"],
        "unlocked_scenarios": ["in_website", "cold_ad", "cold_referral"],
        "unlocked_mechanics": ["basic_emotions", "factual_simple_traps"],
    },
    {
        "level": 2, "name": "Оператор", "xp_required": 500, "max_difficulty": 3,
        "description": "Расширение кругозора: 9 новых архетипов из 5 групп. От благодарного до аналитика-паралитика. Эмоциональные ловушки базового уровня.",
        "unlocked_archetypes": ["grateful", "delegator", "avoidant", "stubborn", "guilty", "family_man", "elderly", "referred", "overthinker"],
        "unlocked_scenarios": ["in_hotline", "cold_social"],
        "unlocked_mechanics": ["emotional_basic_traps"],
    },
    {
        "level": 3, "name": "Консультант", "xp_required": 1200, "max_difficulty": 4,
        "description": "Доменно-специфические клиенты: переговорщики, обвинители. Первые сложные техники. Разблокировка базового конструктора.",
        "unlocked_archetypes": ["blamer", "negotiator", "young_debtor", "just_fired", "teacher", "doctor", "influenced"],
        "unlocked_scenarios": ["warm_callback", "in_chatbot", "cold_database"],
        "unlocked_mechanics": ["factual_complex_traps", "intra_session_adaptive_lite", "constructor_basic"],
    },
    {
        "level": 4, "name": "Менеджер", "xp_required": 2000, "max_difficulty": 5,
        "description": "Манипуляторы и конспирологи. Мульти-стадийные возражения. 11 новых архетипов из Social, Cognitive, Temporal.",
        "unlocked_archetypes": ["manipulator", "returner", "conspiracy", "ashamed", "auditor", "storyteller", "misinformed", "collector_call", "accountant", "reputation_guard", "breadwinner"],
        "unlocked_scenarios": ["cold_base", "warm_repeat", "in_partner", "special_ghosted"],
        "unlocked_mechanics": ["emotional_advanced_traps", "multi_stage_objections"],
    },
    {
        "level": 5, "name": "Ст. менеджер", "xp_required": 3200, "max_difficulty": 5,
        "description": "Полная адаптивная система. 15 новых архетипов включая маятник и фильтратор. Конструктор: +контекст клиента. PvP и Knowledge Quiz открыты.",
        "unlocked_archetypes": ["sarcastic", "shopper", "rushed", "overwhelmed", "deflector", "agreeable_ghost", "mood_swinger", "selective_listener", "technical", "it_specialist", "military", "court_notice", "salary_arrest", "strategist", "intermediary"],
        "unlocked_scenarios": ["warm_noanswer", "in_social", "cold_partner", "warm_webinar", "follow_up_first", "special_urgent"],
        "unlocked_mechanics": ["full_intra_session_adaptive", "hints_system", "constructor_context", "pvp_classic", "knowledge_quiz"],
    },
    # ═══ EPOCH II: МАСТЕРСТВО (Levels 6-10) ═══
    {
        "level": 6, "name": "Клозер", "xp_required": 5700, "max_difficulty": 6,
        "description": "Параноики и всезнайки. Первые гибриды. Конструктор: +эмоциональный пресет. 9 новых архетипов.",
        "unlocked_archetypes": ["know_it_all", "paranoid", "guarantor", "righteous", "black_white", "community_leader", "salesperson", "ghosting", "foreign_speaker"],
        "unlocked_scenarios": ["warm_refused", "cold_premium", "special_guarantor", "crisis_collector"],
        "unlocked_mechanics": ["simple_hybrids", "expert_reference_traps", "constructor_emotion_preset"],
    },
    {
        "level": 7, "name": "Дожимщик", "xp_required": 9200, "max_difficulty": 7,
        "description": "Враждебные клиенты, пары. Каскадные ловушки и полные цепочки. 13 новых архетипов включая пассивно-агрессивного.",
        "unlocked_archetypes": ["hostile", "aggressive", "couple", "frozen", "fortress", "caregiver", "repeat_caller", "pre_court", "post_refusal", "passive_aggressive", "divorced", "memory_issues", "government"],
        "unlocked_scenarios": ["upsell", "warm_dropped", "special_couple", "follow_up_second", "crisis_pre_court", "compliance_basic"],
        "unlocked_mechanics": ["cascade_traps", "couple_call_mechanic", "full_chains", "pvp_tournament"],
    },
    {
        "level": 8, "name": "Антикризисный", "xp_required": 13700, "max_difficulty": 8,
        "description": "Фейковые переходы и challenge mode. Конструктор: +модификаторы среды. 10 новых архетипов T3-T4.",
        "unlocked_archetypes": ["lawyer_client", "crying", "power_player", "litigious", "widow", "inheritance_trap", "business_collapse", "aggressive_desperate", "manipulator_crying", "journalist"],
        "unlocked_scenarios": ["rescue", "warm_vip", "special_inheritance", "follow_up_third", "crisis_business", "compliance_docs"],
        "unlocked_mechanics": ["fake_transitions", "challenge_mode", "all_trap_types", "constructor_environment"],
    },
    {
        "level": 9, "name": "Эксперт 127-ФЗ", "xp_required": 19700, "max_difficulty": 9,
        "description": "Сложные гибриды и комбинированные атаки. Конструктор: +превью-досье (все 8 шагов). 5 новых экстремальных архетипов.",
        "unlocked_archetypes": ["know_it_all_paranoid", "couple_disagreeing", "scorched_earth", "psychologist", "magical_thinker"],
        "unlocked_scenarios": ["vip_debtor", "special_psychologist", "follow_up_rescue", "crisis_criminal", "compliance_legal", "multi_party_basic"],
        "unlocked_mechanics": ["combined_attack", "emotional_spike", "complex_hybrids", "constructor_preview", "pvp_rapid_fire", "bot_ladder"],
    },
    {
        "level": 10, "name": "Мастер", "xp_required": 27700, "max_difficulty": 10,
        "description": "Максимальная сложность. Boss mode. Все тиры архетипов доступны. 9 T4-архетипов включая истерика и VIP.",
        "unlocked_archetypes": ["smoke_screen", "hysteric", "celebrity", "elderly_paranoid", "multi_debtor_family", "medical_crisis", "criminal_risk", "lawyer_level_2", "competitor_employee"],
        "unlocked_scenarios": ["special_vip", "special_medical", "crisis_full", "compliance_full", "multi_party_creditors", "multi_party_family"],
        "unlocked_mechanics": ["boss_mode", "ultimate_traps", "full_variability", "pvp_gauntlet", "boss_rush"],
    },
    # ═══ EPOCH III: СПЕЦОПЕРАЦИИ (Levels 11-15) ═══
    {
        "level": 11, "name": "Спецагент I", "xp_required": 39700, "max_difficulty": 10,
        "description": "Юрист на проводе — двойной клиент. Кукловод разблокирован.",
        "unlocked_archetypes": ["puppet_master"],
        "unlocked_scenarios": ["special_lawyer_on_line", "multi_party_lawyer"],
        "unlocked_mechanics": ["dual_client", "extended_randomization"],
    },
    {
        "level": 12, "name": "Спецагент II", "xp_required": 53700, "max_difficulty": 10,
        "description": "Повторное обращение после отказа. Кросс-сессионная память. Истерик-сутяжник. Командный PvP 2v2.",
        "unlocked_archetypes": ["hysteric_litigious"],
        "unlocked_scenarios": ["special_re_engagement", "follow_up_memory"],
        "unlocked_mechanics": ["cross_session_memory", "team_battle_2v2"],
    },
    {
        "level": 13, "name": "Спецагент III", "xp_required": 71700, "max_difficulty": 10,
        "description": "Три кредитора одновременно. Юрист-кукловод — каскад юридических ловушек.",
        "unlocked_archetypes": ["puppet_master_lawyer"],
        "unlocked_scenarios": ["special_multi_creditor", "multi_party_full", "compliance_advanced"],
        "unlocked_mechanics": ["multi_party_conversation"],
    },
    {
        "level": 14, "name": "Командир", "xp_required": 93700, "max_difficulty": 10,
        "description": "Активный конкурент. Переманивание клиента у другой компании.",
        "unlocked_archetypes": [],
        "unlocked_scenarios": ["special_competitor_active", "special_dissatisfied"],
        "unlocked_mechanics": ["competitor_scenario"],
    },
    {
        "level": 15, "name": "Командир II", "xp_required": 121700, "max_difficulty": 10,
        "description": "Срочное банкротство под давлением времени. Хамелеон разблокирован — смена архетипа каждые 3-4 хода.",
        "unlocked_archetypes": ["shifting"],
        "unlocked_scenarios": ["special_urgent_bankruptcy", "crisis_deadline"],
        "unlocked_mechanics": ["time_pressure_mode"],
    },
    # ═══ EPOCH IV: ЛЕГЕНДА (Levels 16-20) ═══
    {
        "level": 16, "name": "Гроссмейстер I", "xp_required": 156700, "max_difficulty": 10,
        "description": "Рандомный марафон: 3 сессии с полностью рандомными параметрами. Гибриды в конструкторе.",
        "unlocked_archetypes": [],
        "unlocked_scenarios": [],
        "unlocked_mechanics": ["random_marathon", "full_randomization", "constructor_multi_hybrid"],
    },
    {
        "level": 17, "name": "Гроссмейстер II", "xp_required": 191700, "max_difficulty": 10,
        "description": "Стресс-тест: 5 агрессивных клиентов подряд. Механика усталости менеджера.",
        "unlocked_archetypes": [],
        "unlocked_scenarios": [],
        "unlocked_mechanics": ["stress_test_series", "fatigue_mechanic"],
    },
    {
        "level": 18, "name": "Гроссмейстер III", "xp_required": 241700, "max_difficulty": 10,
        "description": "Режим наставника: co-op обучение младших менеджеров. Шаринг персонажей.",
        "unlocked_archetypes": [],
        "unlocked_scenarios": ["special_mentoring", "special_coop"],
        "unlocked_mechanics": ["mentor_mode", "coop_mode", "character_sharing"],
    },
    {
        "level": 19, "name": "Директор", "xp_required": 311700, "max_difficulty": 10,
        "description": "Босс-файт: Абсолют — 3+ архетипов, все механики, все ловушки. Финальное испытание.",
        "unlocked_archetypes": ["ultimate"],
        "unlocked_scenarios": ["special_boss"],
        "unlocked_mechanics": ["boss_fight", "archetype_shifting"],
    },
    {
        "level": 20, "name": "Охотник", "xp_required": 381700, "max_difficulty": 10,
        "description": "Вершина мастерства. Custom scenario builder, replay mode, mentor dashboard. Все возможности платформы.",
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
        "code": "marathon_500",
        "name": "Полтысячи",
        "description": "500 тренировок. Это уже образ жизни.",
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
        "description": "Все 10 навыков достигли 80+",
        "condition": {"type": "all_skills_threshold", "min_value": 80},
        "xp_bonus": 200,
        "rarity": "epic",
        "category": "skills",
    },
    {
        "code": "all_skills_90",
        "name": "Универсальный мастер",
        "description": "Все 10 навыков достигли 90+",
        "condition": {"type": "all_skills_threshold", "min_value": 90},
        "xp_bonus": 500,
        "rarity": "legendary",
        "category": "skills",
    },
    # ─── New skill achievements (DOC_06: 4 new skills) ───
    {
        "code": "time_master",
        "name": "Хронометрист",
        "description": "Навык «Тайм-менеджмент» достиг 90+",
        "condition": {"type": "skill_threshold", "skill": "time_management", "min_value": 90},
        "xp_bonus": 75,
        "rarity": "rare",
        "category": "skills",
    },
    {
        "code": "chameleon",
        "name": "Хамелеон",
        "description": "Навык «Адаптация» достиг 90+",
        "condition": {"type": "skill_threshold", "skill": "adaptation", "min_value": 90},
        "xp_bonus": 75,
        "rarity": "rare",
        "category": "skills",
    },
    {
        "code": "legal_expert",
        "name": "Юрист",
        "description": "Навык «Юридические знания» достиг 90+",
        "condition": {"type": "skill_threshold", "skill": "legal_knowledge", "min_value": 90},
        "xp_bonus": 75,
        "rarity": "rare",
        "category": "skills",
    },
    {
        "code": "rapport_master",
        "name": "Мастер раппорта",
        "description": "Навык «Построение раппорта» достиг 90+",
        "condition": {"type": "skill_threshold", "skill": "rapport_building", "min_value": 90},
        "xp_bonus": 75,
        "rarity": "rare",
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
        "condition": {"type": "deal_with_scenario", "scenarios": ["special_couple"]},
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
    # ─── Эмоциональные ачивки (XHUNTER_PLAN_v2 §2.5) ───
    {
        "code": "first_number",
        "name": "Первый звонок",
        "description": "Ты набрал номер. Это уже больше, чем многие.",
        "condition": {"type": "total_sessions", "count": 1},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "narrative",
    },
    {
        "code": "first_rejection",
        "name": "Первый отказ",
        "description": "Бывает. Каждый отказ — урок. Двигайся дальше.",
        "condition": {"type": "score_below", "max_score": 30, "count": 1},
        "xp_bonus": 30,
        "rarity": "common",
        "category": "narrative",
    },
    {
        "code": "from_ashes",
        "name": "Из пепла",
        "description": "Разговор шёл не по плану. Но ты вытянул сделку.",
        "condition": {"type": "deal_after_bad_replies", "bad_count": 5},
        "xp_bonus": 500,
        "rarity": "epic",
        "category": "narrative",
    },
    {
        "code": "night_owl",
        "name": "Ночная смена",
        "description": "Тренировки после 22:00. Дисциплина не знает расписания.",
        "condition": {"type": "sessions_after_hour", "hour": 22, "count": 5},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "narrative",
    },
    {
        "code": "steel_nerves",
        "name": "Стальные нервы",
        "description": "Клиент давил. Угрожал. Ты сохранил спокойствие и закрыл сделку.",
        "condition": {"type": "deal_with_archetype", "archetype": "aggressive", "min_difficulty": 9},
        "xp_bonus": 1000,
        "rarity": "legendary",
        "category": "narrative",
    },
    {
        "code": "revenge",
        "name": "Реванш",
        "description": "Ловушка побеждала трижды. На четвёртый раз — ты справился.",
        "condition": {"type": "trap_dodge_after_fails", "fail_count": 3},
        "xp_bonus": 500,
        "rarity": "epic",
        "category": "narrative",
    },
    {
        "code": "understood_all",
        "name": "Знаток людей",
        "description": "Работал с каждым типом клиента. Теперь понимаешь всех.",
        "condition": {"type": "unique_archetypes_played", "count": 100},
        "xp_bonus": 1000,
        "rarity": "legendary",
        "category": "narrative",
    },
    {
        "code": "arena_debut",
        "name": "Дебют на арене",
        "description": "Первая победа в PvP. Ты готов к соревнованиям.",
        "condition": {"type": "pvp_wins", "count": 1},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "narrative",
    },
    {
        "code": "winning_streak",
        "name": "Серия побед",
        "description": "5 побед подряд на арене. Уверенность растёт.",
        "condition": {"type": "pvp_win_streak", "count": 5},
        "xp_bonus": 500,
        "rarity": "epic",
        "category": "narrative",
    },
    {
        "code": "daily_discipline",
        "name": "Дисциплина дня",
        "description": "10 тренировок за один день. Не одержимость — целеустремлённость.",
        "condition": {"type": "sessions_in_day", "count": 10},
        "xp_bonus": 500,
        "rarity": "epic",
        "category": "narrative",
    },
    {
        "code": "impossible",
        "name": "За гранью возможного",
        "description": "95+ баллов на максимальной сложности. Мастерство в чистом виде.",
        "condition": {"type": "score_threshold_difficulty", "min_score": 95, "min_difficulty": 10},
        "xp_bonus": 1000,
        "rarity": "legendary",
        "category": "narrative",
    },
    # ─── Scenario milestones (kept: 45/60 as endpoints) ───
    {
        "code": "scenarios_45",
        "name": "Первопроходец",
        "description": "Сыграл 45 разных сценариев",
        "condition": {"type": "unique_scenarios_played", "count": 45},
        "xp_bonus": 400,
        "rarity": "epic",
        "category": "progression",
    },
    {
        "code": "scenarios_60",
        "name": "Мастер всех сценариев",
        "description": "Сыграл все 60 сценариев",
        "condition": {"type": "unique_scenarios_played", "count": 60},
        "xp_bonus": 1000,
        "rarity": "legendary",
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

    # ═══════════════════════════════════════════════════════════════════
    #  NEW ACHIEVEMENTS (92 entries)
    # ═══════════════════════════════════════════════════════════════════

    # ─── Категория: Результаты (results) — 12 new ───
    {
        "code": "sessions_10",
        "name": "Десятка",
        "description": "Завершил 10 тренировочных сессий",
        "condition": {"type": "total_sessions", "count": 10},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "results",
    },
    {
        "code": "sessions_50",
        "name": "Полсотни",
        "description": "Завершил 50 тренировочных сессий",
        "condition": {"type": "total_sessions", "count": 50},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "results",
    },
    {
        "code": "sessions_1000",
        "name": "Тысячник",
        "description": "Завершил 1000 тренировочных сессий",
        "condition": {"type": "total_sessions", "count": 1000},
        "xp_bonus": 1000,
        "rarity": "legendary",
        "category": "results",
    },
    {
        "code": "deals_10",
        "name": "Десять сделок",
        "description": "Закрыл 10 сделок",
        "condition": {"type": "total_deals", "count": 10},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "results",
    },
    {
        "code": "deals_50",
        "name": "Полсотни сделок",
        "description": "Закрыл 50 сделок",
        "condition": {"type": "total_deals", "count": 50},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "results",
    },
    {
        "code": "deals_100",
        "name": "Сотня сделок",
        "description": "Закрыл 100 сделок",
        "condition": {"type": "total_deals", "count": 100},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "results",
    },
    {
        "code": "deals_500",
        "name": "Пятьсот сделок",
        "description": "Закрыл 500 сделок",
        "condition": {"type": "total_deals", "count": 500},
        "xp_bonus": 500,
        "rarity": "epic",
        "category": "results",
    },
    {
        "code": "score_70_first",
        "name": "Первый порог",
        "description": "Первый score ≥ 70 за сессию",
        "condition": {"type": "score_threshold", "min_score": 70, "count": 1},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "results",
    },
    {
        "code": "score_80_first",
        "name": "Хороший старт",
        "description": "Первый score ≥ 80 за сессию",
        "condition": {"type": "score_threshold", "min_score": 80, "count": 1},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "results",
    },
    {
        "code": "score_100",
        "name": "Абсолютный идеал",
        "description": "Набрал 100 баллов за сессию",
        "condition": {"type": "score_threshold", "min_score": 100, "count": 1},
        "xp_bonus": 500,
        "rarity": "epic",
        "category": "results",
    },
    {
        "code": "training_10h",
        "name": "10 часов",
        "description": "Суммарно 10 часов тренировок",
        "condition": {"type": "total_training_hours", "hours": 10},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "results",
    },
    {
        "code": "training_50h",
        "name": "50 часов",
        "description": "Суммарно 50 часов тренировок",
        "condition": {"type": "total_training_hours", "hours": 50},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "results",
    },

    # ─── Категория: Вызовы (challenges) — 15 new ───
    {
        "code": "resistance_breaker",
        "name": "Укротитель сопротивления",
        "description": "Закрыл сделку с архетипом из группы сопротивления",
        "condition": {"type": "deal_with_archetype_group", "group": "resistance"},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "challenges",
    },
    {
        "code": "emotional_handler",
        "name": "Эмоциональный мастер",
        "description": "Закрыл сделку с архетипом из эмоциональной группы",
        "condition": {"type": "deal_with_archetype_group", "group": "emotional"},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "challenges",
    },
    {
        "code": "control_dominator",
        "name": "Обуздатель контроля",
        "description": "Закрыл сделку с архетипом из группы контроля",
        "condition": {"type": "deal_with_archetype_group", "group": "control"},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "challenges",
    },
    {
        "code": "avoidance_catcher",
        "name": "Ловец уклонистов",
        "description": "Закрыл сделку с архетипом из группы уклонения",
        "condition": {"type": "deal_with_archetype_group", "group": "avoidance"},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "challenges",
    },
    {
        "code": "all_groups_dealt",
        "name": "Мастер всех групп",
        "description": "Закрыл сделки со всеми группами архетипов (минимум 10 в каждой)",
        "condition": {"type": "deal_with_archetype_group_all", "min_count": 10},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "challenges",
    },
    {
        "code": "outbound_cold_complete",
        "name": "Холодный мастер",
        "description": "Прошёл все сценарии группы A — исходящие холодные",
        "condition": {"type": "scenario_group_complete", "group": "A_outbound_cold"},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "challenges",
    },
    {
        "code": "outbound_warm_complete",
        "name": "Тёплый мастер",
        "description": "Прошёл все сценарии группы B — исходящие тёплые",
        "condition": {"type": "scenario_group_complete", "group": "B_outbound_warm"},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "challenges",
    },
    {
        "code": "inbound_complete",
        "name": "Входящий мастер",
        "description": "Прошёл все сценарии группы C — входящие",
        "condition": {"type": "scenario_group_complete", "group": "C_inbound"},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "challenges",
    },
    {
        "code": "special_complete",
        "name": "Спец по спецам",
        "description": "Прошёл все сценарии группы D — спецсценарии",
        "condition": {"type": "scenario_group_complete", "group": "D_special"},
        "xp_bonus": 100,
        "rarity": "rare",
        "category": "challenges",
    },
    {
        "code": "diff_3_deal",
        "name": "Первая ступень",
        "description": "Закрыл сделку на difficulty 3",
        "condition": {"type": "deal_at_difficulty", "difficulty": 3},
        "xp_bonus": 30,
        "rarity": "common",
        "category": "challenges",
    },
    {
        "code": "diff_5_deal",
        "name": "Средний уровень",
        "description": "Закрыл сделку на difficulty 5",
        "condition": {"type": "deal_at_difficulty", "difficulty": 5},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "challenges",
    },
    {
        "code": "diff_7_deal",
        "name": "Высшая лига",
        "description": "Закрыл сделку на difficulty 7",
        "condition": {"type": "deal_at_difficulty", "difficulty": 7},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "challenges",
    },
    {
        "code": "compound_deal",
        "name": "Укротитель гибрида",
        "description": "Закрыл сделку с гибридным архетипом (2+ компонента)",
        "condition": {"type": "compound_archetype_deal", "min_components": 2},
        "xp_bonus": 100,
        "rarity": "rare",
        "category": "challenges",
    },
    {
        "code": "ultimate_deal",
        "name": "Победитель Ultimate",
        "description": "Закрыл сделку с гибридным архетипом (3+ компонента)",
        "condition": {"type": "compound_archetype_deal", "min_components": 3},
        "xp_bonus": 200,
        "rarity": "epic",
        "category": "challenges",
    },
    {
        "code": "solo_legend",
        "name": "Одинокий волк",
        "description": "Закрыл сделку: score ≥ 90, difficulty 10, гибрид, без подсказок",
        "condition": {"type": "solo_legend", "min_score": 90, "difficulty": 10, "compound": True, "no_hints": True},
        "xp_bonus": 1000,
        "rarity": "legendary",
        "category": "challenges",
    },

    # ─── Категория: Прогрессия (progression) — 10 new ───
    {
        "code": "level_5",
        "name": "Кадет",
        "description": "Достиг 5 уровня",
        "condition": {"type": "reach_level", "level": 5},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "progression",
    },
    {
        "code": "level_10",
        "name": "Лейтенант",
        "description": "Достиг 10 уровня",
        "condition": {"type": "reach_level", "level": 10},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "progression",
    },
    {
        "code": "level_15",
        "name": "Капитан",
        "description": "Достиг 15 уровня",
        "condition": {"type": "reach_level", "level": 15},
        "xp_bonus": 500,
        "rarity": "epic",
        "category": "progression",
    },
    {
        "code": "epoch_1_complete",
        "name": "Эпоха новичка",
        "description": "Завершил Эпоху I (уровни 1-5)",
        "condition": {"type": "epoch_complete", "epoch": 1},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "progression",
    },
    {
        "code": "epoch_2_complete",
        "name": "Эпоха роста",
        "description": "Завершил Эпоху II (уровни 6-10)",
        "condition": {"type": "epoch_complete", "epoch": 2},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "progression",
    },
    {
        "code": "epoch_3_complete",
        "name": "Эпоха мастерства",
        "description": "Завершил Эпоху III (уровни 11-15)",
        "condition": {"type": "epoch_complete", "epoch": 3},
        "xp_bonus": 500,
        "rarity": "epic",
        "category": "progression",
    },
    {
        "code": "epoch_4_complete",
        "name": "Эпоха легенды",
        "description": "Завершил Эпоху IV (уровни 16-20)",
        "condition": {"type": "epoch_complete", "epoch": 4},
        "xp_bonus": 1000,
        "rarity": "legendary",
        "category": "progression",
    },
    # NOTE: archetypes_50_v2, archetypes_100_v2, scenarios_30_v2 removed — duplicates
    # of narrative achievements (understood_all, etc). See §2.5 cleanup.

    # ─── Категория: Арена (arena) — 20 new ───
    {
        "code": "arena_first_fight",
        "name": "Первый бой",
        "description": "Провёл первый PvP-матч на арене",
        "condition": {"type": "arena_pvp_matches", "count": 1},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "arena",
    },
    {
        "code": "arena_first_win",
        "name": "Первая победа",
        "description": "Выиграл первый PvP-матч на арене",
        "condition": {"type": "arena_pvp_wins", "count": 1},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "arena",
    },
    {
        "code": "arena_win_streak_5",
        "name": "Серия побед",
        "description": "5 побед подряд на арене",
        "condition": {"type": "arena_pvp_streak", "count": 5},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "arena",
    },
    {
        "code": "arena_win_streak_10",
        "name": "Непобедимый боец",
        "description": "10 побед подряд на арене",
        "condition": {"type": "arena_pvp_streak", "count": 10},
        "xp_bonus": 500,
        "rarity": "epic",
        "category": "arena",
    },
    {
        "code": "arena_duelist_10",
        "name": "Дуэлянт",
        "description": "Выиграл 10 PvP-матчей на арене",
        "condition": {"type": "arena_pvp_wins", "count": 10},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "arena",
    },
    {
        "code": "arena_duelist_50",
        "name": "Гладиатор",
        "description": "Выиграл 50 PvP-матчей на арене",
        "condition": {"type": "arena_pvp_wins", "count": 50},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "arena",
    },
    {
        "code": "arena_tier_silver",
        "name": "Серебряный боец",
        "description": "Достиг серебряного тира на арене",
        "condition": {"type": "arena_tier_reached", "tier": "silver"},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "arena",
    },
    {
        "code": "arena_tier_gold",
        "name": "Золотой боец",
        "description": "Достиг золотого тира на арене",
        "condition": {"type": "arena_tier_reached", "tier": "gold"},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "arena",
    },
    {
        "code": "arena_tier_platinum",
        "name": "Платиновый боец",
        "description": "Достиг платинового тира на арене",
        "condition": {"type": "arena_tier_reached", "tier": "platinum"},
        "xp_bonus": 500,
        "rarity": "epic",
        "category": "arena",
    },
    {
        "code": "arena_tier_diamond",
        "name": "Бриллиантовый",
        "description": "Достиг бриллиантового тира на арене",
        "condition": {"type": "arena_tier_reached", "tier": "diamond"},
        "xp_bonus": 1000,
        "rarity": "legendary",
        "category": "arena",
    },
    {
        "code": "arena_classic_win",
        "name": "Классик",
        "description": "Победил в классическом режиме арены",
        "condition": {"type": "arena_mode_win", "mode": "classic"},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "arena",
    },
    {
        "code": "arena_rapid_win",
        "name": "Молниеносный",
        "description": "Победил в режиме rapid fire на арене",
        "condition": {"type": "arena_mode_win", "mode": "rapid_fire"},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "arena",
    },
    {
        "code": "arena_gauntlet_win",
        "name": "Испытатель",
        "description": "Победил в режиме gauntlet на арене",
        "condition": {"type": "arena_mode_win", "mode": "gauntlet"},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "arena",
    },
    {
        "code": "arena_team_win",
        "name": "Командный боец",
        "description": "Победил в режиме командного боя на арене",
        "condition": {"type": "arena_mode_win", "mode": "team_battle"},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "arena",
    },
    {
        "code": "arena_blitz_perfect",
        "name": "Идеальный блиц",
        "description": "Идеальное прохождение блиц-режима на арене",
        "condition": {"type": "arena_blitz_perfect"},
        "xp_bonus": 500,
        "rarity": "epic",
        "category": "arena",
    },
    {
        "code": "arena_all_categories",
        "name": "Эрудит",
        "description": "Освоил 10 категорий с точностью ≥ 80% на арене",
        "condition": {"type": "arena_category_mastered", "count": 10, "min_accuracy": 80},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "arena",
    },
    {
        "code": "arena_fz127_expert",
        "name": "Эксперт 127-ФЗ",
        "description": "Освоил 10 категорий с точностью ≥ 90% на арене",
        "condition": {"type": "arena_category_mastered", "count": 10, "min_accuracy": 90},
        "xp_bonus": 500,
        "rarity": "epic",
        "category": "arena",
    },
    {
        "code": "arena_first_tournament",
        "name": "Турнирный боец",
        "description": "Принял участие в первом турнире",
        "condition": {"type": "arena_tournament_participated", "count": 1},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "arena",
    },
    {
        "code": "arena_podium",
        "name": "Подиум",
        "description": "Занял место в топ-3 на турнире",
        "condition": {"type": "arena_tournament_place", "max_place": 3},
        "xp_bonus": 500,
        "rarity": "epic",
        "category": "arena",
    },
    {
        "code": "arena_champion",
        "name": "Чемпион турнира",
        "description": "Занял первое место на турнире",
        "condition": {"type": "arena_tournament_place", "max_place": 1},
        "xp_bonus": 1000,
        "rarity": "legendary",
        "category": "arena",
    },

    # ─── Категория: Социальное (social) — 15 new ───
    {
        "code": "first_share",
        "name": "Первый шаг",
        "description": "Первый раз поделился результатом",
        "condition": {"type": "share_count", "count": 1},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "social",
    },
    {
        "code": "sharer_5",
        "name": "Активный делитель",
        "description": "Поделился результатами 5 раз",
        "condition": {"type": "share_count", "count": 5},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "social",
    },
    {
        "code": "sharer_10",
        "name": "Амбассадор",
        "description": "Поделился результатами 10 раз",
        "condition": {"type": "share_count", "count": 10},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "social",
    },
    {
        "code": "challenge_winner_1",
        "name": "Первый вызов",
        "description": "Выиграл первый вызов",
        "condition": {"type": "challenge_wins", "count": 1},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "social",
    },
    {
        "code": "challenge_winner_5",
        "name": "Покоритель вызовов",
        "description": "Выиграл 5 вызовов",
        "condition": {"type": "challenge_wins", "count": 5},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "social",
    },
    {
        "code": "challenge_winner_10",
        "name": "Непревзойдённый",
        "description": "Выиграл 10 вызовов",
        "condition": {"type": "challenge_wins", "count": 10},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "social",
    },
    {
        "code": "mentor_1",
        "name": "Наставник",
        "description": "Помог 1 игроку в роли наставника",
        "condition": {"type": "mentor_count", "count": 1},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "social",
    },
    {
        "code": "mentor_5",
        "name": "Мастер-наставник",
        "description": "Помог 5 игрокам в роли наставника",
        "condition": {"type": "mentor_count", "count": 5},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "social",
    },
    {
        "code": "mentor_10",
        "name": "Гуру наставничества",
        "description": "Помог 10 игрокам в роли наставника",
        "condition": {"type": "mentor_count", "count": 10},
        "xp_bonus": 500,
        "rarity": "epic",
        "category": "social",
    },
    {
        "code": "team_challenge_win",
        "name": "Командная победа",
        "description": "Выиграл командный вызов",
        "condition": {"type": "team_challenge_win"},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "social",
    },
    {
        "code": "team_streak_3",
        "name": "Командный дух",
        "description": "3 командных победы подряд",
        "condition": {"type": "team_challenge_streak", "count": 3},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "social",
    },
    {
        "code": "team_week_champion",
        "name": "Лучшая команда",
        "description": "Лучшая команда недели",
        "condition": {"type": "team_week_champion"},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "social",
    },
    {
        "code": "community_10",
        "name": "Общительный",
        "description": "Сыграл против 10 разных соперников",
        "condition": {"type": "community_opponents", "count": 10},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "social",
    },
    {
        "code": "community_25",
        "name": "Сетевик",
        "description": "Сыграл против 25 разных соперников",
        "condition": {"type": "community_opponents", "count": 25},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "social",
    },
    {
        "code": "community_50",
        "name": "Социальная звезда",
        "description": "Сыграл против 50 разных соперников",
        "condition": {"type": "community_opponents", "count": 50},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "social",
    },

    # ─── Категория: Нарратив (narrative) — 10 new ───
    {
        "code": "first_story_complete",
        "name": "Первая история",
        "description": "Завершил первую историю",
        "condition": {"type": "story_complete", "count": 1},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "narrative",
    },
    {
        "code": "stories_5",
        "name": "Рассказчик",
        "description": "Завершил 5 историй",
        "condition": {"type": "story_complete", "count": 5},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "narrative",
    },
    {
        "code": "story_perfect",
        "name": "Идеальная история",
        "description": "Набрал 90+ баллов за историю",
        "condition": {"type": "story_score_milestone", "min_score": 90},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "narrative",
    },
    {
        "code": "saved_family",
        "name": "Спас семью",
        "description": "Нарративное событие: спас семью",
        "condition": {"type": "narrative_event", "event": "saved_family"},
        "xp_bonus": 500,
        "rarity": "epic",
        "category": "narrative",
    },
    {
        "code": "anger_whisperer",
        "name": "Укротитель гнева",
        "description": "Нарративное событие: укротил гнев клиента",
        "condition": {"type": "narrative_event", "event": "anger_whisperer"},
        "xp_bonus": 500,
        "rarity": "epic",
        "category": "narrative",
    },
    {
        "code": "crm_portfolio_5",
        "name": "Начинающий портфель",
        "description": "Собрал портфель из 5 клиентов в CRM",
        "condition": {"type": "crm_portfolio", "count": 5},
        "xp_bonus": 50,
        "rarity": "common",
        "category": "narrative",
    },
    {
        "code": "crm_portfolio_10",
        "name": "Растущий портфель",
        "description": "Собрал портфель из 10 клиентов в CRM",
        "condition": {"type": "crm_portfolio", "count": 10},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "narrative",
    },
    {
        "code": "crm_portfolio_20",
        "name": "Зрелый портфель",
        "description": "Собрал портфель из 20 клиентов в CRM",
        "condition": {"type": "crm_portfolio", "count": 20},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "narrative",
    },
    {
        "code": "full_arc_deal",
        "name": "Полная дуга",
        "description": "Завершил полную сюжетную дугу сделки",
        "condition": {"type": "full_story_arc_deal"},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "narrative",
    },
    {
        "code": "the_comeback_story",
        "name": "Великий камбэк",
        "description": "Нарративное событие: великий камбэк",
        "condition": {"type": "narrative_event", "event": "the_comeback"},
        "xp_bonus": 1000,
        "rarity": "legendary",
        "category": "narrative",
    },

    # ─── Категория: Секретные (secret) — 10 new ───
    {
        "code": "night_owl",
        "name": "Полуночник",
        "description": "Тренировался глубокой ночью 3 раза",
        "condition": {"type": "time_of_day", "after_hour": 0, "before_hour": 5, "count": 3},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "secret",
        "is_secret": True,
        "hint": "Совы тоже тренируются...",
    },
    {
        "code": "early_bird",
        "name": "Ранняя пташка",
        "description": "Тренировался ранним утром 3 раза",
        "condition": {"type": "time_of_day", "after_hour": 5, "before_hour": 7, "count": 3},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "secret",
        "is_secret": True,
        "hint": "Кто рано встаёт...",
    },
    {
        "code": "fake_survivor",
        "name": "Не на того напал",
        "description": "Пережил 3 фейковых перехода подряд",
        "condition": {"type": "consecutive_fake_survive", "count": 3},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "secret",
        "is_secret": True,
        "hint": "Не все переходы настоящие...",
    },
    {
        "code": "skeptic_vs_paranoid",
        "name": "Параноик vs скептик",
        "description": "Особая комбинация: параноик + холодный базовый",
        "condition": {"type": "specific_combo", "archetype": "paranoid", "scenario": "cold_base"},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "secret",
        "is_secret": True,
        "hint": "Некоторые комбинации особенные...",
    },
    {
        "code": "lawyer_vs_lawyer",
        "name": "Юрист vs юрист",
        "description": "Особая комбинация: клиент-юрист + юрист на проводе",
        "condition": {"type": "specific_combo", "archetype": "lawyer_client", "scenario": "special_lawyer_on_line"},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "secret",
        "is_secret": True,
        "hint": "Когда встречаются два юриста...",
    },
    {
        "code": "crying_rescue",
        "name": "Спаси и сохрани",
        "description": "Особая комбинация: плачущий клиент + сценарий rescue",
        "condition": {"type": "specific_combo", "archetype": "crying", "scenario": "rescue"},
        "xp_bonus": 200,
        "rarity": "rare",
        "category": "secret",
        "is_secret": True,
        "hint": "Самые трудные сделки...",
    },
    {
        "code": "short_talks_anti",
        "name": "Короткие разговоры",
        "description": "Клиент бросил трубку 3 раза подряд",
        "condition": {"type": "fail_streak", "outcome": "hangup", "count": 3},
        "xp_bonus": 0,
        "rarity": "common",
        "category": "secret",
        "is_secret": True,
        "is_anti": True,
        "recommendation": "Попробуйте говорить мягче и задавать открытые вопросы",
    },
    {
        "code": "diy_lawyer_anti",
        "name": "Юрист-самоучка",
        "description": "Допустил 3 юридические ошибки за 5 сессий",
        "condition": {"type": "legal_errors", "count": 3, "within_sessions": 5},
        "xp_bonus": 0,
        "rarity": "common",
        "category": "secret",
        "is_secret": True,
        "is_anti": True,
        "recommendation": "Изучите основы 127-ФЗ в разделе Знания",
    },
    {
        "code": "template_talker_anti",
        "name": "По шаблону",
        "description": "5 сессий подряд с низкой вариативностью ответов",
        "condition": {"type": "low_variability_streak", "count": 5},
        "xp_bonus": 0,
        "rarity": "common",
        "category": "secret",
        "is_secret": True,
        "is_anti": True,
        "recommendation": "Старайтесь адаптировать ответы под клиента",
    },
    {
        "code": "weekend_warrior",
        "name": "Выходной боец",
        "description": "Провёл 10 сессий в выходные дни",
        "condition": {"type": "weekend_sessions", "count": 10},
        "xp_bonus": 75,
        "rarity": "uncommon",
        "category": "secret",
        "is_secret": True,
        "hint": "Некоторые тренируются и в выходные...",
    },
    # ─── PvE Achievements (DOC_10 §6) ───
    {"code": "pve_first_bot_win", "name": "Первая победа над ботом", "description": "Выиграл PvE-дуэль", "condition": {"type": "pve_wins", "count": 1}, "xp_bonus": 25, "rarity": "common", "category": "arena"},
    {"code": "pve_ladder_conqueror", "name": "Покоритель лестницы", "description": "Победил все 5 ботов в Bot Ladder", "condition": {"type": "pve_ladder_complete", "all_defeated": True}, "xp_bonus": 150, "rarity": "rare", "category": "arena"},
    {"code": "pve_ladder_perfect", "name": "Идеальная лестница", "description": "Bot Ladder с cumulative score > 400", "condition": {"type": "pve_ladder_score", "min_score": 400}, "xp_bonus": 200, "rarity": "epic", "category": "arena"},
    {"code": "pve_boss_slayer", "name": "Победитель боссов", "description": "Победил все 3 босса в Boss Rush", "condition": {"type": "pve_boss_all_defeated"}, "xp_bonus": 200, "rarity": "epic", "category": "arena"},
    {"code": "pve_boss_perfectionist", "name": "Безупречный юрист", "description": "Победил Юриста без единой ошибки", "condition": {"type": "pve_boss_flawless", "boss_type": "perfectionist"}, "xp_bonus": 100, "rarity": "rare", "category": "arena"},
    {"code": "pve_boss_composure", "name": "Стальные нервы (босс)", "description": "Победил Вампира с composure > 50%", "condition": {"type": "pve_boss_composure", "min_composure": 50}, "xp_bonus": 100, "rarity": "rare", "category": "arena"},
    {"code": "pve_boss_chameleon", "name": "Мастер адаптации (босс)", "description": "Победил Хамелеона с score > 70", "condition": {"type": "pve_boss_score", "boss_type": "chameleon", "min_score": 70}, "xp_bonus": 100, "rarity": "rare", "category": "arena"},
    {"code": "pve_training_10", "name": "Прилежный ученик", "description": "Провёл 10 тренировочных матчей", "condition": {"type": "pve_training_count", "count": 10}, "xp_bonus": 50, "rarity": "common", "category": "arena"},
    {"code": "pve_mirror_win", "name": "Превзошёл себя", "description": "Победил своё зеркало", "condition": {"type": "pve_mirror_wins", "count": 1}, "xp_bonus": 100, "rarity": "rare", "category": "arena"},
    {"code": "pve_mirror_streak_3", "name": "Триумф над собой", "description": "Победил зеркало 3 раза подряд", "condition": {"type": "pve_mirror_streak", "count": 3}, "xp_bonus": 150, "rarity": "epic", "category": "arena"},
    {"code": "pve_all_modes", "name": "Мастер PvE", "description": "Победил в каждом из 5 PvE-режимов", "condition": {"type": "pve_all_modes_won"}, "xp_bonus": 300, "rarity": "epic", "category": "arena"},
    # ─── Cross-System Achievements (DOC_14 §5.1) ───
    {"code": "cross_bridge", "name": "Мост", "description": "Тренировка + PvP-дуэль в один день", "condition": {"type": "cross_same_day", "activity_a": "training", "activity_b": "pvp_duel"}, "xp_bonus": 200, "rarity": "rare", "category": "arena"},
    {"code": "cross_academic_warrior", "name": "Академик-воин", "description": "Score 80+ в Quiz + выиграть PvP в один день", "condition": {"type": "cross_same_day", "activity_a": "knowledge_80", "activity_b": "pvp_win"}, "xp_bonus": 200, "rarity": "rare", "category": "arena"},
    {"code": "cross_full_cycle", "name": "Полный цикл", "description": "Потренировать архетип -> встретить в PvP -> победить", "condition": {"type": "cross_archetype_cycle", "steps": ["train", "pvp_meet", "pvp_win"]}, "xp_bonus": 500, "rarity": "epic", "category": "arena"},
    {"code": "cross_theory_practice", "name": "Теория и практика", "description": "Quiz 90%+ в категории + score 80+ в тренировке с ловушками этой категории", "condition": {"type": "cross_category_mastery", "min_quiz_accuracy": 90, "min_training_score": 80}, "xp_bonus": 500, "rarity": "epic", "category": "arena"},
    {"code": "cross_comeback", "name": "Путь реванша", "description": "Проиграть PvP архетипу -> 3 тренировки -> победить в PvP", "condition": {"type": "cross_revenge", "min_losses": 1, "min_training_sessions": 3, "require_win": True}, "xp_bonus": 1000, "rarity": "legendary", "category": "arena"},
    {"code": "cross_triple_threat", "name": "Тройная угроза", "description": "Score 80+ + PvP win + Quiz 90% в один день", "condition": {"type": "cross_same_day", "activity_a": "training_80", "activity_b": "pvp_win", "activity_c": "knowledge_90"}, "xp_bonus": 1000, "rarity": "legendary", "category": "arena"},
    {"code": "cross_mentor", "name": "Наставник (кросс)", "description": "Помочь 3 игрокам через менторский режим (уровень 15+)", "condition": {"type": "mentor_count", "count": 3}, "xp_bonus": 500, "rarity": "epic", "category": "arena"},
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
                    # Upsert: обновляем существующие (use json.dumps for asyncpg JSONB compat)
                    import json as _json
                    await session.execute(
                        text("""
                            UPDATE level_definitions SET
                                name = :name,
                                description = :description,
                                xp_required = :xp_required,
                                max_difficulty = :max_difficulty,
                                unlocked_archetypes = cast(:unlocked_archetypes as jsonb),
                                unlocked_scenarios = cast(:unlocked_scenarios as jsonb),
                                unlocked_mechanics = cast(:unlocked_mechanics as jsonb)
                            WHERE level = :level
                        """),
                        {
                            **lvl,
                            "unlocked_archetypes": _json.dumps(lvl["unlocked_archetypes"]),
                            "unlocked_scenarios": _json.dumps(lvl["unlocked_scenarios"]),
                            "unlocked_mechanics": _json.dumps(lvl["unlocked_mechanics"]),
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

# Имена рангов (для UI)
LEVEL_NAMES: dict[int, str] = {lvl["level"]: lvl["name"] for lvl in LEVELS}

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
