"""Seed roleplay v2 data: professions, emotion profiles, traps, objection chains."""

import asyncio

from app.config import settings  # noqa: F401
from app.database import async_session, engine, Base
from app.models import *  # noqa: F401,F403
from app.models.roleplay import (
    ArchetypeCode,
    EmotionProfile,
    LeadSource,
    ObjectionChain,
    ProfessionCategory,
    ProfessionProfile,
    Trap,
)


async def seed_roleplay():
    async with async_session() as db:
        await _seed_professions(db)
        await _seed_emotion_profiles(db)
        await _seed_traps(db)
        await _seed_objection_chains(db)
        await db.commit()

    print("\n✓ Roleplay v2 seed data created!")


# ── Professions (30+) ─────────────────────────────────────────────

async def _seed_professions(db):
    data = [
        # BUDGET
        ("teacher", "Учитель", ProfessionCategory.budget, 300000, 800000, 2, "standard",
         ["коллеги узнают", "директор уволит", "позор в школе"],
         {"style": "культурная речь", "markers": ["извините", "пожалуйста", "понимаете"]}),
        ("doctor", "Врач", ProfessionCategory.budget, 500000, 1500000, 3, "professional",
         ["потеря лицензии", "огласка среди пациентов"],
         {"style": "медицинская терминология", "markers": ["диагноз", "симптомы", "процедура"]}),
        ("nurse", "Медсестра", ProfessionCategory.budget, 200000, 600000, 1, "simple",
         ["заберут последнее", "дети без еды"],
         {"style": "простая эмоциональная речь", "markers": ["боже мой", "как же так", "не могу"]}),
        ("kindergarten", "Воспитатель", ProfessionCategory.budget, 200000, 500000, 1, "simple",
         ["позор перед родителями детей"],
         {"style": "тихая неуверенная", "markers": ["наверное", "может быть", "я не знаю"]}),

        # GOVERNMENT
        ("municipal_official", "Муниципальный чиновник", ProfessionCategory.government, 500000, 2000000, 5, "professional",
         ["потеря должности", "проверка доходов", "публичность"],
         {"style": "канцелярит", "markers": ["в рамках", "согласно", "надлежащим образом"]}),
        ("police", "Полицейский", ProfessionCategory.government, 700000, 2000000, 4, "standard",
         ["увольнение из органов", "потеря пенсии по выслуге"],
         {"style": "командный", "markers": ["объясните", "предъявите", "на каком основании"]}),
        ("bailiff", "Судебный пристав", ProfessionCategory.government, 400000, 1000000, 7, "legal",
         ["коллеги узнают", "профессиональный стыд"],
         {"style": "знает терминологию", "markers": ["исполнительное производство", "арест", "взыскание"]}),

        # MILITARY
        ("contractor", "Контрактник", ProfessionCategory.military, 1000000, 4000000, 2, "simple",
         ["потеря жилья по военной ипотеке", "увольнение из армии"],
         {"style": "краткий дисциплинированный", "markers": ["так точно", "понял", "короче"]}),
        ("officer_retired", "Офицер запаса", ProfessionCategory.military, 800000, 3000000, 3, "standard",
         ["потеря военной пенсии", "стыд — офицер и банкрот"],
         {"style": "командный но растерянный", "markers": ["в моё время", "я привык к порядку"]}),
        ("svo_family", "Семья участника СВО", ProfessionCategory.military, 300000, 1500000, 1, "simple",
         ["муж на фронте", "долги копятся", "паника"],
         {"style": "эмоциональная", "markers": ["муж там", "не знаю что делать", "помогите"]}),

        # PENSIONERS
        ("pensioner", "Пенсионер", ProfessionCategory.pensioner, 200000, 800000, 1, "simple",
         ["заберут квартиру", "пенсию заберут", "позор на старости"],
         {"style": "медленная", "markers": ["деточка", "в наше время", "я не понимаю"]}),
        ("disabled", "Инвалид", ProfessionCategory.pensioner, 150000, 500000, 1, "simple",
         ["потеря пособия", "бюрократия"],
         {"style": "уставший", "markers": ["мне тяжело", "здоровье не позволяет"]}),
        ("military_pensioner", "Военный пенсионер", ProfessionCategory.pensioner, 500000, 2000000, 3, "standard",
         ["потеря военной пенсии", "стыд перед сослуживцами"],
         {"style": "чёткий требовательный", "markers": ["я полковник в отставке", "доложите"]}),

        # ENTREPRENEURS
        ("ex_ip", "Бывший ИП", ProfessionCategory.entrepreneur, 1000000, 10000000, 4, "professional",
         ["субсидиарная ответственность", "уголовка за налоги"],
         {"style": "деловой уставший", "markers": ["бизнес", "налоговая", "субсидиарка"]}),
        ("self_employed", "Самозанятый", ProfessionCategory.entrepreneur, 200000, 800000, 3, "standard",
         ["потеря клиентов", "невозможность работать"],
         {"style": "предпринимательский", "markers": ["мои клиенты", "доход нестабильный"]}),
        ("farmer", "Фермер", ProfessionCategory.entrepreneur, 500000, 5000000, 2, "simple",
         ["потеря земли", "потеря техники"],
         {"style": "простой конкретный", "markers": ["земля", "урожай", "техника"]}),

        # WORKERS
        ("driver", "Водитель", ProfessionCategory.worker, 300000, 1000000, 1, "simple",
         ["заберут машину", "как кормить семью"],
         {"style": "простой прямой", "markers": ["рейс", "зарплата серая", "неофициально"]}),
        ("builder", "Строитель", ProfessionCategory.worker, 300000, 1500000, 1, "simple",
         ["сезонная работа", "зимой работы нет"],
         {"style": "грубоватый конкретный", "markers": ["объект", "бригада", "сезон"]}),
        ("courier", "Курьер", ProfessionCategory.worker, 100000, 500000, 1, "simple",
         ["всю жизнь буду платить", "страх перед системой"],
         {"style": "быстрый нервный", "markers": ["заказ", "приложение", "штраф"]}),

        # IT / OFFICE
        ("programmer", "Программист", ProfessionCategory.it_office, 500000, 3000000, 6, "professional",
         ["запрет на руководящие", "пятно в резюме"],
         {"style": "аналитический", "markers": ["алгоритм", "процент", "статистика"]}),
        ("accountant", "Бухгалтер", ProfessionCategory.it_office, 400000, 1500000, 7, "professional",
         ["профессиональный стыд", "коллеги узнают"],
         {"style": "точная с цифрами", "markers": ["баланс", "дебет", "50% удержание"]}),
        ("sales_manager", "Менеджер по продажам", ProfessionCategory.it_office, 300000, 1000000, 3, "standard",
         ["потеря работы", "я же сам продажник"],
         {"style": "коммуникабельный", "markers": ["клиент", "сделка", "план продаж"]}),

        # TRADE / SERVICE
        ("seller", "Продавец", ProfessionCategory.trade_service, 200000, 700000, 1, "simple",
         ["нечем платить юристу", "стыд"],
         {"style": "простая стесняется", "markers": ["зарплата маленькая", "смена"]}),
        ("hairdresser", "Парикмахер/мастер маникюра", ProfessionCategory.trade_service, 200000, 800000, 2, "simple",
         ["клиенты узнают", "придётся закрыться"],
         {"style": "общительная", "markers": ["мои клиентки", "салон", "аренда"]}),
        ("realtor", "Риелтор", ProfessionCategory.trade_service, 500000, 3000000, 5, "professional",
         ["репутация", "кто купит квартиру у банкрота"],
         {"style": "деловой торгуется", "markers": ["сделка", "объект", "комиссия"]}),

        # HOMEMAKERS
        ("maternity_leave", "Мать в декрете", ProfessionCategory.homemaker, 200000, 600000, 1, "simple",
         ["муж узнает", "мат.капитал заберут"],
         {"style": "торопится шёпотом", "markers": ["ребёнок рядом", "муж не знает", "тихо"]}),
        ("multi_child", "Многодетная мать", ProfessionCategory.homemaker, 300000, 1000000, 1, "simple",
         ["дети пострадают", "органы опеки"],
         {"style": "уставшая практичная", "markers": ["трое детей", "не хватает", "каждый рубль"]}),

        # SPECIAL
        ("lawyer_other", "Юрист (другой специализации)", ProfessionCategory.special, 500000, 2000000, 9, "legal",
         ["профессиональный позор", "я же юрист"],
         {"style": "юридическая терминология", "markers": ["статья", "норма", "судебная практика"]}),
        ("ex_convict", "Бывший осуждённый", ProfessionCategory.special, 200000, 800000, 2, "simple",
         ["опять посадят", "полное недоверие"],
         {"style": "жаргон агрессивная защита", "markers": ["менты", "подстава", "зона"]}),
        ("student", "Студент", ProfessionCategory.special, 100000, 400000, 1, "simple",
         ["вся жизнь впереди а уже банкрот", "стыд перед родителями"],
         {"style": "сленг неуверенность", "markers": ["кредитка", "рассрочка", "родители узнают"]}),
        ("dnr_lnr", "Переселенец ДНР/ЛНР", ProfessionCategory.special, 200000, 1000000, 1, "simple",
         ["документов нет", "как докажу", "депортация"],
         {"style": "диалект недоверие", "markers": ["документы потеряли", "оттуда", "мы приехали"]}),
        ("ex_businessman", "Бывший предприниматель", ProfessionCategory.special, 2000000, 20000000, 6, "professional",
         ["субсидиарка", "потеряю всё", "уголовка"],
         {"style": "деловой разочарованный", "markers": ["бизнес закрылся", "партнёр кинул", "налоговая"]}),
    ]

    professions = []
    for code, name, category, debt_min, debt_max, lit, vocab, fears, speech in data:
        professions.append(ProfessionProfile(
            code=code,
            name=name,
            category=category,
            typical_debt_min=debt_min,
            typical_debt_max=debt_max,
            legal_literacy=lit,
            vocabulary_level=vocab,
            specific_fears=fears,
            specific_objections=[],
            speech_patterns=speech,
        ))
    db.add_all(professions)
    await db.flush()
    print(f"  Professions: {len(professions)}")


# ── Emotion Profiles (7 archetypes) ──────────────────────────────

async def _seed_emotion_profiles(db):
    profiles = [
        EmotionProfile(
            archetype_code="skeptic",
            transition_matrix={
                "cold":      {"empathy": 0, "facts": 1, "pressure": 0, "bad_response": -1, "acknowledge": 0, "name_use": 0},
                "guarded":  {"empathy": 0, "facts": 1, "pressure": -1, "bad_response": -2, "acknowledge": 1, "name_use": 0},
                "curious":   {"empathy": 1, "facts": 1, "pressure": -1, "bad_response": -1, "acknowledge": 1, "name_use": 1},
                "considering":      {"empathy": 1, "facts": 0, "pressure": 0, "bad_response": -1, "acknowledge": 0, "name_use": 1},
                "deal":      {"empathy": 0, "facts": 0, "pressure": 0, "bad_response": -1, "acknowledge": 0, "name_use": 0},
            },
            rollback_triggers=["inaccuracy", "no_proof"],
            rollback_severity=2,
            breaking_point={"trigger": "kad_arbitr_reference", "jump": 2},
            initial_state="cold",
            max_state_first_call="deal",
            fake_transitions=False,
        ),
        EmotionProfile(
            archetype_code="anxious",
            transition_matrix={
                "cold":      {"empathy": 1, "facts": 0, "pressure": -2, "bad_response": -1, "acknowledge": 1, "name_use": 1},
                "guarded":  {"empathy": 1, "facts": 1, "pressure": -2, "bad_response": -1, "acknowledge": 1, "name_use": 1},
                "curious":   {"empathy": 1, "facts": 1, "pressure": -2, "bad_response": -2, "acknowledge": 1, "name_use": 0},
                "considering":      {"empathy": 0, "facts": 0, "pressure": -1, "bad_response": -1, "acknowledge": 0, "name_use": 0},
                "deal":      {"empathy": 0, "facts": 0, "pressure": -1, "bad_response": 0, "acknowledge": 0, "name_use": 0},
            },
            rollback_triggers=["court_mention", "bailiff_mention", "publicity"],
            rollback_severity=2,
            breaking_point={"trigger": "similar_success_story", "jump": 2},
            initial_state="cold",
            max_state_first_call="considering",
            fake_transitions=False,
        ),
        EmotionProfile(
            archetype_code="aggressive",
            transition_matrix={
                "cold":      {"empathy": 0, "facts": 0, "pressure": -1, "bad_response": -1, "acknowledge": 1, "name_use": 0},
                "guarded":  {"empathy": 0, "facts": 1, "pressure": 0, "bad_response": -1, "acknowledge": 1, "name_use": 0},
                "curious":   {"empathy": 1, "facts": 1, "pressure": 0, "bad_response": -1, "acknowledge": 1, "name_use": 1},
                "considering":      {"empathy": 1, "facts": 0, "pressure": 0, "bad_response": 0, "acknowledge": 0, "name_use": 1},
                "deal":      {"empathy": 0, "facts": 0, "pressure": 0, "bad_response": -1, "acknowledge": 0, "name_use": 0},
            },
            rollback_triggers=["interruption", "weakness", "excuse"],
            rollback_severity=2,
            breaking_point={"trigger": "no_aggression_response_x3", "jump": 2},
            initial_state="cold",
            max_state_first_call="deal",
            fake_transitions=False,
        ),
        EmotionProfile(
            archetype_code="passive",
            transition_matrix={
                "cold":      {"empathy": 0, "facts": 0, "pressure": 0, "bad_response": 0, "motivator": 2, "name_use": 0},
                "guarded":  {"empathy": 1, "facts": 0, "pressure": 0, "bad_response": 0, "motivator": 1, "name_use": 1},
                "curious":   {"empathy": 1, "facts": 1, "pressure": 0, "bad_response": -1, "motivator": 1, "name_use": 0},
                "considering":      {"empathy": 0, "facts": 1, "pressure": 0, "bad_response": -1, "motivator": 0, "name_use": 0},
                "deal":      {"empathy": 0, "facts": 0, "pressure": 0, "bad_response": -1, "motivator": 0, "name_use": 0},
            },
            rollback_triggers=["long_monologue", "money_mention"],
            rollback_severity=1,
            breaking_point={"trigger": "children_grandchildren", "jump": 2},
            initial_state="cold",
            max_state_first_call="deal",
            fake_transitions=False,
        ),
        EmotionProfile(
            archetype_code="pragmatic",
            transition_matrix={
                "cold":      {"empathy": 0, "facts": 1, "pressure": 0, "bad_response": -1, "speed": 1, "name_use": 0},
                "guarded":  {"empathy": 0, "facts": 1, "pressure": 0, "bad_response": -2, "speed": 1, "name_use": 0},
                "curious":   {"empathy": 0, "facts": 1, "pressure": 0, "bad_response": -1, "speed": 1, "name_use": 1},
                "considering":      {"empathy": 1, "facts": 0, "pressure": 0, "bad_response": -1, "speed": 0, "name_use": 1},
                "deal":      {"empathy": 0, "facts": 0, "pressure": 0, "bad_response": -1, "speed": 0, "name_use": 0},
            },
            rollback_triggers=["repetition", "filler_words", "slow_response"],
            rollback_severity=2,
            breaking_point={"trigger": "exact_cost_and_timeline", "jump": 2},
            initial_state="cold",
            max_state_first_call="deal",
            fake_transitions=False,
        ),
        EmotionProfile(
            archetype_code="manipulator",
            transition_matrix={
                "cold":      {"empathy": 1, "facts": 1, "pressure": 0, "bad_response": 0, "boundary": 0, "name_use": 1},
                "guarded":  {"empathy": 1, "facts": 1, "pressure": 0, "bad_response": 0, "boundary": 1, "name_use": 0},
                "curious":   {"empathy": 0, "facts": 0, "pressure": 0, "bad_response": 0, "boundary": 1, "name_use": 1},
                "considering":      {"empathy": 0, "facts": 0, "pressure": 0, "bad_response": -1, "boundary": 1, "name_use": 0},
                "deal":      {"empathy": 0, "facts": 0, "pressure": 0, "bad_response": -1, "boundary": 0, "name_use": 0},
            },
            rollback_triggers=["free_consultation_given"],
            rollback_severity=3,  # Can go from warming all the way to cold
            breaking_point={"trigger": "initiative_takeover_meeting", "jump": 2},
            initial_state="cold",
            max_state_first_call="deal",
            fake_transitions=True,
        ),
        EmotionProfile(
            archetype_code="delegator",
            transition_matrix={
                "cold":      {"empathy": 0, "facts": 0, "pressure": -1, "bad_response": -1, "personal": 1, "name_use": 0},
                "guarded":  {"empathy": 1, "facts": 0, "pressure": 0, "bad_response": -1, "personal": 1, "name_use": 1},
                "curious":   {"empathy": 1, "facts": 1, "pressure": 0, "bad_response": -1, "personal": 0, "name_use": 1},
                "considering":      {"empathy": 0, "facts": 1, "pressure": 0, "bad_response": 0, "personal": 0, "name_use": 0},
                "deal":      {"empathy": 0, "facts": 0, "pressure": 0, "bad_response": -1, "personal": 0, "name_use": 0},
            },
            rollback_triggers=["agreed_to_call_wife", "agreed_to_intermediary"],
            rollback_severity=5,  # Session failure
            breaking_point={"trigger": "personal_consequences", "jump": 2},
            initial_state="cold",
            max_state_first_call="deal",
            fake_transitions=False,
        ),
    ]
    db.add_all(profiles)
    await db.flush()
    print(f"  Emotion profiles: {len(profiles)}")


# ── Traps (15) ────────────────────────────────────────────────────

async def _seed_traps(db):
    data = [
        # Legal traps
        ("Запрос 100% гарантий", "legal", "Вы гарантируете, что ВСЕ долги спишут?",
         ["гарантируем", "100%", "точно спишут", "обязательно"],
         ["статистика", "97%", "индивидуально", "разберём ваш случай"],
         "Статистика положительных решений — 97%, но каждый случай индивидуален. Давайте разберём ваш.",
         -5, 3, 3),
        ("Бесплатная консультация по документам", "legal", "Расскажите, какие документы нужны, я сам подам",
         ["паспорт", "справка", "2-НДФЛ", "список документов", "выписка"],
         ["на консультации", "нюансы вашей ситуации", "разберём на встрече"],
         "Могу рассказать общий порядок, но для правильной подготовки важно учесть нюансы вашей ситуации — это мы разберём на консультации.",
         -3, 2, 4),
        ("Провокация на юр.совет", "legal", "Скажите как юрист — мне подавать на банкротство или нет?",
         ["подавайте", "не подавайте", "вам нужно", "рекомендую"],
         ["без анализа документов", "не могу", "на консультации", "похожие ситуации"],
         "Я не могу дать рекомендацию без анализа документов. Но могу рассказать, как выглядит в похожих ситуациях.",
         -3, 3, 5),
        ("Незаконный совет — не платить", "legal", "А можно просто перестать платить и подождать 3 года?",
         ["можно", "да", "срок давности", "ничего не будет"],
         ["пени растут", "приставы", "взыскание", "давайте посмотрим"],
         "Пока вы ждёте, пени растут, приставы работают. Давайте посмотрим что эффективнее в вашем случае.",
         -5, 3, 4),
        ("Цитирование закона", "legal", "В статье 213.4 написано минимум 500 тысяч! У меня меньше!",
         ["да", "вы правы", "только от 500"],
         ["ранее был порог", "сейчас закон позволяет", "при определённых условиях"],
         "Ранее был порог 500К, но сейчас закон позволяет подать и с меньшей суммой при определённых условиях.",
         -3, 3, 6),

        # Emotional traps
        ("Давление на жалость", "emotional", "У меня ребёнок-инвалид, нечем кормить семью... *плачет*",
         ["скидку", "бесплатно", "не знаю что сказать"],
         ["понимаю", "тяжело", "именно поэтому", "остановит взыскания"],
         "Понимаю, как вам сейчас тяжело. Именно поэтому важно начать процедуру — она остановит взыскания.",
         -3, 2, 5),
        ("Агрессивная провокация", "emotional", "Вы мошенники! Я на вас жалобу напишу в прокуратуру!",
         ["оправдываться", "нет мы не", "как вы смеете", "грубость"],
         ["понимаю раздражение", "конкретно", "в вашей ситуации", "вы решите"],
         "Понимаю ваше раздражение. Давайте расскажу конкретно, что мы можем сделать в вашей ситуации.",
         -5, 3, 6),
        ("Манипуляция стыдом", "emotional", "Вы наживаетесь на несчастных людях! Вам не стыдно?",
         ["защищаться", "нет", "мы честные", "обидно слышать"],
         ["понимаю впечатление", "задача", "законно", "решить проблему"],
         "Понимаю, почему может сложиться такое впечатление. Наша задача — помочь вам законно решить проблему с долгами.",
         -3, 2, 5),
        ("Ультиматум по цене", "emotional", "Либо сейчас точную цену, либо кладу трубку!",
         ["50 тысяч", "100 тысяч", "назвать точную сумму"],
         ["зависит от сложности", "кредиторов", "вилку", "от X до Y", "на консультации"],
         "Цена зависит от сложности — количества кредиторов и суммы. Вилка: от X до Y. Точную цифру определим на консультации.",
         -3, 2, 4),

        # Manipulative traps
        ("Бесконечные вопросы", "manipulative", "А вот ещё вопрос... а как насчёт... а ещё одно...",
         ["отвечать на всё", "без конца"],
         ["много вопросов", "нормально", "назначить консультацию", "разберём детально"],
         "Вижу, что у вас много вопросов — это нормально. Предлагаю назначить консультацию, где разберём всё детально.",
         -3, 2, 5),
        ("Ложное 'подумаю'", "manipulative", "Спасибо, мне нужно подумать. Перезвоню...",
         ["хорошо", "звоните", "ждём"],
         ["расчёт", "WhatsApp", "когда перезвонить", "договоримся"],
         "Конечно. Давайте отправлю расчёт на WhatsApp? И договоримся, когда мне перезвонить.",
         -3, 2, 3),
        ("Делегирование жене", "manipulative", "Поговорите лучше с моей женой, она разбирается в этом",
         ["хорошо", "давайте номер жены", "перезвоню ей"],
         ["на ваше имя", "важно чтобы вы", "втроём", "совместная встреча"],
         "Банкротство оформляется на ваше имя, поэтому важно чтобы вы понимали процесс. Может назначим встречу втроём?",
         -3, 3, 5),
        ("Ложное согласие", "manipulative", "Да-да, всё понятно, запишите меня!",
         ["отлично записал", "ждём"],
         ["подтвержу", "придёте", "адрес", "напоминание", "подготовить"],
         "Отлично! Подтверждаю: вы придёте в [дата/время] по адресу [X]? Отправлю напоминание. Что-то подготовить с собой?",
         0, 2, 3),
        ("Сравнение с конкурентом", "manipulative", "А мне в другой компании обещали за 30 тысяч всё сделать!",
         ["обесценить", "они врут", "дешевле сделаем"],
         ["часть стоимости", "что входит", "фиксированная", "все этапы"],
         "30 тысяч — скорее всего только часть. Важно уточнить что входит. Наша цена фиксированная и включает все этапы.",
         -3, 2, 5),
        ("Переписать квартиру", "manipulative", "А если квартиру на жену переписать до банкротства?",
         ["можно", "хорошая идея", "да попробуйте"],
         ["оспариваются", "3 года", "ст. 195 УК", "лучше легальная"],
         "Сделки за 3 года оспариваются. Ст. 195 УК — до 3 лет. Лучше использовать легальную защиту имущества.",
         -5, 3, 7),
    ]

    traps = []
    for name, cat, phrase, wrong, correct, example, penalty, bonus, diff in data:
        traps.append(Trap(
            name=name,
            category=cat,
            client_phrase=phrase,
            wrong_response_keywords=wrong,
            correct_response_keywords=correct,
            correct_response_example=example,
            penalty=penalty,
            bonus=bonus,
            difficulty=diff,
        ))
    db.add_all(traps)
    await db.flush()
    print(f"  Traps: {len(traps)}")


# ── Objection Chains (5) ─────────────────────────────────────────

async def _seed_objection_chains(db):
    chains = [
        ObjectionChain(
            name="Ценовая цепочка",
            difficulty=5,
            steps=[
                {"order": 0, "text": "Сколько стоит? 150 тысяч?! Это дорого!", "category": "price", "trigger": "price_response", "trap": False},
                {"order": 1, "text": "А мне в другой компании обещали за 30 тысяч...", "category": "competitor", "trigger": "competitor_response", "trap": True},
                {"order": 2, "text": "Ну ладно, я подумаю и перезвоню...", "category": "timing", "trigger": "closing_attempt", "trap": True},
            ],
        ),
        ObjectionChain(
            name="Цепочка недоверия",
            difficulty=6,
            steps=[
                {"order": 0, "text": "Я не верю что долги можно списать. Это развод.", "category": "trust", "trigger": "proof_given", "trap": False},
                {"order": 1, "text": "Ну назовите хоть один случай. Конкретно.", "category": "trust", "trigger": "case_given", "trap": False},
                {"order": 2, "text": "А если суд откажет? Деньги вернёте?", "category": "price", "trigger": "guarantee_response", "trap": True},
            ],
        ),
        ObjectionChain(
            name="Цепочка дезинформации",
            difficulty=5,
            steps=[
                {"order": 0, "text": "Мой сосед банкротился — у него всё забрали!", "category": "trust", "trigger": "myth_debunked", "trap": False},
                {"order": 1, "text": "А я читал в интернете что это мошенничество!", "category": "trust", "trigger": "law_referenced", "trap": False},
                {"order": 2, "text": "Мой знакомый юрист говорит — не надо этого делать", "category": "trust", "trigger": "joint_consultation_offered", "trap": False},
            ],
        ),
        ObjectionChain(
            name="Цепочка манипулятора",
            difficulty=8,
            steps=[
                {"order": 0, "text": "Очень интересно! Расскажите про процедуру подробнее...", "category": "need", "trigger": "info_given", "trap": False},
                {"order": 1, "text": "А какие документы нужны? Список есть?", "category": "need", "trigger": "boundary_or_info", "trap": True},
                {"order": 2, "text": "А в какой суд подавать? Сколько длится?", "category": "need", "trigger": "boundary_or_info", "trap": True},
                {"order": 3, "text": "Спасибо! Я всё понял, теперь сам подам. До свидания!", "category": "need", "trigger": "lost_client", "trap": True},
            ],
        ),
        ObjectionChain(
            name="Цепочка третьих лиц",
            difficulty=6,
            steps=[
                {"order": 0, "text": "Мне нужно посоветоваться с мужем/женой...", "category": "timing", "trigger": "joint_meeting_offered", "trap": True},
                {"order": 1, "text": "Муж/жена говорит что это плохая идея", "category": "trust", "trigger": "third_party_handled", "trap": False},
                {"order": 2, "text": "А знакомый юрист сказал что можно дешевле", "category": "competitor", "trigger": "competitor_comparison", "trap": True},
            ],
        ),
    ]
    db.add_all(chains)
    await db.flush()
    print(f"  Objection chains: {len(chains)}")


if __name__ == "__main__":
    asyncio.run(seed_roleplay())
