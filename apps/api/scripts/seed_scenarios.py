"""Seed 60 scenario templates for Hunter888 roleplay system (DOC_05: 8 groups).

Usage:
    python -m scripts.seed_scenarios          # from apps/api/
    # or via make target:
    make seed-scenarios

Each scenario includes:
- Call context (who_calls, funnel_stage, prior_contact)
- Initial conditions (emotion, awareness, motivation)
- Duration and difficulty
- Conversation stages (group-specific templates)
- Target outcome

Note: archetype_weights are NOT included here — they are generated
dynamically by scenario_weights.py at runtime.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Allow running from apps/api/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text

from app.database import async_session, engine, Base
from app.models.scenario import ScenarioTemplate

logger = logging.getLogger(__name__)


# ─── Stage templates by group ─────────────────────────────────────────────────

def _stage(order: int, name: str, description: str, required: bool = True) -> dict:
    return {"order": order, "name": name, "description": description, "required": required}


STAGES_COLD = [
    _stage(1, "Приветствие", "Представление, установление контакта, причина звонка"),
    _stage(2, "Зацепка", "Выявление интереса, привлечение внимания клиента"),
    _stage(3, "Квалификация", "Выявление потребностей, ситуации клиента"),
    _stage(4, "Презентация", "Представление решения, работа с возражениями"),
    _stage(5, "Закрытие", "Фиксация договорённости, назначение следующего шага"),
]

STAGES_WARM = [
    _stage(1, "Контакт", "Восстановление контакта, напоминание о себе"),
    _stage(2, "Изменения", "Выяснение изменений в ситуации клиента"),
    _stage(3, "Презентация", "Обновлённое предложение с учётом новых данных"),
    _stage(4, "Возражения", "Проработка возражений и сомнений"),
    _stage(5, "Закрытие", "Фиксация договорённости, назначение встречи"),
]

STAGES_INBOUND = [
    _stage(1, "Приём", "Приём звонка, приветствие, выяснение причины обращения"),
    _stage(2, "Квалификация", "Выявление потребностей и ситуации"),
    _stage(3, "Консультация", "Предоставление информации, презентация решения"),
    _stage(4, "Закрытие", "Фиксация следующего шага, назначение встречи"),
]

STAGES_FOLLOW_UP = [
    _stage(1, "Напоминание", "Напоминание о предыдущем контакте и договорённостях"),
    _stage(2, "Новая ценность", "Предоставление новой информации или ценности"),
    _stage(3, "Воронка", "Продвижение клиента по воронке продаж"),
    _stage(4, "Закрытие", "Фиксация результата, назначение следующего шага"),
]

STAGES_CRISIS = [
    _stage(1, "Стабилизация", "Снятие эмоционального напряжения, установление доверия"),
    _stage(2, "Квалификация", "Выяснение реальной ситуации и проблемы"),
    _stage(3, "План", "Разработка плана действий совместно с клиентом"),
    _stage(4, "Презентация", "Представление конкретного решения"),
    _stage(5, "Закрытие", "Фиксация плана, назначение следующего шага"),
]

STAGES_COMPLIANCE = [
    _stage(1, "Приветствие", "Представление, объяснение цели проверки"),
    _stage(2, "Вопросы", "Задавание контрольных вопросов, сбор информации"),
    _stage(3, "Квалификация", "Анализ ответов, определение соответствия"),
    _stage(4, "Закрытие", "Подведение итогов, рекомендации, следующие шаги"),
]

STAGES_MULTI_PARTY = [
    _stage(1, "Участники", "Идентификация всех участников, установление ролей"),
    _stage(2, "Квалификация", "Выяснение позиций каждой стороны"),
    _stage(3, "Презентация", "Представление решения, учитывающего интересы всех сторон"),
    _stage(4, "Медиация", "Поиск компромисса, снятие противоречий"),
    _stage(5, "Закрытие", "Фиксация общего решения, план действий"),
]


# ─── Special group stages (custom per scenario) ───────────────────────────────

STAGES_SPECIAL_GHOSTED = [
    _stage(1, "Контакт", "Попытка восстановить связь с пропавшим клиентом"),
    _stage(2, "Причина", "Выяснение причины исчезновения"),
    _stage(3, "Реактивация", "Предложение новой ценности"),
    _stage(4, "Закрытие", "Фиксация договорённости о следующем контакте"),
]

STAGES_SPECIAL_URGENT = [
    _stage(1, "Приём", "Быстрая идентификация срочной ситуации"),
    _stage(2, "Диагностика", "Оценка масштаба проблемы"),
    _stage(3, "Решение", "Предложение экстренного решения"),
    _stage(4, "Действие", "Немедленные шаги по реализации"),
    _stage(5, "Закрытие", "Фиксация плана, контрольная точка"),
]

STAGES_SPECIAL_GUARANTOR = [
    _stage(1, "Контакт", "Установление контакта с поручителем"),
    _stage(2, "Ситуация", "Объяснение ситуации, правовой контекст"),
    _stage(3, "Квалификация", "Выяснение возможностей поручителя"),
    _stage(4, "Переговоры", "Обсуждение вариантов решения"),
    _stage(5, "Закрытие", "Фиксация плана действий"),
]

STAGES_SPECIAL_COUPLE = [
    _stage(1, "Контакт", "Установление контакта с обоими партнёрами"),
    _stage(2, "Позиции", "Выяснение позиции каждого партнёра"),
    _stage(3, "Презентация", "Решение, учитывающее интересы обоих"),
    _stage(4, "Медиация", "Снятие разногласий между партнёрами"),
    _stage(5, "Закрытие", "Общее решение, план действий"),
]

STAGES_UPSELL = [
    _stage(1, "Контакт", "Приветствие текущего клиента"),
    _stage(2, "Анализ", "Анализ текущего использования, выявление потребностей"),
    _stage(3, "Предложение", "Презентация дополнительного продукта"),
    _stage(4, "Закрытие", "Оформление, фиксация оплаты"),
]

STAGES_RESCUE = [
    _stage(1, "Контакт", "Срочное восстановление контакта"),
    _stage(2, "Проблема", "Выяснение причины ухода"),
    _stage(3, "Решение", "Предложение персонального решения"),
    _stage(4, "Удержание", "Закрепление клиента, особые условия"),
    _stage(5, "Закрытие", "Фиксация нового соглашения"),
]

STAGES_SPECIAL_INHERITANCE = [
    _stage(1, "Контакт", "Деликатное установление контакта"),
    _stage(2, "Ситуация", "Выяснение правового статуса наследства"),
    _stage(3, "Квалификация", "Определение объёма обязательств"),
    _stage(4, "Консультация", "Правовая консультация по опциям"),
    _stage(5, "Закрытие", "План действий, назначение встречи"),
]

STAGES_VIP_DEBTOR = [
    _stage(1, "Приветствие", "VIP-приветствие, персональный подход"),
    _stage(2, "Ситуация", "Деликатное выяснение ситуации"),
    _stage(3, "Предложение", "Эксклюзивные условия решения"),
    _stage(4, "Переговоры", "Высокоуровневые переговоры"),
    _stage(5, "Закрытие", "Персональный план, VIP-сопровождение"),
]

STAGES_SPECIAL_PSYCHOLOGIST = [
    _stage(1, "Контакт", "Осторожное установление контакта"),
    _stage(2, "Эмпатия", "Глубокая эмпатия, активное слушание"),
    _stage(3, "Стабилизация", "Эмоциональная стабилизация клиента"),
    _stage(4, "Решение", "Мягкое предложение конструктивного выхода"),
    _stage(5, "Закрытие", "Фиксация следующего контакта"),
]

STAGES_SPECIAL_VIP = [
    _stage(1, "Приветствие", "VIP-приветствие, статусный подход"),
    _stage(2, "Диагностика", "Комплексная диагностика ситуации"),
    _stage(3, "Решение", "Премиальное решение"),
    _stage(4, "Согласование", "Высокоуровневое согласование"),
    _stage(5, "Закрытие", "Персональный план, VIP-сопровождение"),
]

STAGES_SPECIAL_MEDICAL = [
    _stage(1, "Контакт", "Деликатное установление контакта"),
    _stage(2, "Ситуация", "Выяснение медицинской и финансовой ситуации"),
    _stage(3, "Квалификация", "Определение возможностей клиента"),
    _stage(4, "Решение", "Гибкий план с учётом обстоятельств"),
    _stage(5, "Закрытие", "Фиксация плана, поддержка"),
]

STAGES_SPECIAL_BOSS = [
    _stage(1, "Приветствие", "Вступление в контакт с максимально сложным клиентом"),
    _stage(2, "Выживание", "Удержание контакта под давлением"),
    _stage(3, "Квалификация", "Выявление истинных потребностей за фасадом"),
    _stage(4, "Презентация", "Убедительная аргументация на высшем уровне"),
    _stage(5, "Закрытие", "Закрытие сделки босс-уровня"),
]


# ═════════════════════════════════════════════════════════════════════════════
# 60 SCENARIO TEMPLATE DEFINITIONS
# ═════════════════════════════════════════════════════════════════════════════

SCENARIO_TEMPLATES: list[dict] = [

    # ═══ GROUP A: OUTBOUND COLD (10) ═══════════════════════════════════════

    # 1. cold_ad
    {
        "code": "cold_ad",
        "name": "Холодный звонок по рекламной заявке",
        "description": "Клиент оставил заявку на сайте 1-7 дней назад. Менеджер звонит впервые. Клиент может не помнить заявку.",
        "group_name": "A_outbound_cold",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "cold",
        "client_awareness": "low",
        "client_motivation": "medium",
        "typical_duration_minutes": 8,
        "max_duration_minutes": 12,
        "target_outcome": "meeting",
        "difficulty": 4,
        "stages": STAGES_COLD,
    },
    # 2. cold_referral
    {
        "code": "cold_referral",
        "name": "Холодный звонок по рекомендации",
        "description": "Контакт получен по рекомендации от существующего клиента или партнёра. Есть предварительное доверие.",
        "group_name": "A_outbound_cold",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "curious",
        "client_awareness": "low",
        "client_motivation": "medium",
        "typical_duration_minutes": 6,
        "max_duration_minutes": 10,
        "target_outcome": "meeting",
        "difficulty": 3,
        "stages": STAGES_COLD,
    },
    # 3. cold_social
    {
        "code": "cold_social",
        "name": "Холодный звонок через соцсети",
        "description": "Контакт найден через социальные сети (VK, Telegram). Клиент не ожидает звонка.",
        "group_name": "A_outbound_cold",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "guarded",
        "client_awareness": "zero",
        "client_motivation": "low",
        "typical_duration_minutes": 4,
        "max_duration_minutes": 8,
        "target_outcome": "callback",
        "difficulty": 4,
        "stages": STAGES_COLD,
    },
    # 4. cold_database
    {
        "code": "cold_database",
        "name": "Холодный звонок по базе ФССП",
        "description": "Контакт из базы ФССП. Клиент в сложной ситуации, может быть агрессивен.",
        "group_name": "A_outbound_cold",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "hostile",
        "client_awareness": "zero",
        "client_motivation": "none",
        "typical_duration_minutes": 3,
        "max_duration_minutes": 7,
        "target_outcome": "callback",
        "difficulty": 7,
        "stages": STAGES_COLD,
    },
    # 5. cold_base
    {
        "code": "cold_base",
        "name": "Холодный звонок по купленной базе",
        "description": "Контакт из купленной базы данных. Клиент не ожидает звонка, высокий процент отказов.",
        "group_name": "A_outbound_cold",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "hostile",
        "client_awareness": "zero",
        "client_motivation": "none",
        "typical_duration_minutes": 3,
        "max_duration_minutes": 7,
        "target_outcome": "callback",
        "difficulty": 7,
        "stages": STAGES_COLD,
    },
    # 6. cold_partner
    {
        "code": "cold_partner",
        "name": "Холодный звонок от партнёра",
        "description": "Контакт передан партнёрской организацией. Есть контекст сотрудничества.",
        "group_name": "A_outbound_cold",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "cold",
        "client_awareness": "low",
        "client_motivation": "medium",
        "typical_duration_minutes": 6,
        "max_duration_minutes": 10,
        "target_outcome": "meeting",
        "difficulty": 4,
        "stages": STAGES_COLD,
    },
    # 7. cold_premium
    {
        "code": "cold_premium",
        "name": "Холодный звонок по VIP-списку",
        "description": "Контакт из VIP-списка. Клиент с высоким чеком, требует статусного подхода.",
        "group_name": "A_outbound_cold",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "guarded",
        "client_awareness": "low",
        "client_motivation": "low",
        "typical_duration_minutes": 6,
        "max_duration_minutes": 12,
        "target_outcome": "meeting",
        "difficulty": 6,
        "stages": STAGES_COLD,
    },
    # 8. cold_event
    {
        "code": "cold_event",
        "name": "Холодный звонок после мероприятия",
        "description": "Контакт получен на мероприятии (выставка, конференция). Клиент проявил интерес.",
        "group_name": "A_outbound_cold",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "curious",
        "client_awareness": "low",
        "client_motivation": "medium",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 8,
        "target_outcome": "meeting",
        "difficulty": 3,
        "stages": STAGES_COLD,
    },
    # 9. cold_expired
    {
        "code": "cold_expired",
        "name": "Холодный звонок по просроченному лиду",
        "description": "Лид давностью 30+ дней. Клиент мог забыть о заявке или уже решить вопрос.",
        "group_name": "A_outbound_cold",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "cold",
        "client_awareness": "zero",
        "client_motivation": "low",
        "typical_duration_minutes": 4,
        "max_duration_minutes": 8,
        "target_outcome": "callback",
        "difficulty": 5,
        "stages": STAGES_COLD,
    },
    # 10. cold_insurance
    {
        "code": "cold_insurance",
        "name": "Холодный звонок через страховую/МФО",
        "description": "Контакт из партнёрской страховой или МФО. Клиент имеет финансовые обязательства.",
        "group_name": "A_outbound_cold",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "guarded",
        "client_awareness": "low",
        "client_motivation": "medium",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 10,
        "target_outcome": "meeting",
        "difficulty": 5,
        "stages": STAGES_COLD,
    },

    # ═══ GROUP B: OUTBOUND WARM (10) ═══════════════════════════════════════

    # 11. warm_callback
    {
        "code": "warm_callback",
        "name": "Запланированный обратный звонок",
        "description": "Менеджер перезванивает по договорённости. Клиент ожидает звонка.",
        "group_name": "B_outbound_warm",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "curious",
        "client_awareness": "medium",
        "client_motivation": "medium",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 10,
        "target_outcome": "meeting",
        "difficulty": 3,
        "stages": STAGES_WARM,
    },
    # 12. warm_noanswer
    {
        "code": "warm_noanswer",
        "name": "Повторный звонок без ответа",
        "description": "Клиент не ответил на предыдущие звонки. Попытка дозвониться повторно.",
        "group_name": "B_outbound_warm",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": True,
        "initial_emotion": "cold",
        "client_awareness": "low",
        "client_motivation": "low",
        "typical_duration_minutes": 4,
        "max_duration_minutes": 8,
        "target_outcome": "callback",
        "difficulty": 5,
        "stages": STAGES_WARM,
    },
    # 13. warm_refused
    {
        "code": "warm_refused",
        "name": "Повторное вовлечение отказника",
        "description": "Клиент ранее отказался. Менеджер пытается реактивировать контакт с новым предложением.",
        "group_name": "B_outbound_warm",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": True,
        "initial_emotion": "hostile",
        "client_awareness": "medium",
        "client_motivation": "negative",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 10,
        "target_outcome": "meeting",
        "difficulty": 8,
        "stages": STAGES_WARM,
    },
    # 14. warm_dropped
    {
        "code": "warm_dropped",
        "name": "Возврат ушедшего клиента",
        "description": "Клиент прекратил сотрудничество. Менеджер пытается вернуть.",
        "group_name": "B_outbound_warm",
        "who_calls": "manager",
        "funnel_stage": "retention",
        "prior_contact": True,
        "initial_emotion": "guarded",
        "client_awareness": "high",
        "client_motivation": "low",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 10,
        "target_outcome": "meeting",
        "difficulty": 6,
        "stages": STAGES_WARM,
    },
    # 15. warm_repeat
    {
        "code": "warm_repeat",
        "name": "Повторный звонок текущему клиенту",
        "description": "Плановый звонок существующему клиенту для продвижения по воронке.",
        "group_name": "B_outbound_warm",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "curious",
        "client_awareness": "medium",
        "client_motivation": "medium",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 8,
        "target_outcome": "meeting",
        "difficulty": 4,
        "stages": STAGES_WARM,
    },
    # 16. warm_webinar
    {
        "code": "warm_webinar",
        "name": "Звонок после вебинара",
        "description": "Клиент посетил вебинар. Менеджер звонит для конвертации в сделку.",
        "group_name": "B_outbound_warm",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "curious",
        "client_awareness": "medium",
        "client_motivation": "medium",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 8,
        "target_outcome": "meeting",
        "difficulty": 3,
        "stages": STAGES_WARM,
    },
    # 17. warm_vip
    {
        "code": "warm_vip",
        "name": "VIP повторный звонок",
        "description": "Повторный звонок VIP-клиенту. Требуется статусный подход и гибкость.",
        "group_name": "B_outbound_warm",
        "who_calls": "manager",
        "funnel_stage": "close",
        "prior_contact": True,
        "initial_emotion": "guarded",
        "client_awareness": "high",
        "client_motivation": "medium",
        "typical_duration_minutes": 6,
        "max_duration_minutes": 12,
        "target_outcome": "meeting",
        "difficulty": 7,
        "stages": STAGES_WARM,
    },
    # 18. warm_ghosted
    {
        "code": "warm_ghosted",
        "name": "Клиент пропал",
        "description": "Клиент перестал выходить на связь после начала диалога.",
        "group_name": "B_outbound_warm",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "cold",
        "client_awareness": "medium",
        "client_motivation": "low",
        "typical_duration_minutes": 3,
        "max_duration_minutes": 6,
        "target_outcome": "callback",
        "difficulty": 5,
        "stages": STAGES_WARM,
    },
    # 19. warm_complaint
    {
        "code": "warm_complaint",
        "name": "Звонок после жалобы",
        "description": "Клиент ранее подал жалобу. Менеджер восстанавливает доверие.",
        "group_name": "B_outbound_warm",
        "who_calls": "manager",
        "funnel_stage": "retention",
        "prior_contact": True,
        "initial_emotion": "hostile",
        "client_awareness": "high",
        "client_motivation": "negative",
        "typical_duration_minutes": 6,
        "max_duration_minutes": 12,
        "target_outcome": "meeting",
        "difficulty": 6,
        "stages": STAGES_WARM,
    },
    # 20. warm_competitor
    {
        "code": "warm_competitor",
        "name": "Ушёл к конкуренту",
        "description": "Клиент ушёл к конкуренту. Менеджер пытается вернуть, предлагая лучшие условия.",
        "group_name": "B_outbound_warm",
        "who_calls": "manager",
        "funnel_stage": "retention",
        "prior_contact": True,
        "initial_emotion": "guarded",
        "client_awareness": "high",
        "client_motivation": "negative",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 10,
        "target_outcome": "meeting",
        "difficulty": 8,
        "stages": STAGES_WARM,
    },

    # ═══ GROUP C: INBOUND (8) ══════════════════════════════════════════════

    # 21. in_website
    {
        "code": "in_website",
        "name": "Входящий с сайта",
        "description": "Клиент заполнил форму на сайте и звонит для уточнения. Высокая мотивация.",
        "group_name": "C_inbound",
        "who_calls": "client",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "curious",
        "client_awareness": "medium",
        "client_motivation": "high",
        "typical_duration_minutes": 6,
        "max_duration_minutes": 10,
        "target_outcome": "meeting",
        "difficulty": 2,
        "stages": STAGES_INBOUND,
    },
    # 22. in_hotline
    {
        "code": "in_hotline",
        "name": "Входящий на горячую линию",
        "description": "Клиент звонит на горячую линию. Может быть разная степень осведомлённости.",
        "group_name": "C_inbound",
        "who_calls": "client",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "curious",
        "client_awareness": "low",
        "client_motivation": "high",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 10,
        "target_outcome": "meeting",
        "difficulty": 3,
        "stages": STAGES_INBOUND,
    },
    # 23. in_social
    {
        "code": "in_social",
        "name": "Входящий из соцсетей",
        "description": "Клиент написал в соцсети и просит перезвонить. Средняя мотивация.",
        "group_name": "C_inbound",
        "who_calls": "client",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "curious",
        "client_awareness": "low",
        "client_motivation": "medium",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 8,
        "target_outcome": "meeting",
        "difficulty": 4,
        "stages": STAGES_INBOUND,
    },
    # 24. in_chatbot
    {
        "code": "in_chatbot",
        "name": "Входящий из чат-бота",
        "description": "Клиент общался с чат-ботом и запросил звонок менеджера.",
        "group_name": "C_inbound",
        "who_calls": "client",
        "funnel_stage": "qualification",
        "prior_contact": False,
        "initial_emotion": "curious",
        "client_awareness": "medium",
        "client_motivation": "medium",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 8,
        "target_outcome": "meeting",
        "difficulty": 3,
        "stages": STAGES_INBOUND,
    },
    # 25. in_partner
    {
        "code": "in_partner",
        "name": "Входящий по рекомендации партнёра",
        "description": "Клиент обращается по рекомендации партнёрской организации.",
        "group_name": "C_inbound",
        "who_calls": "client",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "curious",
        "client_awareness": "low",
        "client_motivation": "medium",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 10,
        "target_outcome": "meeting",
        "difficulty": 4,
        "stages": STAGES_INBOUND,
    },
    # 26. in_complaint
    {
        "code": "in_complaint",
        "name": "Входящая жалоба",
        "description": "Клиент звонит с жалобой. Высокий эмоциональный накал, требуется деэскалация.",
        "group_name": "C_inbound",
        "who_calls": "client",
        "funnel_stage": "retention",
        "prior_contact": True,
        "initial_emotion": "hostile",
        "client_awareness": "high",
        "client_motivation": "very_high",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 12,
        "target_outcome": "meeting",
        "difficulty": 5,
        "stages": STAGES_INBOUND,
    },
    # 27. in_urgent
    {
        "code": "in_urgent",
        "name": "Срочный входящий",
        "description": "Клиент звонит с срочным запросом. Требуется быстрая реакция.",
        "group_name": "C_inbound",
        "who_calls": "client",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "guarded",
        "client_awareness": "low",
        "client_motivation": "very_high",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 10,
        "target_outcome": "meeting",
        "difficulty": 6,
        "stages": STAGES_INBOUND,
    },
    # 28. in_corporate
    {
        "code": "in_corporate",
        "name": "Корпоративный входящий",
        "description": "Представитель компании обращается по корпоративному вопросу. Формальный стиль.",
        "group_name": "C_inbound",
        "who_calls": "client",
        "funnel_stage": "qualification",
        "prior_contact": False,
        "initial_emotion": "cold",
        "client_awareness": "medium",
        "client_motivation": "medium",
        "typical_duration_minutes": 8,
        "max_duration_minutes": 15,
        "target_outcome": "meeting",
        "difficulty": 5,
        "stages": STAGES_INBOUND,
    },

    # ═══ GROUP D: SPECIAL (12) ═════════════════════════════════════════════

    # 29. special_ghosted
    {
        "code": "special_ghosted",
        "name": "Призрак-клиент",
        "description": "Клиент полностью пропал после начала процесса. Попытка восстановить контакт.",
        "group_name": "D_special",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "cold",
        "client_awareness": "medium",
        "client_motivation": "low",
        "typical_duration_minutes": 3,
        "max_duration_minutes": 6,
        "target_outcome": "callback",
        "difficulty": 5,
        "stages": STAGES_SPECIAL_GHOSTED,
    },
    # 30. special_urgent
    {
        "code": "special_urgent",
        "name": "Срочная ситуация",
        "description": "Клиент в экстренной ситуации: суд, арест счетов, дедлайн. Требуется быстрое решение.",
        "group_name": "D_special",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "guarded",
        "client_awareness": "low",
        "client_motivation": "very_high",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 10,
        "target_outcome": "meeting",
        "difficulty": 6,
        "stages": STAGES_SPECIAL_URGENT,
    },
    # 31. special_guarantor
    {
        "code": "special_guarantor",
        "name": "Работа с поручителем",
        "description": "Контакт с поручителем по кредиту. Юридически тонкая ситуация.",
        "group_name": "D_special",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": False,
        "initial_emotion": "hostile",
        "client_awareness": "low",
        "client_motivation": "none",
        "typical_duration_minutes": 6,
        "max_duration_minutes": 12,
        "target_outcome": "meeting",
        "difficulty": 6,
        "stages": STAGES_SPECIAL_GUARANTOR,
    },
    # 32. special_couple
    {
        "code": "special_couple",
        "name": "Звонок паре",
        "description": "Разговор с парой (муж и жена). Два собеседника с разными позициями.",
        "group_name": "D_special",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "guarded",
        "client_awareness": "medium",
        "client_motivation": "medium",
        "typical_duration_minutes": 8,
        "max_duration_minutes": 15,
        "target_outcome": "meeting",
        "difficulty": 7,
        "stages": STAGES_SPECIAL_COUPLE,
    },
    # 33. upsell
    {
        "code": "upsell",
        "name": "Допродажа",
        "description": "Текущий клиент. Менеджер предлагает дополнительный продукт или расширение.",
        "group_name": "D_special",
        "who_calls": "manager",
        "funnel_stage": "upsell",
        "prior_contact": True,
        "initial_emotion": "curious",
        "client_awareness": "high",
        "client_motivation": "medium",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 8,
        "target_outcome": "payment",
        "difficulty": 5,
        "stages": STAGES_UPSELL,
    },
    # 34. rescue
    {
        "code": "rescue",
        "name": "Спасение клиента",
        "description": "Клиент на грани ухода. Экстренное удержание с персональными условиями.",
        "group_name": "D_special",
        "who_calls": "manager",
        "funnel_stage": "retention",
        "prior_contact": True,
        "initial_emotion": "hostile",
        "client_awareness": "high",
        "client_motivation": "negative",
        "typical_duration_minutes": 6,
        "max_duration_minutes": 12,
        "target_outcome": "retention",
        "difficulty": 7,
        "stages": STAGES_RESCUE,
    },
    # 35. special_inheritance
    {
        "code": "special_inheritance",
        "name": "Наследственный долг",
        "description": "Клиент унаследовал долг. Деликатная ситуация: утрата + финансовые обязательства.",
        "group_name": "D_special",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": False,
        "initial_emotion": "guarded",
        "client_awareness": "low",
        "client_motivation": "low",
        "typical_duration_minutes": 8,
        "max_duration_minutes": 15,
        "target_outcome": "meeting",
        "difficulty": 7,
        "stages": STAGES_SPECIAL_INHERITANCE,
    },
    # 36. vip_debtor
    {
        "code": "vip_debtor",
        "name": "VIP-должник",
        "description": "Крупный должник с высоким статусом. Требует премиального и деликатного подхода.",
        "group_name": "D_special",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "guarded",
        "client_awareness": "high",
        "client_motivation": "low",
        "typical_duration_minutes": 8,
        "max_duration_minutes": 15,
        "target_outcome": "meeting",
        "difficulty": 8,
        "stages": STAGES_VIP_DEBTOR,
    },
    # 37. special_psychologist
    {
        "code": "special_psychologist",
        "name": "Психологически сложный клиент",
        "description": "Клиент в тяжёлом эмоциональном состоянии. Требуется психологическая чуткость.",
        "group_name": "D_special",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "hostile",
        "client_awareness": "low",
        "client_motivation": "none",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 12,
        "target_outcome": "callback",
        "difficulty": 8,
        "stages": STAGES_SPECIAL_PSYCHOLOGIST,
    },
    # 38. special_vip
    {
        "code": "special_vip",
        "name": "VIP-медицинский случай",
        "description": "VIP-клиент с медицинскими обстоятельствами. Максимальная деликатность.",
        "group_name": "D_special",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "guarded",
        "client_awareness": "medium",
        "client_motivation": "low",
        "typical_duration_minutes": 8,
        "max_duration_minutes": 15,
        "target_outcome": "meeting",
        "difficulty": 8,
        "stages": STAGES_SPECIAL_VIP,
    },
    # 39. special_medical
    {
        "code": "special_medical",
        "name": "Медицинский долг",
        "description": "Клиент с долгом за медицинские услуги. Особые обстоятельства и эмпатия.",
        "group_name": "D_special",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": False,
        "initial_emotion": "guarded",
        "client_awareness": "low",
        "client_motivation": "low",
        "typical_duration_minutes": 6,
        "max_duration_minutes": 12,
        "target_outcome": "meeting",
        "difficulty": 7,
        "stages": STAGES_SPECIAL_MEDICAL,
    },
    # 40. special_boss
    {
        "code": "special_boss",
        "name": "Босс-файт",
        "description": "Финальное испытание: максимально сложный клиент с комбинацией всех техник. Все механики активны.",
        "group_name": "D_special",
        "who_calls": "manager",
        "funnel_stage": "close",
        "prior_contact": True,
        "initial_emotion": "hostile",
        "client_awareness": "high",
        "client_motivation": "negative",
        "typical_duration_minutes": 10,
        "max_duration_minutes": 20,
        "target_outcome": "deal",
        "difficulty": 10,
        "stages": STAGES_SPECIAL_BOSS,
    },

    # ═══ GROUP E: FOLLOW-UP (5) ════════════════════════════════════════════

    # 41. follow_up_first
    {
        "code": "follow_up_first",
        "name": "Первый follow-up",
        "description": "Первый плановый перезвон после контакта. Продвижение клиента к встрече.",
        "group_name": "E_follow_up",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "cold",
        "client_awareness": "medium",
        "client_motivation": "medium",
        "typical_duration_minutes": 4,
        "max_duration_minutes": 8,
        "target_outcome": "meeting",
        "difficulty": 3,
        "stages": STAGES_FOLLOW_UP,
    },
    # 42. follow_up_second
    {
        "code": "follow_up_second",
        "name": "Второй follow-up",
        "description": "Второй перезвон. Клиент тянет с решением, нужно усилить мотивацию.",
        "group_name": "E_follow_up",
        "who_calls": "manager",
        "funnel_stage": "meeting",
        "prior_contact": True,
        "initial_emotion": "cold",
        "client_awareness": "medium",
        "client_motivation": "low",
        "typical_duration_minutes": 4,
        "max_duration_minutes": 8,
        "target_outcome": "meeting",
        "difficulty": 4,
        "stages": STAGES_FOLLOW_UP,
    },
    # 43. follow_up_third
    {
        "code": "follow_up_third",
        "name": "Третий follow-up",
        "description": "Третий перезвон. Последняя попытка конвертации перед закрытием лида.",
        "group_name": "E_follow_up",
        "who_calls": "manager",
        "funnel_stage": "close",
        "prior_contact": True,
        "initial_emotion": "guarded",
        "client_awareness": "high",
        "client_motivation": "low",
        "typical_duration_minutes": 4,
        "max_duration_minutes": 8,
        "target_outcome": "deal",
        "difficulty": 5,
        "stages": STAGES_FOLLOW_UP,
    },
    # 44. follow_up_rescue
    {
        "code": "follow_up_rescue",
        "name": "Спасательный follow-up",
        "description": "Follow-up для клиента, который начал уходить. Экстренная реактивация.",
        "group_name": "E_follow_up",
        "who_calls": "manager",
        "funnel_stage": "retention",
        "prior_contact": True,
        "initial_emotion": "hostile",
        "client_awareness": "high",
        "client_motivation": "negative",
        "typical_duration_minutes": 3,
        "max_duration_minutes": 6,
        "target_outcome": "callback",
        "difficulty": 6,
        "stages": STAGES_FOLLOW_UP,
    },
    # 45. follow_up_memory
    {
        "code": "follow_up_memory",
        "name": "Follow-up с памятью",
        "description": "Follow-up с использованием кросс-сессионной памяти. Глубокая персонализация.",
        "group_name": "E_follow_up",
        "who_calls": "manager",
        "funnel_stage": "close",
        "prior_contact": True,
        "initial_emotion": "guarded",
        "client_awareness": "high",
        "client_motivation": "medium",
        "typical_duration_minutes": 6,
        "max_duration_minutes": 12,
        "target_outcome": "deal",
        "difficulty": 7,
        "stages": STAGES_FOLLOW_UP,
    },

    # ═══ GROUP F: CRISIS (5) ═══════════════════════════════════════════════

    # 46. crisis_collector
    {
        "code": "crisis_collector",
        "name": "Пост-коллекторский кризис",
        "description": "Клиент пострадал от действий коллекторов. Высокий стресс, недоверие к системе.",
        "group_name": "F_crisis",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "hostile",
        "client_awareness": "low",
        "client_motivation": "low",
        "typical_duration_minutes": 6,
        "max_duration_minutes": 12,
        "target_outcome": "meeting",
        "difficulty": 6,
        "stages": STAGES_CRISIS,
    },
    # 47. crisis_pre_court
    {
        "code": "crisis_pre_court",
        "name": "Предсудебный кризис",
        "description": "Клиент получил повестку в суд. Паника, нужна срочная помощь.",
        "group_name": "F_crisis",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "hostile",
        "client_awareness": "low",
        "client_motivation": "very_high",
        "typical_duration_minutes": 6,
        "max_duration_minutes": 12,
        "target_outcome": "meeting",
        "difficulty": 7,
        "stages": STAGES_CRISIS,
    },
    # 48. crisis_business
    {
        "code": "crisis_business",
        "name": "Крах бизнеса",
        "description": "Бизнес клиента разорился. Множественные долги, паника, отчаяние.",
        "group_name": "F_crisis",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "hostile",
        "client_awareness": "low",
        "client_motivation": "medium",
        "typical_duration_minutes": 8,
        "max_duration_minutes": 15,
        "target_outcome": "meeting",
        "difficulty": 7,
        "stages": STAGES_CRISIS,
    },
    # 49. crisis_criminal
    {
        "code": "crisis_criminal",
        "name": "Уголовный риск",
        "description": "Клиент столкнулся с угрозой уголовного преследования по финансовым статьям.",
        "group_name": "F_crisis",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "hostile",
        "client_awareness": "low",
        "client_motivation": "very_high",
        "typical_duration_minutes": 6,
        "max_duration_minutes": 12,
        "target_outcome": "meeting",
        "difficulty": 8,
        "stages": STAGES_CRISIS,
    },
    # 50. crisis_full
    {
        "code": "crisis_full",
        "name": "Полный кризис",
        "description": "Клиент в полном кризисе: суд + коллекторы + арест счетов + семейные проблемы.",
        "group_name": "F_crisis",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "hostile",
        "client_awareness": "low",
        "client_motivation": "very_high",
        "typical_duration_minutes": 8,
        "max_duration_minutes": 15,
        "target_outcome": "meeting",
        "difficulty": 9,
        "stages": STAGES_CRISIS,
    },

    # ═══ GROUP G: COMPLIANCE (5) ═══════════════════════════════════════════

    # 51. compliance_basic
    {
        "code": "compliance_basic",
        "name": "Базовая проверка",
        "description": "Базовая проверка соответствия: верификация данных клиента и базовые вопросы.",
        "group_name": "G_compliance",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "cold",
        "client_awareness": "medium",
        "client_motivation": "medium",
        "typical_duration_minutes": 6,
        "max_duration_minutes": 12,
        "target_outcome": "meeting",
        "difficulty": 5,
        "stages": STAGES_COMPLIANCE,
    },
    # 52. compliance_docs
    {
        "code": "compliance_docs",
        "name": "Проверка документов",
        "description": "Проверка документации: верификация справок, договоров, выписок.",
        "group_name": "G_compliance",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "cold",
        "client_awareness": "medium",
        "client_motivation": "medium",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 10,
        "target_outcome": "meeting",
        "difficulty": 6,
        "stages": STAGES_COMPLIANCE,
    },
    # 53. compliance_legal
    {
        "code": "compliance_legal",
        "name": "Юридическая проверка",
        "description": "Проверка юридического соответствия: правовой статус, обременения, ограничения.",
        "group_name": "G_compliance",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "guarded",
        "client_awareness": "medium",
        "client_motivation": "low",
        "typical_duration_minutes": 8,
        "max_duration_minutes": 15,
        "target_outcome": "meeting",
        "difficulty": 7,
        "stages": STAGES_COMPLIANCE,
    },
    # 54. compliance_advanced
    {
        "code": "compliance_advanced",
        "name": "Расширенная проверка",
        "description": "Углублённая проверка: перекрёстные вопросы, выявление несоответствий.",
        "group_name": "G_compliance",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "guarded",
        "client_awareness": "medium",
        "client_motivation": "low",
        "typical_duration_minutes": 8,
        "max_duration_minutes": 15,
        "target_outcome": "meeting",
        "difficulty": 8,
        "stages": STAGES_COMPLIANCE,
    },
    # 55. compliance_full
    {
        "code": "compliance_full",
        "name": "Полная проверка",
        "description": "Полный цикл compliance: все виды проверок, стресс-тестирование клиента.",
        "group_name": "G_compliance",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "guarded",
        "client_awareness": "high",
        "client_motivation": "low",
        "typical_duration_minutes": 10,
        "max_duration_minutes": 20,
        "target_outcome": "meeting",
        "difficulty": 9,
        "stages": STAGES_COMPLIANCE,
    },

    # ═══ GROUP H: MULTI-PARTY (5) ═════════════════════════════════════════

    # 56. multi_party_basic
    {
        "code": "multi_party_basic",
        "name": "Базовый мультипарти",
        "description": "Разговор с двумя участниками. Базовая медиация между сторонами.",
        "group_name": "H_multi_party",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "guarded",
        "client_awareness": "medium",
        "client_motivation": "medium",
        "typical_duration_minutes": 8,
        "max_duration_minutes": 15,
        "target_outcome": "meeting",
        "difficulty": 7,
        "stages": STAGES_MULTI_PARTY,
    },
    # 57. multi_party_lawyer
    {
        "code": "multi_party_lawyer",
        "name": "Мультипарти с юристом",
        "description": "Клиент привёл юриста. Двойная аудитория: эмоциональный клиент + рациональный юрист.",
        "group_name": "H_multi_party",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "guarded",
        "client_awareness": "high",
        "client_motivation": "medium",
        "typical_duration_minutes": 10,
        "max_duration_minutes": 18,
        "target_outcome": "meeting",
        "difficulty": 8,
        "stages": STAGES_MULTI_PARTY,
    },
    # 58. multi_party_creditors
    {
        "code": "multi_party_creditors",
        "name": "Мультипарти с кредиторами",
        "description": "Конференция с несколькими кредиторами. Сложные финансовые переговоры.",
        "group_name": "H_multi_party",
        "who_calls": "manager",
        "funnel_stage": "close",
        "prior_contact": True,
        "initial_emotion": "hostile",
        "client_awareness": "high",
        "client_motivation": "medium",
        "typical_duration_minutes": 8,
        "max_duration_minutes": 15,
        "target_outcome": "meeting",
        "difficulty": 8,
        "stages": STAGES_MULTI_PARTY,
    },
    # 59. multi_party_family
    {
        "code": "multi_party_family",
        "name": "Семейный мультипарти",
        "description": "Семейный звонок: несколько членов семьи с разными позициями и эмоциями.",
        "group_name": "H_multi_party",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "guarded",
        "client_awareness": "medium",
        "client_motivation": "medium",
        "typical_duration_minutes": 8,
        "max_duration_minutes": 15,
        "target_outcome": "meeting",
        "difficulty": 7,
        "stages": STAGES_MULTI_PARTY,
    },
    # 60. multi_party_full
    {
        "code": "multi_party_full",
        "name": "Полный мультипарти",
        "description": "3+ участника: клиент, юрист, кредитор. Максимальная сложность медиации.",
        "group_name": "H_multi_party",
        "who_calls": "manager",
        "funnel_stage": "close",
        "prior_contact": True,
        "initial_emotion": "hostile",
        "client_awareness": "high",
        "client_motivation": "medium",
        "typical_duration_minutes": 12,
        "max_duration_minutes": 20,
        "target_outcome": "meeting",
        "difficulty": 9,
        "stages": STAGES_MULTI_PARTY,
    },
]


# ═════════════════════════════════════════════════════════════════════════════
# Seed function
# ═════════════════════════════════════════════════════════════════════════════

async def seed_scenario_templates() -> None:
    """Upsert all 60 scenario templates into the database."""
    async with async_session() as session:
        async with session.begin():
            existing_codes = (
                await session.execute(select(ScenarioTemplate.code))
            ).scalars().all()

            inserted = 0
            updated = 0

            for tpl in SCENARIO_TEMPLATES:
                if tpl["code"] not in existing_codes:
                    session.add(ScenarioTemplate(**tpl))
                    inserted += 1
                else:
                    # Upsert: update existing record
                    set_clauses = []
                    params = {"p_code": tpl["code"]}
                    for key, value in tpl.items():
                        if key == "code":
                            continue
                        param_name = f"p_{key}"
                        if key == "stages":
                            set_clauses.append(f"{key} = cast(:{param_name} as jsonb)")
                            params[param_name] = json.dumps(value, ensure_ascii=False)
                        elif isinstance(value, bool):
                            set_clauses.append(f"{key} = :{param_name}")
                            params[param_name] = value
                        else:
                            set_clauses.append(f"{key} = :{param_name}")
                            params[param_name] = value

                    if set_clauses:
                        sql = text(
                            f"UPDATE scenario_templates SET {', '.join(set_clauses)} "
                            f"WHERE code = :p_code"
                        )
                        await session.execute(sql, params)
                        updated += 1

        await session.commit()
        total = len(SCENARIO_TEMPLATES)
        print(
            f"Seeded {total} scenario templates "
            f"({inserted} inserted, {updated} updated)"
        )


# ═════════════════════════════════════════════════════════════════════════════
# Entrypoint
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_scenario_templates())
