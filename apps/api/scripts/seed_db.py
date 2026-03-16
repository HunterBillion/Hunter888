"""Seed database with initial data for development."""

import asyncio
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings  # noqa: F401
from app.core.security import hash_password
from app.database import async_session, engine, Base
from app.models import *  # noqa: F401,F403
from app.models.character import Character, EmotionState, Objection, ObjectionCategory
from app.models.scenario import Scenario, ScenarioType
from app.models.script import Checkpoint, Script
from app.models.training import AssignedTraining  # noqa: F401
from app.models.user import Team, User, UserRole


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        await _seed_team_and_admin(db)
        script = await _seed_script(db)
        character = await _seed_characters(db)
        await _seed_scenario(db, character.id, script.id)
        await _seed_objections(db)
        await db.commit()

    print("Seed data created successfully!")


async def _seed_team_and_admin(db: AsyncSession):
    team = Team(name="Отдел продаж", description="Основная команда менеджеров")
    db.add(team)
    await db.flush()

    admin = User(
        email="admin@trainer.local",
        hashed_password=hash_password("admin123"),
        full_name="Администратор",
        role=UserRole.admin,
        team_id=team.id,
    )
    manager = User(
        email="manager@trainer.local",
        hashed_password=hash_password("manager123"),
        full_name="Иван Петров",
        role=UserRole.manager,
        team_id=team.id,
    )
    rop = User(
        email="rop@trainer.local",
        hashed_password=hash_password("rop12345"),
        full_name="Ольга Смирнова",
        role=UserRole.rop,
        team_id=team.id,
    )
    db.add_all([admin, manager, rop])
    await db.flush()
    print(f"  Created team: {team.name}")
    print(f"  Created users: admin, manager, rop")


async def _seed_script(db: AsyncSession) -> Script:
    script = Script(
        title="Холодный звонок — БФЛ",
        description="Базовый скрипт холодного звонка для услуги банкротства физических лиц",
        version="1.0",
    )
    db.add(script)
    await db.flush()

    checkpoints = [
        Checkpoint(
            script_id=script.id,
            title="Приветствие",
            description="Представиться, назвать компанию, спросить удобно ли говорить",
            order_index=0,
            keywords=["здравствуйте", "добрый день", "компания", "удобно говорить"],
            weight=1.0,
        ),
        Checkpoint(
            script_id=script.id,
            title="Выявление ситуации",
            description="Узнать о долгах, кредиторах, текущей ситуации клиента",
            order_index=1,
            keywords=["долги", "кредиты", "банк", "ситуация", "сумма"],
            weight=1.2,
        ),
        Checkpoint(
            script_id=script.id,
            title="Презентация решения",
            description="Рассказать о процедуре банкротства, выгодах, сроках",
            order_index=2,
            keywords=["банкротство", "списание", "процедура", "закон", "127-ФЗ"],
            weight=1.0,
        ),
        Checkpoint(
            script_id=script.id,
            title="Работа с возражениями",
            description="Обработать основные возражения клиента",
            order_index=3,
            keywords=["понимаю", "согласен", "давайте разберёмся", "на самом деле"],
            weight=1.3,
        ),
        Checkpoint(
            script_id=script.id,
            title="Закрытие на встречу",
            description="Предложить конкретное время для бесплатной консультации",
            order_index=4,
            keywords=["встреча", "консультация", "бесплатно", "завтра", "удобно", "время"],
            weight=1.5,
        ),
    ]
    db.add_all(checkpoints)
    await db.flush()
    print(f"  Created script: {script.title} ({len(checkpoints)} checkpoints)")
    return script


async def _seed_characters(db: AsyncSession) -> Character:
    skeptic = Character(
        name="Андрей Петрович",
        slug="skeptic",
        description="Скептичный владелец строительного бизнеса, 47 лет. Не доверяет банкам после негативного опыта.",
        personality_traits={
            "trust": 0.2,
            "patience": 0.4,
            "openness": 0.3,
            "emotional": 0.5,
        },
        initial_emotion=EmotionState.cold,
        difficulty=5,
        prompt_version="v1",
        prompt_path="prompts/skeptic_v1.md",
    )
    anxious = Character(
        name="Елена Сергеевна",
        slug="anxious",
        description="Тревожная бухгалтер, 35 лет. Боится финансовых рисков, нуждается в поддержке.",
        personality_traits={
            "trust": 0.3,
            "patience": 0.7,
            "openness": 0.4,
            "emotional": 0.8,
        },
        initial_emotion=EmotionState.cold,
        difficulty=3,
        prompt_version="v1",
        prompt_path="prompts/anxious_v1.md",
    )
    aggressive = Character(
        name="Дмитрий Игоревич",
        slug="aggressive",
        description="Агрессивный директор логистической компании, 52 года. Давит авторитетом, ценит время.",
        personality_traits={
            "trust": 0.1,
            "patience": 0.2,
            "openness": 0.2,
            "emotional": 0.7,
        },
        initial_emotion=EmotionState.cold,
        difficulty=8,
        prompt_version="v1",
        prompt_path="prompts/aggressive_v1.md",
    )
    db.add_all([skeptic, anxious, aggressive])
    await db.flush()
    print(f"  Created characters: {skeptic.name}, {anxious.name}, {aggressive.name}")
    return skeptic


async def _seed_scenario(db: AsyncSession, character_id: uuid.UUID, script_id: uuid.UUID):
    scenario = Scenario(
        title="Холодный звонок — Скептик",
        description="Вы звоните Алексею Михайлову, владельцу автосервиса. У него долги перед банком и налоговой. Ваша задача — назначить бесплатную консультацию.",
        scenario_type=ScenarioType.cold_call,
        character_id=character_id,
        script_id=script_id,
        difficulty=5,
        estimated_duration_minutes=10,
    )
    db.add(scenario)
    await db.flush()
    print(f"  Created scenario: {scenario.title}")


async def _seed_objections(db: AsyncSession):
    objections_data = [
        # Trust
        (ObjectionCategory.trust, "Откуда у вас мой номер?", 0.3, "Объяснить источник, предложить удалить"),
        (ObjectionCategory.trust, "А вы вообще кто такие?", 0.4, "Представить компанию, дать ссылку на сайт"),
        (ObjectionCategory.trust, "В интернете пишут что это развод", 0.6, "Дать социальное доказательство, отзывы"),
        (ObjectionCategory.trust, "Почему я должен вам доверять?", 0.7, "Кейсы, лицензии, гарантии"),
        # Price
        (ObjectionCategory.price, "Сколько это стоит?", 0.3, "Назвать диапазон, объяснить ценность"),
        (ObjectionCategory.price, "У меня нет денег на это", 0.5, "Рассрочка, сравнение с суммой долгов"),
        (ObjectionCategory.price, "А если не получится — деньги вернёте?", 0.6, "Гарантии, этапная оплата"),
        (ObjectionCategory.price, "У знакомого юриста дешевле", 0.7, "Сравнение услуг, риски самостоятельного ведения"),
        # Need
        (ObjectionCategory.need, "Мне это не нужно", 0.4, "Уточнить ситуацию, найти боль"),
        (ObjectionCategory.need, "Я сам разберусь", 0.5, "Риски самостоятельного решения"),
        (ObjectionCategory.need, "Подожду, может само рассосётся", 0.6, "Последствия бездействия, сроки"),
        (ObjectionCategory.need, "У меня не такая уж большая сумма", 0.4, "Пороги для процедуры, рост долга"),
        # Timing
        (ObjectionCategory.timing, "Мне сейчас некогда", 0.3, "Предложить удобное время"),
        (ObjectionCategory.timing, "Перезвоните через месяц", 0.4, "Срочность, что может измениться"),
        (ObjectionCategory.timing, "Сколько это займёт времени?", 0.3, "Конкретные сроки процедуры"),
        (ObjectionCategory.timing, "У меня бизнес, не могу отвлекаться", 0.5, "Минимальное участие клиента"),
        # Competitor
        (ObjectionCategory.competitor, "Мне уже звонили из другой компании", 0.5, "Выделить УТП"),
        (ObjectionCategory.competitor, "А чем вы лучше других?", 0.6, "Конкретные преимущества"),
        (ObjectionCategory.competitor, "Знакомый юрист может сделать дешевле", 0.7, "Специализация, опыт, гарантии"),
        (ObjectionCategory.competitor, "Я уже обращался — не помогло", 0.8, "Узнать что пошло не так, предложить другой подход"),
    ]

    objections = [
        Objection(
            category=cat,
            text=txt,
            difficulty=diff,
            recommended_response_hint=hint,
        )
        for cat, txt, diff, hint in objections_data
    ]
    db.add_all(objections)
    await db.flush()
    print(f"  Created {len(objections)} objections")


if __name__ == "__main__":
    asyncio.run(seed())
