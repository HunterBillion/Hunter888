"""Behavioral Intelligence — Daily Advice Engine.

Generates one personalized recommendation per user per day based on:
- Weakest skill from ManagerProgress
- Behavioral patterns from BehaviorSnapshot
- Arena quiz weak categories
- Emotional profile (confidence/stress)
- Recent progress trends

Scheduled daily at 06:00 AM via APScheduler.
Shown on dashboard as "Совет дня".
"""

import logging
import random
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.behavior import BehaviorSnapshot, DailyAdvice, EmotionProfile, ProgressTrend

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Advice templates — categorized by trigger
# ═══════════════════════════════════════════════════════════════════════════════

ADVICE_TEMPLATES = {
    "weak_skill": [
        {
            "title": "Прокачайте навык: {skill_name}",
            "body": (
                "Ваш навык «{skill_name}» составляет {skill_score}/100 — "
                "это ваше самое слабое место. В последних {sessions} сессиях "
                "вы {trend_text}. Рекомендуем пройти тренировку со сценарием "
                "«{scenario}» на сложности {difficulty}."
            ),
            "action_type": "start_training",
        },
    ],
    "arena_knowledge": [
        {
            "title": "Подтяните знания: {category_name}",
            "body": (
                "В Арене знаний ваша точность по теме «{category_name}» составляет {accuracy}%. "
                "Пройдите тематический тест — это займёт 5-7 минут и значительно "
                "улучшит вашу юридическую подготовку."
            ),
            "action_type": "start_quiz",
        },
    ],
    "confidence_low": [
        {
            "title": "Повысьте уверенность в переговорах",
            "body": (
                "Ваш индекс уверенности: {confidence}/100. В ваших ответах "
                "часто встречаются неуверенные формулировки ({hesitations} за последнюю сессию). "
                "Совет: используйте конкретные цифры и ссылки на статьи закона — "
                "это придаёт убедительность. Попробуйте лёгкий сценарий для разминки."
            ),
            "action_type": "start_training",
        },
    ],
    "stress_high": [
        {
            "title": "Управление стрессом в переговорах",
            "body": (
                "Мы заметили повышенный уровень стресса ({stress}/100) в ваших "
                "последних сессиях. Когда клиент давит — делайте паузу перед ответом "
                "и переформулируйте его возражение. Попробуйте тренировку с лёгким "
                "архетипом для восстановления уверенности."
            ),
            "action_type": "start_training",
        },
    ],
    "streak_motivation": [
        {
            "title": "Отличная серия! Не останавливайтесь",
            "body": (
                "У вас {streak} дней тренировок подряд — {streak_comment}! "
                "Сегодня попробуйте более сложный сценарий для роста. "
                "Ваш текущий уровень: {level}, до следующего осталось {xp_to_next} XP."
            ),
            "action_type": "start_training",
        },
    ],
    "decline_alert": [
        {
            "title": "Мы заметили снижение результатов",
            "body": (
                "За последние {period} дней ваши показатели снизились на {delta}. "
                "Это нормально — у всех бывают спады. Главное — не останавливаться. "
                "Начните с лёгкой тренировки сегодня, а завтра усложните."
            ),
            "action_type": "start_training",
        },
    ],
    "general": [
        {
            "title": "Совет дня: техника «Зеркало»",
            "body": (
                "Повторяйте ключевые слова клиента в своих ответах — "
                "это создаёт ощущение, что вы его слышите. Пример: "
                "Клиент: «Мне дорого» → Вы: «Я понимаю, что вопрос стоимости важен. "
                "Давайте разберём, из чего складывается цена». Попробуйте в следующей тренировке!"
            ),
            "action_type": None,
        },
        {
            "title": "Совет дня: правильные паузы",
            "body": (
                "Не бойтесь пауз в разговоре. 2-3 секунды тишины после возражения "
                "клиента показывают, что вы обдумываете его слова. Это мощный "
                "инструмент — клиент чувствует уважение."
            ),
            "action_type": None,
        },
        {
            "title": "Совет дня: ссылайтесь на закон",
            "body": (
                "Когда клиент сомневается — ссылайтесь на конкретные статьи. "
                "«Согласно ст. 213.4 ФЗ-127...» звучит убедительнее чем «Ну, по закону...». "
                "Пройдите блиц-тест в Арене знаний для разминки!"
            ),
            "action_type": "start_quiz",
        },
    ],
}

SKILL_NAMES_RU = {
    "empathy": "Эмпатия",
    "knowledge": "Знание продукта",
    "objection_handling": "Работа с возражениями",
    "stress_resistance": "Стрессоустойчивость",
    "closing": "Закрытие сделки",
    "qualification": "Квалификация клиента",
}

SKILL_SCENARIOS = {
    "empathy": [("rescue", 4), ("special_couple", 5)],
    "knowledge": [("in_website", 3), ("in_hotline", 4)],
    "objection_handling": [("cold_ad", 5), ("cold_referral", 4)],
    "stress_resistance": [("cold_base", 3), ("rescue", 4)],
    "closing": [("in_website", 5), ("upsell", 6)],
    "qualification": [("in_hotline", 3), ("cold_referral", 4)],
}


# ═══════════════════════════════════════════════════════════════════════════════
# Main generation logic
# ═══════════════════════════════════════════════════════════════════════════════


async def generate_daily_advice(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> DailyAdvice | None:
    """Generate personalized daily advice for a user.

    Returns None if advice already exists for today.
    Priority: decline_alert > weak_skill > confidence_low > stress_high > arena > streak > general
    """
    today = datetime.now(timezone.utc).date()

    # Check if already generated today
    existing = await db.execute(
        select(DailyAdvice).where(
            DailyAdvice.user_id == user_id,
            DailyAdvice.advice_date == today,
        )
    )
    if existing.scalar_one_or_none():
        return None  # Already generated

    # Gather data
    profile = await _get_emotion_profile(user_id, db)
    recent_snapshots = await _get_recent_snapshots(user_id, db, days=7)
    recent_trend = await _get_latest_trend(user_id, db)
    manager_progress = await _get_manager_progress(user_id, db)
    arena_weak = await _get_arena_weak_categories(user_id, db)

    # ── Priority 1: Decline alert ─────────────────────────────────────────
    # PR (2026-05-06): ProgressTrend.direction is Mapped[str] (see
    # models/behavior.py:194), not an enum — `.value` raised
    # AttributeError. Same class of bug as the behavior.py:99 fix
    # (PR-cleanup #281). Was logged hourly for every active user by
    # the scheduler.
    if recent_trend and recent_trend.direction == "declining" and recent_trend.score_delta < -5:
        advice = _build_from_template("decline_alert", {
            "period": 7,
            "delta": f"{abs(recent_trend.score_delta):.0f}",
        })
        advice.priority = 1
        advice.source_analysis = {"trigger": "decline", "delta": recent_trend.score_delta}
        return await _save_advice(user_id, today, advice, db)

    # ── Priority 2: Weak skill ────────────────────────────────────────────
    if manager_progress:
        skills = {
            "empathy": getattr(manager_progress, "skill_empathy", 50),
            "knowledge": getattr(manager_progress, "skill_knowledge", 50),
            "objection_handling": getattr(manager_progress, "skill_objection_handling", 50),
            "stress_resistance": getattr(manager_progress, "skill_stress_resistance", 50),
            "closing": getattr(manager_progress, "skill_closing", 50),
            "qualification": getattr(manager_progress, "skill_qualification", 50),
        }
        weakest = min(skills, key=skills.get)
        if skills[weakest] < 45:
            scenarios = SKILL_SCENARIOS.get(weakest, [("in_website", 3)])
            scenario, diff = random.choice(scenarios)
            trend_text = "показали снижение" if recent_trend and recent_trend.score_delta < 0 else "стабильны"
            advice = _build_from_template("weak_skill", {
                "skill_name": SKILL_NAMES_RU.get(weakest, weakest),
                "skill_score": skills[weakest],
                "sessions": len(recent_snapshots),
                "trend_text": trend_text,
                "scenario": scenario,
                "difficulty": diff,
            })
            advice.priority = 2
            advice.action_data = {"scenario_code": scenario, "difficulty": diff}
            advice.source_analysis = {"trigger": "weak_skill", "skill": weakest, "score": skills[weakest]}
            return await _save_advice(user_id, today, advice, db)

    # ── Priority 3: Low confidence ────────────────────────────────────────
    if profile and profile.overall_confidence < 40:
        last_snap = recent_snapshots[0] if recent_snapshots else None
        advice = _build_from_template("confidence_low", {
            "confidence": f"{profile.overall_confidence:.0f}",
            "hesitations": last_snap.hesitation_count if last_snap else 0,
        })
        advice.priority = 3
        advice.action_data = {"scenario_code": "in_website", "difficulty": 3}
        advice.source_analysis = {"trigger": "confidence", "score": profile.overall_confidence}
        return await _save_advice(user_id, today, advice, db)

    # ── Priority 4: High stress ───────────────────────────────────────────
    if profile and profile.overall_stress_resistance < 35:
        advice = _build_from_template("stress_high", {
            "stress": f"{100 - profile.overall_stress_resistance:.0f}",
        })
        advice.priority = 4
        advice.action_data = {"scenario_code": "cold_referral", "difficulty": 2}
        advice.source_analysis = {"trigger": "stress", "resistance": profile.overall_stress_resistance}
        return await _save_advice(user_id, today, advice, db)

    # ── Priority 5: Arena knowledge gap ───────────────────────────────────
    if arena_weak:
        cat = arena_weak[0]
        cat_names = {
            "eligibility": "Условия банкротства", "procedure": "Порядок процедуры",
            "property": "Имущество", "consequences": "Последствия", "costs": "Стоимость",
            "creditors": "Кредиторы", "documents": "Документы", "timeline": "Сроки",
            "court": "Судебные процессы", "rights": "Права должника",
        }
        advice = _build_from_template("arena_knowledge", {
            "category_name": cat_names.get(cat["category"], cat["category"]),
            "accuracy": f"{cat['accuracy']:.0f}",
        })
        advice.priority = 5
        advice.action_data = {"quiz_mode": "themed", "category": cat["category"]}
        advice.source_analysis = {"trigger": "arena_weak", "category": cat["category"], "accuracy": cat["accuracy"]}
        return await _save_advice(user_id, today, advice, db)

    # ── Priority 6: Streak motivation ─────────────────────────────────────
    if manager_progress:
        streak = getattr(manager_progress, "arena_daily_streak", 0) or getattr(manager_progress, "current_deal_streak", 0)
        if streak >= 3:
            streak_comments = {3: "хорошее начало", 5: "впечатляюще", 7: "настоящий профи", 10: "легенда!"}
            comment = streak_comments.get(streak, f"{streak} дней подряд!")
            level = getattr(manager_progress, "current_level", 1)
            xp = getattr(manager_progress, "current_xp", 0)
            advice = _build_from_template("streak_motivation", {
                "streak": streak,
                "streak_comment": comment,
                "level": level,
                "xp_to_next": max(0, int(100 * (level + 1) ** 1.5) - xp),
            })
            advice.priority = 6
            advice.source_analysis = {"trigger": "streak", "streak": streak}
            return await _save_advice(user_id, today, advice, db)

    # ── Priority 10: General advice ───────────────────────────────────────
    advice = _build_from_template("general", {})
    advice.priority = 10
    advice.source_analysis = {"trigger": "general"}
    return await _save_advice(user_id, today, advice, db)


async def get_today_advice(user_id: uuid.UUID, db: AsyncSession) -> DailyAdvice | None:
    """Get today's advice for a user (or generate if missing)."""
    today = datetime.now(timezone.utc).date()
    result = await db.execute(
        select(DailyAdvice).where(
            DailyAdvice.user_id == user_id,
            DailyAdvice.advice_date == today,
        )
    )
    advice = result.scalar_one_or_none()
    if advice is None:
        advice = await generate_daily_advice(user_id, db)
    return advice


# ═══════════════════════════════════════════════════════════════════════════════
# Data fetchers
# ═══════════════════════════════════════════════════════════════════════════════


async def _get_emotion_profile(user_id: uuid.UUID, db: AsyncSession) -> EmotionProfile | None:
    result = await db.execute(select(EmotionProfile).where(EmotionProfile.user_id == user_id))
    return result.scalar_one_or_none()


async def _get_recent_snapshots(user_id: uuid.UUID, db: AsyncSession, days: int = 7) -> list[BehaviorSnapshot]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(BehaviorSnapshot)
        .where(BehaviorSnapshot.user_id == user_id, BehaviorSnapshot.created_at >= since)
        .order_by(BehaviorSnapshot.created_at.desc())
        .limit(20)
    )
    return list(result.scalars().all())


async def _get_latest_trend(user_id: uuid.UUID, db: AsyncSession) -> ProgressTrend | None:
    result = await db.execute(
        select(ProgressTrend)
        .where(ProgressTrend.user_id == user_id)
        .order_by(ProgressTrend.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _get_manager_progress(user_id: uuid.UUID, db: AsyncSession):
    """Get ManagerProgress without circular import."""
    try:
        from app.models.progress import ManagerProgress
        result = await db.execute(select(ManagerProgress).where(ManagerProgress.user_id == user_id))
        return result.scalar_one_or_none()
    except Exception:
        return None


async def _get_arena_weak_categories(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """Get weak Arena categories (accuracy < 60%)."""
    try:
        from app.services.knowledge_quiz import get_category_progress
        progress = await get_category_progress(user_id, db)
        weak = [
            {"category": p["category"], "accuracy": p["mastery_pct"]}
            for p in progress
            if p.get("total_answers", 0) >= 3 and p.get("mastery_pct", 100) < 60
        ]
        return sorted(weak, key=lambda x: x["accuracy"])
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# Template helpers
# ═══════════════════════════════════════════════════════════════════════════════


class _AdviceBuilder:
    """Temporary holder for advice properties before DB save."""
    def __init__(self):
        self.title = ""
        self.body = ""
        self.category = "general"
        self.priority = 10
        self.action_type = None
        self.action_data = None
        self.source_analysis = None


def _build_from_template(category: str, params: dict) -> _AdviceBuilder:
    """Build advice from template with parameter substitution."""
    templates = ADVICE_TEMPLATES.get(category, ADVICE_TEMPLATES["general"])
    template = random.choice(templates)

    builder = _AdviceBuilder()
    builder.category = category
    builder.action_type = template.get("action_type")

    try:
        builder.title = template["title"].format(**params)
    except (KeyError, IndexError):
        builder.title = template["title"]

    try:
        builder.body = template["body"].format(**params)
    except (KeyError, IndexError):
        builder.body = template["body"]

    return builder


async def _save_advice(
    user_id: uuid.UUID, today: date, builder: _AdviceBuilder, db: AsyncSession,
) -> DailyAdvice:
    advice = DailyAdvice(
        user_id=user_id,
        advice_date=today,
        title=builder.title,
        body=builder.body,
        category=builder.category,
        priority=builder.priority,
        action_type=builder.action_type,
        action_data=builder.action_data,
        source_analysis=builder.source_analysis,
    )
    db.add(advice)
    await db.flush()
    logger.info("DailyAdvice generated: user=%s category=%s priority=%d", user_id, builder.category, builder.priority)
    return advice
