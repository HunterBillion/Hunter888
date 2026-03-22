"""Gamification engine v2: XP, levels, streaks, achievements, narrative achievements, anti-achievements.

v1 (production):
- XP system: BASE(50) + score_bonus(2/pt) + streak_bonus(10/day, cap 50) + perfect(100 at 90+)
- Level formula: 100 * level^1.5 (progressive difficulty)
- Streaks: consecutive calendar days with 1+ completed session
- 8 basic achievements: first_session, streak_3/7, score_80/90, sessions_10/50, all_characters
- Leaderboard: weekly/monthly/all-time grouped by user

v2 (upgrade — Agent 5):
- Achievement rarity → XP multiplier: Rare=+200, Epic=+500, Legendary=+1000
- First earn = full XP, repeat = 20% (for repeatable achievements)
- 6 narrative achievements tied to Game Director events
- 3 anti-achievements (soft negative feedback, no XP penalty)
- AchievementValidator with registry pattern and dependency injection
- Reputation integration via services/reputation.py (separate cross-cutting service)
"""

import logging
import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import Achievement, UserAchievement
from app.models.training import SessionStatus, TrainingSession

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# XP SYSTEM
# ═════════════════════════════════════════════════════════════════════════════

BASE_XP_PER_SESSION = 50
XP_PER_SCORE_POINT = 2       # score 0-100 → 0-200 bonus XP
STREAK_BONUS_XP = 10         # per streak day (capped at 50)
STREAK_BONUS_CAP = 50
PERFECT_SCORE_BONUS = 100    # score >= 90

# Achievement rarity → XP multiplier
RARITY_XP: dict[str, int] = {
    "common": 50,
    "rare": 200,
    "epic": 500,
    "legendary": 1000,
}

# Repeat earn = 20% of original XP
REPEAT_EARN_MULTIPLIER = 0.2


def xp_for_level(level: int) -> int:
    """Total XP required to reach a given level."""
    if level <= 1:
        return 0
    return int(100 * math.pow(level, 1.5))


def level_from_xp(total_xp: int) -> int:
    """Calculate level from total accumulated XP."""
    level = 1
    while xp_for_level(level + 1) <= total_xp:
        level += 1
    return level


def calculate_session_xp(score_total: float | None, streak_days: int) -> int:
    """Calculate XP earned from a single completed session."""
    xp = BASE_XP_PER_SESSION

    if score_total is not None:
        xp += int(score_total * XP_PER_SCORE_POINT)
        if score_total >= 90:
            xp += PERFECT_SCORE_BONUS

    streak_bonus = min(streak_days * STREAK_BONUS_XP, STREAK_BONUS_CAP)
    xp += streak_bonus

    return xp


def calculate_achievement_xp(rarity: str, is_first_earn: bool = True) -> int:
    """Calculate XP bonus for earning an achievement.

    Args:
        rarity: Achievement rarity (common, rare, epic, legendary)
        is_first_earn: True if first time earning this achievement

    Returns:
        XP bonus amount
    """
    base = RARITY_XP.get(rarity, 50)
    if is_first_earn:
        return base
    return int(base * REPEAT_EARN_MULTIPLIER)


# ═════════════════════════════════════════════════════════════════════════════
# STREAKS
# ═════════════════════════════════════════════════════════════════════════════

async def calculate_streak(user_id: uuid.UUID, db: AsyncSession) -> int:
    """Calculate current consecutive-day streak for a user."""
    result = await db.execute(
        select(func.date(TrainingSession.started_at))
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
        )
        .distinct()
        .order_by(func.date(TrainingSession.started_at).desc())
    )
    dates = [row[0] for row in result.all()]

    if not dates:
        return 0

    today = date.today()
    if dates[0] != today and dates[0] != today - timedelta(days=1):
        return 0

    streak = 1
    for i in range(1, len(dates)):
        if dates[i - 1] - dates[i] == timedelta(days=1):
            streak += 1
        else:
            break

    return streak


# ═════════════════════════════════════════════════════════════════════════════
# XP AGGREGATION
# ═════════════════════════════════════════════════════════════════════════════

async def get_user_total_xp(user_id: uuid.UUID, db: AsyncSession) -> int:
    """Calculate total XP from all completed sessions."""
    result = await db.execute(
        select(TrainingSession.score_total)
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
        )
        .order_by(TrainingSession.started_at)
    )
    scores = [row[0] for row in result.all()]

    total_xp = 0
    for i, score in enumerate(scores):
        streak_at_time = min(i, 5)
        total_xp += calculate_session_xp(score, streak_at_time)

    return total_xp


# ═════════════════════════════════════════════════════════════════════════════
# ACHIEVEMENT DEFINITIONS
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class AchievementDef:
    """Achievement definition with rarity, data source, and validation."""
    slug: str
    title: str
    description: str
    icon: str
    rarity: str                                      # common, rare, epic, legendary
    category: str                                     # basic, narrative, anti
    data_source: str                                  # stats, game_director, trap_service, scoring_service
    repeatable: bool = False                          # can be earned multiple times
    check_fn: Optional[str] = None                    # name of check method in AchievementValidator
    check_lambda: Optional[Callable] = None           # inline lambda for simple checks
    conditions: Optional[dict] = None                 # additional conditions (min_scenarios, min_difficulty, etc.)
    recommendation: Optional[str] = None              # fix recommendation (for anti-achievements)


# ── v1 Basic achievements ────────────────────────────────────────────────────

BASIC_ACHIEVEMENTS: list[AchievementDef] = [
    AchievementDef(
        slug="first_session",
        title="Первый звонок",
        description="Завершите первую тренировку",
        icon="phone",
        rarity="common",
        category="basic",
        data_source="stats",
        check_lambda=lambda stats: stats["completed_sessions"] >= 1,
    ),
    AchievementDef(
        slug="streak_3",
        title="Три дня подряд",
        description="Тренируйтесь 3 дня подряд",
        icon="flame",
        rarity="common",
        category="basic",
        data_source="stats",
        check_lambda=lambda stats: stats["streak"] >= 3,
    ),
    AchievementDef(
        slug="streak_7",
        title="Неделя без перерыва",
        description="Тренируйтесь 7 дней подряд",
        icon="zap",
        rarity="rare",
        category="basic",
        data_source="stats",
        check_lambda=lambda stats: stats["streak"] >= 7,
    ),
    AchievementDef(
        slug="score_80",
        title="Профессионал",
        description="Наберите 80+ баллов в тренировке",
        icon="star",
        rarity="common",
        category="basic",
        data_source="stats",
        check_lambda=lambda stats: stats["best_score"] is not None and stats["best_score"] >= 80,
    ),
    AchievementDef(
        slug="score_90",
        title="Мастер переговоров",
        description="Наберите 90+ баллов в тренировке",
        icon="trophy",
        rarity="rare",
        category="basic",
        data_source="stats",
        check_lambda=lambda stats: stats["best_score"] is not None and stats["best_score"] >= 90,
    ),
    AchievementDef(
        slug="sessions_10",
        title="Десятка",
        description="Завершите 10 тренировок",
        icon="target",
        rarity="common",
        category="basic",
        data_source="stats",
        check_lambda=lambda stats: stats["completed_sessions"] >= 10,
    ),
    AchievementDef(
        slug="sessions_50",
        title="Полсотни",
        description="Завершите 50 тренировок",
        icon="award",
        rarity="rare",
        category="basic",
        data_source="stats",
        check_lambda=lambda stats: stats["completed_sessions"] >= 50,
    ),
    AchievementDef(
        slug="all_characters",
        title="Знаток характеров",
        description="Пройдите тренировку с каждым персонажем",
        icon="users",
        rarity="rare",
        category="basic",
        data_source="stats",
        check_lambda=lambda stats: stats["unique_characters"] >= 3,
    ),
]

# ── v2 Narrative achievements ────────────────────────────────────────────────

NARRATIVE_ACHIEVEMENTS: list[AchievementDef] = [
    AchievementDef(
        slug="saved_family",
        title="Спас семью",
        description="Закройте сделку с клиентом при активном сюжете «Жена узнала о долгах»",
        icon="heart",
        rarity="legendary",
        category="narrative",
        data_source="game_director",
        check_fn="check_saved_family",
    ),
    AchievementDef(
        slug="master_of_callbacks",
        title="Мастер перезвонов",
        description="Переведите 5 клиентов из CALLBACK_SCHEDULED в MEETING_SET без GHOSTING",
        icon="phone-callback",
        rarity="epic",
        category="narrative",
        data_source="game_director",
        check_fn="check_master_of_callbacks",
    ),
    AchievementDef(
        slug="anger_whisperer",
        title="Укротитель гнева",
        description="Деэскалируйте 3 клиентов из hostile в curious или выше за один звонок",
        icon="shield",
        rarity="epic",
        category="narrative",
        data_source="scoring_service",
        check_fn="check_anger_whisperer",
    ),
    AchievementDef(
        slug="memory_keeper",
        title="Хранитель памяти",
        description="Пройдите все memory_check ловушки в сюжетной арке из 5+ звонков",
        icon="brain",
        rarity="rare",
        category="narrative",
        data_source="trap_service",
        check_fn="check_memory_keeper",
    ),
    AchievementDef(
        slug="legal_eagle",
        title="Юрист от бога",
        description="Ноль неверных правовых утверждений в 10 сессиях (5+ сценариев, сложность ≥ 6)",
        icon="scale",
        rarity="rare",
        category="narrative",
        data_source="scoring_service",
        check_fn="check_legal_eagle",
        conditions={
            "min_sessions": 10,
            "min_unique_scenarios": 5,
            "min_avg_difficulty": 6,
        },
    ),
    AchievementDef(
        slug="the_comeback",
        title="Камбэк",
        description="Реактивируйте клиента из REJECTED в DEAL_CLOSED",
        icon="refresh",
        rarity="legendary",
        category="narrative",
        data_source="game_director",
        check_fn="check_the_comeback",
    ),
]

# ── v2 Anti-achievements (soft negative feedback) ───────────────────────────

ANTI_ACHIEVEMENTS: list[AchievementDef] = [
    AchievementDef(
        slug="short_talks",
        title="Короткие разговоры",
        description="3 hangup подряд — клиенты бросают трубку",
        icon="phone-off",
        rarity="common",
        category="anti",
        data_source="stats",
        check_fn="check_short_talks",
        repeatable=True,
        recommendation="Попробуйте начинать разговор с напоминания о заявке клиента, "
                       "а не с презентации услуги. Мягкий вход снижает вероятность hangup.",
    ),
    AchievementDef(
        slug="diy_lawyer",
        title="Юрист-самоучка",
        description="3 неверных правовых утверждения за последние 5 сессий",
        icon="alert-triangle",
        rarity="common",
        category="anti",
        data_source="scoring_service",
        check_fn="check_diy_lawyer",
        repeatable=True,
        recommendation="Повторите материалы по 127-ФЗ и ст. 446 ГПК РФ. "
                       "Используйте формулировки из базы знаний, а не свои интерпретации.",
    ),
    AchievementDef(
        slug="by_the_book",
        title="По шаблону",
        description="5 сессий с низкой вариативностью ответов",
        icon="copy",
        rarity="common",
        category="anti",
        data_source="scoring_service",
        check_fn="check_by_the_book",
        repeatable=True,
        recommendation="Попробуйте адаптировать скрипт под конкретного клиента. "
                       "Учитывайте архетип и эмоциональное состояние при выборе слов.",
    ),
]

# Combined registry
ALL_ACHIEVEMENT_DEFS: list[AchievementDef] = (
    BASIC_ACHIEVEMENTS + NARRATIVE_ACHIEVEMENTS + ANTI_ACHIEVEMENTS
)


# ═════════════════════════════════════════════════════════════════════════════
# ACHIEVEMENT VALIDATOR (Registry Pattern)
# ═════════════════════════════════════════════════════════════════════════════

class AchievementValidator:
    """Centralized achievement validation with dependency injection.

    Each achievement registers a check function + data source.
    Validator fetches data from the appropriate service and runs the check.

    Usage:
        validator = AchievementValidator(
            scoring_service=scoring_svc,
            trap_service=trap_svc,
            game_director_service=gd_svc,
        )
        newly_awarded = await validator.check_all(user_id, db, stats)
    """

    def __init__(
        self,
        scoring_service=None,
        trap_service=None,
        game_director_service=None,
    ):
        self._scoring = scoring_service
        self._traps = trap_service
        self._game_director = game_director_service

        # Registry: slug → check method
        self._checks: dict[str, Callable] = {
            # Narrative
            "check_saved_family": self._check_saved_family,
            "check_master_of_callbacks": self._check_master_of_callbacks,
            "check_anger_whisperer": self._check_anger_whisperer,
            "check_memory_keeper": self._check_memory_keeper,
            "check_legal_eagle": self._check_legal_eagle,
            "check_the_comeback": self._check_the_comeback,
            # Anti
            "check_short_talks": self._check_short_talks,
            "check_diy_lawyer": self._check_diy_lawyer,
            "check_by_the_book": self._check_by_the_book,
        }

    async def check_all(
        self,
        user_id: uuid.UUID,
        db: AsyncSession,
        stats: dict,
    ) -> list[dict]:
        """Check all achievements and return newly earned ones.

        Args:
            user_id: Manager user ID
            db: Database session
            stats: Pre-gathered stats dict (completed_sessions, best_score, streak, etc.)

        Returns:
            List of newly awarded achievement dicts with XP bonus info
        """
        # Get already earned slugs
        earned_result = await db.execute(
            select(Achievement.slug)
            .join(UserAchievement, UserAchievement.achievement_id == Achievement.id)
            .where(UserAchievement.user_id == user_id)
        )
        earned_slugs = {row[0] for row in earned_result.all()}

        # Count times each slug was earned (for repeatable)
        earn_counts: dict[str, int] = {}
        if earned_slugs:
            count_result = await db.execute(
                select(Achievement.slug, func.count(UserAchievement.id))
                .join(UserAchievement, UserAchievement.achievement_id == Achievement.id)
                .where(UserAchievement.user_id == user_id)
                .group_by(Achievement.slug)
            )
            earn_counts = {row[0]: row[1] for row in count_result.all()}

        newly_awarded = []

        for defn in ALL_ACHIEVEMENT_DEFS:
            # Skip non-repeatable if already earned
            if defn.slug in earned_slugs and not defn.repeatable:
                continue

            # Run check
            passed = False
            if defn.check_lambda is not None:
                passed = defn.check_lambda(stats)
            elif defn.check_fn and defn.check_fn in self._checks:
                try:
                    passed = await self._checks[defn.check_fn](user_id, db, stats)
                except Exception as e:
                    logger.warning("Achievement check %s failed: %s", defn.check_fn, e)
                    continue
            else:
                continue

            if not passed:
                continue

            # Calculate XP
            times_earned = earn_counts.get(defn.slug, 0)
            is_first = times_earned == 0
            xp_bonus = calculate_achievement_xp(defn.rarity, is_first)

            # Ensure achievement row exists
            ach_result = await db.execute(
                select(Achievement).where(Achievement.slug == defn.slug)
            )
            achievement = ach_result.scalar_one_or_none()
            if not achievement:
                achievement = Achievement(
                    slug=defn.slug,
                    title=defn.title,
                    description=defn.description,
                    icon_url=defn.icon,
                    criteria={
                        "type": defn.slug,
                        "rarity": defn.rarity,
                        "category": defn.category,
                    },
                )
                db.add(achievement)
                await db.flush()

            # Award
            user_ach = UserAchievement(
                user_id=user_id,
                achievement_id=achievement.id,
            )
            db.add(user_ach)

            award_info = {
                "slug": defn.slug,
                "title": defn.title,
                "description": defn.description,
                "icon": defn.icon,
                "rarity": defn.rarity,
                "category": defn.category,
                "xp_bonus": xp_bonus,
                "is_first_earn": is_first,
            }
            if defn.recommendation:
                award_info["recommendation"] = defn.recommendation
            newly_awarded.append(award_info)

        if newly_awarded:
            logger.info("User %s earned %d achievements: %s",
                        user_id, len(newly_awarded),
                        [a["slug"] for a in newly_awarded])

        return newly_awarded

    # ── Narrative achievement checks ─────────────────────────────────────────

    async def _check_saved_family(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Legendary: closed deal with client who had 'wife_found_debts' storylet active."""
        if not self._game_director:
            return False
        return await self._game_director.check_storylet_deal(
            user_id, storylet_type="wife_found_debts"
        )

    async def _check_master_of_callbacks(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Epic: 5 clients converted CALLBACK_SCHEDULED → MEETING_SET without GHOSTING."""
        if not self._game_director:
            return False
        count = await self._game_director.count_callback_conversions(
            user_id, without_ghosting=True
        )
        return count >= 5

    async def _check_anger_whisperer(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Epic: de-escalated 3 clients from hostile to curious+ in a single call."""
        if not self._scoring:
            return False
        count = await self._scoring.count_deescalations(
            user_id, from_state="hostile", to_min_state="curious"
        )
        return count >= 3

    async def _check_memory_keeper(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Rare: passed all memory_check traps in a 5+ call story arc."""
        if not self._traps:
            return False
        return await self._traps.check_memory_keeper(
            user_id, min_calls_in_arc=5
        )

    async def _check_legal_eagle(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Rare: zero incorrect legal statements in 10 sessions.

        Conditions: 5+ unique scenarios, average difficulty ≥ 6.
        """
        if not self._scoring:
            return False
        legal_stats = await self._scoring.get_legal_accuracy_stats(
            user_id, last_n_sessions=10
        )
        if not legal_stats:
            return False
        return (
            legal_stats.get("incorrect_count", 999) == 0
            and legal_stats.get("unique_scenarios", 0) >= 5
            and legal_stats.get("avg_difficulty", 0) >= 6
        )

    async def _check_the_comeback(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Legendary: reactivated client from REJECTED to DEAL_CLOSED."""
        if not self._game_director:
            return False
        return await self._game_director.check_lifecycle_transition(
            user_id, from_state="REJECTED", to_state="DEAL_CLOSED"
        )

    # ── Anti-achievement checks ──────────────────────────────────────────────

    async def _check_short_talks(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Anti: 3 consecutive hangups (emotion_timeline ends with hangup)."""
        result = await db.execute(
            select(TrainingSession.emotion_timeline)
            .where(
                TrainingSession.user_id == user_id,
                TrainingSession.status == SessionStatus.completed,
            )
            .order_by(TrainingSession.started_at.desc())
            .limit(3)
        )
        timelines = [row[0] for row in result.all()]

        if len(timelines) < 3:
            return False

        hangup_count = 0
        for timeline in timelines:
            if not timeline:
                continue
            # emotion_timeline is a list of state transitions
            states = timeline if isinstance(timeline, list) else timeline.get("states", [])
            if states and str(states[-1]).lower() in ("hangup", "hostile"):
                hangup_count += 1

        return hangup_count >= 3

    async def _check_diy_lawyer(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Anti: 3+ incorrect legal statements in last 5 sessions."""
        if not self._scoring:
            return False
        legal_stats = await self._scoring.get_legal_accuracy_stats(
            user_id, last_n_sessions=5
        )
        if not legal_stats:
            return False
        return legal_stats.get("incorrect_count", 0) >= 3

    async def _check_by_the_book(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Anti: 5 sessions with low variability (score_communication < 40)."""
        result = await db.execute(
            select(TrainingSession.score_communication)
            .where(
                TrainingSession.user_id == user_id,
                TrainingSession.status == SessionStatus.completed,
            )
            .order_by(TrainingSession.started_at.desc())
            .limit(5)
        )
        scores = [row[0] for row in result.all() if row[0] is not None]

        if len(scores) < 5:
            return False

        low_variability = sum(1 for s in scores if s < 40)
        return low_variability >= 5


# ═════════════════════════════════════════════════════════════════════════════
# BACKWARD-COMPATIBLE check_and_award_achievements (v1 API preserved)
# ═════════════════════════════════════════════════════════════════════════════

async def check_and_award_achievements(
    user_id: uuid.UUID, db: AsyncSession
) -> list[dict]:
    """Check all achievement conditions and award any newly earned ones.

    v2: Uses AchievementValidator internally but maintains v1 API signature.
    Note: Narrative achievements that require game_director/trap_service/scoring_service
    will be skipped if those services are not injected. Use create_validator() for full
    achievement checking.

    Returns list of newly awarded achievements.
    """
    # Gather stats
    streak = await calculate_streak(user_id, db)

    stats_result = await db.execute(
        select(
            func.count(TrainingSession.id),
            func.max(TrainingSession.score_total),
        ).where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
        )
    )
    row = stats_result.one()
    completed_sessions = row[0] or 0
    best_score = float(row[1]) if row[1] is not None else None

    # Count unique characters via scenarios
    chars_result = await db.execute(
        select(func.count(func.distinct(TrainingSession.scenario_id))).where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
        )
    )
    unique_characters = chars_result.scalar() or 0

    stats = {
        "completed_sessions": completed_sessions,
        "best_score": best_score,
        "streak": streak,
        "unique_characters": unique_characters,
    }

    # Use validator (without optional services — narrative checks will be skipped)
    validator = AchievementValidator()
    return await validator.check_all(user_id, db, stats)


def create_validator(
    scoring_service=None,
    trap_service=None,
    game_director_service=None,
) -> AchievementValidator:
    """Factory for AchievementValidator with dependency injection.

    Usage in DI container / startup:
        validator = create_validator(
            scoring_service=scoring_svc,
            trap_service=trap_svc,
            game_director_service=gd_svc,
        )
    """
    return AchievementValidator(
        scoring_service=scoring_service,
        trap_service=trap_service,
        game_director_service=game_director_service,
    )


# ═════════════════════════════════════════════════════════════════════════════
# LEADERBOARD (unchanged from v1)
# ═════════════════════════════════════════════════════════════════════════════

async def get_leaderboard(
    db: AsyncSession,
    period: str = "week",
    team_id: uuid.UUID | None = None,
    limit: int = 20,
) -> list[dict]:
    """Generate leaderboard from actual session data."""
    from app.models.user import User

    if period == "week":
        since = datetime.now(timezone.utc) - timedelta(days=7)
    elif period == "month":
        since = datetime.now(timezone.utc) - timedelta(days=30)
    else:
        since = datetime.min.replace(tzinfo=timezone.utc)

    query = (
        select(
            TrainingSession.user_id,
            User.full_name,
            User.avatar_url,
            func.count(TrainingSession.id).label("sessions_count"),
            func.coalesce(func.sum(TrainingSession.score_total), 0).label("total_score"),
            func.coalesce(func.avg(TrainingSession.score_total), 0).label("avg_score"),
        )
        .join(User, User.id == TrainingSession.user_id)
        .where(
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= since,
        )
        .group_by(TrainingSession.user_id, User.full_name, User.avatar_url)
        .order_by(func.sum(TrainingSession.score_total).desc())
        .limit(limit)
    )

    if team_id:
        query = query.where(User.team_id == team_id)

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "rank": i + 1,
            "user_id": str(row[0]),
            "full_name": row[1],
            "avatar_url": row[2],
            "sessions_count": row[3],
            "total_score": round(float(row[4]), 1),
            "avg_score": round(float(row[5]), 1),
        }
        for i, row in enumerate(rows)
    ]
