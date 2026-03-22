"""Seed database with initial data for development/pilot."""

import asyncio
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings  # noqa: F401
from app.core.security import hash_password
from app.database import async_session
from app.models import *  # noqa: F401,F403
from app.models.character import Character, EmotionState, Objection, ObjectionCategory
from app.models.scenario import Scenario, ScenarioType
from app.models.script import Checkpoint, Script
from app.models.training import AssignedTraining  # noqa: F401
from app.models.analytics import Achievement
from app.models.user import Team, User, UserConsent, UserRole


async def seed():
    async with async_session() as db:
        # Check if users already exist (idempotent seed)
        existing = await db.execute(text("SELECT count(*) FROM users"))
        user_count = existing.scalar()

        if user_count and user_count > 0:
            print(f"  ℹ Users already exist ({user_count}), skipping users & teams...")
            # Load existing teams for FK references
            t_result = await db.execute(text("SELECT id, name FROM teams"))
            t_rows = t_result.all()
            teams = {}
            for r in t_rows:
                if "B2B" in r[1]:
                    teams["b2b"] = type("T", (), {"id": r[0], "name": r[1]})()
                else:
                    teams["sales"] = type("T", (), {"id": r[0], "name": r[1]})()
        else:
            teams = await _seed_teams(db)
            await _seed_users(db, teams)

        # ── Consent records (152-FZ) ──────────────────────────────────
        # Auto-accept required consents for all seed users so training works immediately.
        await _seed_consents(db)

        # Check if scripts exist
        existing_scripts = await db.execute(text("SELECT count(*) FROM scripts"))
        if existing_scripts.scalar() > 0:
            print("  ℹ Scripts already exist, skipping...")
            s_result = await db.execute(text("SELECT id, title FROM scripts"))
            scripts = {}
            for r in s_result.all():
                if "Холодный" in r[1]:
                    scripts["cold"] = type("S", (), {"id": r[0]})()
                elif "Дожим" in r[1]:
                    scripts["warm"] = type("S", (), {"id": r[0]})()
                else:
                    scripts["objection"] = type("S", (), {"id": r[0]})()
        else:
            scripts = await _seed_scripts(db)

        # Check if characters exist
        existing_chars = await db.execute(text("SELECT count(*) FROM characters"))
        if existing_chars.scalar() > 0:
            print("  ℹ Characters already exist, skipping...")
            c_result = await db.execute(text("SELECT id, slug FROM characters"))
            characters = {r[1]: type("C", (), {"id": r[0]})() for r in c_result.all()}
        else:
            characters = await _seed_characters(db)

        # Check if scenarios exist
        existing_scenarios = await db.execute(text("SELECT count(*) FROM scenarios"))
        if existing_scenarios.scalar() > 0:
            print("  ℹ Scenarios already exist, skipping...")
        else:
            await _seed_scenarios(db, characters, scripts)

        # Always try objections and achievements (they use ON CONFLICT or check)
        try:
            existing_obj = await db.execute(text("SELECT count(*) FROM objections"))
            if existing_obj.scalar() == 0:
                await _seed_objections(db)
            else:
                print("  ℹ Objections already exist, skipping...")
        except Exception:
            await _seed_objections(db)

        try:
            existing_ach = await db.execute(text("SELECT count(*) FROM achievements"))
            if existing_ach.scalar() == 0:
                await _seed_achievements(db)
            else:
                print("  ℹ Achievements already exist, skipping...")
        except Exception:
            await _seed_achievements(db)

        await db.commit()

    print("\n✓ Seed data created successfully!")


# ── Consent records ────────────────────────────────────────────────

async def _seed_consents(db: AsyncSession):
    """Auto-accept required 152-FZ consent for every seed user.

    Without this, AuthLayout redirects ALL users to /consent and
    POST /training/sessions returns 403 (check_consent_accepted fails).
    """
    existing = await db.execute(text(
        "SELECT count(*) FROM user_consents WHERE consent_type = 'personal_data_processing'"
    ))
    if (existing.scalar() or 0) > 0:
        print("  ℹ Consent records already exist, skipping...")
        return

    user_rows = await db.execute(text("SELECT id FROM users"))
    user_ids = [r[0] for r in user_rows.all()]

    consents = [
        UserConsent(
            user_id=uid,
            consent_type="personal_data_processing",
            version="1.0",
            accepted=True,
            ip_address="127.0.0.1",
        )
        for uid in user_ids
    ]
    db.add_all(consents)
    await db.flush()
    print(f"  Consents: {len(consents)} users auto-accepted personal_data_processing v1.0")


# ── Teams ──────────────────────────────────────────────────────────

async def _seed_teams(db: AsyncSession) -> dict[str, Team]:
    team1 = Team(name="Отдел продаж", description="Основная команда менеджеров по продажам БФЛ")
    team2 = Team(name="Отдел B2B", description="Работа с корпоративными клиентами и ИП")
    db.add_all([team1, team2])
    await db.flush()
    print(f"  Teams: {team1.name}, {team2.name}")
    return {"sales": team1, "b2b": team2}


# ── Users (8) ──────────────────────────────────────────────────────

async def _seed_users(db: AsyncSession, teams: dict[str, Team]):
    users = [
        User(
            email="admin@trainer.local",
            hashed_password=hash_password("Adm1n!2024"),
            full_name="Администратор",
            role=UserRole.admin,
            team_id=teams["sales"].id,
        ),
        User(
            email="rop1@trainer.local",
            hashed_password=hash_password("Rop1!pass"),
            full_name="Елена Кузнецова",
            role=UserRole.rop,
            team_id=teams["sales"].id,
        ),
        User(
            email="rop2@trainer.local",
            hashed_password=hash_password("Rop2!pass"),
            full_name="Сергей Волков",
            role=UserRole.rop,
            team_id=teams["b2b"].id,
        ),
        User(
            email="method@trainer.local",
            hashed_password=hash_password("Method!1"),
            full_name="Анна Методист",
            role=UserRole.methodologist,
        ),
        User(
            email="manager1@trainer.local",
            hashed_password=hash_password("Mgr1!pass"),
            full_name="Иван Петров",
            role=UserRole.manager,
            team_id=teams["sales"].id,
        ),
        User(
            email="manager2@trainer.local",
            hashed_password=hash_password("Mgr2!pass"),
            full_name="Мария Сидорова",
            role=UserRole.manager,
            team_id=teams["sales"].id,
        ),
        User(
            email="manager3@trainer.local",
            hashed_password=hash_password("Mgr3!pass"),
            full_name="Дмитрий Козлов",
            role=UserRole.manager,
            team_id=teams["b2b"].id,
        ),
        User(
            email="manager4@trainer.local",
            hashed_password=hash_password("Mgr4!pass"),
            full_name="Ксения Морозова",
            role=UserRole.manager,
            team_id=teams["b2b"].id,
        ),
    ]
    db.add_all(users)
    await db.flush()
    print(f"  Users: {len(users)} (1 admin, 2 rop, 1 methodologist, 4 managers)")


# ── Scripts (3 types with unique checkpoints) ──────────────────────

async def _seed_scripts(db: AsyncSession) -> dict[str, Script]:
    # Script 1: Cold call
    cold = Script(
        title="Холодный звонок — БФЛ",
        description="Скрипт первого контакта: квалификация + запись на консультацию",
        version="1.0",
    )
    db.add(cold)
    await db.flush()

    cold_checkpoints = [
        Checkpoint(script_id=cold.id, title="Приветствие и хук", order_index=0, weight=1.0,
                   description="Представиться, назвать компанию, дать причину звонка за 15 секунд",
                   keywords=["здравствуйте", "добрый день", "компания", "помогаем", "списать", "долги"]),
        Checkpoint(script_id=cold.id, title="Квалификация", order_index=1, weight=1.2,
                   description="Узнать: сумму долгов, количество кредиторов, наличие просрочек, имущество, работу",
                   keywords=["долги", "кредиты", "сумма", "просрочка", "имущество", "работа", "доход"]),
        Checkpoint(script_id=cold.id, title="Мини-презентация", order_index=2, weight=1.0,
                   description="Объяснить процедуру банкротства: 127-ФЗ, сроки 8-10 мес, результат — списание",
                   keywords=["банкротство", "127", "списание", "процедура", "закон", "арбитражный"]),
        Checkpoint(script_id=cold.id, title="Работа с возражениями", order_index=3, weight=1.3,
                   description="Присоединиться, уточнить причину, аргументировать, проверить снято ли",
                   keywords=["понимаю", "согласен", "давайте", "разберёмся", "на самом деле", "вы правы"]),
        Checkpoint(script_id=cold.id, title="Закрытие на консультацию", order_index=4, weight=1.5,
                   description="Предложить бесплатную консультацию, дать альтернативу по времени",
                   keywords=["встреча", "консультация", "бесплатно", "завтра", "удобно", "время", "записать"]),
    ]
    db.add_all(cold_checkpoints)

    # Script 2: Warm call (follow-up / dojim)
    warm = Script(
        title="Дожим — повторный контакт",
        description="Скрипт для клиента, который был на консультации и ушёл думать",
        version="1.0",
    )
    db.add(warm)
    await db.flush()

    warm_checkpoints = [
        Checkpoint(script_id=warm.id, title="Напоминание", order_index=0, weight=1.0,
                   description="Напомнить о встрече, уточнить помнит ли клиент. Без давления.",
                   keywords=["встречались", "помните", "консультация", "прошлый раз", "решение"]),
        Checkpoint(script_id=warm.id, title="Выявление сомнений", order_index=1, weight=1.3,
                   description="Выяснить что реально останавливает: цена, страх, третьи лица, конкурент",
                   keywords=["что останавливает", "сомнения", "почему", "что мешает", "муж", "жена"]),
        Checkpoint(script_id=warm.id, title="Адресный ответ", order_index=2, weight=1.2,
                   description="Ответить именно на тот страх/сомнение, которое клиент озвучил",
                   keywords=["понимаю", "давайте разберём", "конкретно", "в вашем случае"]),
        Checkpoint(script_id=warm.id, title="Расчёт потерь", order_index=3, weight=1.4,
                   description="Показать сколько клиент теряет за каждый месяц промедления (пени, штрафы)",
                   keywords=["пени", "штраф", "каждый месяц", "растёт", "теряете", "рублей"]),
        Checkpoint(script_id=warm.id, title="Повторная запись", order_index=4, weight=1.5,
                   description="Записать на повторную консультацию или подписание договора",
                   keywords=["приходите", "запишу", "когда удобно", "договор", "начнём"]),
    ]
    db.add_all(warm_checkpoints)

    # Script 3: Objection handling
    objh = Script(
        title="Работа с возражениями — фокус",
        description="Скрипт для отработки конкретных возражений (дорого, знакомый юрист, сам через МФЦ)",
        version="1.0",
    )
    db.add(objh)
    await db.flush()

    objh_checkpoints = [
        Checkpoint(script_id=objh.id, title="Присоединение", order_index=0, weight=1.0,
                   description="Согласиться с правом клиента на сомнения, не спорить",
                   keywords=["понимаю", "вы правы", "логичный вопрос", "согласен"]),
        Checkpoint(script_id=objh.id, title="Уточнение причины", order_index=1, weight=1.3,
                   description="Понять что именно стоит за возражением — реальная причина vs отговорка",
                   keywords=["а что именно", "почему", "расскажите", "что вас смущает"]),
        Checkpoint(script_id=objh.id, title="Аргументация", order_index=2, weight=1.2,
                   description="Дать конкретный ответ с цифрами, законами, кейсами",
                   keywords=["на самом деле", "по закону", "например", "у нас был клиент", "статистика"]),
        Checkpoint(script_id=objh.id, title="Сравнение альтернатив", order_index=3, weight=1.4,
                   description="Сравнить: текущий путь vs банкротство vs альтернатива клиента",
                   keywords=["сравните", "если продолжать", "альтернатива", "через год", "итого"]),
        Checkpoint(script_id=objh.id, title="Фиксация", order_index=4, weight=1.5,
                   description="Проверить снято ли возражение, зафиксировать следующий шаг",
                   keywords=["ответил", "снял", "ещё вопросы", "давайте", "договорились"]),
    ]
    db.add_all(objh_checkpoints)

    await db.flush()
    print(f"  Scripts: 3 ({5+5+5} checkpoints)")
    return {"cold": cold, "warm": warm, "objection": objh}


# ── Characters (5) ─────────────────────────────────────────────────

async def _seed_characters(db: AsyncSession) -> dict[str, Character]:
    chars = {
        "skeptic": Character(
            name="Алексей Михайлов",
            slug="skeptic",
            description="Скептик, 42 года, владелец автосервиса. Долг 2.1М (банк + налоговая). Прагматик — думает цифрами, не верит обещаниям.",
            personality_traits={"trust": 0.2, "patience": 0.4, "openness": 0.3, "emotional": 0.3},
            initial_emotion=EmotionState.cold,
            difficulty=5,
            prompt_version="v1",
            prompt_path="characters/skeptic_v1.md",
        ),
        "anxious": Character(
            name="Марина Петрова",
            slug="anxious",
            description="Тревожная бухгалтер, 35 лет. Долг 1.8М (3 кредита на операцию маме). Боится последствий, чувствует вину.",
            personality_traits={"trust": 0.3, "patience": 0.7, "openness": 0.4, "emotional": 0.9},
            initial_emotion=EmotionState.cold,
            difficulty=3,
            prompt_version="v1",
            prompt_path="characters/anxious_v1.md",
        ),
        "aggressive": Character(
            name="Дмитрий Козлов",
            slug="aggressive",
            description="Агрессивный бывший предприниматель, 38 лет. Долг 4.5М. Обвиняет всех, не доверяет юристам. За бронёй — страх и усталость.",
            personality_traits={"trust": 0.1, "patience": 0.2, "openness": 0.2, "emotional": 0.8},
            initial_emotion=EmotionState.cold,
            difficulty=8,
            prompt_version="v1",
            prompt_path="characters/aggressive_v1.md",
        ),
        "passive": Character(
            name="Ольга Васильева",
            slug="passive",
            description="Апатичная пенсионерка, 58 лет. Долг 650К (5 МФО). Устала, не верит что что-то можно изменить. Говорит тихо, коротко.",
            personality_traits={"trust": 0.3, "patience": 0.8, "openness": 0.2, "emotional": 0.4},
            initial_emotion=EmotionState.cold,
            difficulty=4,
            prompt_version="v1",
            prompt_path="characters/passive_v1.md",
        ),
        "pragmatic": Character(
            name="Артём Новиков",
            slug="pragmatic",
            description="Торопливый прагматик, 29 лет, IT. Долг 900К (кредитки + потребы). Знает про 127-ФЗ, перебивает, требует цифры.",
            personality_traits={"trust": 0.4, "patience": 0.1, "openness": 0.5, "emotional": 0.2},
            initial_emotion=EmotionState.cold,
            difficulty=6,
            prompt_version="v1",
            prompt_path="characters/pragmatic_v1.md",
        ),
        "manipulator": Character(
            name="Марина Кузнецова",
            slug="manipulator",
            description="Манипулятор, 38 лет, администратор клиники. Долг 1.2М. Вытягивает бесплатную экспертизу, ложное согласие, бесконечные вопросы.",
            personality_traits={"trust": 0.5, "patience": 0.9, "openness": 0.7, "emotional": 0.3},
            initial_emotion=EmotionState.cold,
            difficulty=7,
            prompt_version="v1",
            prompt_path="characters/manipulator_v1.md",
        ),
        "delegator": Character(
            name="Геннадий Фёдоров",
            slug="delegator",
            description="Делегатор, 52 года, охранник. Долг 1.8М. Не решает сам — 'поговорите с женой'. Простой, добрый, но не уверен в себе.",
            personality_traits={"trust": 0.4, "patience": 0.7, "openness": 0.3, "emotional": 0.5},
            initial_emotion=EmotionState.cold,
            difficulty=5,
            prompt_version="v1",
            prompt_path="characters/delegator_v1.md",
        ),
    }

    db.add_all(chars.values())
    await db.flush()
    print(f"  Characters: {len(chars)} ({', '.join(c.name for c in chars.values())})")
    return chars


# ── Scenarios (8) ──────────────────────────────────────────────────

async def _seed_scenarios(db: AsyncSession, characters: dict[str, Character], scripts: dict[str, Script]):
    scenarios = [
        # Cold calls (5)
        Scenario(
            title="Холодный звонок — Скептик",
            description="Алексей Михайлов, владелец автосервиса. Долг 2.1М. Скептичен, требует цифры и доказательства. Цель: записать на бесплатную консультацию.",
            scenario_type=ScenarioType.cold_call,
            character_id=characters["skeptic"].id,
            script_id=scripts["cold"].id,
            difficulty=5,
            estimated_duration_minutes=10,
        ),
        Scenario(
            title="Холодный звонок — Тревожная клиентка",
            description="Марина Петрова, бухгалтер. Долг 1.8М из-за операции мамы. Боится за квартиру, за дочку. Цель: успокоить и записать.",
            scenario_type=ScenarioType.cold_call,
            character_id=characters["anxious"].id,
            script_id=scripts["cold"].id,
            difficulty=3,
            estimated_duration_minutes=10,
        ),
        Scenario(
            title="Холодный звонок — Агрессивный должник",
            description="Дмитрий Козлов, бывший бизнесмен. Долг 4.5М. Агрессивный, обвиняет всех. Сложнейший клиент — не терпит скрипты.",
            scenario_type=ScenarioType.cold_call,
            character_id=characters["aggressive"].id,
            script_id=scripts["cold"].id,
            difficulty=8,
            estimated_duration_minutes=10,
        ),
        Scenario(
            title="Холодный звонок — Апатичная пенсионерка",
            description="Ольга Васильева, 58 лет. Долг 650К по МФО. Устала, не верит ни во что. Нужно найти мотивацию через внучку и картину жизни после.",
            scenario_type=ScenarioType.cold_call,
            character_id=characters["passive"].id,
            script_id=scripts["cold"].id,
            difficulty=4,
            estimated_duration_minutes=12,
        ),
        Scenario(
            title="Холодный звонок — Торопливый должник",
            description="Артём Новиков, IT-шник 29 лет. Долг 900К по кредиткам. Знает про банкротство, перебивает, требует конкретику за 2 минуты.",
            scenario_type=ScenarioType.cold_call,
            character_id=characters["pragmatic"].id,
            script_id=scripts["cold"].id,
            difficulty=6,
            estimated_duration_minutes=8,
        ),
        # Warm call (1)
        Scenario(
            title="Дожим — «Подумаю и перезвоню»",
            description="Марина Петрова была на консультации неделю назад, ушла думать. Муж сказал «сами разберёмся». Нужно снять возражение третьего лица и записать повторно.",
            scenario_type=ScenarioType.warm_call,
            character_id=characters["anxious"].id,
            script_id=scripts["warm"].id,
            difficulty=5,
            estimated_duration_minutes=10,
        ),
        # Objection handling (2)
        Scenario(
            title="Возражения — «Дорого + знакомый юрист»",
            description="Алексей знает про банкротство, но считает услугу дорогой. У него «знакомый юрист за 30 тысяч». Нужно математически показать разницу в качестве и рисках.",
            scenario_type=ScenarioType.objection_handling,
            character_id=characters["skeptic"].id,
            script_id=scripts["objection"].id,
            difficulty=7,
            estimated_duration_minutes=10,
        ),
        Scenario(
            title="Возражения — «Уже обманули»",
            description="Дмитрий заплатил 80К другой фирме — они пропали. Глубокое недоверие. Нельзя «продавать» — только факты, номера дел, проверяемые гарантии.",
            scenario_type=ScenarioType.objection_handling,
            character_id=characters["aggressive"].id,
            script_id=scripts["objection"].id,
            difficulty=9,
            estimated_duration_minutes=12,
        ),
        # ── NEW: Manipulator + Delegator ──
        Scenario(
            title="Холодный звонок — Манипулятор",
            description="Марина Кузнецова, 38 лет. Вытягивает бесплатную экспертизу, задаёт бесконечные вопросы, ложное согласие. Цель: установить границу и записать на консультацию.",
            scenario_type=ScenarioType.cold_call,
            character_id=characters["manipulator"].id,
            script_id=scripts["cold"].id,
            difficulty=7,
            estimated_duration_minutes=12,
        ),
        Scenario(
            title="Холодный звонок — Делегатор",
            description="Геннадий Фёдоров, 52 года. 'Поговорите с женой'. Не решает сам, делегирует. Цель: удержать ЛПР, объяснить простыми словами, записать.",
            scenario_type=ScenarioType.cold_call,
            character_id=characters["delegator"].id,
            script_id=scripts["cold"].id,
            difficulty=5,
            estimated_duration_minutes=10,
        ),
        Scenario(
            title="Работа с возражениями — Манипулятор-эксперт",
            description="Марина уже знает основы. Задаёт провокационные вопросы, пытается получить бесплатный расчёт. Цель: границы + ценность встречи.",
            scenario_type=ScenarioType.objection_handling,
            character_id=characters["manipulator"].id,
            script_id=scripts["objection"].id,
            difficulty=8,
            estimated_duration_minutes=15,
        ),
    ]
    db.add_all(scenarios)
    await db.flush()
    print(f"  Scenarios: {len(scenarios)} (7 cold, 1 warm, 3 objection)")


# ── Objections (30) ────────────────────────────────────────────────

async def _seed_objections(db: AsyncSession):
    data = [
        # Trust (6)
        (ObjectionCategory.trust, "Откуда у вас мой номер?", 0.3, "Объяснить источник, предложить удалить если не актуально"),
        (ObjectionCategory.trust, "А вы точно не коллекторы?", 0.4, "Отличить от коллекторов: мы помогаем списать, а не взыскать"),
        (ObjectionCategory.trust, "В интернете пишут что это всё развод", 0.6, "Дать номер дела на kad.arbitr.ru для проверки"),
        (ObjectionCategory.trust, "Я уже обращался к юристам — заплатил и обманули", 0.8, "Признать правоту, дать инструменты проверки: реестр СРО, arbitr.ru"),
        (ObjectionCategory.trust, "Почему я должен вам верить?", 0.7, "Предложить проверить: ИНН, ОГРН, kad.arbitr.ru, отзывы на независимых площадках"),
        (ObjectionCategory.trust, "Покажите документы что вы легальная контора", 0.5, "Предложить прислать на WhatsApp: лицензия, свидетельство, реквизиты"),
        # Price (6)
        (ObjectionCategory.price, "Сколько это стоит? Наверняка дорого", 0.3, "Назвать диапазон, сравнить с суммой долга и ежемесячных платежей"),
        (ObjectionCategory.price, "У меня нет денег даже на еду, а тут платить", 0.5, "Рассрочка, сравнение: 14К/мес на кредиты vs 8К/мес за банкротство"),
        (ObjectionCategory.price, "Знакомый юрист за 30 тысяч всё сделает", 0.7, "Уточнить что входит: управляющий? Госпошлина? Суд? Обычно 30К — только документы"),
        (ObjectionCategory.price, "Я сам через МФЦ подам — бесплатно", 0.6, "55% отказов, строгие требования: долг 50-500К, закрытое исп. производство"),
        (ObjectionCategory.price, "А если не получится — деньги вернёте?", 0.6, "Этапная оплата, гарантии в договоре, статистика успешных дел"),
        (ObjectionCategory.price, "Госпошлина 300 руб + управляющий 25К — зачем мне вы?", 0.8, "Управляющий без юриста = риск, суд требует документы, ошибка = отказ"),
        # Need (5)
        (ObjectionCategory.need, "Я сам разберусь со своими долгами", 0.5, "Уточнить план: сколько лет, сколько переплата, что с пенями"),
        (ObjectionCategory.need, "Подожду, может само рассосётся", 0.6, "Показать что происходит: пени растут, приставы придут, 50% зарплаты"),
        (ObjectionCategory.need, "Просто перестану платить — что они мне сделают?", 0.7, "Суд → приставы → блокировка карт → арест имущества → запрет выезда"),
        (ObjectionCategory.need, "Мне стыдно — банкротство это позор", 0.5, "Нормализовать: 127-ФЗ, сотни тысяч россиян, это право а не стыд"),
        (ObjectionCategory.need, "Банк сказал что нельзя банкротиться", 0.6, "Банк заинтересован получить деньги. Закон на вашей стороне."),
        # Timing (4)
        (ObjectionCategory.timing, "Мне сейчас некогда, перезвоните потом", 0.3, "Зафиксировать конкретное время: завтра в 14:00 или послезавтра в 11:00?"),
        (ObjectionCategory.timing, "Мне нужно подумать", 0.5, "Что именно обдумать? Давайте разберём прямо сейчас."),
        (ObjectionCategory.timing, "Нужно посоветоваться с мужем/женой", 0.5, "Приходите вместе на консультацию — это бесплатно, покажем расчёт обоим"),
        (ObjectionCategory.timing, "8-10 месяцев?! Слишком долго!", 0.4, "Сравнить: 10 месяцев vs 15 лет платить кредиты. Что короче?"),
        # Competitor (5)
        (ObjectionCategory.competitor, "Мне уже звонили из другой компании", 0.5, "Узнать кто, что предложили. Спросить — записались ли? Если нет — значит не убедили."),
        (ObjectionCategory.competitor, "А чем вы лучше других?", 0.6, "Не «лучше» — а специализация: N закрытых дел, средний срок, гарантии в договоре"),
        (ObjectionCategory.competitor, "Я уже обращался — потратил деньги, ничего не вышло", 0.8, "Что именно пошло не так? Узнать причину, предложить аудит бесплатно"),
        (ObjectionCategory.competitor, "Можно же на авито юриста найти за копейки", 0.5, "Банкротство = суд + управляющий + документы. Частник не покроет весь процесс"),
        # Illegal schemes (4)
        (ObjectionCategory.trust, "А если квартиру на жену переписать до банкротства?", 0.9, "Сделки за 3 года оспариваются. Ст. 195 УК — до 3 лет. Лучше легальная защита."),
        (ObjectionCategory.trust, "Переоформлю машину на тёщу — и банкротство", 0.9, "Управляющий проверит все сделки за 3 года. Риск: не списание а уголовка."),
        (ObjectionCategory.need, "Сосед так сделал — переоформил и списал", 0.7, "Каждый случай проверяют. Если найдут — отменят банкротство + штраф."),
        (ObjectionCategory.need, "После банкротства кредит не дадут никогда", 0.5, "Ограничение 5 лет. Клиенты через 2 года получают ипотеку."),
    ]

    objections = [
        Objection(category=cat, text=txt, difficulty=diff, recommended_response_hint=hint)
        for cat, txt, diff, hint in data
    ]
    db.add_all(objections)
    await db.flush()
    print(f"  Objections: {len(objections)}")


# ── Achievements (10) ──────────────────────────────────────────────

async def _seed_achievements(db: AsyncSession):
    data = [
        ("first_session", "Первый звонок", "Завершите первую тренировку", "phone", {"type": "first_session"}),
        ("streak_3", "Три дня подряд", "Тренируйтесь 3 дня подряд", "flame", {"type": "streak", "days": 3}),
        ("streak_7", "Неделя без перерыва", "Тренируйтесь 7 дней подряд", "zap", {"type": "streak", "days": 7}),
        ("score_80", "Профессионал", "Наберите 80+ баллов", "star", {"type": "score", "min": 80}),
        ("score_90", "Мастер переговоров", "Наберите 90+ баллов", "trophy", {"type": "score", "min": 90}),
        ("sessions_10", "Десятка", "Завершите 10 тренировок", "target", {"type": "sessions", "count": 10}),
        ("sessions_50", "Полсотни", "Завершите 50 тренировок", "award", {"type": "sessions", "count": 50}),
        ("all_characters", "Знаток характеров", "Пройдите тренировку с каждым персонажем", "users", {"type": "all_characters"}),
        ("cold_master", "Мастер холодных", "Наберите 80+ в 3 разных cold_call", "phone-call", {"type": "cold_master", "min_score": 80, "count": 3}),
        ("objection_killer", "Убийца возражений", "Наберите 85+ в сценарии возражений", "sword", {"type": "score_scenario", "scenario_type": "objection_handling", "min": 85}),
    ]
    achievements = [
        Achievement(slug=slug, title=title, description=desc, icon_url=icon, criteria=criteria)
        for slug, title, desc, icon, criteria in data
    ]
    db.add_all(achievements)
    await db.flush()
    print(f"  Achievements: {len(achievements)}")


if __name__ == "__main__":
    asyncio.run(seed())
