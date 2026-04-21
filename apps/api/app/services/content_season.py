"""Content Season service — narrative pacing and calendar-gated content.

Provides:
  - get_active_season(): current season with chapters
  - get_current_chapter(): currently open chapter
  - seed_first_season(): create Season 1 data
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.season_content import ContentSeason, SeasonChapter

logger = logging.getLogger(__name__)

# ── Season themes for narrative variety ──────────────────────────────────────

SEASON_THEMES = {
    "crisis_management": {
        "name_template": "Сезон {n}: Кризис ликвидности",
        "description": "Клиенты в тяжёлой ситуации. Банкротство — единственный выход. Работа с эмоциями и срочностью.",
    },
    "market_expansion": {
        "name_template": "Сезон {n}: Новый рынок",
        "description": "Компания выходит на новый сегмент. Холодные звонки, недоверие, конкуренты.",
    },
    "team_scaling": {
        "name_template": "Сезон {n}: Масштабирование",
        "description": "Рост команды. Менторство, делегирование, контроль качества. Сложные кейсы для опытных.",
    },
    "restructuring": {
        "name_template": "Сезон {n}: Реструктуризация",
        "description": "Изменение законодательства. Новые правила, путаница клиентов, правовые нюансы.",
    },
}


async def get_active_season(db: AsyncSession) -> dict | None:
    """Get the currently active season with its chapters."""
    result = await db.execute(
        select(ContentSeason).where(ContentSeason.is_active == True)  # noqa: E712
    )
    season = result.scalar_one_or_none()
    if not season:
        return None

    chapters_result = await db.execute(
        select(SeasonChapter)
        .where(SeasonChapter.season_id == season.id)
        .order_by(SeasonChapter.chapter_number)
    )
    chapters = chapters_result.scalars().all()

    now = datetime.now(timezone.utc)
    current_chapter = None
    for ch in chapters:
        if ch.is_active and (ch.unlocks_at is None or ch.unlocks_at <= now):
            current_chapter = ch

    return {
        "id": str(season.id),
        "code": season.code,
        "name": season.name,
        "description": season.description,
        "theme": season.theme,
        "start_date": season.start_date.isoformat(),
        "end_date": season.end_date.isoformat(),
        "chapters": [
            {
                "id": str(ch.id),
                "number": ch.chapter_number,
                "name": ch.name,
                "description": ch.description,
                "narrative_intro": ch.narrative_intro,
                "is_active": ch.is_active,
                "is_unlocked": ch.unlocks_at is None or ch.unlocks_at <= now,
                "unlocks_at": ch.unlocks_at.isoformat() if ch.unlocks_at else None,
                "scenario_count": len(ch.scenario_ids or []),
            }
            for ch in chapters
        ],
        "current_chapter": {
            "number": current_chapter.chapter_number,
            "name": current_chapter.name,
            "narrative_intro": current_chapter.narrative_intro,
        } if current_chapter else None,
    }


async def seed_first_season(db: AsyncSession) -> ContentSeason:
    """Create Season 1 with 3 chapters. Idempotent."""
    result = await db.execute(
        select(ContentSeason).where(ContentSeason.code == "season_1")
    )
    existing = result.scalar_one_or_none()
    if existing:
        logger.info("Season 1 already exists, skipping seed")
        return existing

    from datetime import timedelta

    now = datetime.now(timezone.utc)
    season = ContentSeason(
        code="season_1",
        name="Сезон 1: Кризис ликвидности",
        description="Клиенты переживают финансовый кризис. Работа с тревожными и отчаявшимися должниками.",
        theme="crisis_management",
        start_date=now,
        end_date=now + timedelta(days=90),
        is_active=True,
        chapter_count=3,
        scenario_pool=[],
        special_archetypes=["desperate", "anxious", "crying"],
        rewards={"completion_xp": 500, "title": "Антикризисный менеджер", "border": "season_1_gold"},
    )
    db.add(season)
    await db.flush()

    chapters_data = [
        {
            "number": 1,
            "name": "Глава 1: Первый контакт",
            "description": "Установить доверие с клиентом в состоянии паники",
            "narrative_intro": (
                "Экономический кризис ударил по вашему региону. Поток обращений вырос в 3 раза. "
                "Каждый звонок — человек на грани. Ваша задача — не просто продать, а стать опорой. "
                "Покажите, что банкротство — не крах, а новое начало."
            ),
            "is_active": True,
            "unlocks_at": None,
        },
        {
            "number": 2,
            "name": "Глава 2: Эскалация",
            "description": "Клиенты с агрессией и манипуляциями — кризис обостряется",
            "narrative_intro": (
                "Прошёл месяц. Первая волна клиентов прошла, но те, кто остался — самые сложные. "
                "Агрессивные, манипулирующие, юридически подкованные. Каждый звонок — испытание "
                "на стрессоустойчивость. Ваш рейтинг в компании растёт, но и ожидания выше."
            ),
            "is_active": True,
            "unlocks_at": now + timedelta(days=30),
        },
        {
            "number": 3,
            "name": "Глава 3: Разрешение",
            "description": "Финальные кейсы — сложные ситуации с максимальными ставками",
            "narrative_intro": (
                "Квартал подходит к концу. Остались самые сложные клиенты: те, кто отказывал трижды. "
                "Те, кто грозил судом. Те, кто плакал и бросал трубку. Это ваш финальный экзамен. "
                "Закройте сезон — и получите звание Антикризисного менеджера."
            ),
            "is_active": True,
            "unlocks_at": now + timedelta(days=60),
        },
    ]

    for ch_data in chapters_data:
        chapter = SeasonChapter(
            season_id=season.id,
            chapter_number=ch_data["number"],
            name=ch_data["name"],
            description=ch_data["description"],
            narrative_intro=ch_data["narrative_intro"],
            is_active=ch_data["is_active"],
            unlocks_at=ch_data.get("unlocks_at"),
        )
        db.add(chapter)

    await db.flush()
    logger.info("Seeded Season 1 with 3 chapters")
    return season
