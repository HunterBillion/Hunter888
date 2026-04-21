"""Daily Drill — 3-minute micro-simulation for daily habit loop.

Each drill is a focused 3-5 reply AI dialogue targeting the user's weakest skill.
Completing one drill per day maintains the drill streak and awards base XP.

Flow:
  1. GET /training/daily-drill → returns DrillConfig (skill, archetype, scenario stub)
  2. User completes micro-dialogue (3-5 exchanges, ~3 minutes)
  3. POST /training/daily-drill/complete → awards XP, updates streak, returns result
"""

from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import ManagerProgress

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

DRILL_BASE_XP = 25
DRILL_STREAK_BONUS_PER_DAY = 5  # +5 XP per streak day
DRILL_STREAK_BONUS_CAP = 30     # max streak bonus
DRILL_MAX_EXCHANGES = 5         # 5 reply pairs max
DRILL_MIN_SCORE_FOR_XP = 0      # all drills award XP (low barrier)

# Skill → archetype mapping for drill selection
SKILL_TO_ARCHETYPES: dict[str, list[str]] = {
    "skill_empathy": ["anxious", "crying", "overwhelmed", "desperate", "grateful"],
    "skill_knowledge": ["know_it_all", "litigious", "auditor", "lawyer_client", "misinformed"],
    "skill_objection_handling": ["skeptic", "blamer", "sarcastic", "pragmatic", "negotiator"],
    "skill_stress_resistance": ["aggressive", "hostile", "manipulator", "power_player", "hysteric"],
    "skill_closing": ["passive", "avoidant", "procrastinator", "ghosting", "delegator"],
    "skill_qualification": ["shopper", "rushed", "concrete", "overthinker", "storyteller"],
}

# Skill → micro-scenario templates
SKILL_TO_DRILL_PROMPTS: dict[str, list[dict[str, str]]] = {
    "skill_empathy": [
        {"title": "Тревожный клиент", "focus": "Установите эмоциональный контакт за 3 реплики"},
        {"title": "Слёзы по телефону", "focus": "Покажите понимание и предложите конкретный шаг"},
    ],
    "skill_knowledge": [
        {"title": "Правовой вопрос", "focus": "Клиент спрашивает про 127-ФЗ. Ответьте точно"},
        {"title": "Ложная информация", "focus": "Клиент цитирует неверную статью. Мягко поправьте"},
    ],
    "skill_objection_handling": [
        {"title": "Это развод", "focus": "Снимите возражение 'это мошенники' за 3 реплики"},
        {"title": "Мне это не нужно", "focus": "Выявите реальную потребность через возражение"},
    ],
    "skill_stress_resistance": [
        {"title": "Агрессивный звонок", "focus": "Не поддавайтесь на провокацию, переведите в конструктив"},
        {"title": "Давление и угрозы", "focus": "Сохраняйте спокойствие, предложите решение"},
    ],
    "skill_closing": [
        {"title": "Вечный 'подумаю'", "focus": "Подведите пассивного клиента к конкретному шагу"},
        {"title": "Ускользающая сделка", "focus": "Зафиксируйте договорённость до конца звонка"},
    ],
    "skill_qualification": [
        {"title": "Быстрая квалификация", "focus": "Определите потенциал клиента за 3 вопроса"},
        {"title": "Запутанная история", "focus": "Выделите ключевые факты из длинного рассказа"},
    ],
}


@dataclass
class DrillConfig:
    """Configuration for a single daily drill."""
    drill_id: str
    skill_focus: str
    skill_name_ru: str
    archetype: str
    title: str
    focus_description: str
    max_exchanges: int = DRILL_MAX_EXCHANGES
    already_completed_today: bool = False


@dataclass
class DrillResult:
    """Result of completing a daily drill."""
    xp_earned: int
    streak_bonus: int
    new_drill_streak: int
    best_drill_streak: int
    total_drills: int
    chest_type: str | None = None  # "bronze" for daily drill


SKILL_NAMES_RU: dict[str, str] = {
    "skill_empathy": "Эмпатия",
    "skill_knowledge": "Правовые знания",
    "skill_objection_handling": "Работа с возражениями",
    "skill_stress_resistance": "Стрессоустойчивость",
    "skill_closing": "Закрытие сделки",
    "skill_qualification": "Квалификация",
}


async def get_drill_config(
    user_id: uuid.UUID, db: AsyncSession
) -> DrillConfig:
    """Generate today's drill config based on user's weakest skill."""
    result = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user_id)
    )
    profile = result.scalar_one_or_none()

    # Check if already completed today
    already_done = False
    if profile and profile.last_drill_date:
        today = datetime.now(timezone.utc).date()
        last_date = profile.last_drill_date
        if hasattr(last_date, "date"):
            last_date = last_date.date()
        already_done = last_date == today

    # Find weakest skill
    if profile:
        skills = {
            "skill_empathy": profile.skill_empathy,
            "skill_knowledge": profile.skill_knowledge,
            "skill_objection_handling": profile.skill_objection_handling,
            "skill_stress_resistance": profile.skill_stress_resistance,
            "skill_closing": profile.skill_closing,
            "skill_qualification": profile.skill_qualification,
        }
        # Pick from bottom 2 weakest skills (slight randomness)
        sorted_skills = sorted(skills.items(), key=lambda x: x[1])
        weakest = random.choice(sorted_skills[:2])
        skill_key = weakest[0]
    else:
        skill_key = random.choice(list(SKILL_TO_ARCHETYPES.keys()))

    # Pick archetype and drill template
    archetypes = SKILL_TO_ARCHETYPES.get(skill_key, ["skeptic"])
    archetype = random.choice(archetypes)

    templates = SKILL_TO_DRILL_PROMPTS.get(skill_key, [{"title": "Тренировка", "focus": "Отработайте навык"}])
    template = random.choice(templates)

    return DrillConfig(
        drill_id=str(uuid.uuid4()),
        skill_focus=skill_key,
        skill_name_ru=SKILL_NAMES_RU.get(skill_key, skill_key),
        archetype=archetype,
        title=template["title"],
        focus_description=template["focus"],
        max_exchanges=DRILL_MAX_EXCHANGES,
        already_completed_today=already_done,
    )


async def complete_drill(
    user_id: uuid.UUID,
    score: float,
    db: AsyncSession,
) -> DrillResult:
    """Complete a daily drill: award XP, update streak, log result.

    Args:
        user_id: The user completing the drill
        score: Score 0-100 from the micro-simulation
        db: Database session

    Returns:
        DrillResult with XP breakdown and updated streak info
    """
    # SELECT FOR UPDATE prevents concurrent drill completions (race condition → double XP)
    result = await db.execute(
        select(ManagerProgress)
        .where(ManagerProgress.user_id == user_id)
        .with_for_update()
    )
    profile = result.scalar_one_or_none()
    if not profile:
        logger.warning("No ManagerProgress for user %s during drill complete", user_id)
        return DrillResult(xp_earned=0, streak_bonus=0, new_drill_streak=0, best_drill_streak=0, total_drills=0)

    today = datetime.now(timezone.utc)
    today_date = today.date()

    # Check if already completed today (idempotency)
    if profile.last_drill_date:
        last_date = profile.last_drill_date
        if hasattr(last_date, "date"):
            last_date = last_date.date()
        if last_date == today_date:
            # Already completed — return current state without double-awarding
            return DrillResult(
                xp_earned=0,
                streak_bonus=0,
                new_drill_streak=profile.drill_streak,
                best_drill_streak=profile.best_drill_streak,
                total_drills=profile.total_drills,
            )

    # Calculate streak
    old_streak = profile.drill_streak
    if profile.last_drill_date:
        last_date = profile.last_drill_date
        if hasattr(last_date, "date"):
            last_date = last_date.date()
        days_gap = (today_date - last_date).days
        if days_gap == 1:
            # Consecutive day — extend streak
            new_streak = old_streak + 1
        elif days_gap == 0:
            # Same day — keep streak (shouldn't reach here due to idempotency above)
            new_streak = old_streak
        else:
            # Gap > 1 day — check for streak freeze
            freeze_applied = await _try_apply_streak_freeze(user_id, db)
            new_streak = (old_streak + 1) if freeze_applied else 1
    else:
        new_streak = 1  # First ever drill

    # Calculate XP
    streak_bonus = min(new_streak * DRILL_STREAK_BONUS_PER_DAY, DRILL_STREAK_BONUS_CAP)
    xp_earned = DRILL_BASE_XP + streak_bonus

    # Update profile
    profile.last_drill_date = today
    profile.drill_streak = new_streak
    profile.best_drill_streak = max(profile.best_drill_streak, new_streak)
    profile.total_drills += 1
    profile.total_xp += xp_earned
    profile.current_xp += xp_earned

    # Write XPLog
    try:
        from app.models.xp_log import XPLog, SP_RATES
        xp_log = XPLog(
            user_id=user_id,
            source="daily_drill",
            amount=xp_earned,
            multiplier=1.0,
            season_points=SP_RATES.get("daily_goal", 5),
        )
        db.add(xp_log)
    except Exception:
        logger.warning("Failed to write XPLog for drill user=%s", user_id, exc_info=True)

    await db.flush()

    logger.info(
        "Drill completed: user=%s streak=%d->%d xp=%d (base=%d streak_bonus=%d)",
        user_id, old_streak, new_streak, xp_earned, DRILL_BASE_XP, streak_bonus,
    )

    # Emit event for achievements and notifications
    try:
        from app.services.event_bus import event_bus, GameEvent
        await event_bus.emit(GameEvent(
            kind="training_completed",
            user_id=user_id,
            db=db,
            payload={
                "source": "daily_drill",
                "score": score,
                "drill_streak": new_streak,
            },
        ))
    except Exception:
        logger.debug("EventBus emit failed for drill", exc_info=True)

    return DrillResult(
        xp_earned=xp_earned,
        streak_bonus=streak_bonus,
        new_drill_streak=new_streak,
        best_drill_streak=max(profile.best_drill_streak, new_streak),
        total_drills=profile.total_drills,
        chest_type="bronze",  # Every drill awards a bronze chest
    )


async def _try_apply_streak_freeze(user_id: uuid.UUID, db: AsyncSession) -> bool:
    """Try to use a streak freeze to save the streak. Returns True if applied."""
    from app.models.progress import StreakFreeze

    result = await db.execute(
        select(StreakFreeze)
        .where(
            StreakFreeze.user_id == user_id,
            StreakFreeze.used_at.is_(None),
        )
        .order_by(StreakFreeze.purchased_at.asc())
        .limit(1)
    )
    freeze = result.scalar_one_or_none()
    if not freeze:
        return False

    freeze.used_at = datetime.now(timezone.utc)
    logger.info("Streak freeze applied for user %s", user_id)
    return True
