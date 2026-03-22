"""Seed 15 scenario templates for Hunter888 roleplay system (ТЗ-05).

Usage:
    python -m scripts.seed_scenarios          # from apps/api/
    # or via make target:
    make seed-scenarios

Each scenario includes:
- Archetype weights (25 codes, sum ≈ 100)
- Conversation stages with goals/mistakes/emotion ranges
- Scoring modifiers, trap config, chain recommendations
- Awareness prompt injection and stage-skip reactions

Canonical emotion states used throughout:
  cold, guarded, curious, considering, negotiating, deal, testing, callback, hostile, hangup
"""

import asyncio
import logging
import sys
from pathlib import Path

# Allow running from apps/api/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.database import async_session, engine, Base
from app.models.scenario import ScenarioTemplate

logger = logging.getLogger(__name__)

# ─── 25 canonical archetype codes ───────────────────────────────────────────
ALL_ARCHETYPES = [
    "skeptic", "anxious", "passive", "avoidant", "paranoid", "ashamed",
    "aggressive", "hostile", "blamer", "sarcastic",
    "manipulator", "pragmatic", "delegator", "know_it_all", "negotiator", "shopper",
    "desperate", "crying", "grateful", "overwhelmed",
    "returner", "referred", "rushed", "lawyer_client", "couple",
]


def _w(**kw: float) -> dict[str, float]:
    """Build archetype weight dict, filling unlisted archetypes with 0."""
    result = {a: 0.0 for a in ALL_ARCHETYPES}
    result.update(kw)
    total = sum(result.values())
    if abs(total - 100.0) > 0.5:
        logger.warning("Archetype weights sum = %.1f (expected 100)", total)
    return result


# ─── Stage builder helpers ──────────────────────────────────────────────────

def _stage(order, name, description, goals, mistakes, emotions, dur_min, dur_max,
           required=True, red_flag="hangup"):
    return {
        "order": order,
        "name": name,
        "description": description,
        "manager_goals": goals,
        "manager_mistakes": mistakes,
        "expected_emotion_range": emotions,
        "emotion_red_flag": red_flag,
        "duration_min": dur_min,
        "duration_max": dur_max,
        "required": required,
    }


# ═════════════════════════════════════════════════════════════════════════════
# SCENARIO DEFINITIONS
# ═════════════════════════════════════════════════════════════════════════════

SCENARIOS: list[dict] = [
    # ─── #1 COLD_AD ──────────────────────────────────────────────────────────
    {
        "code": "cold_ad",
        "name": "Холодный по рекламной заявке",
        "description": "Клиент оставил заявку на сайте 1-7 дней назад. Менеджер звонит впервые.",
        "group_name": "A_outbound_cold",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "cold",
        "initial_emotion_variants": {"cold": 0.45, "guarded": 0.30, "curious": 0.25},
        "client_awareness": "low",
        "client_motivation": "medium",
        "typical_duration_minutes": 8,
        "max_duration_minutes": 12,
        "typical_reply_count_min": 8,
        "typical_reply_count_max": 15,
        "target_outcome": "meeting",
        "difficulty": 4,
        "archetype_weights": _w(
            skeptic=18, avoidant=14, passive=12, anxious=11, pragmatic=9,
            rushed=6, paranoid=5, know_it_all=4, shopper=4, desperate=3,
            crying=2, hostile=2, aggressive=2, manipulator=1.5, blamer=1.5,
            returner=1, couple=1, lawyer_client=1, delegator=0.5, ashamed=0.5,
            overwhelmed=0.3, sarcastic=0.2,
        ),
        "lead_sources": [
            "yandex_direct", "vk_target", "google_ads", "mytarget",
            "seo_organic", "telegram_ads",
        ],
        "stages": [
            _stage(1, "Приветствие", "Представление, напоминание о заявке",
                   ["Представиться (имя + компания)", "Напомнить о заявке с сайта",
                    "Убедиться что нужный человек", "Спросить удобно ли говорить"],
                   ["Не назвал причину звонка", "Не напомнил о заявке",
                    "Сразу перешёл к продаже", "Назвал клиента должником"],
                   ["cold", "guarded"], 1, 2),
            _stage(2, "Квалификация", "Выяснение ситуации клиента",
                   ["Узнать общую сумму долга", "Выяснить кредиторов",
                    "Понять стадию (просрочка/коллекторы/суд)", "Узнать про имущество"],
                   ["Вопросы как на допросе", "Нет эмпатии", "Пропуск этапа",
                    "Спрашивает про доход"],
                   ["guarded", "curious", "considering"], 2, 4),
            _stage(3, "Презентация", "Объяснение как банкротство решает проблему",
                   ["Привязать к ситуации клиента", "Назвать 127-ФЗ",
                    "Снять главный страх", "Показать выгоду"],
                   ["Шаблонная речь", "Перегрузка терминами",
                    "Обещает 100% результат", "Называет точную стоимость"],
                   ["considering", "curious"], 2, 3),
            _stage(4, "Работа с возражениями", "Обработка 1-3 возражений",
                   ["Выслушать полностью", "Присоединиться",
                    "Аргументированный ответ", "Проверить снято ли"],
                   ["Спорит", "Игнорирует возражение", "Давит на эмоции",
                    "Обесценивает страхи"],
                   ["considering", "curious", "guarded"], 3, 5),
            _stage(5, "Закрытие", "Назначение встречи",
                   ["Предложить 2-3 конкретных слота", "Объяснить что на встрече",
                    "Сказать что бесплатно", "Зафиксировать дату"],
                   ["Нет конкретного времени", "Один вариант",
                    "Не объяснил что на встрече"],
                   ["considering", "negotiating", "deal"], 1, 2),
            _stage(6, "Прощание", "Фиксация договорённости",
                   ["Повторить дату/время/адрес", "Напомнить что взять",
                    "Предложить SMS", "Тёплое прощание"],
                   ["Не повторил дату", "Бросил трубку быстро"],
                   ["deal", "callback"], 1, 1),
        ],
        "recommended_chains": [
            {"code": "proof_chain", "name": "Цепочка доказательств"},
            {"code": "minimal_step_chain", "name": "Цепочка минимального шага"},
            {"code": "fear_chain", "name": "Цепочка страхов"},
        ],
        "trap_pool_categories": ["price", "emotional", "manipulative"],
        "traps_count_min": 1,
        "traps_count_max": 2,
        "cascades_count": 0,
        "scoring_modifiers": [
            {"param": "script_adherence", "delta": 2, "condition": "Напомнил о заявке"},
            {"param": "script_adherence", "delta": -5, "condition": "Не задал вопросов на квалификации"},
            {"param": "empathy", "delta": 3, "condition": "Проявил участие при рассказе"},
            {"param": "empathy", "delta": -3, "condition": "Перебил клиента"},
            {"param": "objection_handling", "delta": 2, "condition": "Присоединение перед ответом"},
            {"param": "objection_handling", "delta": -4, "condition": "Спорил с клиентом"},
            {"param": "result", "delta": 5, "condition": "Встреча с конкретной датой"},
            {"param": "result", "delta": -5, "condition": "Не предложил следующий шаг"},
            {"param": "legal_accuracy", "delta": -10, "condition": "Обещал 100% списание"},
        ],
        "awareness_prompt": (
            "Ты слышал про банкротство — видел рекламу. Знаешь что «можно списать долги», "
            "но не знаешь деталей. Путаешь факты. Задаёшь вопросы: «А квартиру заберут?»"
        ),
        "stage_skip_reactions": {
            "greeting_skip": "А вы кто вообще? Откуда мой номер?",
            "qualification_skip": "Подождите, вы даже не спросили мою ситуацию!",
            "closing_no_time": "Ну, я подумаю и сам позвоню...",
            "guarantee_claim": "А вы точно можете гарантировать? Что-то не верится...",
        },
        "client_prompt_template": (
            "Ты — человек, который {days_ago} дней назад оставил заявку на сайте. "
            "Ты {remembers_state} эту заявку. Долг: {total_debt}₽. "
            "Кредиторы: {creditors}. Стадия: {stage}."
        ),
    },

    # ─── #2 COLD_BASE ────────────────────────────────────────────────────────
    {
        "code": "cold_base",
        "name": "Холодный по купленной базе",
        "description": "Звонок по базе должников (ФССП, бюро). Клиент НЕ оставлял заявку.",
        "group_name": "A_outbound_cold",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "cold",
        "initial_emotion_variants": {"cold": 0.20, "hostile": 0.50, "guarded": 0.30},
        "client_awareness": "zero",
        "client_motivation": "none",
        "typical_duration_minutes": 3,
        "max_duration_minutes": 7,
        "typical_reply_count_min": 5,
        "typical_reply_count_max": 10,
        "target_outcome": "callback",
        "difficulty": 7,
        "archetype_weights": _w(
            hostile=22, aggressive=14, paranoid=12, avoidant=10, rushed=8,
            skeptic=7, passive=5, anxious=5, desperate=4, pragmatic=3,
            blamer=2, ashamed=2, lawyer_client=1.5, crying=1, manipulator=1,
            sarcastic=0.7, know_it_all=0.5, shopper=0.5, overwhelmed=0.3,
            delegator=0.2, couple=0.2, negotiator=0.1,
        ),
        "lead_sources": [
            "fssp_database", "credit_bureau", "mfo_database",
            "purchased_base", "court_decisions",
        ],
        "stages": [
            _stage(1, "Приветствие + легитимация",
                   "Представление с легитимной причиной звонка (без нарушения 152-ФЗ)",
                   ["Представиться", "Легитимная причина звонка",
                    "Заинтересовать за 10-15 сек"],
                   ["Назвал сумму долга (152-ФЗ!)", "Назвал клиента должником",
                    "Слишком длинное вступление", "Говорит неуверенно"],
                   ["cold", "hostile", "guarded"], 2, 3),
            _stage(2, "Зацепка",
                   "Одна фраза-крючок чтобы клиент не бросил трубку",
                   ["Одна причина продолжить", "Факт вызывающий интерес",
                    "Не давить"],
                   ["FOMO-давление", "Запугивание", "Слишком длинно"],
                   ["guarded", "curious"], 1, 2),
            _stage(3, "Мини-квалификация",
                   "Быстрые 2-3 вопроса о ситуации",
                   ["Понять масштаб проблемы", "Узнать стадию",
                    "Определить подходит ли под банкротство"],
                   ["Слишком много вопросов", "Личные вопросы про доход"],
                   ["curious", "considering"], 2, 3, required=False),
            _stage(4, "Краткая презентация",
                   "30 секунд — суть банкротства",
                   ["За 30 сек дать суть", "Не углубляться — предложить встречу"],
                   ["Слишком долго", "Перегрузка терминами"],
                   ["considering", "curious"], 1, 2, required=False),
            _stage(5, "Закрытие на callback",
                   "Предложить перезвон или встречу",
                   ["Предложить callback", "Зафиксировать время"],
                   ["Не предложил конкретику"],
                   ["considering", "callback"], 1, 2),
        ],
        "recommended_chains": [
            {"code": "challenge_chain", "name": "Цепочка вызова"},
            {"code": "verification_chain", "name": "Цепочка проверки"},
            {"code": "quick_value_chain", "name": "Цепочка быстрой пользы"},
        ],
        "trap_pool_categories": ["provocative", "legal"],
        "traps_count_min": 1,
        "traps_count_max": 1,
        "cascades_count": 0,
        "scoring_modifiers": [
            {"param": "legal_accuracy", "delta": -15, "condition": "Назвал конкретную сумму долга (152-ФЗ)"},
            {"param": "legal_accuracy", "delta": -10, "condition": "Назвал клиента должником"},
            {"param": "script_adherence", "delta": 3, "condition": "Корректная легитимация"},
            {"param": "empathy", "delta": 5, "condition": "Спокоен при агрессии"},
            {"param": "empathy", "delta": -5, "condition": "Повысил голос / стал спорить"},
            {"param": "result", "delta": 5, "condition": "Callback с датой"},
            {"param": "stress_resistance", "delta": 3, "condition": "Выдержал 3+ возражения"},
        ],
        "awareness_prompt": (
            "Ты НИЧЕГО не знаешь о банкротстве. Ты не оставлял заявку. "
            "Первая реакция — раздражение: «Кто вы? Откуда мой номер?» "
            "Если менеджер назовёт сумму долга — агрессия: «Откуда вы знаете?!»"
        ),
        "stage_skip_reactions": {
            "greeting_skip": "Алло, кто это?!",
            "debt_mention": "С чего вы взяли, что у меня долги?!",
            "pressure": "Всё, до свидания!",
        },
        "client_prompt_template": (
            "Тебе звонит незнакомая компания. Ты НЕ оставлял заявку. "
            "Тебе регулярно звонят коллекторы, ты устал от звонков. "
            "Долг: {total_debt}₽. Кредиторы: {creditors}. Стадия: {stage}."
        ),
    },

    # ─── #3 COLD_REFERRAL ────────────────────────────────────────────────────
    {
        "code": "cold_referral",
        "name": "Холодный по рекомендации",
        "description": "Звонок по контакту от знакомого/родственника клиента.",
        "group_name": "A_outbound_cold",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "guarded",
        "initial_emotion_variants": {"guarded": 0.50, "curious": 0.30, "cold": 0.20},
        "client_awareness": "low",
        "client_motivation": "medium",
        "typical_duration_minutes": 6,
        "max_duration_minutes": 10,
        "typical_reply_count_min": 8,
        "typical_reply_count_max": 12,
        "target_outcome": "meeting",
        "difficulty": 3,
        "archetype_weights": _w(
            skeptic=15, anxious=14, passive=12, pragmatic=11, avoidant=10,
            delegator=8, desperate=6, ashamed=5, rushed=4, hostile=3,
            blamer=3, shopper=2, crying=2, paranoid=1.5, know_it_all=1,
            manipulator=0.8, overwhelmed=0.5, aggressive=0.5, sarcastic=0.3,
            lawyer_client=0.2, couple=0.1, negotiator=0.1,
        ),
        "lead_sources": ["client_referral", "friend_referral", "family_referral"],
        "stages": [
            _stage(1, "Приветствие с рекомендателем",
                   "Упоминание рекомендателя — главный козырь",
                   ["Представиться", "Упомянуть рекомендателя по имени",
                    "Объяснить контекст", "Не раскрывать детали от рекомендателя"],
                   ["Не упомянул рекомендателя", "Раскрыл информацию от рекомендателя",
                    "Назвал сумму долга"],
                   ["guarded", "curious"], 1, 2),
            _stage(2, "Квалификация",
                   "Мягкое выяснение ситуации",
                   ["Узнать ситуацию", "Уточнить что рекомендатель уже рассказал"],
                   ["Предполагает что знает ситуацию", "Слишком прямо"],
                   ["curious", "considering"], 2, 3),
            _stage(3, "Презентация",
                   "С опорой на кейс рекомендателя",
                   ["Упомянуть кейс рекомендателя", "Показать что похожие ситуации решаемы"],
                   ["Давать точные обещания"],
                   ["considering", "curious"], 2, 3),
            _stage(4, "Возражения",
                   "Работа с типичными для referral возражениями",
                   ["Обработать стыд/ожидания", "Не обесценивать"],
                   ["Обесценивание", "Давление"],
                   ["considering", "guarded"], 2, 4),
            _stage(5, "Закрытие", "Назначение встречи",
                   ["Конкретные слоты", "Бесплатно"],
                   ["Нет конкретики"],
                   ["negotiating", "deal"], 1, 2),
        ],
        "recommended_chains": [
            {"code": "social_proof_chain", "name": "Цепочка социального доказательства"},
            {"code": "shame_chain", "name": "Цепочка стыда"},
            {"code": "minimal_step_chain", "name": "Цепочка минимального шага"},
        ],
        "trap_pool_categories": ["emotional", "manipulative"],
        "traps_count_min": 1,
        "traps_count_max": 2,
        "cascades_count": 0,
        "scoring_modifiers": [
            {"param": "script_adherence", "delta": 3, "condition": "Упомянул рекомендателя в 1й реплике"},
            {"param": "script_adherence", "delta": -5, "condition": "Не упомянул рекомендателя"},
            {"param": "empathy", "delta": 3, "condition": "Тактично обошёл тему стыда"},
            {"param": "empathy", "delta": -5, "condition": "Раскрыл информацию от рекомендателя"},
            {"param": "result", "delta": 5, "condition": "Назначил встречу"},
        ],
        "awareness_prompt": (
            "Знакомый ({referrer_name}) тебе рассказывал о компании. "
            "Ты знаешь примерно что такое банкротство. Немного стесняешься."
        ),
        "stage_skip_reactions": {
            "no_referrer_mention": "А откуда вы про меня знаете?",
            "info_leak": "Он что, всем рассказывает про мои долги?!",
        },
        "client_prompt_template": (
            "Тебе позвонили по рекомендации {referrer_name}. "
            "При упоминании рекомендателя — смягчись. "
            "Если НЕ упомянут — будь настороженным."
        ),
    },

    # ─── #4 COLD_PARTNER ─────────────────────────────────────────────────────
    {
        "code": "cold_partner",
        "name": "Холодный от партнёра",
        "description": "Контакт от профессионала: юрист, бухгалтер, риелтор.",
        "group_name": "A_outbound_cold",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "guarded",
        "initial_emotion_variants": {"guarded": 0.45, "curious": 0.35, "cold": 0.20},
        "client_awareness": "low",
        "client_motivation": "medium",
        "typical_duration_minutes": 6,
        "max_duration_minutes": 10,
        "typical_reply_count_min": 8,
        "typical_reply_count_max": 12,
        "target_outcome": "meeting",
        "difficulty": 4,
        "archetype_weights": _w(
            pragmatic=18, skeptic=14, anxious=12, passive=10, avoidant=8,
            rushed=7, know_it_all=6, lawyer_client=5, overwhelmed=4,
            desperate=3, shopper=3, blamer=2.5, ashamed=2, hostile=1.5,
            delegator=1, crying=0.8, manipulator=0.5, paranoid=0.5,
            aggressive=0.3, sarcastic=0.3, couple=0.2, negotiator=0.2,
            returner=0.1, referred=0.1,
        ),
        "lead_sources": ["lawyer_partner", "accountant_partner", "realtor_partner", "financial_advisor"],
        "stages": [
            _stage(1, "Приветствие с партнёром",
                   "Упоминание партнёра и его профессии",
                   ["Представиться", "Упомянуть партнёра", "Подчеркнуть специализацию"],
                   ["Не упомянул партнёра", "Не объяснил специализацию"],
                   ["guarded", "curious"], 1, 2),
            _stage(2, "Квалификация", "Выяснение ситуации",
                   ["Узнать ситуацию", "Понять контекст от партнёра"],
                   ["Слишком прямо", "Не учёл контекст от партнёра"],
                   ["curious", "considering"], 2, 3),
            _stage(3, "Презентация", "С акцентом на экспертность",
                   ["Использовать авторитет партнёра", "Показать специализацию"],
                   ["Шаблонная презентация"],
                   ["considering"], 2, 3),
            _stage(4, "Возражения", "Экспертные возражения",
                   ["Объяснить разницу специализации", "Конкретные ответы"],
                   ["Некомпетентный ответ"],
                   ["considering", "guarded"], 2, 4),
            _stage(5, "Закрытие", "Встреча",
                   ["Конкретные слоты", "Бесплатно"],
                   ["Нет конкретики"],
                   ["negotiating", "deal"], 1, 2),
        ],
        "recommended_chains": [
            {"code": "expertise_chain", "name": "Цепочка экспертности"},
            {"code": "proof_chain", "name": "Цепочка доказательств"},
            {"code": "minimal_step_chain", "name": "Цепочка минимального шага"},
        ],
        "trap_pool_categories": ["expert", "price"],
        "traps_count_min": 1,
        "traps_count_max": 2,
        "cascades_count": 0,
        "scoring_modifiers": [
            {"param": "script_adherence", "delta": 3, "condition": "Упомянул партнёра"},
            {"param": "script_adherence", "delta": -5, "condition": "Не упомянул партнёра"},
            {"param": "objection_handling", "delta": 3, "condition": "Объяснил разницу специализации"},
            {"param": "result", "delta": 5, "condition": "Назначил встречу"},
        ],
        "awareness_prompt": (
            "Профессионал ({partner_name}) порекомендовал обратиться. "
            "Ты в «рабочем режиме» — прагматичен, задаёшь конкретные вопросы."
        ),
        "stage_skip_reactions": {
            "no_partner_mention": "А откуда вы про меня узнали?",
        },
        "client_prompt_template": (
            "Тебе позвонили по рекомендации {partner_type} {partner_name}. "
            "Ты обращался к нему по другому вопросу ({partner_context})."
        ),
    },

    # ─── #5 WARM_CALLBACK ────────────────────────────────────────────────────
    {
        "code": "warm_callback",
        "name": "Перезвон по договорённости",
        "description": "Клиент попросил перезвонить через N дней.",
        "group_name": "B_outbound_warm",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "guarded",
        "initial_emotion_variants": {"guarded": 0.40, "curious": 0.35, "cold": 0.25},
        "client_awareness": "medium",
        "client_motivation": "medium",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 10,
        "typical_reply_count_min": 6,
        "typical_reply_count_max": 12,
        "target_outcome": "meeting",
        "difficulty": 3,
        "archetype_weights": _w(
            skeptic=16, pragmatic=14, passive=12, anxious=10, avoidant=9,
            shopper=8, delegator=7, rushed=5, know_it_all=4, desperate=3,
            blamer=3, hostile=2, ashamed=2, manipulator=1.5, overwhelmed=1,
            crying=0.8, paranoid=0.5, lawyer_client=0.5, aggressive=0.3,
            couple=0.2, sarcastic=0.1, negotiator=0.1,
        ),
        "lead_sources": [
            "callback_from_cold_ad", "callback_from_cold_base",
            "callback_from_incoming", "callback_from_social",
        ],
        "stages": [
            _stage(1, "Повторное установление контакта",
                   "Напоминание о прошлом разговоре",
                   ["Напомнить о себе", "Сослаться на прошлый разговор",
                    "Показать что помнит детали"],
                   ["Звонит как впервые", "Не помнит деталей",
                    "Перезвонил не в то время"],
                   ["guarded", "curious"], 1, 2),
            _stage(2, "Выявление изменений",
                   "Что изменилось с прошлого разговора",
                   ["Спросить удалось ли подумать", "Выявить новые вопросы"],
                   ["Не спросил", "Давит: ну что решили?"],
                   ["curious", "considering"], 1, 3),
            _stage(3, "Доп. презентация",
                   "Если появились новые вопросы",
                   ["Ответить на новые вопросы", "Не повторять"],
                   ["Повторяет то же самое"],
                   ["considering"], 1, 3, required=False),
            _stage(4, "Новые возражения",
                   "Мифы из интернета, мнение семьи, конкуренты",
                   ["Развеять мифы", "Работа с семьёй"],
                   ["Обесценивает мнение семьи"],
                   ["considering", "guarded"], 2, 4),
            _stage(5, "Закрытие", "Встреча",
                   ["Конкретные слоты", "Предложить прийти с супругом"],
                   ["Нет конкретики"],
                   ["negotiating", "deal"], 1, 2),
        ],
        "recommended_chains": [
            {"code": "info_chain", "name": "Цепочка информирования"},
            {"code": "family_approval_chain", "name": "Цепочка семейного одобрения"},
            {"code": "comparison_chain", "name": "Цепочка сравнения"},
        ],
        "trap_pool_categories": ["emotional", "expert", "price"],
        "traps_count_min": 2,
        "traps_count_max": 3,
        "cascades_count": 1,
        "scoring_modifiers": [
            {"param": "script_adherence", "delta": 3, "condition": "Сослался на прошлый разговор"},
            {"param": "script_adherence", "delta": -5, "condition": "Начал как впервые"},
            {"param": "empathy", "delta": 3, "condition": "Не давит при выяснении"},
            {"param": "objection_handling", "delta": 4, "condition": "Развеял миф из интернета"},
            {"param": "result", "delta": 5, "condition": "Назначил встречу"},
            {"param": "result", "delta": -3, "condition": "Клиент снова попросил перезвонить"},
        ],
        "awareness_prompt": (
            "Ты уже общался с менеджером. Знаешь основы банкротства. "
            "За это время почитал интернет — появились новые вопросы/мифы."
        ),
        "stage_skip_reactions": {
            "no_reference": "Мы вроде уже это обсуждали?",
            "pressure": "Я же сказал что подумаю! Зачем давите?",
        },
        "client_prompt_template": (
            "С тобой уже общались {days_ago} дней назад. "
            "Ты попросил перезвонить, потому что: {callback_reason}. "
            "Что изменилось: {changes}."
        ),
    },

    # ─── #6 WARM_NOANSWER ───────────────────────────────────────────────────
    {
        "code": "warm_noanswer",
        "name": "Перезвон (не ответил)",
        "description": "Клиент ранее не взял трубку. 2-й/3-й/4-й звонок.",
        "group_name": "B_outbound_warm",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "cold",
        "initial_emotion_variants": {"cold": 0.40, "hostile": 0.30, "guarded": 0.30},
        "client_awareness": "zero",
        "client_motivation": "low",
        "typical_duration_minutes": 4,
        "max_duration_minutes": 8,
        "typical_reply_count_min": 5,
        "typical_reply_count_max": 10,
        "target_outcome": "callback",
        "difficulty": 5,
        "archetype_weights": _w(
            hostile=18, avoidant=15, rushed=12, skeptic=10, passive=8,
            paranoid=7, anxious=6, aggressive=5, pragmatic=4, desperate=3,
            blamer=3, ashamed=2, crying=1.5, shopper=1.5, manipulator=1,
            know_it_all=0.8, delegator=0.7, overwhelmed=0.5,
            lawyer_client=0.5, sarcastic=0.3, couple=0.2,
        ),
        "lead_sources": ["retry_cold_ad", "retry_cold_base", "retry_incoming"],
        "stages": [
            _stage(1, "Приветствие + контекст перезвона",
                   "Упоминание предыдущих попыток",
                   ["Представиться", "Упомянуть что звонил ранее",
                    "Кратко назвать причину"],
                   ["Извиняется за настойчивость", "Агрессивное начало",
                    "Не упомянул прошлые попытки"],
                   ["cold", "hostile", "guarded"], 1, 2),
            _stage(2, "Быстрая зацепка",
                   "10-секундная зацепка",
                   ["Одна фраза-крючок", "Причина не класть трубку"],
                   ["Слишком длинно", "Давление"],
                   ["guarded", "curious"], 1, 1),
            _stage(3, "Квалификация",
                   "Если клиент остался",
                   ["Быстрая квалификация"],
                   ["Слишком много вопросов"],
                   ["curious", "considering"], 2, 3, required=False),
            _stage(4, "Закрытие",
                   "Callback или WhatsApp",
                   ["Предложить callback/WhatsApp", "Зафиксировать"],
                   ["Не предложил конкретику"],
                   ["considering", "callback"], 1, 2),
        ],
        "recommended_chains": [
            {"code": "quick_value_chain", "name": "Цепочка быстрой пользы"},
            {"code": "challenge_chain", "name": "Цепочка вызова"},
            {"code": "minimal_step_chain", "name": "Цепочка минимального шага"},
        ],
        "trap_pool_categories": ["provocative"],
        "traps_count_min": 1,
        "traps_count_max": 1,
        "cascades_count": 0,
        "scoring_modifiers": [
            {"param": "stress_resistance", "delta": 5, "condition": "Спокойно реагирует на «хватит звонить»"},
            {"param": "empathy", "delta": 3, "condition": "«Понимаю что неудобно — буквально 30 сек»"},
            {"param": "result", "delta": 5, "condition": "Получил callback/встречу"},
        ],
        "awareness_prompt": (
            "Тебе звонят повторно. Ты не брал трубку ранее. "
            "Причина: {noanswer_reason}. Мало терпения."
        ),
        "stage_skip_reactions": {
            "aggressive_start": "Вы мне третий раз звоните! Что надо?",
        },
        "client_prompt_template": (
            "Тебе звонит менеджер, который уже звонил {attempts_count} раз. "
            "Ты не брал трубку, потому что: {noanswer_reason}."
        ),
    },

    # ─── #7 WARM_REFUSED ─────────────────────────────────────────────────────
    {
        "code": "warm_refused",
        "name": "Дожим отказника",
        "description": "Клиент сказал «нет» 1-4 недели назад. Ситуация могла измениться.",
        "group_name": "B_outbound_warm",
        "who_calls": "manager",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "cold",
        "initial_emotion_variants": {"cold": 0.35, "hostile": 0.35, "guarded": 0.30},
        "client_awareness": "medium",
        "client_motivation": "low",
        "typical_duration_minutes": 5,
        "max_duration_minutes": 10,
        "typical_reply_count_min": 6,
        "typical_reply_count_max": 14,
        "target_outcome": "meeting",
        "difficulty": 8,
        "archetype_weights": _w(
            returner=25, hostile=15, skeptic=12, avoidant=10, desperate=8,
            passive=6, anxious=5, blamer=4, pragmatic=3, aggressive=3,
            shopper=2, ashamed=2, crying=1.5, rushed=1, manipulator=0.8,
            delegator=0.5, paranoid=0.5, overwhelmed=0.3, know_it_all=0.2,
            lawyer_client=0.1, sarcastic=0.1,
        ),
        "lead_sources": [
            "refused_cold_ad", "refused_cold_base", "refused_incoming",
            "refused_meeting", "refused_callback",
        ],
        "stages": [
            _stage(1, "Повторное установление контакта",
                   "Признание прошлого контакта и отказа",
                   ["Напомнить о себе и дате", "Признать прошлое решение",
                    "Дать причину повторного звонка", "Считать эмоцию"],
                   ["Звонит как впервые", "Извиняется", "Давит",
                    "Не помнит деталей", "Упрекает"],
                   ["cold", "hostile", "guarded"], 2, 3),
            _stage(2, "Выявление изменений",
                   "Поиск триггера — что изменилось к худшему",
                   ["Спросить об изменениях", "Найти триггер",
                    "Эмпатия при ухудшении"],
                   ["Злорадство", "Не спрашивает", "Разочарование"],
                   ["guarded", "curious", "considering"], 1, 3),
            _stage(3, "Обновлённая презентация",
                   "Привязка к изменениям, новая информация",
                   ["Привязать к изменениям", "Новая информация"],
                   ["Повторяет старое"],
                   ["considering", "curious"], 2, 3),
            _stage(4, "Возражения + закрытие",
                   "Финальная обработка и назначение",
                   ["Обработать новые возражения", "Предложить встречу/callback"],
                   ["Давление", "Сдаётся слишком быстро"],
                   ["considering", "negotiating", "deal"], 2, 4),
        ],
        "recommended_chains": [
            {"code": "grudge_chain", "name": "Цепочка обиды"},
            {"code": "trigger_chain", "name": "Цепочка триггера"},
            {"code": "comparison_chain", "name": "Цепочка сравнения"},
        ],
        "trap_pool_categories": ["emotional", "provocative", "manipulative"],
        "traps_count_min": 2,
        "traps_count_max": 3,
        "cascades_count": 1,
        "scoring_modifiers": [
            {"param": "script_adherence", "delta": 5, "condition": "Признал прошлый контакт и отказ"},
            {"param": "script_adherence", "delta": -8, "condition": "Звонит как впервые"},
            {"param": "empathy", "delta": 5, "condition": "Не злорадствует при ухудшении"},
            {"param": "empathy", "delta": -5, "condition": "«А я же говорил!»"},
            {"param": "stress_resistance", "delta": 5, "condition": "Спокойно принял повторный отказ"},
            {"param": "result", "delta": 8, "condition": "Назначил встречу"},
            {"param": "result", "delta": 4, "condition": "Callback с датой"},
        ],
        "awareness_prompt": (
            "Ты отказался {weeks_ago} недель назад. Причина: {refusal_reason}. "
            "Что изменилось: {changes}. Цена доверия выше."
        ),
        "stage_skip_reactions": {
            "no_acknowledgment": "Мы же уже это обсуждали!",
            "pressure": "Сколько можно? Не звоните!",
            "gloating": "Не надо меня поучать!",
        },
        "client_prompt_template": (
            "Ты отказался от услуги {weeks_ago} недель назад. "
            "Причина: {refusal_reason}. Что изменилось: {changes}. "
            "Первая реакция: «Опять вы? Я же сказал нет.»"
        ),
    },

    # ─── #8 WARM_DROPPED ─────────────────────────────────────────────────────
    {
        "code": "warm_dropped",
        "name": "Возврат «отвалившегося»",
        "description": "Клиент был на встрече, но не оплатил. Прошло 3-14 дней.",
        "group_name": "B_outbound_warm",
        "who_calls": "manager",
        "funnel_stage": "close",
        "prior_contact": True,
        "initial_emotion": "guarded",
        "initial_emotion_variants": {"guarded": 0.50, "cold": 0.25, "considering": 0.25},
        "client_awareness": "high",
        "client_motivation": "medium",
        "typical_duration_minutes": 7,
        "max_duration_minutes": 12,
        "typical_reply_count_min": 8,
        "typical_reply_count_max": 15,
        "target_outcome": "payment",
        "difficulty": 6,
        "archetype_weights": _w(
            avoidant=18, skeptic=14, anxious=12, pragmatic=10, passive=8,
            delegator=7, shopper=6, returner=5, blamer=4, manipulator=3,
            hostile=3, desperate=2.5, overwhelmed=2, rushed=1.5, ashamed=1,
            crying=0.8, know_it_all=0.5, paranoid=0.5, aggressive=0.5,
            lawyer_client=0.3, sarcastic=0.2, couple=0.2,
        ),
        "lead_sources": [
            "dropped_after_meeting", "dropped_after_proposal", "dropped_after_followup",
        ],
        "stages": [
            _stage(1, "Напоминание о встрече",
                   "Позитивная повестка, прогресс по делу",
                   ["Напомнить о встрече", "Рассказать о прогрессе",
                    "Спросить впечатление"],
                   ["Сразу «когда оплатите?»", "Не помнит деталей"],
                   ["guarded", "considering"], 1, 2),
            _stage(2, "Выяснение причины паузы",
                   "Мягко выявить реальную причину",
                   ["Понять причину", "Не давить"],
                   ["Давит на оплату", "Не спрашивает причину"],
                   ["considering", "guarded"], 2, 3),
            _stage(3, "Работа с причиной",
                   "Персональная стратегия для каждой причины",
                   ["Рассрочка/пауза/пакет", "Разбор мифов",
                    "Предложить прийти с родственником"],
                   ["Не предлагает альтернатив", "Давит"],
                   ["considering", "curious"], 2, 4),
            _stage(4, "Закрытие",
                   "Оплата или повторная встреча",
                   ["Конкретное действие", "Рассрочка с суммами"],
                   ["Нет конкретики"],
                   ["negotiating", "deal"], 1, 2),
        ],
        "recommended_chains": [
            {"code": "affordability_chain", "name": "Цепочка финансовой доступности"},
            {"code": "retrust_chain", "name": "Цепочка повторного доверия"},
            {"code": "comparison_chain", "name": "Цепочка сравнения"},
        ],
        "trap_pool_categories": ["price", "emotional", "manipulative"],
        "traps_count_min": 2,
        "traps_count_max": 3,
        "cascades_count": 1,
        "scoring_modifiers": [
            {"param": "script_adherence", "delta": 3, "condition": "Напомнил о встрече и юристе"},
            {"param": "empathy", "delta": 4, "condition": "Не давит при выяснении причины"},
            {"param": "objection_handling", "delta": 5, "condition": "Предложил рассрочку с суммами"},
            {"param": "result", "delta": 10, "condition": "Клиент согласился оплатить"},
            {"param": "result", "delta": 5, "condition": "Повторная встреча назначена"},
        ],
        "awareness_prompt": (
            "Ты был на консультации. Юрист разобрал ситуацию. "
            "Тебе предложили пакет за {price}₽. Не оплатил потому что: {drop_reason}."
        ),
        "stage_skip_reactions": {
            "payment_pressure": "Ну пока не получается...",
        },
        "client_prompt_template": (
            "Ты был на консультации {days_ago} дней назад. Юрист {lawyer_name} "
            "разобрал ситуацию. Пакет стоит {price}₽. Не оплатил: {drop_reason}."
        ),
    },

    # ─── #9 IN_WEBSITE ───────────────────────────────────────────────────────
    {
        "code": "in_website",
        "name": "Входящий с сайта",
        "description": "Клиент заполнил форму на сайте и ждёт звонка. Самый горячий лид.",
        "group_name": "C_inbound",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "curious",
        "initial_emotion_variants": {"curious": 0.55, "considering": 0.30, "guarded": 0.15},
        "client_awareness": "medium",
        "client_motivation": "high",
        "typical_duration_minutes": 7,
        "max_duration_minutes": 12,
        "typical_reply_count_min": 8,
        "typical_reply_count_max": 15,
        "target_outcome": "meeting",
        "difficulty": 2,
        "archetype_weights": _w(
            pragmatic=20, anxious=15, skeptic=12, desperate=10, shopper=9,
            know_it_all=7, passive=5, lawyer_client=5, overwhelmed=4,
            crying=3, delegator=2.5, blamer=2, ashamed=1.5, rushed=1.5,
            avoidant=1, manipulator=0.5, hostile=0.5, paranoid=0.2,
            couple=0.1, negotiator=0.1, sarcastic=0.1,
        ),
        "lead_sources": ["website_form", "website_callback", "website_chat", "website_calculator"],
        "stages": [
            _stage(1, "Приветствие", "Быстрое, профессиональное",
                   ["Быстро представиться", "Подтвердить заявку",
                    "Показать готовность помочь"],
                   ["Слишком длинное вступление", "Шаблонный скрипт"],
                   ["curious"], 1, 1),
            _stage(2, "Квалификация", "Детальная — клиент готов отвечать",
                   ["Сумма", "Кредиторы", "Имущество", "Стадия"],
                   ["Слишком много вопросов подряд"],
                   ["curious", "considering"], 2, 4),
            _stage(3, "Презентация", "Привязка к ситуации, не базовая теория",
                   ["Привязать к ЕГО ситуации", "Не повторять сайт"],
                   ["Повторяет что на сайте", "Общие фразы"],
                   ["considering"], 2, 3),
            _stage(4, "Возражения", "Минимальные — клиент мотивирован",
                   ["Конкретные ответы на вопросы"],
                   ["Некомпетентность"],
                   ["considering", "negotiating"], 1, 3),
            _stage(5, "Закрытие", "Клиент готов — нужна конкретика",
                   ["Конкретные слоты", "Бесплатно", "Что взять"],
                   ["Нет конкретики", "Потерял горячего клиента"],
                   ["negotiating", "deal"], 1, 2),
        ],
        "recommended_chains": [
            {"code": "value_chain", "name": "Цепочка ценности"},
            {"code": "property_chain", "name": "Цепочка имущества"},
            {"code": "expert_chain", "name": "Цепочка экспертных вопросов"},
        ],
        "trap_pool_categories": ["price", "expert"],
        "traps_count_min": 1,
        "traps_count_max": 2,
        "cascades_count": 0,
        "scoring_modifiers": [
            {"param": "script_adherence", "delta": 2, "condition": "Быстрое профессиональное приветствие"},
            {"param": "script_adherence", "delta": -3, "condition": "Затянул вступление"},
            {"param": "empathy", "delta": 3, "condition": "Внимательно выслушал"},
            {"param": "legal_accuracy", "delta": 3, "condition": "Точные юридические ответы"},
            {"param": "result", "delta": 5, "condition": "Встреча назначена"},
            {"param": "result", "delta": -5, "condition": "Потерял горячего клиента"},
        ],
        "awareness_prompt": (
            "Ты осознанно ищешь помощь. Читал сайт компании. "
            "У тебя конкретные вопросы: стоимость, сроки, имущество. "
            "Если менеджер говорит то что на сайте — «Это я читал, а конкретно?»"
        ),
        "stage_skip_reactions": {
            "template_speech": "Это я на сайте читала. А конкретно по моей ситуации?",
        },
        "client_prompt_template": (
            "Ты заполнил форму на сайте и ждёшь звонка. Ты мотивирован. "
            "Читал сайт — знаешь основы. Хочешь конкретику по своей ситуации."
        ),
    },

    # ─── #10 IN_HOTLINE ──────────────────────────────────────────────────────
    {
        "code": "in_hotline",
        "name": "Входящий с горячей линии",
        "description": "Клиент сам позвонил. Часто в панике или отчаянии.",
        "group_name": "C_inbound",
        "who_calls": "client",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "curious",
        "initial_emotion_variants": {"curious": 0.25, "hostile": 0.05, "considering": 0.20, "cold": 0.50},
        "client_awareness": "low",
        "client_motivation": "very_high",
        "typical_duration_minutes": 10,
        "max_duration_minutes": 18,
        "typical_reply_count_min": 10,
        "typical_reply_count_max": 20,
        "target_outcome": "meeting",
        "difficulty": 3,
        "archetype_weights": _w(
            desperate=22, anxious=18, crying=10, pragmatic=9, shopper=7,
            ashamed=6, blamer=5, skeptic=4, know_it_all=4, passive=3,
            lawyer_client=3, delegator=2.5, overwhelmed=2, rushed=1.5,
            manipulator=1, couple=0.7, avoidant=0.5, sarcastic=0.5,
            paranoid=0.2, negotiator=0.1,
        ),
        "lead_sources": ["hotline_call", "8800_number", "callback_widget"],
        "stages": [
            _stage(1, "Приём звонка", "Стандартное приветствие + открытый вопрос",
                   ["Тёплое приветствие", "«Чем могу помочь?»"],
                   ["Холодное формальное приветствие", "Сразу к вопросам"],
                   ["curious", "cold"], 1, 1),
            _stage(2, "Выслушивание", "КЛЮЧЕВОЙ ЭТАП — дать клиенту выговориться",
                   ["Дать выговориться", "Активное слушание",
                    "Собрать информацию", "Установить доверие"],
                   ["Перебивает", "Нет эмпатии", "Торопит",
                    "Начинает давать советы не выслушав"],
                   ["curious", "considering", "cold"], 2, 5),
            _stage(3, "Квалификация", "Уточняющие вопросы после выслушивания",
                   ["Уточнить сумму", "Уточнить кредиторов", "Имущество"],
                   ["Допрос-стиль"],
                   ["considering"], 2, 3),
            _stage(4, "Решение", "Конкретный ответ — что делать",
                   ["Конкретный план", "Снять главный страх",
                    "Показать выход"],
                   ["Невнятность", "Неуверенность"],
                   ["considering", "negotiating"], 2, 3),
            _stage(5, "Назначение встречи", "Клиент мотивирован — конкретное время",
                   ["Конкретные слоты", "Что взять"],
                   ["Не предложил конкретику"],
                   ["negotiating", "deal"], 1, 2),
        ],
        "recommended_chains": [
            {"code": "no_way_out_chain", "name": "Цепочка безвыходности"},
            {"code": "fear_chain", "name": "Цепочка страхов"},
            {"code": "comparison_chain", "name": "Цепочка сравнения"},
        ],
        "trap_pool_categories": ["emotional"],
        "traps_count_min": 1,
        "traps_count_max": 2,
        "cascades_count": 0,
        "scoring_modifiers": [
            {"param": "empathy", "delta": 8, "condition": "Дал выговориться, не перебивал"},
            {"param": "empathy", "delta": -8, "condition": "Перебил в панике/слезах"},
            {"param": "empathy", "delta": 5, "condition": "Адекватно среагировал на суицидальные намёки"},
            {"param": "legal_accuracy", "delta": 3, "condition": "Точные ответы о процедуре"},
            {"param": "result", "delta": 5, "condition": "Встреча назначена"},
            {"param": "result", "delta": -8, "condition": "Потерял горячего клиента"},
        ],
        "awareness_prompt": (
            "Ты мотивирован и ищешь помощь. Эмоциональное состояние: {emotional_state}. "
            "Если менеджер слушает — раскрывайся. Если перебивает — замкнись."
        ),
        "stage_skip_reactions": {
            "interruption": "Вы даже не даёте мне рассказать!",
            "cold_tone": "Может я в другую компанию позвоню...",
        },
        "client_prompt_template": (
            "Ты сам позвонил. Твоё состояние: {emotional_state}. "
            "Твоя история: {client_story}. Задаёшь конкретные вопросы."
        ),
    },

    # ─── #11 IN_SOCIAL ───────────────────────────────────────────────────────
    {
        "code": "in_social",
        "name": "Входящий из соцсетей",
        "description": "Клиент написал в VK/Telegram/WhatsApp. Менеджер перезванивает.",
        "group_name": "C_inbound",
        "who_calls": "manager",
        "funnel_stage": "lead",
        "prior_contact": True,
        "initial_emotion": "guarded",
        "initial_emotion_variants": {"guarded": 0.45, "curious": 0.35, "cold": 0.20},
        "client_awareness": "low",
        "client_motivation": "medium",
        "typical_duration_minutes": 6,
        "max_duration_minutes": 10,
        "typical_reply_count_min": 7,
        "typical_reply_count_max": 13,
        "target_outcome": "meeting",
        "difficulty": 4,
        "archetype_weights": _w(
            skeptic=15, avoidant=13, anxious=12, passive=10, pragmatic=9,
            shopper=8, desperate=6, know_it_all=5, delegator=4,
            overwhelmed=3.5, blamer=3, ashamed=2.5, rushed=2, manipulator=2,
            crying=1.5, paranoid=1, lawyer_client=0.8, hostile=0.5,
            couple=0.5, sarcastic=0.2,
        ),
        "lead_sources": ["vk_message", "telegram_message", "whatsapp_message", "ok_message"],
        "stages": [
            _stage(1, "Приветствие со ссылкой на переписку",
                   "Упоминание мессенджера и сообщения клиента",
                   ["Представиться", "Сослаться на переписку",
                    "Объяснить почему звонит", "Спросить удобно ли"],
                   ["Не упомянул переписку", "Агрессивная продажа",
                    "Позвонил без предупреждения"],
                   ["guarded", "curious"], 1, 2),
            _stage(2, "Квалификация", "Стандартная квалификация",
                   ["Сумма", "Кредиторы", "Стадия"],
                   ["Допрос"],
                   ["curious", "considering"], 2, 3),
            _stage(3, "Презентация", "Привязка к ситуации",
                   ["Привязать", "Закон"],
                   ["Шаблон"],
                   ["considering"], 2, 3),
            _stage(4, "Возражения", "В т.ч. предпочтение текста",
                   ["Мягкий подход", "Уважать формат"],
                   ["Давить на тех кто предпочитает текст"],
                   ["considering", "guarded"], 2, 3),
            _stage(5, "Закрытие", "Встреча или callback",
                   ["Конкретные слоты", "Скинуть инфо в мессенджер"],
                   ["Нет конкретики"],
                   ["negotiating", "deal", "callback"], 1, 2),
        ],
        "recommended_chains": [
            {"code": "comfort_chain", "name": "Цепочка комфорта"},
            {"code": "minimal_step_chain", "name": "Цепочка минимального шага"},
            {"code": "proof_chain", "name": "Цепочка доказательств"},
        ],
        "trap_pool_categories": ["emotional", "manipulative"],
        "traps_count_min": 1,
        "traps_count_max": 2,
        "cascades_count": 0,
        "scoring_modifiers": [
            {"param": "script_adherence", "delta": 3, "condition": "Сослался на переписку"},
            {"param": "empathy", "delta": 3, "condition": "Мягкий подход"},
            {"param": "empathy", "delta": -3, "condition": "Давит на предпочитающего текст"},
            {"param": "result", "delta": 5, "condition": "Встреча"},
        ],
        "awareness_prompt": (
            "Ты написал в {social_channel}. Предпочитаешь текст. "
            "Звонок — не очень комфортно. Если менеджер мягкий — расслабься."
        ),
        "stage_skip_reactions": {
            "no_chat_reference": "А вы кто? Откуда мой номер?",
            "text_preference": "Мне неудобно сейчас, давайте в переписке",
        },
        "client_prompt_template": (
            "Ты написал в {social_channel}: «{original_message}». "
            "Тебе перезвонили. Предпочитаешь текстовое общение."
        ),
    },

    # ─── #12 UPSELL ──────────────────────────────────────────────────────────
    {
        "code": "upsell",
        "name": "Допродажа расширенного пакета",
        "description": "Клиент оплатил базовый пакет. Предлагаем расширенный.",
        "group_name": "D_special",
        "who_calls": "manager",
        "funnel_stage": "upsell",
        "prior_contact": True,
        "initial_emotion": "considering",
        "initial_emotion_variants": {"considering": 0.50, "guarded": 0.30, "curious": 0.20},
        "client_awareness": "high",
        "client_motivation": "neutral",
        "typical_duration_minutes": 7,
        "max_duration_minutes": 12,
        "typical_reply_count_min": 8,
        "typical_reply_count_max": 14,
        "target_outcome": "upsell",
        "difficulty": 4,
        "archetype_weights": _w(
            pragmatic=22, skeptic=16, anxious=14, overwhelmed=8, passive=7,
            manipulator=6, blamer=5, know_it_all=5, delegator=4, shopper=3,
            rushed=3, avoidant=2.5, lawyer_client=2, ashamed=1, hostile=0.5,
            desperate=0.5, crying=0.3, paranoid=0.2,
        ),
        "lead_sources": ["existing_client_basic", "existing_client_standard"],
        "stages": [
            _stage(1, "Обновление статуса",
                   "Позитивная повестка — прогресс по делу",
                   ["Рассказать о прогрессе", "Создать ощущение движения"],
                   ["Сразу к допродаже"],
                   ["considering"], 1, 2),
            _stage(2, "Выявление потребности",
                   "Поиск болевой точки для upsell",
                   ["Спросить о текущих проблемах", "Найти точку входа"],
                   ["Не спрашивает, сразу предлагает"],
                   ["considering", "curious"], 2, 3),
            _stage(3, "Презентация пакета",
                   "Привязка к потребности, не просто «больше услуг»",
                   ["Конкретная выгода", "Сравнение пакетов"],
                   ["Просто «дороже = лучше»"],
                   ["considering", "negotiating"], 2, 3),
            _stage(4, "Возражения",
                   "Ценовые возражения, недоверие к допродаже",
                   ["Показать ROI", "Предложить рассрочку"],
                   ["Давление"],
                   ["considering", "guarded"], 2, 3),
            _stage(5, "Закрытие", "Переход на расширенный пакет",
                   ["Конкретное предложение", "Рассрочка"],
                   ["Нет конкретики"],
                   ["negotiating", "deal"], 1, 2),
        ],
        "recommended_chains": [
            {"code": "value_chain", "name": "Цепочка ценности"},
            {"code": "risk_chain", "name": "Цепочка риска"},
            {"code": "installment_chain", "name": "Цепочка рассрочки"},
        ],
        "trap_pool_categories": ["price", "manipulative"],
        "traps_count_min": 1,
        "traps_count_max": 2,
        "cascades_count": 0,
        "scoring_modifiers": [
            {"param": "empathy", "delta": 3, "condition": "Начал с обновления статуса"},
            {"param": "objection_handling", "delta": 5, "condition": "Показал конкретную ценность"},
            {"param": "result", "delta": 10, "condition": "Перешёл на расширенный пакет"},
            {"param": "result", "delta": -3, "condition": "Обиделся на допродажу"},
        ],
        "awareness_prompt": (
            "Ты уже клиент. Оплатил базовый пакет. Доверяешь компании, "
            "но чувствителен к доп. тратам. Хочешь видеть конкретную ценность."
        ),
        "stage_skip_reactions": {
            "direct_upsell": "Вы просто хотите ещё денег содрать?",
        },
        "client_prompt_template": (
            "Ты клиент с базовым пакетом ({current_package}₽). "
            "Доверяешь компании, но доп. траты нужно обосновать."
        ),
    },

    # ─── #13 RESCUE ──────────────────────────────────────────────────────────
    {
        "code": "rescue",
        "name": "Спасение (отказ от услуги)",
        "description": "Клиент оплатил, но хочет отказаться и вернуть деньги.",
        "group_name": "D_special",
        "who_calls": "both",
        "funnel_stage": "retention",
        "prior_contact": True,
        "initial_emotion": "hostile",
        "initial_emotion_variants": {"hostile": 0.50, "guarded": 0.30, "cold": 0.20},
        "client_awareness": "high",
        "client_motivation": "negative",
        "typical_duration_minutes": 10,
        "max_duration_minutes": 18,
        "typical_reply_count_min": 10,
        "typical_reply_count_max": 20,
        "target_outcome": "retention",
        "difficulty": 9,
        "archetype_weights": _w(
            hostile=20, blamer=18, anxious=14, manipulator=10, skeptic=8,
            overwhelmed=6, delegator=5, pragmatic=5, ashamed=4, aggressive=3,
            crying=2.5, desperate=2, shopper=1, paranoid=0.5,
            lawyer_client=0.5, avoidant=0.3, sarcastic=0.2,
        ),
        "lead_sources": ["cancel_request", "complaint_call", "payment_stop"],
        "stages": [
            _stage(1, "Приём жалобы",
                   "Выслушать без оправданий",
                   ["Выслушать полностью", "Не спорить", "Проявить понимание"],
                   ["«Нет-нет, вы не можете!»", "Оправдания", "Давление", "Паника"],
                   ["hostile", "guarded"], 1, 2),
            _stage(2, "Выяснение причины",
                   "Понять РЕАЛЬНУЮ причину (не всегда первая озвученная)",
                   ["Понять реальную причину", "Уточняющие вопросы",
                    "Отделить эмоции от фактов"],
                   ["Спорит", "Не спрашивает причину"],
                   ["hostile", "guarded", "considering"], 2, 4),
            _stage(3, "Работа с причиной",
                   "Персональная стратегия для каждой причины",
                   ["Адресная работа с причиной", "Конкретные шаги"],
                   ["Шаблонный ответ", "Обесценивание причины"],
                   ["considering", "guarded"], 2, 3),
            _stage(4, "Предложение альтернативы",
                   "Не «продолжить как есть» а что-то НОВОЕ",
                   ["Другой пакет/пауза/доп.сервис", "Ощущение что услышали"],
                   ["Ничего нового", "Формальный ответ"],
                   ["considering", "negotiating"], 1, 2),
            _stage(5, "Результат",
                   "Клиент остаётся или передаём юристу",
                   ["Зафиксировать решение", "Если уходит — передать юристу"],
                   ["Обрабатывает возврат сам"],
                   ["deal", "callback", "hostile"], 1, 2),
        ],
        "recommended_chains": [
            {"code": "rescue_chain", "name": "Цепочка спасения"},
            {"code": "comparison_chain", "name": "Цепочка сравнения"},
            {"code": "empathy_chain", "name": "Цепочка эмпатии"},
        ],
        "trap_pool_categories": ["provocative", "emotional", "legal", "manipulative"],
        "traps_count_min": 3,
        "traps_count_max": 4,
        "cascades_count": 2,
        "scoring_modifiers": [
            {"param": "empathy", "delta": 8, "condition": "Выслушал без оправданий"},
            {"param": "empathy", "delta": -8, "condition": "Начал спорить/оправдываться"},
            {"param": "stress_resistance", "delta": 5, "condition": "Спокоен при угрозах"},
            {"param": "objection_handling", "delta": 5, "condition": "Предложил конкретную альтернативу"},
            {"param": "result", "delta": 10, "condition": "Клиент остался"},
            {"param": "result", "delta": 3, "condition": "Пауза/пересмотр"},
            {"param": "result", "delta": -5, "condition": "Ушёл с негативом"},
        ],
        "awareness_prompt": (
            "Ты оплатил услугу и хочешь отказаться. Причина: {cancel_reason}. "
            "Ты решителен, но не безапелляционен. Если предложат решение — рассмотришь."
        ),
        "stage_skip_reactions": {
            "argument": "Вы не слушаете! Мне не нужны ваши оправдания!",
            "no_alternative": "Значит вам плевать на клиентов?",
        },
        "client_prompt_template": (
            "Ты оплатил услугу, но хочешь отказаться. Причина: {cancel_reason}. "
            "Если менеджер выслушает и предложит решение — рассмотри. "
            "Если спорит — ужесточи позицию."
        ),
    },

    # ─── #14 COUPLE_CALL ─────────────────────────────────────────────────────
    {
        "code": "couple_call",
        "name": "Семейный звонок",
        "description": "На линии двое — основной клиент и супруг/родственник.",
        "group_name": "D_special",
        "who_calls": "both",
        "funnel_stage": "qualification",
        "prior_contact": True,
        "initial_emotion": "guarded",
        "initial_emotion_variants": {"guarded": 0.40, "curious": 0.30, "hostile": 0.15, "considering": 0.15},
        "client_awareness": "mixed",
        "client_motivation": "mixed",
        "typical_duration_minutes": 12,
        "max_duration_minutes": 18,
        "typical_reply_count_min": 12,
        "typical_reply_count_max": 20,
        "target_outcome": "meeting",
        "difficulty": 7,
        "archetype_weights": _w(
            couple=30, anxious=15, delegator=12, passive=8, skeptic=7,
            pragmatic=6, desperate=5, blamer=4, avoidant=3, ashamed=3,
            overwhelmed=2, crying=2, hostile=1, manipulator=1, rushed=0.5,
            know_it_all=0.3, paranoid=0.2,
        ),
        "lead_sources": ["couple_referral", "spouse_initiated", "family_meeting"],
        "stages": [
            _stage(1, "Приветствие обоих",
                   "Обращение к обоим по имени",
                   ["Приветствовать обоих", "Установить кто основной",
                    "Показать что рады обоим"],
                   ["Игнорирует второго", "Встаёт на чью-то сторону"],
                   ["guarded", "curious"], 1, 2),
            _stage(2, "Квалификация (обоих)",
                   "Вопросы к обоим, вовлечение второго",
                   ["Обращаться к обоим", "Спрашивать мнение второго"],
                   ["Игнорирует мнение второго"],
                   ["curious", "considering"], 2, 4),
            _stage(3, "Презентация (для обоих)",
                   "Адресация страхов второго, выгода для семьи",
                   ["Страхи ВТОРОГО", "Выгода для семьи"],
                   ["Говорит только с одним"],
                   ["considering"], 2, 3),
            _stage(4, "Работа с разногласиями",
                   "Модерация если мнения разные",
                   ["Модерировать не принимая сторону", "Найти общее"],
                   ["Встал на сторону одного", "Игнорирует спор"],
                   ["considering", "guarded"], 3, 5),
            _stage(5, "Закрытие",
                   "Согласие ОБОИХ",
                   ["Прийти вместе", "Конкретные слоты"],
                   ["Только один согласен"],
                   ["negotiating", "deal"], 1, 2),
        ],
        "recommended_chains": [
            {"code": "family_dispute_chain", "name": "Цепочка семейного спора"},
            {"code": "family_protection_chain", "name": "Цепочка защиты семьи"},
            {"code": "second_opinion_chain", "name": "Цепочка второго мнения"},
        ],
        "trap_pool_categories": ["emotional", "provocative"],
        "traps_count_min": 2,
        "traps_count_max": 3,
        "cascades_count": 1,
        "scoring_modifiers": [
            {"param": "empathy", "delta": 5, "condition": "Обращался к обоим"},
            {"param": "empathy", "delta": -5, "condition": "Встал на сторону одного"},
            {"param": "empathy", "delta": 3, "condition": "Корректно модерировал спор"},
            {"param": "result", "delta": 8, "condition": "Оба согласились на встречу"},
            {"param": "result", "delta": 3, "condition": "Один согласился + второй не против"},
        ],
        "awareness_prompt": (
            "Ты и {partner_name} на линии вместе. У вас разные мнения. "
            "Один — за, другой — скептичен/против."
        ),
        "stage_skip_reactions": {
            "ignore_partner": "А вы у меня/него/неё не спросили!",
            "take_side": "Вы вообще на чьей стороне?",
        },
        "client_prompt_template": (
            "Ты и {partner_name} на линии. Ты — {role_in_couple}. "
            "Твоя позиция: {primary_position}. "
            "Позиция {partner_name}: {partner_position}."
        ),
    },

    # ─── #15 VIP_DEBTOR ──────────────────────────────────────────────────────
    {
        "code": "vip_debtor",
        "name": "VIP-должник (крупный долг)",
        "description": "Долг >5М. Предприниматель, субсидиарная ответственность.",
        "group_name": "D_special",
        "who_calls": "both",
        "funnel_stage": "lead",
        "prior_contact": False,
        "initial_emotion": "testing",
        "initial_emotion_variants": {"testing": 0.40, "guarded": 0.30, "considering": 0.20, "cold": 0.10},
        "client_awareness": "high",
        "client_motivation": "high",
        "typical_duration_minutes": 15,
        "max_duration_minutes": 25,
        "typical_reply_count_min": 15,
        "typical_reply_count_max": 25,
        "target_outcome": "meeting",
        "difficulty": 8,
        "archetype_weights": _w(
            know_it_all=15, pragmatic=12, overwhelmed=10, skeptic=8,
            lawyer_client=9, anxious=6, manipulator=5, hostile=4,
            shopper=3, blamer=2.5, desperate=2, rushed=2, avoidant=1,
            paranoid=1, aggressive=0.5, passive=0.5, ashamed=0.3,
            delegator=0.2, negotiator=18,
        ),
        "lead_sources": ["vip_referral", "lawyer_referral", "website_vip", "business_network"],
        "stages": [
            _stage(1, "Приветствие (VIP-формат)",
                   "Уверенное, профессиональное, деловое",
                   ["Представиться уверенно", "Показать работу с крупными делами",
                    "Деловой тон"],
                   ["Панибратство", "Шаблонный скрипт"],
                   ["testing", "guarded"], 1, 2),
            _stage(2, "Расширенная квалификация",
                   "Глубокая: сумма, структура, субсидиарка, имущество, сделки",
                   ["Общая сумма", "Структура (ИП/ООО/поручительства)",
                    "Субсидиарная ответственность", "Имущество", "Сделки за 3 года"],
                   ["Не спросил про субсидиарку", "Не спросил про сделки",
                    "Показал некомпетентность", "Пытался блефовать"],
                   ["testing", "considering"], 3, 5),
            _stage(3, "Демонстрация экспертизы",
                   "Опыт компании, сложные кейсы, команда",
                   ["Упомянуть опыт", "Сложные кейсы", "Старший юрист"],
                   ["Некомпетентный ответ", "Пустые обещания"],
                   ["considering", "curious"], 2, 3),
            _stage(4, "Экспертные возражения",
                   "Сложные юридические вопросы, тестирование менеджера",
                   ["Уверенные ответы", "Честно: 'это вопрос для юриста'"],
                   ["Блеф", "Неверная информация", "Потеря уверенности"],
                   ["testing", "considering", "guarded"], 3, 5),
            _stage(5, "Встреча со старшим юристом",
                   "Назначение на конкретного опытного юриста",
                   ["Назвать конкретного юриста", "Его опыт",
                    "Конкретные слоты"],
                   ["Не назвал юриста", "Обычная консультация"],
                   ["negotiating", "deal"], 1, 2),
        ],
        "recommended_chains": [
            {"code": "exam_chain", "name": "Цепочка экзамена"},
            {"code": "expertise_chain", "name": "Цепочка экспертности"},
            {"code": "vip_service_chain", "name": "Цепочка VIP-сервиса"},
        ],
        "trap_pool_categories": ["expert", "legal", "price", "professional"],
        "traps_count_min": 3,
        "traps_count_max": 5,
        "cascades_count": 2,
        "scoring_modifiers": [
            {"param": "legal_accuracy", "delta": 5, "condition": "Корректный ответ на экспертный вопрос"},
            {"param": "legal_accuracy", "delta": -10, "condition": "Неверная юридическая информация"},
            {"param": "legal_accuracy", "delta": 3, "condition": "Честно сказал 'это вопрос для юриста'"},
            {"param": "script_adherence", "delta": 3, "condition": "Расширенная квалификация"},
            {"param": "empathy", "delta": 3, "condition": "Уважительный деловой тон"},
            {"param": "result", "delta": 8, "condition": "Встреча со старшим юристом"},
            {"param": "result", "delta": -10, "condition": "Потерял VIP-клиента"},
        ],
        "awareness_prompt": (
            "Ты — предприниматель/бывший. Долг >5М₽. Хорошо разбираешься. "
            "Тестируешь менеджера. Не терпишь шаблонов и некомпетентности. "
            "Если менеджер честен — уважаешь. Если блефует — уходишь."
        ),
        "stage_skip_reactions": {
            "incompetence": "Вы вообще разбираетесь в этом?",
            "template_answer": "Мне не нужны общие фразы. Конкретику давайте.",
            "bluff_detected": "Это неправда. Я проверю у своего юриста.",
        },
        "client_prompt_template": (
            "Ты — предприниматель. Долг: {total_debt}₽. "
            "Структура: {debt_structure}. Имущество: {property_list}. "
            "Сделки за 3 года: {recent_transactions}. "
            "Задаёшь 2-3 экспертных вопроса."
        ),
    },
]


# ═════════════════════════════════════════════════════════════════════════════
# SEEDER
# ═════════════════════════════════════════════════════════════════════════════

async def seed() -> None:
    async with async_session() as session:
        for data in SCENARIOS:
            code = data["code"]
            existing = await session.execute(
                select(ScenarioTemplate).where(ScenarioTemplate.code == code)
            )
            if existing.scalar_one_or_none():
                logger.info("Scenario %s already exists, skipping", code)
                continue

            template = ScenarioTemplate(**data)
            session.add(template)
            logger.info("Created scenario template: %s — %s", code, data["name"])

        await session.commit()
        logger.info("Seeded %d scenario templates", len(SCENARIOS))


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
