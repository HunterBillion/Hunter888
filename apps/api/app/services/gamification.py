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
    "uncommon": 75,
    "rare": 200,
    "epic": 500,
    "legendary": 1000,
}

# Repeat earn = 20% of original XP
REPEAT_EARN_MULTIPLIER = 0.2


def xp_for_level(level: int) -> int:
    """Total XP required to reach a given level.

    Uses explicit table from seed_levels.py (DOC_03 §3.4).
    Fallback to formula only for levels > 20.
    """
    from scripts.seed_levels import LEVEL_XP_THRESHOLDS
    if level in LEVEL_XP_THRESHOLDS:
        return LEVEL_XP_THRESHOLDS[level]
    if level <= 1:
        return 0
    # Fallback for hypothetical levels beyond 20
    return int(100 * math.pow(level, 1.5))


def level_from_xp(total_xp: int) -> int:
    """Calculate level from total accumulated XP.

    Uses explicit table from seed_levels.py (DOC_03 §3.4).
    """
    from scripts.seed_levels import get_level_for_xp
    return get_level_for_xp(total_xp)


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
    """Calculate total XP from all completed sessions (training + arena)."""
    # Training XP
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

    # Arena XP — estimated from completed quiz sessions
    from app.models.knowledge import KnowledgeQuizSession, QuizSessionStatus
    from app.services.arena_xp import calculate_arena_xp

    arena_result = await db.execute(
        select(KnowledgeQuizSession)
        .where(
            KnowledgeQuizSession.user_id == user_id,
            KnowledgeQuizSession.status == QuizSessionStatus.completed,
        )
        .order_by(KnowledgeQuizSession.started_at)
    )
    arena_sessions = arena_result.scalars().all()

    for i, session in enumerate(arena_sessions):
        mode = session.mode.value if hasattr(session.mode, 'value') else str(session.mode)
        is_pvp = mode == "pvp"
        xp_info = calculate_arena_xp(
            mode=mode if not is_pvp else "pvp",
            score=session.score or 0,
            correct=session.correct_answers or 0,
            total=session.total_questions or 1,
            streak_days=min(i, 6),
            is_pvp_win=False,  # Approximation — exact data requires participant lookup
        )
        total_xp += xp_info["total"]

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
    # ── Level milestones ──
    AchievementDef(
        slug="level_5",
        title="Кадет",
        description="Достигните 5 уровня",
        icon="chevrons-up",
        rarity="rare",
        category="basic",
        data_source="stats",
        check_lambda=lambda stats: stats.get("level", 0) >= 5,
    ),
    AchievementDef(
        slug="level_10",
        title="Лейтенант",
        description="Достигните 10 уровня",
        icon="shield-check",
        rarity="epic",
        category="basic",
        data_source="stats",
        check_lambda=lambda stats: stats.get("level", 0) >= 10,
    ),
    AchievementDef(
        slug="level_20",
        title="Капитан",
        description="Достигните 20 уровня",
        icon="crown",
        rarity="legendary",
        category="basic",
        data_source="stats",
        check_lambda=lambda stats: stats.get("level", 0) >= 20,
    ),
    # ── Extended streaks ──
    AchievementDef(
        slug="streak_14",
        title="Двухнедельный марафон",
        description="Тренируйтесь 14 дней подряд",
        icon="calendar-check",
        rarity="epic",
        category="basic",
        data_source="stats",
        check_lambda=lambda stats: stats["streak"] >= 14,
    ),
    AchievementDef(
        slug="streak_30",
        title="Несгибаемый",
        description="Тренируйтесь 30 дней подряд",
        icon="medal",
        rarity="legendary",
        category="basic",
        data_source="stats",
        check_lambda=lambda stats: stats["streak"] >= 30,
    ),
    # ── Session performance ──
    AchievementDef(
        slug="script_master",
        title="Мастер скрипта",
        description="Пройдите все 7 стадий продажи за одну сессию",
        icon="list-checks",
        rarity="rare",
        category="basic",
        data_source="stats",
        check_fn="check_script_master",
    ),
    AchievementDef(
        slug="marathon_runner",
        title="Марафонец",
        description="Полностью пройдите 5-звонковую историю",
        icon="route",
        rarity="rare",
        category="basic",
        data_source="stats",
        check_fn="check_marathon_runner",
    ),
    AchievementDef(
        slug="perfect_qualification",
        title="Идеальная квалификация",
        description="100% качества на этапе квалификации",
        icon="clipboard-check",
        rarity="common",
        category="basic",
        data_source="stats",
        check_fn="check_perfect_qualification",
    ),
    AchievementDef(
        slug="trap_master",
        title="Повелитель ловушек",
        description="Обезвредьте 5 ловушек за одну сессию",
        icon="shield-alert",
        rarity="epic",
        category="basic",
        data_source="stats",
        check_fn="check_trap_master",
    ),
    AchievementDef(
        slug="no_hints_needed",
        title="Без подсказок",
        description="Наберите 80+ баллов без использования подсказок",
        icon="brain",
        rarity="rare",
        category="basic",
        data_source="stats",
        check_fn="check_no_hints_needed",
    ),
    # ── Archetype mastery ──
    AchievementDef(
        slug="all_archetypes_easy",
        title="Знаток новичков",
        description="Пройдите все архетипы на лёгкой сложности",
        icon="users-round",
        rarity="rare",
        category="basic",
        data_source="stats",
        check_fn="check_all_archetypes_easy",
    ),
    AchievementDef(
        slug="all_archetypes_hard",
        title="Покоритель всех",
        description="Пройдите все архетипы на высокой сложности",
        icon="users-cog",
        rarity="legendary",
        category="basic",
        data_source="stats",
        check_fn="check_all_archetypes_hard",
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

# ── v3 Arena Knowledge achievements ────────────────────────────────────────

ARENA_ACHIEVEMENTS: list[AchievementDef] = [
    AchievementDef(
        slug="arena_first_fight",
        title="Первый бой",
        description="Провести первый PvP матч в Арене знаний",
        icon="swords",
        rarity="common",
        category="arena",
        data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_pvp_matches", 0) >= 1,
    ),
    AchievementDef(
        slug="arena_legal_expert",
        title="Юридический грамотей",
        description="Набрать 80%+ в тематическом тесте по любой категории",
        icon="book-open",
        rarity="common",
        category="arena",
        data_source="arena_stats",
        check_lambda=lambda stats: stats.get("best_themed_accuracy", 0) >= 80,
    ),
    AchievementDef(
        slug="arena_blitz_master",
        title="Блиц-мастер",
        description="Ответить правильно на 15+ вопросов в блице",
        icon="zap",
        rarity="rare",
        category="arena",
        data_source="arena_stats",
        check_lambda=lambda stats: stats.get("best_blitz_correct", 0) >= 15,
    ),
    AchievementDef(
        slug="arena_duelist",
        title="Дуэлянт",
        description="Одержать 10 побед в PvP Арене",
        icon="sword",
        rarity="rare",
        category="arena",
        data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_pvp_wins", 0) >= 10,
    ),
    AchievementDef(
        slug="arena_invincible",
        title="Непобедимый",
        description="Одержать 5 побед подряд в PvP Арене",
        icon="shield",
        rarity="epic",
        category="arena",
        data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_best_win_streak", 0) >= 5,
    ),
    AchievementDef(
        slug="arena_fz127_expert",
        title="Эксперт 127-ФЗ",
        description="Набрать 90%+ по всем 10 категориям знаний",
        icon="award",
        rarity="epic",
        category="arena",
        data_source="arena_stats",
        check_lambda=lambda stats: stats.get("categories_above_90", 0) >= 10,
    ),
    AchievementDef(
        slug="arena_grandmaster",
        title="Гроссмейстер",
        description="Достигнуть ELO > 1800 в Арене знаний",
        icon="chess",
        rarity="epic",
        category="arena",
        data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_rating", 0) > 1800,
    ),
    AchievementDef(
        slug="arena_legend",
        title="Легенда Арены",
        description="ELO > 2000 и 50+ матчей в Арене знаний",
        icon="crown",
        rarity="legendary",
        category="arena",
        data_source="arena_stats",
        check_lambda=lambda stats: (
            stats.get("arena_rating", 0) > 2000
            and stats.get("arena_pvp_matches", 0) >= 50
        ),
    ),
    AchievementDef(
        slug="arena_streak_10",
        title="Стрик-10",
        description="10 правильных ответов подряд в любом режиме Арены",
        icon="flame",
        rarity="rare",
        category="arena",
        data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_best_answer_streak", 0) >= 10,
    ),
    AchievementDef(
        slug="arena_teacher",
        title="Учитель",
        description="Помочь 3 коллегам улучшить знания (80%+ после вашего вызова)",
        icon="graduation-cap",
        rarity="rare",
        category="arena",
        data_source="arena_stats",
        check_fn="check_arena_teacher",
    ),
]

# ── v4 Team achievements ───────────────────────────────────────────────────

TEAM_ACHIEVEMENTS: list[AchievementDef] = [
    AchievementDef(
        slug="team_week_champion",
        title="Лучшая команда недели",
        description="Ваша команда заняла 1 место по среднему баллу за неделю",
        icon="trophy",
        rarity="rare",
        category="team",
        data_source="stats",
        check_fn="check_team_week_champion",
        repeatable=True,
    ),
    AchievementDef(
        slug="team_streak_5",
        title="Командный дух",
        description="Вся команда тренировалась 5 дней подряд",
        icon="users",
        rarity="epic",
        category="team",
        data_source="stats",
        check_fn="check_team_streak_5",
    ),
]

# Combined registry
ALL_ACHIEVEMENT_DEFS: list[AchievementDef] = (
    BASIC_ACHIEVEMENTS + NARRATIVE_ACHIEVEMENTS + ANTI_ACHIEVEMENTS
    + ARENA_ACHIEVEMENTS + TEAM_ACHIEVEMENTS
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
            # Arena
            "check_arena_teacher": self._check_arena_teacher,
            # v4 Basic (session-based)
            "check_script_master": self._check_script_master,
            "check_marathon_runner": self._check_marathon_runner,
            "check_perfect_qualification": self._check_perfect_qualification,
            "check_trap_master": self._check_trap_master,
            "check_no_hints_needed": self._check_no_hints_needed,
            "check_all_archetypes_easy": self._check_all_archetypes_easy,
            "check_all_archetypes_hard": self._check_all_archetypes_hard,
            # v4 Team
            "check_team_week_champion": self._check_team_week_champion,
            "check_team_streak_5": self._check_team_streak_5,
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

    # ── v4 Session-based achievement checks ─────────────────────────────────

    async def _check_script_master(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Rare: completed all 7 sales stages in a single session."""
        result = await db.execute(
            select(TrainingSession.score_details).where(
                TrainingSession.user_id == user_id,
                TrainingSession.status == SessionStatus.completed,
            ).order_by(TrainingSession.started_at.desc()).limit(10)
        )
        for (details,) in result.all():
            if not details or not isinstance(details, dict):
                continue
            stages = details.get("stages_completed") or details.get("script_adherence", {}).get("stages_completed")
            if isinstance(stages, (list, int)):
                count = stages if isinstance(stages, int) else len(stages)
                if count >= 7:
                    return True
        return False

    async def _check_marathon_runner(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Rare: completed a full 5-call story."""
        result = await db.execute(
            select(TrainingSession.score_details).where(
                TrainingSession.user_id == user_id,
                TrainingSession.status == SessionStatus.completed,
                TrainingSession.story_mode.is_(True),
            ).order_by(TrainingSession.started_at.desc()).limit(20)
        )
        for (details,) in result.all():
            if not details or not isinstance(details, dict):
                continue
            call_number = details.get("call_number") or details.get("story_call_number", 0)
            total_calls = details.get("total_calls") or details.get("story_total_calls", 0)
            if call_number >= 5 and call_number >= total_calls:
                return True
        return False

    async def _check_perfect_qualification(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Common: 100% quality on qualification stage."""
        result = await db.execute(
            select(TrainingSession.score_details).where(
                TrainingSession.user_id == user_id,
                TrainingSession.status == SessionStatus.completed,
            ).order_by(TrainingSession.started_at.desc()).limit(10)
        )
        for (details,) in result.all():
            if not details or not isinstance(details, dict):
                continue
            stages = details.get("stage_scores", {})
            qual_score = stages.get("qualification", {}).get("quality")
            if qual_score is not None and qual_score >= 100:
                return True
        return False

    async def _check_trap_master(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Epic: dodged 5+ traps in a single session."""
        from app.models.progress import SessionHistory
        result = await db.execute(
            select(SessionHistory.traps_dodged).where(
                SessionHistory.user_id == user_id,
            ).order_by(SessionHistory.completed_at.desc()).limit(20)
        )
        for (dodged,) in result.all():
            if dodged is not None and dodged >= 5:
                return True
        return False

    async def _check_no_hints_needed(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Rare: scored 80+ without using any hints."""
        result = await db.execute(
            select(TrainingSession.score_total, TrainingSession.score_details).where(
                TrainingSession.user_id == user_id,
                TrainingSession.status == SessionStatus.completed,
            ).order_by(TrainingSession.started_at.desc()).limit(10)
        )
        for score_total, details in result.all():
            if score_total is None or score_total < 80:
                continue
            if not details or not isinstance(details, dict):
                continue
            hints_used = details.get("hints_used", details.get("objection_hints_shown", 0))
            if isinstance(hints_used, int) and hints_used == 0:
                return True
        return False

    async def _check_all_archetypes_easy(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Rare: completed all archetypes on easy difficulty (≤3)."""
        return await self._check_all_archetypes_at_difficulty(user_id, db, max_difficulty=3)

    async def _check_all_archetypes_hard(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Legendary: completed all archetypes on hard difficulty (≥7)."""
        return await self._check_all_archetypes_at_difficulty(user_id, db, min_difficulty=7)

    async def _check_all_archetypes_at_difficulty(
        self, user_id: uuid.UUID, db: AsyncSession,
        min_difficulty: int = 0, max_difficulty: int = 10,
    ) -> bool:
        """Helper: check if user completed all known archetypes within difficulty range."""
        from app.models.progress import SessionHistory

        result = await db.execute(
            select(func.array_agg(func.distinct(SessionHistory.archetype_code))).where(
                SessionHistory.user_id == user_id,
                SessionHistory.difficulty >= min_difficulty,
                SessionHistory.difficulty <= max_difficulty,
            )
        )
        completed = result.scalar()
        if not completed:
            return False
        # Minimum 5 unique archetypes to qualify
        return len([a for a in completed if a]) >= 5

    # ── v4 Team achievement checks ────────────────────────────────────────────

    async def _check_team_week_champion(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Rare (repeatable): user's team is #1 by avg score this week."""
        from app.models.user import User, Team

        # Get user's team
        user_result = await db.execute(select(User.team_id).where(User.id == user_id))
        team_id = user_result.scalar()
        if not team_id:
            return False

        week_ago = datetime.utcnow() - timedelta(days=7)

        # Get all teams' average scores this week
        team_scores = await db.execute(
            select(
                User.team_id,
                func.avg(TrainingSession.score_total).label("avg_score"),
            )
            .join(TrainingSession, TrainingSession.user_id == User.id)
            .where(
                TrainingSession.status == SessionStatus.completed,
                TrainingSession.started_at >= week_ago,
                User.team_id.isnot(None),
            )
            .group_by(User.team_id)
            .having(func.count(TrainingSession.id) >= 3)  # Min 3 sessions to qualify
            .order_by(func.avg(TrainingSession.score_total).desc())
        )
        rows = team_scores.all()
        if not rows:
            return False
        # User's team must be #1
        return rows[0][0] == team_id

    async def _check_team_streak_5(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Epic: all team members trained 5 consecutive days."""
        from app.models.user import User

        user_result = await db.execute(select(User.team_id).where(User.id == user_id))
        team_id = user_result.scalar()
        if not team_id:
            return False

        # Get all team members
        members_result = await db.execute(
            select(User.id).where(User.team_id == team_id, User.is_active.is_(True))
        )
        member_ids = [row[0] for row in members_result.all()]
        if len(member_ids) < 2:
            return False

        # Check each member has streak >= 5
        for mid in member_ids:
            member_streak = await calculate_streak(mid, db)
            if member_streak < 5:
                return False
        return True

    # ── Arena achievement checks ──────────────────────────────────────────────

    async def _check_arena_teacher(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict
    ) -> bool:
        """Rare: helped 3 colleagues improve (they scored 80%+ within 7 days of your challenge).

        Logic: user A challenged user B via QuizChallenge. If B completed a themed quiz
        with score >= 80 within 7 days after the challenge → A gets +1 teaching_impact.
        """
        from app.models.knowledge import QuizChallenge, KnowledgeQuizSession, QuizSessionStatus

        # Find all challenges created by this user
        challenges_result = await db.execute(
            select(QuizChallenge).where(
                QuizChallenge.challenger_id == user_id,
                QuizChallenge.session_id.isnot(None),  # Challenge was accepted
            )
        )
        challenges = challenges_result.scalars().all()

        if not challenges:
            return False

        teaching_impact = 0
        checked_opponents: set[uuid.UUID] = set()

        for challenge in challenges:
            if not challenge.accepted_by:
                continue

            accepted_ids = challenge.accepted_by
            if isinstance(accepted_ids, list):
                opponent_ids = [uuid.UUID(uid) if isinstance(uid, str) else uid for uid in accepted_ids]
            else:
                continue

            for opponent_id in opponent_ids:
                if opponent_id == user_id or opponent_id in checked_opponents:
                    continue
                checked_opponents.add(opponent_id)

                # Check if opponent completed a themed quiz with 80%+ within 7 days
                challenge_date = challenge.created_at
                week_later = challenge_date + timedelta(days=7)

                good_session = await db.execute(
                    select(KnowledgeQuizSession.id).where(
                        KnowledgeQuizSession.user_id == opponent_id,
                        KnowledgeQuizSession.status == QuizSessionStatus.completed,
                        KnowledgeQuizSession.mode == "themed",
                        KnowledgeQuizSession.score >= 80,
                        KnowledgeQuizSession.started_at >= challenge_date,
                        KnowledgeQuizSession.started_at <= week_later,
                    ).limit(1)
                )
                if good_session.scalar_one_or_none():
                    teaching_impact += 1
                    if teaching_impact >= 3:
                        return True

        return teaching_impact >= 3


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

    # Get user level for level-based achievements
    from app.models.progress import ManagerProgress
    level_result = await db.execute(
        select(ManagerProgress.current_level).where(ManagerProgress.user_id == user_id)
    )
    user_level = level_result.scalar() or 1

    stats = {
        "completed_sessions": completed_sessions,
        "best_score": best_score,
        "streak": streak,
        "unique_characters": unique_characters,
        "level": user_level,
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


async def get_leaderboard_extended(
    db: AsyncSession,
    sort_by: str = "xp",
    period: str = "week",
    team_id: uuid.UUID | None = None,
    limit: int = 20,
) -> list[dict]:
    """Extended leaderboard with multiple sort criteria.

    sort_by:
      - "xp" — total XP earned in period
      - "score" — average score in period
      - "streak" — current streak days
      - "combined" — weighted: 40% avg_score + 30% XP + 20% streak + 10% sessions
    """
    from app.models.user import User
    from app.models.progress import ManagerProgress

    if period == "week":
        since = datetime.now(timezone.utc) - timedelta(days=7)
    elif period == "month":
        since = datetime.now(timezone.utc) - timedelta(days=30)
    else:
        since = datetime.min.replace(tzinfo=timezone.utc)

    # Base query: sessions in period
    base_query = (
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
        .limit(limit)
    )

    if team_id:
        base_query = base_query.where(User.team_id == team_id)

    # Sort by chosen criteria
    if sort_by == "score":
        base_query = base_query.order_by(func.avg(TrainingSession.score_total).desc())
    else:
        # Default: XP (total_score as proxy), or will be sorted in Python for combined/streak
        base_query = base_query.order_by(func.sum(TrainingSession.score_total).desc())

    result = await db.execute(base_query)
    rows = result.all()

    entries = []
    for row in rows:
        user_id_val = row[0]

        entry = {
            "user_id": str(user_id_val),
            "full_name": row[1],
            "avatar_url": row[2],
            "sessions_count": row[3],
            "total_score": round(float(row[4]), 1),
            "avg_score": round(float(row[5]), 1),
        }

        # Get XP and streak from ManagerProgress
        progress_result = await db.execute(
            select(ManagerProgress.total_xp, ManagerProgress.level).where(
                ManagerProgress.user_id == user_id_val
            )
        )
        progress_row = progress_result.one_or_none()
        entry["total_xp"] = progress_row[0] if progress_row else 0
        entry["level"] = progress_row[1] if progress_row else 1

        # Calculate streak
        streak = await calculate_streak(user_id_val, db)
        entry["streak"] = streak

        entries.append(entry)

    # Sort by chosen criteria
    if sort_by == "streak":
        entries.sort(key=lambda e: e["streak"], reverse=True)
    elif sort_by == "combined":
        # Normalize and combine: 40% avg_score + 30% XP + 20% streak + 10% sessions
        max_xp = max((e["total_xp"] for e in entries), default=1) or 1
        max_streak = max((e["streak"] for e in entries), default=1) or 1
        max_sessions = max((e["sessions_count"] for e in entries), default=1) or 1

        for e in entries:
            e["combined_score"] = round(
                0.4 * (e["avg_score"] / 100)
                + 0.3 * (e["total_xp"] / max_xp)
                + 0.2 * (e["streak"] / max_streak)
                + 0.1 * (e["sessions_count"] / max_sessions),
                4,
            )
        entries.sort(key=lambda e: e.get("combined_score", 0), reverse=True)

    # Assign ranks
    for i, entry in enumerate(entries):
        entry["rank"] = i + 1

    return entries


async def get_team_leaderboard(
    db: AsyncSession,
    period: str = "week",
    limit: int = 10,
) -> list[dict]:
    """Team leaderboard: weighted average score of all team members.

    Visible to ROP role. Teams ranked by average score.
    """
    from app.models.user import User, Team

    if period == "week":
        since = datetime.now(timezone.utc) - timedelta(days=7)
    elif period == "month":
        since = datetime.now(timezone.utc) - timedelta(days=30)
    else:
        since = datetime.min.replace(tzinfo=timezone.utc)

    result = await db.execute(
        select(
            User.team_id,
            Team.name.label("team_name"),
            func.count(func.distinct(TrainingSession.user_id)).label("active_members"),
            func.count(TrainingSession.id).label("total_sessions"),
            func.coalesce(func.avg(TrainingSession.score_total), 0).label("avg_score"),
            func.coalesce(func.sum(TrainingSession.score_total), 0).label("total_score"),
        )
        .join(User, User.id == TrainingSession.user_id)
        .join(Team, Team.id == User.team_id)
        .where(
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= since,
            User.team_id.isnot(None),
        )
        .group_by(User.team_id, Team.name)
        .having(func.count(TrainingSession.id) >= 3)
        .order_by(func.avg(TrainingSession.score_total).desc())
        .limit(limit)
    )
    rows = result.all()

    return [
        {
            "rank": i + 1,
            "team_id": str(row[0]),
            "team_name": row[1],
            "active_members": row[2],
            "total_sessions": row[3],
            "avg_score": round(float(row[4]), 1),
            "total_score": round(float(row[5]), 1),
        }
        for i, row in enumerate(rows)
    ]


# ═════════════════════════════════════════════════════════════════════════════
# ARENA ACHIEVEMENTS — stats collection and checking
# ═════════════════════════════════════════════════════════════════════════════

async def collect_arena_stats(user_id: uuid.UUID, db: AsyncSession) -> dict:
    """Collect all stats needed for arena achievement checking.

    Called after each quiz/PvP session completion in the Arena.
    """
    from app.models.pvp import PvPRating
    from app.models.knowledge import KnowledgeQuizSession, KnowledgeAnswer, QuizSessionStatus
    from app.models.progress import ManagerProgress
    from app.services.knowledge_quiz import get_category_progress

    stats: dict = {}

    # PvP rating stats
    rating_result = await db.execute(
        select(PvPRating).where(
            PvPRating.user_id == user_id,
            PvPRating.rating_type == "knowledge_arena",
        )
    )
    arena_rating = rating_result.scalar_one_or_none()
    if arena_rating:
        stats["arena_rating"] = arena_rating.rating
        stats["arena_pvp_matches"] = arena_rating.total_duels
        stats["arena_pvp_wins"] = arena_rating.wins
        stats["arena_best_win_streak"] = arena_rating.best_streak
    else:
        stats["arena_rating"] = 0
        stats["arena_pvp_matches"] = 0
        stats["arena_pvp_wins"] = 0
        stats["arena_best_win_streak"] = 0

    # Quiz session stats
    sessions_result = await db.execute(
        select(KnowledgeQuizSession).where(
            KnowledgeQuizSession.user_id == user_id,
            KnowledgeQuizSession.status == QuizSessionStatus.completed,
        )
    )
    completed_sessions = sessions_result.scalars().all()

    # Best blitz score
    blitz_sessions = [s for s in completed_sessions if s.mode.value == "blitz"]
    stats["best_blitz_correct"] = max(
        (s.correct_answers for s in blitz_sessions), default=0
    )

    # Best themed accuracy
    themed_sessions = [s for s in completed_sessions if s.mode.value == "themed"]
    stats["best_themed_accuracy"] = max(
        (s.score for s in themed_sessions), default=0
    )

    # Category mastery (how many categories have 90%+ accuracy)
    try:
        category_progress = await get_category_progress(user_id, db)
        stats["categories_above_90"] = sum(
            1 for cp in category_progress
            if cp.get("mastery_pct", 0) >= 90
        )
    except Exception:
        stats["categories_above_90"] = 0

    # Answer streaks from ManagerProgress
    progress_result = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user_id)
    )
    progress = progress_result.scalar_one_or_none()
    if progress:
        stats["arena_best_answer_streak"] = progress.arena_best_answer_streak
    else:
        stats["arena_best_answer_streak"] = 0

    # Also include training stats for combined achievement checking
    streak = await calculate_streak(user_id, db)
    training_result = await db.execute(
        select(
            func.count(TrainingSession.id),
            func.max(TrainingSession.score_total),
        ).where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
        )
    )
    t_row = training_result.one()
    stats["completed_sessions"] = t_row[0] or 0
    stats["best_score"] = float(t_row[1]) if t_row[1] is not None else None
    stats["streak"] = streak

    chars_result = await db.execute(
        select(func.count(func.distinct(TrainingSession.scenario_id))).where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
        )
    )
    stats["unique_characters"] = chars_result.scalar() or 0

    return stats


async def check_arena_achievements(
    user_id: uuid.UUID, db: AsyncSession
) -> list[dict]:
    """Check and award arena achievements after a quiz/PvP session.

    Returns list of newly earned achievements (for WS notification).
    """
    stats = await collect_arena_stats(user_id, db)

    validator = AchievementValidator()
    return await validator.check_all(user_id, db, stats)
