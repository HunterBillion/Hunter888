"""
DOC_04: Seed 90 checkpoint definitions for 20 levels.
Each level has 4-5 checkpoints (2-3 required + 1-2 bonus).

Usage:
    python -m scripts.seed_checkpoints
"""
from __future__ import annotations

import asyncio

# ──────────────────────────────────────────────────────────────────────
#  90 Checkpoint Definitions (DOC_04 §4-23)
# ──────────────────────────────────────────────────────────────────────

CHECKPOINTS: list[dict] = [
    # ═══ LEVEL 1: Стажёр ═══
    {"code": "lvl01_first_session", "level": 1, "order_num": 1, "name": "Первый звонок", "description": "Завершите хотя бы 1 тренировочную сессию", "condition": {"type": "total_sessions", "count": 1}, "xp_reward": 30, "is_required": True, "category": "training"},
    {"code": "lvl01_score_50", "level": 1, "order_num": 2, "name": "Проба пера", "description": "Получите score >= 50 хотя бы в 1 сессии", "condition": {"type": "score_threshold", "min_score": 50, "count": 1}, "xp_reward": 50, "is_required": True, "category": "training"},
    {"code": "lvl01_calibration", "level": 1, "order_num": 3, "name": "Калибровка", "description": "Пройдите калибровочную сессию", "condition": {"type": "calibration_complete"}, "xp_reward": 30, "is_required": True, "category": "training"},
    {"code": "lvl01_two_archetypes", "level": 1, "order_num": 4, "name": "Две стороны", "description": "Сыграйте 2 разных архетипа", "condition": {"type": "unique_archetypes_played", "count": 2}, "xp_reward": 50, "is_required": False, "category": "training"},

    # ═══ LEVEL 2: Новичок ═══
    {"code": "lvl02_variety_score", "level": 2, "order_num": 1, "name": "Диагност", "description": "Score >= 55 на 3 разных архетипах", "condition": {"type": "archetype_group_variety", "group": "any", "min_score": 55, "count": 3}, "xp_reward": 75, "is_required": True, "category": "training"},
    {"code": "lvl02_calibration_done", "level": 2, "order_num": 2, "name": "Калибровка завершена", "description": "Завершите калибровку (3 сессии)", "condition": {"type": "total_sessions", "count": 3}, "xp_reward": 50, "is_required": True, "category": "training"},
    {"code": "lvl02_first_deal", "level": 2, "order_num": 3, "name": "Первая сделка", "description": "Закройте первую сделку", "condition": {"type": "outcome_count", "outcome": "deal", "count": 1}, "xp_reward": 75, "is_required": True, "category": "training"},
    {"code": "lvl02_five_archetypes", "level": 2, "order_num": 4, "name": "Широкий взгляд", "description": "Сыграйте 5 разных архетипов", "condition": {"type": "unique_archetypes_played", "count": 5}, "xp_reward": 50, "is_required": False, "category": "training"},
    {"code": "lvl02_hotline", "level": 2, "order_num": 5, "name": "Горячая линия", "description": "Закройте сделку в сценарии in_hotline", "condition": {"type": "deal_with_scenario", "scenarios": ["in_hotline"]}, "xp_reward": 50, "is_required": False, "category": "training"},

    # ═══ LEVEL 3: Ученик ═══
    {"code": "lvl03_resistance_score", "level": 3, "order_num": 1, "name": "Стальная стена", "description": "Score >= 60 на 2 архетипах группы Resistance", "condition": {"type": "archetype_group_variety", "group": "resistance", "min_score": 60, "count": 2}, "xp_reward": 100, "is_required": True, "category": "training"},
    {"code": "lvl03_warm_deal", "level": 3, "order_num": 2, "name": "Тёплый приём", "description": "Закройте сделку в сценарии warm_callback", "condition": {"type": "deal_with_scenario", "scenarios": ["warm_callback"]}, "xp_reward": 75, "is_required": True, "category": "training"},
    {"code": "lvl03_constructor", "level": 3, "order_num": 3, "name": "Архитектор", "description": "Завершите 1 сессию через конструктор", "condition": {"type": "constructor_session", "min_params": 1, "count": 1}, "xp_reward": 75, "is_required": True, "category": "training"},
    {"code": "lvl03_pve_first", "level": 3, "order_num": 4, "name": "Первый бой", "description": "Проведите PvE-матч", "condition": {"type": "total_sessions", "count": 1}, "xp_reward": 50, "is_required": False, "category": "arena"},
    {"code": "lvl03_clean_session", "level": 3, "order_num": 5, "name": "Чистая работа", "description": "Завершите сессию с 0 антипаттернов", "condition": {"type": "zero_antipatterns", "count": 1}, "xp_reward": 50, "is_required": False, "category": "training"},

    # ═══ LEVEL 4: Практикант ═══
    {"code": "lvl04_manipulator", "level": 4, "order_num": 1, "name": "Укротитель", "description": "Score >= 60 на манипуляторе", "condition": {"type": "score_at_min_difficulty", "min_score": 60, "min_difficulty": 1, "count": 1}, "xp_reward": 100, "is_required": True, "category": "training"},
    {"code": "lvl04_no_traps", "level": 4, "order_num": 2, "name": "Чистый раунд", "description": "Обойдите 3 ловушки подряд без попадания", "condition": {"type": "trap_dodge_streak", "count": 3}, "xp_reward": 75, "is_required": True, "category": "training"},
    {"code": "lvl04_deal_diff4", "level": 4, "order_num": 3, "name": "Планка", "description": "Закройте сделку на сложности >= 4", "condition": {"type": "deal_at_difficulty", "difficulty": 4}, "xp_reward": 100, "is_required": True, "category": "training"},
    {"code": "lvl04_pve_score", "level": 4, "order_num": 4, "name": "Арена зовёт", "description": "Score >= 50 в PvE", "condition": {"type": "score_threshold", "min_score": 50, "count": 1}, "xp_reward": 50, "is_required": False, "category": "arena"},
    {"code": "lvl04_ten_sessions", "level": 4, "order_num": 5, "name": "Десять кругов", "description": "Завершите 10 сессий", "condition": {"type": "total_sessions", "count": 10}, "xp_reward": 50, "is_required": False, "category": "training"},

    # ═══ LEVEL 5: Менеджер ═══
    {"code": "lvl05_all_skills_55", "level": 5, "order_num": 1, "name": "Базовая подготовка", "description": "Все 6 навыков >= 55", "condition": {"type": "all_skills_threshold", "min_value": 55}, "xp_reward": 100, "is_required": True, "category": "training"},
    {"code": "lvl05_five_archetypes_65", "level": 5, "order_num": 2, "name": "Универсал", "description": "Score >= 65 на 5 разных архетипах", "condition": {"type": "archetype_group_variety", "group": "any", "min_score": 65, "count": 5}, "xp_reward": 100, "is_required": True, "category": "training"},
    {"code": "lvl05_four_groups_deal", "level": 5, "order_num": 3, "name": "Мультигруппа", "description": "Закройте сделки с архетипами из 4 разных групп", "condition": {"type": "archetype_group_variety", "group": "cross_group_deals", "min_score": 0, "count": 4}, "xp_reward": 100, "is_required": True, "category": "training"},
    {"code": "lvl05_arena_match", "level": 5, "order_num": 4, "name": "Арена: первый PvP", "description": "Проведите PvP-дуэль", "condition": {"type": "total_sessions", "count": 1}, "xp_reward": 75, "is_required": False, "category": "arena"},
    {"code": "lvl05_knowledge_quiz", "level": 5, "order_num": 5, "name": "Знаток", "description": "Наберите 60% в базовом квизе", "condition": {"type": "knowledge_category_mastery", "category": "general", "min_pct": 60}, "xp_reward": 75, "is_required": False, "category": "knowledge"},

    # ═══ LEVEL 6: Продвинутый ═══
    {"code": "lvl06_expert_archetype", "level": 6, "order_num": 1, "name": "Экспертоборец", "description": "Закройте сделку с know_it_all или paranoid", "condition": {"type": "deal_with_archetype", "archetypes": ["know_it_all", "paranoid"], "min_difficulty": 1}, "xp_reward": 100, "is_required": True, "category": "training"},
    {"code": "lvl06_traps_expert", "level": 6, "order_num": 2, "name": "Ловкий", "description": "Обойдите 5 ловушек подряд", "condition": {"type": "trap_dodge_streak", "count": 5}, "xp_reward": 100, "is_required": True, "category": "training"},
    {"code": "lvl06_knowledge_60", "level": 6, "order_num": 3, "name": "Знание — сила", "description": "Навык knowledge >= 60", "condition": {"type": "skill_threshold", "skill": "knowledge", "min_value": 60}, "xp_reward": 75, "is_required": True, "category": "training"},
    {"code": "lvl06_hybrid_constructor", "level": 6, "order_num": 4, "name": "Гибрид", "description": "Сессия через конструктор с 4+ параметрами", "condition": {"type": "constructor_session", "min_params": 4, "count": 1}, "xp_reward": 75, "is_required": False, "category": "training"},
    {"code": "lvl06_pvp_silver", "level": 6, "order_num": 5, "name": "Серебро", "description": "Достигните серебряного ранга в PvP", "condition": {"type": "pvp_rank_reached", "rank": "silver"}, "xp_reward": 100, "is_required": False, "category": "arena"},

    # ═══ LEVEL 7: Опытный ═══
    {"code": "lvl07_hostile_score", "level": 7, "order_num": 1, "name": "Хладнокровие", "description": "Score >= 60 на сложности >= 5 с враждебным клиентом", "condition": {"type": "score_at_min_difficulty", "min_score": 60, "min_difficulty": 5, "count": 1}, "xp_reward": 100, "is_required": True, "category": "training"},
    {"code": "lvl07_cascade_dodge", "level": 7, "order_num": 2, "name": "Каскадный мастер", "description": "Обойдите 4 каскадные ловушки", "condition": {"type": "trap_dodge_streak", "count": 4}, "xp_reward": 100, "is_required": True, "category": "training"},
    {"code": "lvl07_stress_65", "level": 7, "order_num": 3, "name": "Стальные нервы", "description": "Стрессоустойчивость >= 65", "condition": {"type": "skill_threshold", "skill": "stress_resistance", "min_value": 65}, "xp_reward": 75, "is_required": True, "category": "training"},
    {"code": "lvl07_couple_deal", "level": 7, "order_num": 4, "name": "Медиатор", "description": "Закройте сделку в сценарии special_couple", "condition": {"type": "deal_with_scenario", "scenarios": ["special_couple"]}, "xp_reward": 100, "is_required": False, "category": "training"},
    {"code": "lvl07_tournament", "level": 7, "order_num": 5, "name": "Турнирная заявка", "description": "Примите участие в турнире PvP", "condition": {"type": "total_sessions", "count": 1}, "xp_reward": 75, "is_required": False, "category": "arena"},

    # ═══ LEVEL 8: Профи ═══
    {"code": "lvl08_fake_transition", "level": 8, "order_num": 1, "name": "Детектор лжи", "description": "Сделки с 5 архетипами имеющими FakeTransition", "condition": {"type": "deal_with_archetype", "archetypes": ["shopper", "manipulator", "know_it_all", "paranoid", "lawyer_client"], "min_difficulty": 5}, "xp_reward": 100, "is_required": True, "category": "training"},
    {"code": "lvl08_objection_65", "level": 8, "order_num": 2, "name": "Мастер возражений", "description": "Навык objection_handling >= 65", "condition": {"type": "skill_threshold", "skill": "objection_handling", "min_value": 65}, "xp_reward": 75, "is_required": True, "category": "training"},
    {"code": "lvl08_deal_diff7", "level": 8, "order_num": 3, "name": "Высокая планка", "description": "Закройте сделку на сложности >= 7", "condition": {"type": "deal_at_difficulty", "difficulty": 7}, "xp_reward": 100, "is_required": True, "category": "training"},
    {"code": "lvl08_shared_challenge", "level": 8, "order_num": 4, "name": "Вызов принят", "description": "Выиграйте shared challenge", "condition": {"type": "shared_challenge_won", "count": 1}, "xp_reward": 100, "is_required": False, "category": "social"},
    {"code": "lvl08_knowledge_procedures", "level": 8, "order_num": 5, "name": "Правовед", "description": "70%+ в квизе по процедурам", "condition": {"type": "knowledge_category_mastery", "category": "procedures", "min_pct": 70}, "xp_reward": 75, "is_required": False, "category": "knowledge"},

    # ═══ LEVEL 9: Эксперт ═══
    {"code": "lvl09_hybrid_mastery", "level": 9, "order_num": 1, "name": "Гибридный мастер", "description": "Score >= 65 на 2 архетипах T3", "condition": {"type": "tier_archetype_mastered", "tier": 3, "min_score": 65, "count": 2}, "xp_reward": 100, "is_required": True, "category": "training"},
    {"code": "lvl09_all_skills_65", "level": 9, "order_num": 2, "name": "Полный комплект", "description": "Все 6 навыков >= 65", "condition": {"type": "all_skills_threshold", "min_value": 65}, "xp_reward": 100, "is_required": True, "category": "training"},
    {"code": "lvl09_deal_diff8", "level": 9, "order_num": 3, "name": "Восьмёрка", "description": "Закройте сделку на сложности >= 8", "condition": {"type": "deal_at_difficulty", "difficulty": 8}, "xp_reward": 100, "is_required": True, "category": "training"},
    {"code": "lvl09_pvp_gold", "level": 9, "order_num": 4, "name": "Золотой ранг", "description": "Достигните золотого ранга в PvP", "condition": {"type": "pvp_rank_reached", "rank": "gold"}, "xp_reward": 150, "is_required": False, "category": "arena"},
    {"code": "lvl09_knowledge_legal", "level": 9, "order_num": 5, "name": "Юрист", "description": "75%+ в квизе по законодательству", "condition": {"type": "knowledge_category_mastery", "category": "legislation", "min_pct": 75}, "xp_reward": 75, "is_required": False, "category": "knowledge"},

    # ═══ LEVEL 10: Мастер ═══
    {"code": "lvl10_deal_diff10", "level": 10, "order_num": 1, "name": "Максимум", "description": "Закройте сделку на сложности 10", "condition": {"type": "deal_at_difficulty", "difficulty": 10}, "xp_reward": 150, "is_required": True, "category": "training"},
    {"code": "lvl10_t4_mastery", "level": 10, "order_num": 2, "name": "Элита T4", "description": "Score >= 70 на 3 архетипах T4", "condition": {"type": "tier_archetype_mastered", "tier": 4, "min_score": 70, "count": 3}, "xp_reward": 150, "is_required": True, "category": "training"},
    {"code": "lvl10_stress_70", "level": 10, "order_num": 3, "name": "Стальная воля", "description": "Стрессоустойчивость >= 70", "condition": {"type": "skill_threshold", "skill": "stress_resistance", "min_value": 70}, "xp_reward": 100, "is_required": True, "category": "training"},
    {"code": "lvl10_boss_mode", "level": 10, "order_num": 4, "name": "Boss Mode", "description": "Закройте сделку в boss_mode", "condition": {"type": "deal_in_boss_mode", "min_good_streak": 15}, "xp_reward": 200, "is_required": False, "category": "training"},
    {"code": "lvl10_pvp_platinum", "level": 10, "order_num": 5, "name": "Платиновый ранг", "description": "Достигните платинового ранга в PvP", "condition": {"type": "pvp_rank_reached", "rank": "platinum"}, "xp_reward": 200, "is_required": False, "category": "arena"},

    # ═══ LEVEL 11: Старший мастер I ═══
    {"code": "lvl11_lawyer_score", "level": 11, "order_num": 1, "name": "Юрист на проводе", "description": "Score >= 65 на сложности >= 8 в спецсценарии", "condition": {"type": "score_at_min_difficulty", "min_score": 65, "min_difficulty": 8, "count": 1}, "xp_reward": 150, "is_required": True, "category": "training"},
    {"code": "lvl11_dual_deal", "level": 11, "order_num": 2, "name": "Дуэт", "description": "Сделка в dual_client сценарии", "condition": {"type": "deal_with_scenario", "scenarios": ["special_lawyer_on_line", "multi_party_lawyer"]}, "xp_reward": 150, "is_required": True, "category": "training"},
    {"code": "lvl11_puppet_master", "level": 11, "order_num": 3, "name": "Кукловод повержен", "description": "Сделка с puppet_master на сложности >= 8", "condition": {"type": "deal_with_archetype", "archetypes": ["puppet_master"], "min_difficulty": 8}, "xp_reward": 200, "is_required": False, "category": "training"},
    {"code": "lvl11_social_challenge", "level": 11, "order_num": 4, "name": "Командный дух", "description": "Выиграйте shared challenge", "condition": {"type": "shared_challenge_won", "count": 1}, "xp_reward": 75, "is_required": False, "category": "social"},

    # ═══ LEVEL 12: Старший мастер II ═══
    {"code": "lvl12_re_engagement", "level": 12, "order_num": 1, "name": "Последовательность", "description": "Score >= 65 на сложности >= 8", "condition": {"type": "score_at_min_difficulty", "min_score": 65, "min_difficulty": 8, "count": 1}, "xp_reward": 150, "is_required": True, "category": "training"},
    {"code": "lvl12_consistency", "level": 12, "order_num": 2, "name": "Без расхождений", "description": "Завершите multi-call story со score >= 65", "condition": {"type": "story_completed", "min_score": 65, "count": 1}, "xp_reward": 150, "is_required": True, "category": "training"},
    {"code": "lvl12_hysteric_deal", "level": 12, "order_num": 3, "name": "Истерик-сутяжник", "description": "Сделка с hysteric_litigious на сложности >= 8", "condition": {"type": "deal_with_archetype", "archetypes": ["hysteric_litigious"], "min_difficulty": 8}, "xp_reward": 150, "is_required": True, "category": "training"},
    {"code": "lvl12_team_battle", "level": 12, "order_num": 4, "name": "Командный бой", "description": "Проведите командный PvP 2v2", "condition": {"type": "total_sessions", "count": 1}, "xp_reward": 100, "is_required": False, "category": "arena"},

    # ═══ LEVEL 13: Старший мастер III ═══
    {"code": "lvl13_multi_creditor", "level": 13, "order_num": 1, "name": "Три кредитора", "description": "Score >= 70 на сложности >= 8 трижды", "condition": {"type": "score_at_min_difficulty", "min_score": 70, "min_difficulty": 8, "count": 3}, "xp_reward": 150, "is_required": True, "category": "training"},
    {"code": "lvl13_qualification_75", "level": 13, "order_num": 2, "name": "Квалификатор", "description": "Навык qualification >= 75", "condition": {"type": "skill_threshold", "skill": "qualification", "min_value": 75}, "xp_reward": 100, "is_required": True, "category": "training"},
    {"code": "lvl13_puppet_lawyer", "level": 13, "order_num": 3, "name": "Юрист-кукловод повержен", "description": "Сделка с puppet_master_lawyer на сложности >= 9", "condition": {"type": "deal_with_archetype", "archetypes": ["puppet_master_lawyer"], "min_difficulty": 9}, "xp_reward": 200, "is_required": False, "category": "training"},
    {"code": "lvl13_compliance", "level": 13, "order_num": 4, "name": "Комплаенс-эксперт", "description": "75%+ в квизе по комплаенсу", "condition": {"type": "knowledge_category_mastery", "category": "compliance", "min_pct": 75}, "xp_reward": 100, "is_required": False, "category": "knowledge"},

    # ═══ LEVEL 14: Старший мастер IV ═══
    {"code": "lvl14_competitor", "level": 14, "order_num": 1, "name": "Этичный конкурент", "description": "Score >= 70 на сложности >= 7 трижды", "condition": {"type": "score_at_min_difficulty", "min_score": 70, "min_difficulty": 7, "count": 3}, "xp_reward": 150, "is_required": True, "category": "training"},
    {"code": "lvl14_no_badmouthing", "level": 14, "order_num": 2, "name": "Чистый комплаенс", "description": "5 сессий без критики конкурентов", "condition": {"type": "total_sessions", "count": 5}, "xp_reward": 150, "is_required": True, "category": "training"},
    {"code": "lvl14_steal_deal", "level": 14, "order_num": 3, "name": "Переманивание", "description": "Сделка в сценарии special_competitor_active", "condition": {"type": "deal_with_scenario", "scenarios": ["special_competitor_active"]}, "xp_reward": 150, "is_required": True, "category": "training"},
    {"code": "lvl14_share_challenges", "level": 14, "order_num": 4, "name": "Наставник-lite", "description": "Выиграйте 3 shared challenge", "condition": {"type": "shared_challenge_won", "count": 3}, "xp_reward": 100, "is_required": False, "category": "social"},

    # ═══ LEVEL 15: Старший мастер V ═══
    {"code": "lvl15_time_pressure", "level": 15, "order_num": 1, "name": "Под давлением", "description": "Сделка менее чем за 5 минут", "condition": {"type": "deal_under_time", "max_seconds": 300}, "xp_reward": 150, "is_required": True, "category": "training"},
    {"code": "lvl15_fast_deal", "level": 15, "order_num": 2, "name": "Блиц", "description": "3 сессии подряд с score >= 70", "condition": {"type": "consecutive_sessions_score", "min_score": 70, "count": 3}, "xp_reward": 150, "is_required": True, "category": "training"},
    {"code": "lvl15_all_skills_70", "level": 15, "order_num": 3, "name": "Профессиональная база", "description": "Все 6 навыков >= 70", "condition": {"type": "all_skills_threshold", "min_value": 70}, "xp_reward": 150, "is_required": True, "category": "training"},
    {"code": "lvl15_shifting", "level": 15, "order_num": 4, "name": "Хамелеон", "description": "Score >= 55 на shifting archetype сложности >= 7", "condition": {"type": "score_at_min_difficulty", "min_score": 55, "min_difficulty": 7, "count": 5}, "xp_reward": 200, "is_required": False, "category": "training"},

    # ═══ LEVEL 16: Гроссмейстер I ═══
    {"code": "lvl16_marathon_score", "level": 16, "order_num": 1, "name": "Марафон", "description": "5 сессий подряд с score >= 75", "condition": {"type": "consecutive_sessions_score", "min_score": 75, "count": 5}, "xp_reward": 200, "is_required": True, "category": "training"},
    {"code": "lvl16_marathon_deals", "level": 16, "order_num": 2, "name": "Победный марафон", "description": "10 сделок подряд", "condition": {"type": "deal_streak", "count": 10}, "xp_reward": 150, "is_required": True, "category": "training"},
    {"code": "lvl16_winrate", "level": 16, "order_num": 3, "name": "Победитель", "description": "Score >= 75 в 10 сессиях", "condition": {"type": "score_threshold", "min_score": 75, "count": 10}, "xp_reward": 150, "is_required": False, "category": "training"},
    {"code": "lvl16_pvp_diamond", "level": 16, "order_num": 4, "name": "Алмазная мечта", "description": "Достигните алмазного ранга PvP", "condition": {"type": "pvp_rank_reached", "rank": "diamond"}, "xp_reward": 200, "is_required": False, "category": "arena"},

    # ═══ LEVEL 17: Гроссмейстер II ═══
    {"code": "lvl17_stress_test", "level": 17, "order_num": 1, "name": "Стресс-тест", "description": "5 сессий подряд с score >= 80", "condition": {"type": "consecutive_sessions_score", "min_score": 80, "count": 5}, "xp_reward": 200, "is_required": True, "category": "training"},
    {"code": "lvl17_fatigue_survive", "level": 17, "order_num": 2, "name": "Выносливость", "description": "Завершите 50 сессий", "condition": {"type": "total_sessions", "count": 50}, "xp_reward": 150, "is_required": True, "category": "training"},
    {"code": "lvl17_stress_80", "level": 17, "order_num": 3, "name": "Железная воля", "description": "Стрессоустойчивость >= 80", "condition": {"type": "skill_threshold", "skill": "stress_resistance", "min_value": 80}, "xp_reward": 100, "is_required": True, "category": "training"},
    {"code": "lvl17_shared_5", "level": 17, "order_num": 4, "name": "Наставник", "description": "Выиграйте 5 shared challenge", "condition": {"type": "shared_challenge_won", "count": 5}, "xp_reward": 100, "is_required": False, "category": "social"},

    # ═══ LEVEL 18: Гроссмейстер III ═══
    {"code": "lvl18_mentor_score", "level": 18, "order_num": 1, "name": "Учитель", "description": "Score >= 85 в 5 сессиях", "condition": {"type": "score_threshold", "min_score": 85, "count": 5}, "xp_reward": 200, "is_required": True, "category": "training"},
    {"code": "lvl18_mentee_deal", "level": 18, "order_num": 2, "name": "Успешный менторинг", "description": "Выиграйте 10 shared challenge", "condition": {"type": "shared_challenge_won", "count": 10}, "xp_reward": 200, "is_required": True, "category": "social"},
    {"code": "lvl18_coop", "level": 18, "order_num": 3, "name": "Co-op", "description": "10 co-op сессий", "condition": {"type": "total_sessions", "count": 10}, "xp_reward": 150, "is_required": False, "category": "social"},
    {"code": "lvl18_knowledge_85", "level": 18, "order_num": 4, "name": "Энциклопедист", "description": "85%+ во всех категориях квиза", "condition": {"type": "knowledge_category_mastery", "category": "all", "min_pct": 85}, "xp_reward": 150, "is_required": False, "category": "knowledge"},

    # ═══ LEVEL 19: Гроссмейстер IV ═══
    {"code": "lvl19_all_archetypes", "level": 19, "order_num": 1, "name": "Полная коллекция", "description": "Сыграйте все 100 архетипов", "condition": {"type": "unique_archetypes_played", "count": 100}, "xp_reward": 150, "is_required": True, "category": "training"},
    {"code": "lvl19_boss_fight", "level": 19, "order_num": 2, "name": "Абсолют повержен", "description": "Сделка на сложности 10", "condition": {"type": "deal_at_difficulty", "difficulty": 10}, "xp_reward": 200, "is_required": True, "category": "training"},
    {"code": "lvl19_t4_five", "level": 19, "order_num": 3, "name": "Элита T4 мастер", "description": "Score >= 80 на 5 архетипах T4", "condition": {"type": "tier_archetype_mastered", "tier": 4, "min_score": 80, "count": 5}, "xp_reward": 200, "is_required": True, "category": "training"},
    {"code": "lvl19_all_skills_75", "level": 19, "order_num": 4, "name": "Навыки 75", "description": "Все 6 навыков >= 75", "condition": {"type": "all_skills_threshold", "min_value": 75}, "xp_reward": 150, "is_required": False, "category": "training"},
    {"code": "lvl19_pvp_master", "level": 19, "order_num": 5, "name": "Мастер PvP", "description": "Достигните мастер-ранга PvP", "condition": {"type": "pvp_rank_reached", "rank": "master"}, "xp_reward": 200, "is_required": False, "category": "arena"},

    # ═══ LEVEL 20: Легенда ═══
    {"code": "lvl20_boss_victory", "level": 20, "order_num": 1, "name": "Финальный босс", "description": "Сделка на сложности 10 с ultimate", "condition": {"type": "deal_at_difficulty", "difficulty": 10}, "xp_reward": 200, "is_required": True, "category": "training"},
    {"code": "lvl20_all_skills_80", "level": 20, "order_num": 2, "name": "Мастерство 80", "description": "Все 6 навыков >= 80", "condition": {"type": "all_skills_threshold", "min_value": 80}, "xp_reward": 200, "is_required": True, "category": "training"},
    {"code": "lvl20_winrate_90", "level": 20, "order_num": 3, "name": "Элита", "description": "Score >= 90 в 10 сессиях", "condition": {"type": "score_threshold", "min_score": 90, "count": 10}, "xp_reward": 200, "is_required": True, "category": "training"},
    {"code": "lvl20_custom_scenario", "level": 20, "order_num": 4, "name": "Создатель", "description": "Сессия через конструктор с 8 параметрами", "condition": {"type": "constructor_session", "min_params": 8, "count": 1}, "xp_reward": 200, "is_required": False, "category": "training"},
    {"code": "lvl20_all_scenarios", "level": 20, "order_num": 5, "name": "Все пути", "description": "Сыграйте все 60 сценариев", "condition": {"type": "unique_scenarios_played", "count": 60}, "xp_reward": 200, "is_required": False, "category": "training"},
]


# ──────────────────────────────────────────────────────────────────────
#  Seed function
# ──────────────────────────────────────────────────────────────────────

async def seed_checkpoints() -> None:
    """Seed checkpoint_definitions table."""
    from sqlalchemy import select
    from app.database import async_session as async_session_factory
    from app.models.checkpoint import CheckpointDefinition

    async with async_session_factory() as session:
        async with session.begin():
            existing = (await session.execute(
                select(CheckpointDefinition.code)
            )).scalars().all()

            inserted = 0
            for cp in CHECKPOINTS:
                if cp["code"] not in existing:
                    session.add(CheckpointDefinition(**cp))
                    inserted += 1

        await session.commit()
        print(f"✅ Seeded {inserted} new checkpoints ({len(CHECKPOINTS)} total defined)")


if __name__ == "__main__":
    asyncio.run(seed_checkpoints())
