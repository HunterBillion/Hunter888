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


MIN_SCORE_FOR_XP = 10  # Minimum score to earn any XP (anti-exploit)


def calculate_session_xp(score_total: float | None, streak_days: int) -> int:
    """Calculate XP earned from a single completed session.

    Anti-exploit: sessions with score < MIN_SCORE_FOR_XP earn 0 XP.
    Base XP is now proportional to score (not flat 50).
    """
    # No score or too low → 0 XP (prevents farming empty sessions)
    if score_total is None or score_total < MIN_SCORE_FOR_XP:
        return 0

    # Base XP proportional to score: 50 * (score/100)
    xp = int(BASE_XP_PER_SESSION * min(score_total, 100) / 100)

    # Score-based bonus
    xp += int(score_total * XP_PER_SCORE_POINT)

    # Perfect score bonus
    if score_total >= 90:
        xp += PERFECT_SCORE_BONUS

    # Streak bonus
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
    """Calculate current consecutive-day streak for a user.

    A day is counted when the user completes at least one daily goal
    (e.g. "complete 1 session", "score 70+", "morning warm-up"). Pure
    login doesn't count. Falls back to completed sessions if no goal
    completions exist yet.

    2026-04-20: date bucketing uses the local business timezone
    (settings.app_tz, default Europe/Moscow). Previously `func.date(...)`
    bucketed in UTC, so a session completed at 02:00 MSK landed on
    yesterday's UTC date and the streak visually broke overnight.
    """
    from app.config import settings
    tz_name = settings.app_tz or "Europe/Moscow"

    # Primary: count days with goal completions (active engagement).
    # AT TIME ZONE 'UTC' interprets the timestamp as UTC, then converts to
    # the business tz before taking ::date. This works for aware columns
    # stored as TIMESTAMPTZ — Postgres keeps them in UTC internally.
    try:
        from app.models.progress import GoalCompletionLog
        local_date_expr = func.date(
            func.timezone(tz_name, GoalCompletionLog.completed_at)
        )
        goal_result = await db.execute(
            select(local_date_expr)
            .where(GoalCompletionLog.user_id == user_id)
            .distinct()
            .order_by(local_date_expr.desc())
        )
        goal_dates = [row[0] for row in goal_result.all()]
        if goal_dates:
            return _count_consecutive_days(goal_dates)
    except Exception:
        pass  # Table may not exist yet; fall back to sessions

    # Fallback: count days with completed training sessions.
    local_date_sess = func.date(
        func.timezone(tz_name, TrainingSession.started_at)
    )
    result = await db.execute(
        select(local_date_sess)
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
        )
        .distinct()
        .order_by(local_date_sess.desc())
    )
    dates = [row[0] for row in result.all()]
    return _count_consecutive_days(dates)


def _count_consecutive_days(dates: list) -> int:
    """Count consecutive calendar days from today backwards (local tz)."""
    if not dates:
        return 0

    # 2026-04-20: local-tz "today" matches the bucketing done by the query.
    try:
        from app.utils.local_time import local_today
        today = local_today()
    except Exception:
        today = datetime.now(timezone.utc).date()
    # Allow today or yesterday as the last active day
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
    """Read cached total XP from ManagerProgress (O(1) indexed lookup).

    XP is incrementally maintained by manager_progress.update_after_session()
    and daily_drill.complete_drill(). This replaces the previous O(N) approach
    that recomputed XP from all sessions on every call.
    """
    from app.models.progress import ManagerProgress
    result = await db.execute(
        select(ManagerProgress.total_xp).where(ManagerProgress.user_id == user_id)
    )
    return result.scalar_one_or_none() or 0


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

# ── v5 Seed-aligned achievements (144 codes from seed_levels.py) ────────────
# These cover ALL achievement codes that exist in the DB seed but were not
# previously wired to runtime evaluation logic.

SEED_ACHIEVEMENTS: list[AchievementDef] = [
    # ═══ RESULTS ═══
    AchievementDef(
        slug="first_deal", title="Первая сделка",
        description="Закрыл первую сделку с ИИ-клиентом",
        icon="handshake", rarity="common", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("total_deals", 0) >= 1,
    ),
    AchievementDef(
        slug="first_perfect", title="Первый идеал",
        description="Первый score >= 90 за сессию",
        icon="sparkles", rarity="uncommon", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("best_score") is not None and stats["best_score"] >= 90,
    ),
    AchievementDef(
        slug="streak_5", title="Неудержимый",
        description="5 сделок подряд",
        icon="flame", rarity="uncommon", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("current_deal_streak", 0) >= 5,
    ),
    AchievementDef(
        slug="streak_10", title="Непобедимый",
        description="10 сделок подряд",
        icon="flame", rarity="epic", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("current_deal_streak", 0) >= 10,
    ),
    AchievementDef(
        slug="perfect_score", title="Перфекционист",
        description="Набрал 95+ баллов за одну сессию",
        icon="star", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("best_score") is not None and stats["best_score"] >= 95,
    ),
    AchievementDef(
        slug="century", title="Сотня",
        description="Завершил 100 тренировочных сессий",
        icon="target", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("completed_sessions", 0) >= 100,
    ),
    AchievementDef(
        slug="marathon", title="Марафонец",
        description="Завершил 500 тренировочных сессий",
        icon="route", rarity="legendary", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("completed_sessions", 0) >= 500,
    ),
    AchievementDef(
        slug="sessions_1000", title="Тысячник",
        description="Завершил 1000 тренировочных сессий",
        icon="infinity", rarity="legendary", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("completed_sessions", 0) >= 1000,
    ),
    AchievementDef(
        slug="deals_10", title="Десять сделок",
        description="Закрыл 10 сделок",
        icon="handshake", rarity="common", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("total_deals", 0) >= 10,
    ),
    AchievementDef(
        slug="deals_50", title="Полсотни сделок",
        description="Закрыл 50 сделок",
        icon="handshake", rarity="uncommon", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("total_deals", 0) >= 50,
    ),
    AchievementDef(
        slug="deals_100", title="Сотня сделок",
        description="Закрыл 100 сделок",
        icon="handshake", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("total_deals", 0) >= 100,
    ),
    AchievementDef(
        slug="deals_500", title="Пятьсот сделок",
        description="Закрыл 500 сделок",
        icon="handshake", rarity="epic", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("total_deals", 0) >= 500,
    ),
    AchievementDef(
        slug="score_70_first", title="Первый порог",
        description="Первый score >= 70 за сессию",
        icon="star", rarity="common", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("best_score") is not None and stats["best_score"] >= 70,
    ),
    AchievementDef(
        slug="score_80_first", title="Хороший старт",
        description="Первый score >= 80 за сессию",
        icon="star", rarity="common", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("best_score") is not None and stats["best_score"] >= 80,
    ),
    AchievementDef(
        slug="score_100", title="Абсолютный идеал",
        description="Набрал 100 баллов за сессию",
        icon="gem", rarity="epic", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("best_score") is not None and stats["best_score"] >= 100,
    ),
    AchievementDef(
        slug="training_10h", title="10 часов",
        description="Суммарно 10 часов тренировок",
        icon="clock", rarity="uncommon", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("total_training_hours", 0) >= 10,
    ),
    AchievementDef(
        slug="training_50h", title="50 часов",
        description="Суммарно 50 часов тренировок",
        icon="clock", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("total_training_hours", 0) >= 50,
    ),

    # ═══ SKILLS ═══
    AchievementDef(
        slug="trap_god", title="Бог ловушек",
        description="Обработал 25 ловушек подряд без попадания",
        icon="shield-alert", rarity="epic", category="basic", data_source="stats",
        check_fn="check_trap_dodge_streak",
        conditions={"count": 25},
    ),
    AchievementDef(
        slug="chain_master", title="Цепочечник",
        description="Завершил 10 цепочек разговора подряд",
        icon="link", rarity="uncommon", category="basic", data_source="stats",
        check_fn="check_chain_completion_streak",
        conditions={"count": 10},
    ),
    AchievementDef(
        slug="zero_antipatterns", title="Чистый звонок",
        description="Сессия с 0 антипаттернов",
        icon="sparkle", rarity="common", category="basic", data_source="stats",
        check_fn="check_zero_antipatterns",
        conditions={"count": 1},
    ),
    AchievementDef(
        slug="clean_streak", title="Чистая серия",
        description="5 сессий подряд с 0 антипаттернов",
        icon="sparkles", rarity="rare", category="basic", data_source="stats",
        check_fn="check_zero_antipatterns_streak",
        conditions={"count": 5},
    ),
    AchievementDef(
        slug="empathy_master", title="Эмпат",
        description="Навык Эмпатия достиг 90+",
        icon="heart", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("skill_empathy", 0) >= 90,
    ),
    AchievementDef(
        slug="knowledge_guru", title="Гуру",
        description="Навык Знание продукта достиг 90+",
        icon="book", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("skill_knowledge", 0) >= 90,
    ),
    AchievementDef(
        slug="objection_pro", title="Возражатель",
        description="Навык Работа с возражениями достиг 90+",
        icon="shield", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("skill_objection_handling", 0) >= 90,
    ),
    AchievementDef(
        slug="stress_shield", title="Стальные нервы",
        description="Навык Стрессоустойчивость достиг 90+",
        icon="shield-check", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("skill_stress_resistance", 0) >= 90,
    ),
    AchievementDef(
        slug="closer_elite", title="Элитный клозер",
        description="Навык Закрытие достиг 90+",
        icon="check-circle", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("skill_closing", 0) >= 90,
    ),
    AchievementDef(
        slug="qualifier_pro", title="Квалификатор",
        description="Навык Квалификация достиг 90+",
        icon="clipboard-check", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("skill_qualification", 0) >= 90,
    ),
    AchievementDef(
        slug="time_master", title="Хронометрист",
        description="Навык Тайм-менеджмент достиг 90+",
        icon="clock", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("skill_time_management", 0) >= 90,
    ),
    AchievementDef(
        slug="chameleon", title="Хамелеон",
        description="Навык Адаптация достиг 90+",
        icon="refresh", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("skill_adaptation", 0) >= 90,
    ),
    AchievementDef(
        slug="legal_expert", title="Юрист",
        description="Навык Юридические знания достиг 90+",
        icon="scale", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("skill_legal_knowledge", 0) >= 90,
    ),
    AchievementDef(
        slug="rapport_master", title="Мастер раппорта",
        description="Навык Построение раппорта достиг 90+",
        icon="users", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("skill_rapport_building", 0) >= 90,
    ),
    AchievementDef(
        slug="all_skills_80", title="Мастер на все руки",
        description="Все 10 навыков достигли 80+",
        icon="award", rarity="epic", category="basic", data_source="stats",
        check_lambda=lambda stats: all(
            stats.get(f"skill_{s}", 0) >= 80
            for s in [
                "empathy", "knowledge", "objection_handling", "stress_resistance",
                "closing", "qualification", "time_management", "adaptation",
                "legal_knowledge", "rapport_building",
            ]
        ),
    ),
    AchievementDef(
        slug="all_skills_90", title="Универсальный мастер",
        description="Все 10 навыков достигли 90+",
        icon="crown", rarity="legendary", category="basic", data_source="stats",
        check_lambda=lambda stats: all(
            stats.get(f"skill_{s}", 0) >= 90
            for s in [
                "empathy", "knowledge", "objection_handling", "stress_resistance",
                "closing", "qualification", "time_management", "adaptation",
                "legal_knowledge", "rapport_building",
            ]
        ),
    ),

    # ═══ CHALLENGES ═══
    AchievementDef(
        slug="stress_test", title="Стрессоустойчивый",
        description="Закрыл сделку с hostile/aggressive при difficulty >= 5",
        icon="zap", rarity="common", category="basic", data_source="stats",
        check_fn="check_deal_with_archetype",
        conditions={"archetypes": ["hostile", "aggressive"], "min_difficulty": 5},
    ),
    AchievementDef(
        slug="comeback", title="Камбэк",
        description="Закрыл сделку после серии из 5+ плохих ответов",
        icon="refresh", rarity="uncommon", category="basic", data_source="stats",
        check_fn="check_comeback",
        conditions={"min_bad_streak": 5},
    ),
    AchievementDef(
        slug="speedrun", title="Спринтер",
        description="Закрыл сделку менее чем за 5 минут",
        icon="timer", rarity="common", category="basic", data_source="stats",
        check_fn="check_deal_under_time",
        conditions={"max_seconds": 300},
    ),
    AchievementDef(
        slug="expert_killer", title="Экспертоборец",
        description="Закрыл сделку с know_it_all при difficulty >= 8",
        icon="sword", rarity="rare", category="basic", data_source="stats",
        check_fn="check_deal_with_archetype",
        conditions={"archetypes": ["know_it_all"], "min_difficulty": 8},
    ),
    AchievementDef(
        slug="rescue_hero", title="Спасатель",
        description="Закрыл сделку в сценарии rescue при difficulty >= 6",
        icon="life-buoy", rarity="rare", category="basic", data_source="stats",
        check_fn="check_deal_with_scenario",
        conditions={"scenarios": ["rescue"], "min_difficulty": 6},
    ),
    AchievementDef(
        slug="couple_tamer", title="Укротитель пар",
        description="Закрыл сделку в сценарии couple_call",
        icon="users", rarity="rare", category="basic", data_source="stats",
        check_fn="check_deal_with_scenario",
        conditions={"scenarios": ["special_couple"]},
    ),
    AchievementDef(
        slug="boss_slayer", title="Убийца боссов",
        description="Закрыл сделку при активном boss_mode (good_streak >= 15)",
        icon="skull", rarity="epic", category="basic", data_source="stats",
        check_fn="check_deal_in_boss_mode",
        conditions={"min_good_streak": 15},
    ),
    AchievementDef(
        slug="mercy_to_deal", title="Из пепла",
        description="Закрыл сделку после активации mercy_deal",
        icon="phoenix", rarity="epic", category="basic", data_source="stats",
        check_fn="check_deal_after_mercy",
    ),
    AchievementDef(
        slug="difficulty_10_deal", title="Максимум",
        description="Закрыл сделку на difficulty 10",
        icon="mountain", rarity="rare", category="basic", data_source="stats",
        check_fn="check_deal_at_difficulty",
        conditions={"difficulty": 10},
    ),
    AchievementDef(
        slug="difficulty_10_perfect", title="Абсолют",
        description="Score >= 90 на difficulty 10",
        icon="gem", rarity="legendary", category="basic", data_source="stats",
        check_fn="check_score_at_difficulty",
        conditions={"min_score": 90, "difficulty": 10},
    ),
    AchievementDef(
        slug="diff_3_deal", title="Первая ступень",
        description="Закрыл сделку на difficulty 3",
        icon="step-forward", rarity="common", category="basic", data_source="stats",
        check_fn="check_deal_at_difficulty",
        conditions={"difficulty": 3},
    ),
    AchievementDef(
        slug="diff_5_deal", title="Средний уровень",
        description="Закрыл сделку на difficulty 5",
        icon="step-forward", rarity="common", category="basic", data_source="stats",
        check_fn="check_deal_at_difficulty",
        conditions={"difficulty": 5},
    ),
    AchievementDef(
        slug="diff_7_deal", title="Высшая лига",
        description="Закрыл сделку на difficulty 7",
        icon="step-forward", rarity="uncommon", category="basic", data_source="stats",
        check_fn="check_deal_at_difficulty",
        conditions={"difficulty": 7},
    ),
    AchievementDef(
        slug="resistance_breaker", title="Укротитель сопротивления",
        description="Закрыл сделку с архетипом из группы сопротивления",
        icon="shield-off", rarity="common", category="basic", data_source="stats",
        check_fn="check_deal_with_archetype_group",
        conditions={"group": "resistance"},
    ),
    AchievementDef(
        slug="emotional_handler", title="Эмоциональный мастер",
        description="Закрыл сделку с архетипом из эмоциональной группы",
        icon="heart", rarity="common", category="basic", data_source="stats",
        check_fn="check_deal_with_archetype_group",
        conditions={"group": "emotional"},
    ),
    AchievementDef(
        slug="control_dominator", title="Обуздатель контроля",
        description="Закрыл сделку с архетипом из группы контроля",
        icon="sliders", rarity="common", category="basic", data_source="stats",
        check_fn="check_deal_with_archetype_group",
        conditions={"group": "control"},
    ),
    AchievementDef(
        slug="avoidance_catcher", title="Ловец уклонистов",
        description="Закрыл сделку с архетипом из группы уклонения",
        icon="crosshair", rarity="common", category="basic", data_source="stats",
        check_fn="check_deal_with_archetype_group",
        conditions={"group": "avoidance"},
    ),
    AchievementDef(
        slug="all_groups_dealt", title="Мастер всех групп",
        description="Закрыл сделки со всеми группами архетипов (мин. 10 в каждой)",
        icon="grid", rarity="rare", category="basic", data_source="stats",
        check_fn="check_deal_all_archetype_groups",
        conditions={"min_count": 10},
    ),
    AchievementDef(
        slug="outbound_cold_complete", title="Холодный мастер",
        description="Прошёл все сценарии группы A — исходящие холодные",
        icon="snowflake", rarity="uncommon", category="basic", data_source="stats",
        check_fn="check_scenario_group_complete",
        conditions={"group": "A_outbound_cold"},
    ),
    AchievementDef(
        slug="outbound_warm_complete", title="Тёплый мастер",
        description="Прошёл все сценарии группы B — исходящие тёплые",
        icon="sun", rarity="uncommon", category="basic", data_source="stats",
        check_fn="check_scenario_group_complete",
        conditions={"group": "B_outbound_warm"},
    ),
    AchievementDef(
        slug="inbound_complete", title="Входящий мастер",
        description="Прошёл все сценарии группы C — входящие",
        icon="phone-incoming", rarity="uncommon", category="basic", data_source="stats",
        check_fn="check_scenario_group_complete",
        conditions={"group": "C_inbound"},
    ),
    AchievementDef(
        slug="special_complete", title="Спец по спецам",
        description="Прошёл все сценарии группы D — спецсценарии",
        icon="star", rarity="rare", category="basic", data_source="stats",
        check_fn="check_scenario_group_complete",
        conditions={"group": "D_special"},
    ),
    AchievementDef(
        slug="compound_deal", title="Укротитель гибрида",
        description="Закрыл сделку с гибридным архетипом (2+ компонента)",
        icon="layers", rarity="rare", category="basic", data_source="stats",
        check_fn="check_compound_archetype_deal",
        conditions={"min_components": 2},
    ),
    AchievementDef(
        slug="ultimate_deal", title="Победитель Ultimate",
        description="Закрыл сделку с гибридным архетипом (3+ компонента)",
        icon="layers", rarity="epic", category="basic", data_source="stats",
        check_fn="check_compound_archetype_deal",
        conditions={"min_components": 3},
    ),
    AchievementDef(
        slug="solo_legend", title="Одинокий волк",
        description="Score >= 90, difficulty 10, гибрид, без подсказок",
        icon="wolf", rarity="legendary", category="basic", data_source="stats",
        check_fn="check_solo_legend",
    ),

    # ═══ PROGRESSION ═══
    AchievementDef(
        slug="archetypes_25", title="Знакомец",
        description="Сыграл 25 разных архетипов",
        icon="users", rarity="uncommon", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("unique_archetypes", 0) >= 25,
    ),
    AchievementDef(
        slug="archetypes_50", title="Универсал",
        description="Сыграл 50 разных архетипов",
        icon="users", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("unique_archetypes", 0) >= 50,
    ),
    AchievementDef(
        slug="archetypes_75", title="Энциклопедист",
        description="Сыграл 75 разных архетипов",
        icon="users", rarity="epic", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("unique_archetypes", 0) >= 75,
    ),
    AchievementDef(
        slug="archetypes_100", title="Мастер всех архетипов",
        description="Сыграл все 100 архетипов",
        icon="users", rarity="legendary", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("unique_archetypes", 0) >= 100,
    ),
    AchievementDef(
        slug="archetypes_50_v2", title="Коллекционер",
        description="Сыграл 50 уникальных архетипов (v2)",
        icon="users", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("unique_archetypes", 0) >= 50,
    ),
    AchievementDef(
        slug="archetypes_100_v2", title="Полная коллекция",
        description="Сыграл 100 уникальных архетипов (v2)",
        icon="users", rarity="epic", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("unique_archetypes", 0) >= 100,
    ),
    AchievementDef(
        slug="scenarios_15", title="Путешественник",
        description="Сыграл 15 разных сценариев",
        icon="map", rarity="uncommon", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("unique_scenarios", 0) >= 15,
    ),
    AchievementDef(
        slug="scenarios_30", title="Исследователь",
        description="Сыграл 30 разных сценариев",
        icon="map", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("unique_scenarios", 0) >= 30,
    ),
    AchievementDef(
        slug="scenarios_45", title="Первопроходец",
        description="Сыграл 45 разных сценариев",
        icon="map", rarity="epic", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("unique_scenarios", 0) >= 45,
    ),
    AchievementDef(
        slug="scenarios_60", title="Мастер всех сценариев",
        description="Сыграл все 60 сценариев",
        icon="map", rarity="legendary", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("unique_scenarios", 0) >= 60,
    ),
    AchievementDef(
        slug="scenarios_30_v2", title="Полпути",
        description="Сыграл 30 уникальных сценариев (v2)",
        icon="map", rarity="uncommon", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("unique_scenarios", 0) >= 30,
    ),
    AchievementDef(
        slug="weekly_warrior", title="Боец недели",
        description="20+ сессий за одну неделю",
        icon="calendar", rarity="uncommon", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("sessions_this_week", 0) >= 20,
    ),
    AchievementDef(
        slug="daily_grind", title="Ежедневная практика",
        description="7 дней подряд хотя бы по 1 сессии",
        icon="calendar-check", rarity="common", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("streak", 0) >= 7,
    ),
    AchievementDef(
        slug="level_15", title="Капитан",
        description="Достиг 15 уровня",
        icon="shield-check", rarity="epic", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("level", 0) >= 15,
    ),
    AchievementDef(
        slug="epoch_1_complete", title="Эпоха новичка",
        description="Завершил Эпоху I (уровни 1-5)",
        icon="milestone", rarity="uncommon", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("level", 0) >= 6,
    ),
    AchievementDef(
        slug="epoch_2_complete", title="Эпоха роста",
        description="Завершил Эпоху II (уровни 6-10)",
        icon="milestone", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("level", 0) >= 11,
    ),
    AchievementDef(
        slug="epoch_3_complete", title="Эпоха мастерства",
        description="Завершил Эпоху III (уровни 11-15)",
        icon="milestone", rarity="epic", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("level", 0) >= 16,
    ),
    AchievementDef(
        slug="epoch_4_complete", title="Эпоха легенды",
        description="Завершил Эпоху IV (уровни 16-20)",
        icon="crown", rarity="legendary", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("level", 0) >= 20,
    ),

    # ═══ ARENA (new codes) ═══
    AchievementDef(
        slug="arena_first_win", title="Первая победа",
        description="Выиграл первый PvP-матч на арене",
        icon="sword", rarity="common", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_pvp_wins", 0) >= 1,
    ),
    AchievementDef(
        slug="arena_win_streak_5", title="Серия побед",
        description="5 побед подряд на арене",
        icon="flame", rarity="rare", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_best_win_streak", 0) >= 5,
    ),
    AchievementDef(
        slug="arena_win_streak_10", title="Непобедимый боец",
        description="10 побед подряд на арене",
        icon="flame", rarity="epic", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_best_win_streak", 0) >= 10,
    ),
    AchievementDef(
        slug="arena_duelist_10", title="Дуэлянт",
        description="Выиграл 10 PvP-матчей на арене",
        icon="sword", rarity="uncommon", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_pvp_wins", 0) >= 10,
    ),
    AchievementDef(
        slug="arena_duelist_50", title="Гладиатор",
        description="Выиграл 50 PvP-матчей на арене",
        icon="sword", rarity="rare", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_pvp_wins", 0) >= 50,
    ),
    AchievementDef(
        slug="arena_tier_silver", title="Серебряный боец",
        description="Достиг серебряного тира на арене",
        icon="shield", rarity="uncommon", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_rank_tier", "") in (
            "silver_3", "silver_2", "silver_1", "gold_3", "gold_2", "gold_1",
            "platinum_3", "platinum_2", "platinum_1", "diamond_3", "diamond_2", "diamond_1",
            "master_3", "master_2", "master_1", "grandmaster",
        ),
    ),
    AchievementDef(
        slug="arena_tier_gold", title="Золотой боец",
        description="Достиг золотого тира на арене",
        icon="shield", rarity="rare", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_rank_tier", "") in (
            "gold_3", "gold_2", "gold_1",
            "platinum_3", "platinum_2", "platinum_1", "diamond_3", "diamond_2", "diamond_1",
            "master_3", "master_2", "master_1", "grandmaster",
        ),
    ),
    AchievementDef(
        slug="arena_tier_platinum", title="Платиновый боец",
        description="Достиг платинового тира на арене",
        icon="shield", rarity="epic", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_rank_tier", "") in (
            "platinum_3", "platinum_2", "platinum_1", "diamond_3", "diamond_2", "diamond_1",
            "master_3", "master_2", "master_1", "grandmaster",
        ),
    ),
    AchievementDef(
        slug="arena_tier_diamond", title="Бриллиантовый",
        description="Достиг бриллиантового тира на арене",
        icon="gem", rarity="legendary", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_rank_tier", "") in (
            "diamond_3", "diamond_2", "diamond_1",
            "master_3", "master_2", "master_1", "grandmaster",
        ),
    ),
    AchievementDef(
        slug="arena_classic_win", title="Классик",
        description="Победил в классическом режиме арены",
        icon="trophy", rarity="common", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_mode_wins", {}).get("classic", 0) >= 1,
    ),
    AchievementDef(
        slug="arena_rapid_win", title="Молниеносный",
        description="Победил в режиме rapid fire на арене",
        icon="zap", rarity="common", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_mode_wins", {}).get("rapid_fire", 0) >= 1,
    ),
    AchievementDef(
        slug="arena_gauntlet_win", title="Испытатель",
        description="Победил в режиме gauntlet на арене",
        icon="shield", rarity="uncommon", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_mode_wins", {}).get("gauntlet", 0) >= 1,
    ),
    AchievementDef(
        slug="arena_team_win", title="Командный боец",
        description="Победил в режиме командного боя на арене",
        icon="users", rarity="uncommon", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_mode_wins", {}).get("team_battle", 0) >= 1,
    ),
    AchievementDef(
        slug="arena_blitz_perfect", title="Идеальный блиц",
        description="Идеальное прохождение блиц-режима на арене",
        icon="zap", rarity="epic", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_blitz_perfect", False) is True,
    ),
    AchievementDef(
        slug="arena_all_categories", title="Эрудит",
        description="Освоил 10 категорий с точностью >= 80% на арене",
        icon="book-open", rarity="rare", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("categories_above_80", 0) >= 10,
    ),
    AchievementDef(
        slug="arena_first_tournament", title="Турнирный боец",
        description="Принял участие в первом турнире",
        icon="trophy", rarity="uncommon", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_tournaments_participated", 0) >= 1,
    ),
    AchievementDef(
        slug="arena_podium", title="Подиум",
        description="Занял место в топ-3 на турнире",
        icon="medal", rarity="epic", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_best_tournament_place", 999) <= 3,
    ),
    AchievementDef(
        slug="arena_champion", title="Чемпион турнира",
        description="Занял первое место на турнире",
        icon="crown", rarity="legendary", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("arena_best_tournament_place", 999) <= 1,
    ),

    # ═══ SOCIAL ═══
    AchievementDef(
        slug="first_share", title="Первый шаг",
        description="Первый раз поделился результатом",
        icon="share", rarity="common", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("share_count", 0) >= 1,
    ),
    AchievementDef(
        slug="sharer_5", title="Активный делитель",
        description="Поделился результатами 5 раз",
        icon="share", rarity="common", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("share_count", 0) >= 5,
    ),
    AchievementDef(
        slug="sharer_10", title="Амбассадор",
        description="Поделился результатами 10 раз",
        icon="share", rarity="uncommon", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("share_count", 0) >= 10,
    ),
    AchievementDef(
        slug="challenge_winner_1", title="Первый вызов",
        description="Выиграл первый вызов",
        icon="trophy", rarity="common", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("challenge_wins", 0) >= 1,
    ),
    AchievementDef(
        slug="challenge_winner_5", title="Покоритель вызовов",
        description="Выиграл 5 вызовов",
        icon="trophy", rarity="uncommon", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("challenge_wins", 0) >= 5,
    ),
    AchievementDef(
        slug="challenge_winner_10", title="Непревзойдённый",
        description="Выиграл 10 вызовов",
        icon="trophy", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("challenge_wins", 0) >= 10,
    ),
    AchievementDef(
        slug="mentor_1", title="Наставник",
        description="Помог 1 игроку в роли наставника",
        icon="graduation-cap", rarity="uncommon", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("mentor_count", 0) >= 1,
    ),
    AchievementDef(
        slug="mentor_5", title="Мастер-наставник",
        description="Помог 5 игрокам в роли наставника",
        icon="graduation-cap", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("mentor_count", 0) >= 5,
    ),
    AchievementDef(
        slug="mentor_10", title="Гуру наставничества",
        description="Помог 10 игрокам в роли наставника",
        icon="graduation-cap", rarity="epic", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("mentor_count", 0) >= 10,
    ),
    AchievementDef(
        slug="team_challenge_win", title="Командная победа",
        description="Выиграл командный вызов",
        icon="users", rarity="uncommon", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("team_challenge_wins", 0) >= 1,
    ),
    AchievementDef(
        slug="team_streak_3", title="Командный дух",
        description="3 командных победы подряд",
        icon="flame", rarity="rare", category="basic", data_source="stats",
        check_lambda=lambda stats: stats.get("team_challenge_streak", 0) >= 3,
    ),
    AchievementDef(
        slug="community_10", title="Общительный",
        description="Сыграл против 10 разных соперников",
        icon="users", rarity="common", category="basic", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("unique_opponents", 0) >= 10,
    ),
    AchievementDef(
        slug="community_25", title="Сетевик",
        description="Сыграл против 25 разных соперников",
        icon="users", rarity="uncommon", category="basic", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("unique_opponents", 0) >= 25,
    ),
    AchievementDef(
        slug="community_50", title="Социальная звезда",
        description="Сыграл против 50 разных соперников",
        icon="users", rarity="rare", category="basic", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("unique_opponents", 0) >= 50,
    ),

    # ═══ NARRATIVE (new) ═══
    AchievementDef(
        slug="first_story_complete", title="Первая история",
        description="Завершил первую историю",
        icon="book", rarity="uncommon", category="narrative", data_source="stats",
        check_lambda=lambda stats: stats.get("stories_completed", 0) >= 1,
    ),
    AchievementDef(
        slug="stories_5", title="Рассказчик",
        description="Завершил 5 историй",
        icon="book", rarity="rare", category="narrative", data_source="stats",
        check_lambda=lambda stats: stats.get("stories_completed", 0) >= 5,
    ),
    AchievementDef(
        slug="story_perfect", title="Идеальная история",
        description="Набрал 90+ баллов за историю",
        icon="star", rarity="rare", category="narrative", data_source="stats",
        check_lambda=lambda stats: stats.get("best_story_score", 0) >= 90,
    ),
    AchievementDef(
        slug="crm_portfolio_5", title="Начинающий портфель",
        description="Собрал портфель из 5 клиентов в CRM",
        icon="briefcase", rarity="common", category="narrative", data_source="stats",
        check_lambda=lambda stats: stats.get("crm_portfolio_size", 0) >= 5,
    ),
    AchievementDef(
        slug="crm_portfolio_10", title="Растущий портфель",
        description="Собрал портфель из 10 клиентов в CRM",
        icon="briefcase", rarity="uncommon", category="narrative", data_source="stats",
        check_lambda=lambda stats: stats.get("crm_portfolio_size", 0) >= 10,
    ),
    AchievementDef(
        slug="crm_portfolio_20", title="Зрелый портфель",
        description="Собрал портфель из 20 клиентов в CRM",
        icon="briefcase", rarity="rare", category="narrative", data_source="stats",
        check_lambda=lambda stats: stats.get("crm_portfolio_size", 0) >= 20,
    ),
    AchievementDef(
        slug="full_arc_deal", title="Полная дуга",
        description="Завершил полную сюжетную дугу сделки",
        icon="route", rarity="rare", category="narrative", data_source="game_director",
        check_fn="check_full_arc_deal",
    ),
    AchievementDef(
        slug="the_comeback_story", title="Великий камбэк",
        description="Нарративное событие: великий камбэк",
        icon="refresh", rarity="legendary", category="narrative", data_source="game_director",
        check_fn="check_the_comeback_story",
    ),

    # ═══ SECRET ═══
    AchievementDef(
        slug="night_owl", title="Полуночник",
        description="Тренировался глубокой ночью 3 раза",
        icon="moon", rarity="uncommon", category="basic", data_source="stats",
        check_fn="check_time_of_day",
        conditions={"after_hour": 0, "before_hour": 5, "count": 3},
    ),
    AchievementDef(
        slug="early_bird", title="Ранняя пташка",
        description="Тренировался ранним утром 3 раза",
        icon="sunrise", rarity="uncommon", category="basic", data_source="stats",
        check_fn="check_time_of_day",
        conditions={"after_hour": 5, "before_hour": 7, "count": 3},
    ),
    AchievementDef(
        slug="fake_survivor", title="Не на того напал",
        description="Пережил 3 фейковых перехода подряд",
        icon="shield-alert", rarity="rare", category="basic", data_source="stats",
        check_fn="check_consecutive_fake_survive",
        conditions={"count": 3},
    ),
    AchievementDef(
        slug="skeptic_vs_paranoid", title="Параноик vs скептик",
        description="Особая комбинация: параноик + холодный базовый",
        icon="sparkles", rarity="rare", category="basic", data_source="stats",
        check_fn="check_specific_combo",
        conditions={"archetype": "paranoid", "scenario": "cold_base"},
    ),
    AchievementDef(
        slug="lawyer_vs_lawyer", title="Юрист vs юрист",
        description="Особая комбинация: клиент-юрист + юрист на проводе",
        icon="scale", rarity="rare", category="basic", data_source="stats",
        check_fn="check_specific_combo",
        conditions={"archetype": "lawyer_client", "scenario": "special_lawyer_on_line"},
    ),
    AchievementDef(
        slug="crying_rescue", title="Спаси и сохрани",
        description="Особая комбинация: плачущий клиент + сценарий rescue",
        icon="heart", rarity="rare", category="basic", data_source="stats",
        check_fn="check_specific_combo",
        conditions={"archetype": "crying", "scenario": "rescue"},
    ),
    AchievementDef(
        slug="short_talks_anti", title="Короткие разговоры (анти)",
        description="Клиент бросил трубку 3 раза подряд",
        icon="phone-off", rarity="common", category="anti", data_source="stats",
        check_fn="check_fail_streak",
        conditions={"outcome": "hangup", "count": 3},
        repeatable=True,
        recommendation="Попробуйте говорить мягче и задавать открытые вопросы",
    ),
    AchievementDef(
        slug="diy_lawyer_anti", title="Юрист-самоучка (анти)",
        description="Допустил 3 юридические ошибки за 5 сессий",
        icon="alert-triangle", rarity="common", category="anti", data_source="scoring_service",
        check_fn="check_legal_errors",
        conditions={"count": 3, "within_sessions": 5},
        repeatable=True,
        recommendation="Изучите основы 127-ФЗ в разделе Знания",
    ),
    AchievementDef(
        slug="template_talker_anti", title="По шаблону (анти)",
        description="5 сессий подряд с низкой вариативностью ответов",
        icon="copy", rarity="common", category="anti", data_source="scoring_service",
        check_fn="check_low_variability_streak",
        conditions={"count": 5},
        repeatable=True,
        recommendation="Старайтесь адаптировать ответы под клиента",
    ),
    AchievementDef(
        slug="weekend_warrior", title="Выходной боец",
        description="Провёл 10 сессий в выходные дни",
        icon="calendar", rarity="uncommon", category="basic", data_source="stats",
        check_fn="check_weekend_sessions",
        conditions={"count": 10},
    ),

    # ═══ PVE ═══
    AchievementDef(
        slug="pve_first_bot_win", title="Первая победа над ботом",
        description="Выиграл PvE-дуэль",
        icon="bot", rarity="common", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("pve_wins", 0) >= 1,
    ),
    AchievementDef(
        slug="pve_ladder_conqueror", title="Покоритель лестницы",
        description="Победил все 5 ботов в Bot Ladder",
        icon="ladder", rarity="rare", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("pve_ladder_all_defeated", False) is True,
    ),
    AchievementDef(
        slug="pve_ladder_perfect", title="Идеальная лестница",
        description="Bot Ladder с cumulative score > 400",
        icon="ladder", rarity="epic", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("pve_ladder_best_score", 0) > 400,
    ),
    AchievementDef(
        slug="pve_boss_slayer", title="Победитель боссов",
        description="Победил все 3 босса в Boss Rush",
        icon="skull", rarity="epic", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("pve_bosses_defeated", 0) >= 3,
    ),
    AchievementDef(
        slug="pve_boss_perfectionist", title="Безупречный юрист",
        description="Победил Юриста без единой ошибки",
        icon="scale", rarity="rare", category="arena", data_source="arena_stats",
        check_fn="check_pve_boss_flawless",
        conditions={"boss_type": "perfectionist"},
    ),
    AchievementDef(
        slug="pve_boss_composure", title="Стальные нервы (босс)",
        description="Победил Вампира с composure > 50%",
        icon="shield-check", rarity="rare", category="arena", data_source="arena_stats",
        check_fn="check_pve_boss_composure",
        conditions={"min_composure": 50},
    ),
    AchievementDef(
        slug="pve_boss_chameleon", title="Мастер адаптации (босс)",
        description="Победил Хамелеона с score > 70",
        icon="refresh", rarity="rare", category="arena", data_source="arena_stats",
        check_fn="check_pve_boss_score",
        conditions={"boss_type": "chameleon", "min_score": 70},
    ),
    AchievementDef(
        slug="pve_training_10", title="Прилежный ученик",
        description="Провёл 10 тренировочных матчей",
        icon="book", rarity="common", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("pve_training_count", 0) >= 10,
    ),
    AchievementDef(
        slug="pve_mirror_win", title="Превзошёл себя",
        description="Победил своё зеркало",
        icon="copy", rarity="rare", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("pve_mirror_wins", 0) >= 1,
    ),
    AchievementDef(
        slug="pve_mirror_streak_3", title="Триумф над собой",
        description="Победил зеркало 3 раза подряд",
        icon="copy", rarity="epic", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("pve_mirror_best_streak", 0) >= 3,
    ),
    AchievementDef(
        slug="pve_all_modes", title="Мастер PvE",
        description="Победил в каждом из 5 PvE-режимов",
        icon="grid", rarity="epic", category="arena", data_source="arena_stats",
        check_lambda=lambda stats: stats.get("pve_modes_won", 0) >= 5,
    ),

    # ═══ CROSS-SYSTEM ═══
    AchievementDef(
        slug="cross_bridge", title="Мост",
        description="Тренировка + PvP-дуэль в один день",
        icon="link", rarity="rare", category="arena", data_source="stats",
        check_fn="check_cross_same_day",
        conditions={"activity_a": "training", "activity_b": "pvp_duel"},
    ),
    AchievementDef(
        slug="cross_academic_warrior", title="Академик-воин",
        description="Score 80+ в Quiz + выиграть PvP в один день",
        icon="book-sword", rarity="rare", category="arena", data_source="stats",
        check_fn="check_cross_same_day",
        conditions={"activity_a": "knowledge_80", "activity_b": "pvp_win"},
    ),
    AchievementDef(
        slug="cross_full_cycle", title="Полный цикл",
        description="Потренировать архетип -> встретить в PvP -> победить",
        icon="refresh", rarity="epic", category="arena", data_source="stats",
        check_fn="check_cross_full_cycle",
    ),
    AchievementDef(
        slug="cross_theory_practice", title="Теория и практика",
        description="Quiz 90%+ в категории + score 80+ в тренировке с ловушками",
        icon="book-check", rarity="epic", category="arena", data_source="stats",
        check_fn="check_cross_theory_practice",
    ),
    AchievementDef(
        slug="cross_comeback", title="Путь реванша",
        description="Проиграть PvP -> 3 тренировки -> победить в PvP",
        icon="refresh", rarity="legendary", category="arena", data_source="stats",
        check_fn="check_cross_revenge",
    ),
    AchievementDef(
        slug="cross_triple_threat", title="Тройная угроза",
        description="Score 80+ + PvP win + Quiz 90% в один день",
        icon="crown", rarity="legendary", category="arena", data_source="stats",
        check_fn="check_cross_triple_threat",
    ),
    AchievementDef(
        slug="cross_mentor", title="Наставник (кросс)",
        description="Помочь 3 игрокам через менторский режим (уровень 15+)",
        icon="graduation-cap", rarity="epic", category="arena", data_source="stats",
        check_lambda=lambda stats: (
            stats.get("mentor_count", 0) >= 3
            and stats.get("level", 0) >= 15
        ),
    ),
]

# Combined registry
ALL_ACHIEVEMENT_DEFS: list[AchievementDef] = (
    BASIC_ACHIEVEMENTS + NARRATIVE_ACHIEVEMENTS + ANTI_ACHIEVEMENTS
    + ARENA_ACHIEVEMENTS + TEAM_ACHIEVEMENTS + SEED_ACHIEVEMENTS
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
            # ── v5 Seed-aligned checks ──
            # SessionHistory-based challenges
            "check_deal_with_archetype": self._check_deal_with_archetype,
            "check_deal_with_scenario": self._check_deal_with_scenario,
            "check_deal_at_difficulty": self._check_deal_at_difficulty,
            "check_score_at_difficulty": self._check_score_at_difficulty,
            "check_deal_in_boss_mode": self._check_deal_in_boss_mode,
            "check_deal_after_mercy": self._check_deal_after_mercy,
            "check_comeback": self._check_comeback_session,
            "check_deal_under_time": self._check_deal_under_time,
            "check_deal_with_archetype_group": self._check_deal_with_archetype_group,
            "check_deal_all_archetype_groups": self._check_deal_all_archetype_groups,
            "check_scenario_group_complete": self._check_scenario_group_complete,
            "check_compound_archetype_deal": self._check_compound_archetype_deal,
            "check_solo_legend": self._check_solo_legend,
            # Skill-pattern checks
            "check_trap_dodge_streak": self._check_trap_dodge_streak,
            "check_chain_completion_streak": self._check_chain_completion_streak,
            "check_zero_antipatterns": self._check_zero_antipatterns,
            "check_zero_antipatterns_streak": self._check_zero_antipatterns_streak,
            # Secret / time-based
            "check_time_of_day": self._check_time_of_day,
            "check_weekend_sessions": self._check_weekend_sessions,
            "check_consecutive_fake_survive": self._check_consecutive_fake_survive,
            "check_specific_combo": self._check_specific_combo,
            "check_fail_streak": self._check_fail_streak,
            "check_legal_errors": self._check_legal_errors,
            "check_low_variability_streak": self._check_low_variability_streak,
            # Narrative
            "check_full_arc_deal": self._check_full_arc_deal,
            "check_the_comeback_story": self._check_the_comeback_story,
            # PvE
            "check_pve_boss_flawless": self._check_pve_boss_flawless,
            "check_pve_boss_composure": self._check_pve_boss_composure,
            "check_pve_boss_score": self._check_pve_boss_score,
            # Cross-system
            "check_cross_same_day": self._check_cross_same_day,
            "check_cross_full_cycle": self._check_cross_full_cycle,
            "check_cross_theory_practice": self._check_cross_theory_practice,
            "check_cross_revenge": self._check_cross_revenge,
            "check_cross_triple_threat": self._check_cross_triple_threat,
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
                    passed = await self._checks[defn.check_fn](user_id, db, stats, defn.conditions)
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
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Legendary: closed deal with client who had 'wife_found_debts' storylet active."""
        if not self._game_director:
            return False
        return await self._game_director.check_storylet_deal(
            user_id, storylet_type="wife_found_debts"
        )

    async def _check_master_of_callbacks(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Epic: 5 clients converted CALLBACK_SCHEDULED → MEETING_SET without GHOSTING."""
        if not self._game_director:
            return False
        count = await self._game_director.count_callback_conversions(
            user_id, without_ghosting=True
        )
        return count >= 5

    async def _check_anger_whisperer(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Epic: de-escalated 3 clients from hostile to curious+ in a single call."""
        if not self._scoring:
            return False
        count = await self._scoring.count_deescalations(
            user_id, from_state="hostile", to_min_state="curious"
        )
        return count >= 3

    async def _check_memory_keeper(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Rare: passed all memory_check traps in a 5+ call story arc."""
        if not self._traps:
            return False
        return await self._traps.check_memory_keeper(
            user_id, min_calls_in_arc=5
        )

    async def _check_legal_eagle(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
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
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Legendary: reactivated client from REJECTED to DEAL_CLOSED."""
        if not self._game_director:
            return False
        return await self._game_director.check_lifecycle_transition(
            user_id, from_state="REJECTED", to_state="DEAL_CLOSED"
        )

    # ── Anti-achievement checks ──────────────────────────────────────────────

    async def _check_short_talks(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
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
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
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
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
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
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Rare: completed all 7 sales stages in a single session."""
        result = await db.execute(
            select(TrainingSession.scoring_details).where(
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
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Rare: completed a full 5-call story."""
        result = await db.execute(
            select(TrainingSession.scoring_details).where(
                TrainingSession.user_id == user_id,
                TrainingSession.status == SessionStatus.completed,
                TrainingSession.client_story_id.isnot(None),
            ).order_by(TrainingSession.started_at.desc()).limit(20)
        )
        for (details,) in result.all():
            if not details or not isinstance(details, dict):
                continue
            call_number = details.get("call_number_in_story", 0)
            total_calls = details.get("total_calls_planned", 0)
            if call_number >= 5 and call_number >= total_calls:
                return True
        return False

    async def _check_perfect_qualification(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Common: 100% quality on qualification stage."""
        result = await db.execute(
            select(TrainingSession.scoring_details).where(
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
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
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
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Rare: scored 80+ without using any hints."""
        result = await db.execute(
            select(TrainingSession.score_total, TrainingSession.scoring_details).where(
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
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Rare: completed all archetypes on easy difficulty (≤3)."""
        return await self._check_all_archetypes_at_difficulty(user_id, db, max_difficulty=3)

    async def _check_all_archetypes_hard(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
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
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Rare (repeatable): user's team is #1 by avg score this week."""
        from app.models.user import User, Team

        # Get user's team
        user_result = await db.execute(select(User.team_id).where(User.id == user_id))
        team_id = user_result.scalar()
        if not team_id:
            return False

        week_ago = datetime.now(timezone.utc) - timedelta(days=7)

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
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
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
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
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

    # ── v5 Seed-aligned achievement checks ──────────────────────────────────

    # --- Archetype-group mapping (canonical from progress.py ALL_ARCHETYPES) ---
    _ARCHETYPE_GROUPS: dict[str, list[str]] = {
        "resistance": [
            "skeptic", "blamer", "sarcastic", "aggressive", "hostile",
            "stubborn", "conspiracy", "righteous", "litigious", "scorched_earth",
        ],
        "emotional": [
            "grateful", "anxious", "ashamed", "overwhelmed", "desperate",
            "crying", "guilty", "mood_swinger", "frozen", "hysteric",
        ],
        "control": [
            "pragmatic", "shopper", "negotiator", "know_it_all", "manipulator",
            "lawyer_client", "auditor", "strategist", "power_player", "puppet_master",
        ],
        "avoidance": [
            "passive", "delegator", "avoidant", "paranoid",
            "procrastinator", "ghosting", "deflector", "agreeable_ghost", "fortress", "smoke_screen",
        ],
        "special": [
            "referred", "returner", "rushed", "couple",
            "elderly", "young_debtor", "foreign_speaker", "intermediary", "repeat_caller", "celebrity",
        ],
        "cognitive": [
            "overthinker", "concrete", "storyteller", "misinformed", "selective_listener",
            "black_white", "memory_issues", "technical", "magical_thinker", "lawyer_level_2",
        ],
        "social": [
            "family_man", "influenced", "reputation_guard", "community_leader", "breadwinner",
            "divorced", "guarantor", "widow", "caregiver", "multi_debtor_family",
        ],
        "temporal": [
            "just_fired", "collector_call", "court_notice", "salary_arrest", "pre_court",
            "post_refusal", "inheritance_trap", "business_collapse", "medical_crisis", "criminal_risk",
        ],
        "professional": [
            "teacher", "doctor", "military", "accountant", "salesperson",
            "it_specialist", "government", "journalist", "psychologist", "competitor_employee",
        ],
        "compound": [
            "aggressive_desperate", "manipulator_crying", "know_it_all_paranoid", "passive_aggressive",
            "couple_disagreeing", "elderly_paranoid", "hysteric_litigious", "puppet_master_lawyer",
            "shifting", "ultimate",
        ],
    }

    # --- Scenario-group mapping ---
    _SCENARIO_GROUPS: dict[str, list[str]] = {
        "A_outbound_cold": [
            "cold_ad", "cold_referral", "cold_social", "cold_database", "cold_base",
            "cold_partner", "cold_premium", "cold_event", "cold_expired", "cold_insurance",
        ],
        "B_outbound_warm": [
            "warm_callback", "warm_noanswer", "warm_refused", "warm_dropped",
            "warm_repeat", "warm_webinar", "warm_vip", "warm_ghosted", "warm_complaint", "warm_competitor",
        ],
        "C_inbound": [
            "in_website", "in_hotline", "in_social", "in_chatbot",
            "in_partner", "in_complaint", "in_urgent", "in_corporate",
        ],
        "D_special": [
            "special_ghosted", "special_urgent", "special_guarantor", "special_couple",
            "upsell", "rescue", "special_inheritance", "vip_debtor",
            "special_psychologist", "special_vip", "special_medical", "special_boss",
        ],
    }

    # --- SessionHistory-based challenges ---

    async def _check_deal_with_archetype(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Deal with specific archetype(s), optionally at min difficulty."""
        from app.models.progress import SessionHistory
        if not conditions:
            return False
        archetypes = conditions.get("archetypes", [])
        min_diff = conditions.get("min_difficulty", 0)
        result = await db.execute(
            select(SessionHistory.id).where(
                SessionHistory.user_id == user_id,
                SessionHistory.outcome == "deal",
                SessionHistory.archetype_code.in_(archetypes),
                SessionHistory.difficulty >= min_diff,
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _check_deal_with_scenario(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Deal in specific scenario(s), optionally at min difficulty."""
        from app.models.progress import SessionHistory
        if not conditions:
            return False
        scenarios = conditions.get("scenarios", [])
        min_diff = conditions.get("min_difficulty", 0)
        result = await db.execute(
            select(SessionHistory.id).where(
                SessionHistory.user_id == user_id,
                SessionHistory.outcome == "deal",
                SessionHistory.scenario_code.in_(scenarios),
                SessionHistory.difficulty >= min_diff,
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _check_deal_at_difficulty(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Deal at exact difficulty level."""
        from app.models.progress import SessionHistory
        if not conditions:
            return False
        diff = conditions.get("difficulty", 10)
        result = await db.execute(
            select(SessionHistory.id).where(
                SessionHistory.user_id == user_id,
                SessionHistory.outcome == "deal",
                SessionHistory.difficulty == diff,
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _check_score_at_difficulty(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Score >= X at exact difficulty."""
        from app.models.progress import SessionHistory
        if not conditions:
            return False
        min_score = conditions.get("min_score", 90)
        diff = conditions.get("difficulty", 10)
        result = await db.execute(
            select(SessionHistory.id).where(
                SessionHistory.user_id == user_id,
                SessionHistory.outcome == "deal",
                SessionHistory.score_total >= min_score,
                SessionHistory.difficulty == diff,
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _check_deal_in_boss_mode(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Deal with max_good_streak >= threshold (boss mode indicator)."""
        from app.models.progress import SessionHistory
        min_streak = (conditions or {}).get("min_good_streak", 15)
        result = await db.execute(
            select(SessionHistory.id).where(
                SessionHistory.user_id == user_id,
                SessionHistory.outcome == "deal",
                SessionHistory.max_good_streak >= min_streak,
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _check_deal_after_mercy(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Deal where mercy_activated was True."""
        from app.models.progress import SessionHistory
        result = await db.execute(
            select(SessionHistory.id).where(
                SessionHistory.user_id == user_id,
                SessionHistory.outcome == "deal",
                SessionHistory.mercy_activated.is_(True),
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _check_comeback_session(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Deal where had_comeback is True and max_bad_streak >= threshold."""
        from app.models.progress import SessionHistory
        min_bad = (conditions or {}).get("min_bad_streak", 5)
        result = await db.execute(
            select(SessionHistory.id).where(
                SessionHistory.user_id == user_id,
                SessionHistory.outcome == "deal",
                SessionHistory.had_comeback.is_(True),
                SessionHistory.max_bad_streak >= min_bad,
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _check_deal_under_time(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Deal completed under max_seconds."""
        from app.models.progress import SessionHistory
        max_sec = (conditions or {}).get("max_seconds", 300)
        result = await db.execute(
            select(SessionHistory.id).where(
                SessionHistory.user_id == user_id,
                SessionHistory.outcome == "deal",
                SessionHistory.duration_seconds <= max_sec,
                SessionHistory.duration_seconds > 0,
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _check_deal_with_archetype_group(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Deal with any archetype from a named group."""
        from app.models.progress import SessionHistory
        if not conditions:
            return False
        group_name = conditions.get("group", "")
        group_archetypes = self._ARCHETYPE_GROUPS.get(group_name, [])
        if not group_archetypes:
            return False
        result = await db.execute(
            select(SessionHistory.id).where(
                SessionHistory.user_id == user_id,
                SessionHistory.outcome == "deal",
                SessionHistory.archetype_code.in_(group_archetypes),
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _check_deal_all_archetype_groups(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Deals with all archetype groups, min_count per group."""
        from app.models.progress import SessionHistory
        min_count = (conditions or {}).get("min_count", 10)
        for group_name, group_archetypes in self._ARCHETYPE_GROUPS.items():
            if group_name == "compound":
                continue  # Skip compound group
            result = await db.execute(
                select(func.count(SessionHistory.id)).where(
                    SessionHistory.user_id == user_id,
                    SessionHistory.outcome == "deal",
                    SessionHistory.archetype_code.in_(group_archetypes),
                )
            )
            count = result.scalar() or 0
            if count < min_count:
                return False
        return True

    async def _check_scenario_group_complete(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Completed at least one deal in each scenario of a group."""
        from app.models.progress import SessionHistory
        if not conditions:
            return False
        group_name = conditions.get("group", "")
        group_scenarios = self._SCENARIO_GROUPS.get(group_name, [])
        if not group_scenarios:
            return False
        result = await db.execute(
            select(func.array_agg(func.distinct(SessionHistory.scenario_code))).where(
                SessionHistory.user_id == user_id,
                SessionHistory.outcome == "deal",
                SessionHistory.scenario_code.in_(group_scenarios),
            )
        )
        completed = result.scalar() or []
        return len(set(completed) & set(group_scenarios)) == len(group_scenarios)

    async def _check_compound_archetype_deal(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Deal with a compound archetype (contains underscore separator, X+ components)."""
        from app.models.progress import SessionHistory
        min_components = (conditions or {}).get("min_components", 2)
        compound_archetypes = self._ARCHETYPE_GROUPS.get("compound", [])
        result = await db.execute(
            select(SessionHistory.archetype_code).where(
                SessionHistory.user_id == user_id,
                SessionHistory.outcome == "deal",
                SessionHistory.archetype_code.in_(compound_archetypes),
            )
        )
        for (arch,) in result.all():
            # Count components by underscores in compound names
            parts = arch.split("_")
            if len(parts) >= min_components:
                return True
        return False

    async def _check_solo_legend(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Score >= 90, difficulty 10, compound archetype, no hints."""
        from app.models.progress import SessionHistory
        compound_archetypes = self._ARCHETYPE_GROUPS.get("compound", [])
        result = await db.execute(
            select(SessionHistory.id, SessionHistory.score_breakdown).where(
                SessionHistory.user_id == user_id,
                SessionHistory.outcome == "deal",
                SessionHistory.score_total >= 90,
                SessionHistory.difficulty == 10,
                SessionHistory.archetype_code.in_(compound_archetypes),
            )
        )
        for row_id, breakdown in result.all():
            hints = 0
            if isinstance(breakdown, dict):
                hints = breakdown.get("hints_used", 0)
            if hints == 0:
                return True
        return False

    # --- Skill pattern checks ---

    async def _check_trap_dodge_streak(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Consecutive traps dodged without falling (cumulative across sessions)."""
        from app.models.progress import SessionHistory
        count_needed = (conditions or {}).get("count", 10)
        result = await db.execute(
            select(SessionHistory.traps_dodged, SessionHistory.traps_fell).where(
                SessionHistory.user_id == user_id,
            ).order_by(SessionHistory.created_at.desc()).limit(50)
        )
        consecutive = 0
        for dodged, fell in result.all():
            if fell and fell > 0:
                break  # Streak broken
            consecutive += (dodged or 0)
            if consecutive >= count_needed:
                return True
        return consecutive >= count_needed

    async def _check_chain_completion_streak(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Consecutive sessions where chain_completed is True."""
        from app.models.progress import SessionHistory
        count_needed = (conditions or {}).get("count", 10)
        result = await db.execute(
            select(SessionHistory.chain_completed).where(
                SessionHistory.user_id == user_id,
            ).order_by(SessionHistory.created_at.desc()).limit(count_needed + 5)
        )
        streak = 0
        for (completed,) in result.all():
            if completed:
                streak += 1
                if streak >= count_needed:
                    return True
            else:
                break
        return False

    async def _check_zero_antipatterns(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """At least one session with 0 anti-patterns (anti_patterns score == 0)."""
        from app.models.progress import SessionHistory
        result = await db.execute(
            select(SessionHistory.score_breakdown).where(
                SessionHistory.user_id == user_id,
            ).order_by(SessionHistory.created_at.desc()).limit(20)
        )
        for (breakdown,) in result.all():
            if isinstance(breakdown, dict):
                anti = breakdown.get("anti_patterns", -1)
                if anti is not None and anti == 0:
                    return True
        return False

    async def _check_zero_antipatterns_streak(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Consecutive sessions with 0 anti-patterns."""
        from app.models.progress import SessionHistory
        count_needed = (conditions or {}).get("count", 5)
        result = await db.execute(
            select(SessionHistory.score_breakdown).where(
                SessionHistory.user_id == user_id,
            ).order_by(SessionHistory.created_at.desc()).limit(count_needed + 5)
        )
        streak = 0
        for (breakdown,) in result.all():
            if isinstance(breakdown, dict) and breakdown.get("anti_patterns", -1) == 0:
                streak += 1
                if streak >= count_needed:
                    return True
            else:
                break
        return False

    # --- Secret / time-based ---

    async def _check_time_of_day(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Count sessions started between after_hour and before_hour."""
        from app.models.progress import SessionHistory
        if not conditions:
            return False
        after_h = conditions.get("after_hour", 0)
        before_h = conditions.get("before_hour", 5)
        count_needed = conditions.get("count", 3)
        result = await db.execute(
            select(func.count(SessionHistory.id)).where(
                SessionHistory.user_id == user_id,
                func.extract("hour", SessionHistory.created_at) >= after_h,
                func.extract("hour", SessionHistory.created_at) < before_h,
            )
        )
        return (result.scalar() or 0) >= count_needed

    async def _check_weekend_sessions(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Count sessions on weekends (Saturday=6, Sunday=0 in PostgreSQL dow)."""
        from app.models.progress import SessionHistory
        count_needed = (conditions or {}).get("count", 10)
        result = await db.execute(
            select(func.count(SessionHistory.id)).where(
                SessionHistory.user_id == user_id,
                func.extract("dow", SessionHistory.created_at).in_([0, 6]),
            )
        )
        return (result.scalar() or 0) >= count_needed

    async def _check_consecutive_fake_survive(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Survived N consecutive fake transitions (from score_breakdown data)."""
        from app.models.progress import SessionHistory
        count_needed = (conditions or {}).get("count", 3)
        result = await db.execute(
            select(SessionHistory.score_breakdown).where(
                SessionHistory.user_id == user_id,
            ).order_by(SessionHistory.created_at.desc()).limit(20)
        )
        consecutive = 0
        for (breakdown,) in result.all():
            if not isinstance(breakdown, dict):
                continue
            fake_survived = breakdown.get("fake_transitions_survived", 0)
            if fake_survived and fake_survived > 0:
                consecutive += fake_survived
                if consecutive >= count_needed:
                    return True
            else:
                if consecutive > 0:
                    break  # Streak tracking: stop once we hit a session without fake survives
        return consecutive >= count_needed

    async def _check_specific_combo(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Deal with specific archetype + scenario combination."""
        from app.models.progress import SessionHistory
        if not conditions:
            return False
        archetype = conditions.get("archetype", "")
        scenario = conditions.get("scenario", "")
        result = await db.execute(
            select(SessionHistory.id).where(
                SessionHistory.user_id == user_id,
                SessionHistory.outcome == "deal",
                SessionHistory.archetype_code == archetype,
                SessionHistory.scenario_code == scenario,
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _check_fail_streak(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """N consecutive sessions with specific bad outcome."""
        from app.models.progress import SessionHistory
        if not conditions:
            return False
        outcome = conditions.get("outcome", "hangup")
        count_needed = conditions.get("count", 3)
        result = await db.execute(
            select(SessionHistory.outcome).where(
                SessionHistory.user_id == user_id,
            ).order_by(SessionHistory.created_at.desc()).limit(count_needed)
        )
        outcomes = [row[0] for row in result.all()]
        if len(outcomes) < count_needed:
            return False
        return all(o == outcome for o in outcomes)

    async def _check_legal_errors(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """N legal errors within last M sessions."""
        if not self._scoring:
            return False
        if not conditions:
            return False
        count_needed = conditions.get("count", 3)
        within = conditions.get("within_sessions", 5)
        legal_stats = await self._scoring.get_legal_accuracy_stats(
            user_id, last_n_sessions=within
        )
        if not legal_stats:
            return False
        return legal_stats.get("incorrect_count", 0) >= count_needed

    async def _check_low_variability_streak(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """N consecutive sessions with low variability (communication score < 40)."""
        count_needed = (conditions or {}).get("count", 5)
        result = await db.execute(
            select(TrainingSession.score_communication).where(
                TrainingSession.user_id == user_id,
                TrainingSession.status == SessionStatus.completed,
            ).order_by(TrainingSession.started_at.desc()).limit(count_needed)
        )
        scores = [row[0] for row in result.all() if row[0] is not None]
        if len(scores) < count_needed:
            return False
        return all(s < 40 for s in scores)

    # --- Narrative ---

    async def _check_full_arc_deal(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Completed a full story arc (5+ calls) ending in deal."""
        if not self._game_director:
            return False
        return await self._game_director.check_full_arc_deal(user_id)

    async def _check_the_comeback_story(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Narrative comeback event — reactivated from REJECTED through full story."""
        if not self._game_director:
            return False
        return await self._game_director.check_lifecycle_transition(
            user_id, from_state="REJECTED", to_state="DEAL_CLOSED"
        )

    # --- PvE boss checks ---

    async def _check_pve_boss_flawless(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Defeated a specific boss type without any errors."""
        from app.models.pvp import PvEBossRun
        boss_type = (conditions or {}).get("boss_type", "perfectionist")
        result = await db.execute(
            select(PvEBossRun.id).where(
                PvEBossRun.user_id == user_id,
                PvEBossRun.boss_type == boss_type,
                PvEBossRun.is_defeated.is_(True),
            ).limit(10)
        )
        for (run_id,) in result.all():
            # Check special_mechanics_log for flawless
            run_result = await db.execute(
                select(PvEBossRun.special_mechanics_log).where(PvEBossRun.id == run_id)
            )
            log = run_result.scalar()
            if isinstance(log, dict) and log.get("errors", 0) == 0:
                return True
        return False

    async def _check_pve_boss_composure(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Defeated energy vampire boss with composure above threshold."""
        from app.models.pvp import PvEBossRun
        min_composure = (conditions or {}).get("min_composure", 50)
        # Vampire boss is boss_index=1 (the second boss)
        result = await db.execute(
            select(PvEBossRun.special_mechanics_log).where(
                PvEBossRun.user_id == user_id,
                PvEBossRun.boss_index == 1,
                PvEBossRun.is_defeated.is_(True),
            )
        )
        for (log,) in result.all():
            if isinstance(log, dict):
                composure = log.get("final_composure_pct", 0)
                if composure > min_composure:
                    return True
        return False

    async def _check_pve_boss_score(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Defeated boss of specific type with score above threshold."""
        from app.models.pvp import PvEBossRun
        if not conditions:
            return False
        boss_type = conditions.get("boss_type", "chameleon")
        min_score = conditions.get("min_score", 70)
        result = await db.execute(
            select(PvEBossRun.id).where(
                PvEBossRun.user_id == user_id,
                PvEBossRun.boss_type == boss_type,
                PvEBossRun.is_defeated.is_(True),
                PvEBossRun.score > min_score,
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    # --- Cross-system checks ---

    async def _check_cross_same_day(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Two different activities completed on the same calendar day."""
        from app.models.progress import SessionHistory
        from app.models.pvp import PvPDuel
        if not conditions:
            return False
        activity_a = conditions.get("activity_a", "")
        activity_b = conditions.get("activity_b", "")

        # Get dates with training sessions scoring 80+
        training_dates: set[date] = set()
        if activity_a in ("training", "training_80") or activity_b in ("training", "training_80"):
            min_score = 80 if "80" in activity_a or "80" in activity_b else 0
            result = await db.execute(
                select(func.date(SessionHistory.created_at)).where(
                    SessionHistory.user_id == user_id,
                    SessionHistory.score_total >= min_score,
                ).distinct()
            )
            training_dates = {row[0] for row in result.all()}

        # Get dates with PvP wins/duels
        pvp_dates: set[date] = set()
        if "pvp" in activity_a or "pvp" in activity_b:
            need_win = "win" in activity_a or "win" in activity_b
            query = select(func.date(PvPDuel.completed_at)).where(
                PvPDuel.completed_at.isnot(None),
            )
            if need_win:
                query = query.where(PvPDuel.winner_id == user_id)
            else:
                from sqlalchemy import or_
                query = query.where(
                    or_(PvPDuel.player1_id == user_id, PvPDuel.player2_id == user_id)
                )
            result = await db.execute(query.distinct())
            pvp_dates = {row[0] for row in result.all()}

        # Get dates with knowledge quiz 90%+
        knowledge_dates: set[date] = set()
        if "knowledge" in activity_a or "knowledge" in activity_b:
            from app.models.knowledge import KnowledgeQuizSession, QuizSessionStatus
            min_quiz = 90 if "90" in activity_a or "90" in activity_b else 80
            result = await db.execute(
                select(func.date(KnowledgeQuizSession.started_at)).where(
                    KnowledgeQuizSession.user_id == user_id,
                    KnowledgeQuizSession.status == QuizSessionStatus.completed,
                    KnowledgeQuizSession.score >= min_quiz,
                ).distinct()
            )
            knowledge_dates = {row[0] for row in result.all()}

        # Check overlap of date sets
        all_sets = []
        if training_dates:
            all_sets.append(training_dates)
        if pvp_dates:
            all_sets.append(pvp_dates)
        if knowledge_dates:
            all_sets.append(knowledge_dates)

        if len(all_sets) < 2:
            return False

        # If activity_c is specified, all three must overlap on same day
        if conditions.get("activity_c"):
            if len(all_sets) < 3:
                return False
            common = all_sets[0]
            for s in all_sets[1:]:
                common = common & s
            return len(common) > 0

        # Otherwise: any two sets share a date
        for i in range(len(all_sets)):
            for j in range(i + 1, len(all_sets)):
                if all_sets[i] & all_sets[j]:
                    return True
        return False

    async def _check_cross_full_cycle(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Train an archetype, then meet it in PvP, then win.
        Simplified: user has both training deal AND PvP win with same archetype-related scenario.
        """
        from app.models.progress import SessionHistory
        from app.models.pvp import PvPDuel
        # Get archetypes trained (with deal outcome)
        result = await db.execute(
            select(func.distinct(SessionHistory.archetype_code)).where(
                SessionHistory.user_id == user_id,
                SessionHistory.outcome == "deal",
            )
        )
        trained = {row[0] for row in result.all()}
        if not trained:
            return False
        # Check PvP wins (simplified: user won at least one PvP)
        pvp_result = await db.execute(
            select(PvPDuel.id).where(
                PvPDuel.winner_id == user_id,
            ).limit(1)
        )
        return pvp_result.scalar_one_or_none() is not None and len(trained) >= 1

    async def _check_cross_theory_practice(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Quiz 90%+ in a category AND training score 80+ with traps from that category."""
        from app.models.knowledge import KnowledgeQuizSession, QuizSessionStatus
        from app.models.progress import SessionHistory
        # Check quiz 90%+
        quiz_result = await db.execute(
            select(KnowledgeQuizSession.id).where(
                KnowledgeQuizSession.user_id == user_id,
                KnowledgeQuizSession.status == QuizSessionStatus.completed,
                KnowledgeQuizSession.score >= 90,
            ).limit(1)
        )
        if not quiz_result.scalar_one_or_none():
            return False
        # Check training score 80+ with traps dodged
        train_result = await db.execute(
            select(SessionHistory.id).where(
                SessionHistory.user_id == user_id,
                SessionHistory.score_total >= 80,
                SessionHistory.traps_dodged > 0,
            ).limit(1)
        )
        return train_result.scalar_one_or_none() is not None

    async def _check_cross_revenge(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Lost a PvP -> did 3+ training sessions -> won PvP."""
        from app.models.pvp import PvPDuel
        from app.models.progress import SessionHistory
        from sqlalchemy import or_, and_
        # Find PvP losses
        loss_result = await db.execute(
            select(PvPDuel.completed_at).where(
                or_(PvPDuel.player1_id == user_id, PvPDuel.player2_id == user_id),
                PvPDuel.winner_id != user_id,
                PvPDuel.winner_id.isnot(None),
                PvPDuel.completed_at.isnot(None),
            ).order_by(PvPDuel.completed_at.desc()).limit(10)
        )
        losses = loss_result.all()
        if not losses:
            return False

        for (loss_time,) in losses:
            # Count training sessions after this loss
            training_count_result = await db.execute(
                select(func.count(SessionHistory.id)).where(
                    SessionHistory.user_id == user_id,
                    SessionHistory.created_at > loss_time,
                )
            )
            training_count = training_count_result.scalar() or 0
            if training_count < 3:
                continue
            # Check for PvP win after training
            win_result = await db.execute(
                select(PvPDuel.id).where(
                    PvPDuel.winner_id == user_id,
                    PvPDuel.completed_at > loss_time,
                ).limit(1)
            )
            if win_result.scalar_one_or_none():
                return True
        return False

    async def _check_cross_triple_threat(
        self, user_id: uuid.UUID, db: AsyncSession, stats: dict, conditions: dict | None = None
    ) -> bool:
        """Score 80+ in training + PvP win + Quiz 90% all on the same day."""
        return await self._check_cross_same_day(
            user_id, db, stats,
            {"activity_a": "training_80", "activity_b": "pvp_win", "activity_c": "knowledge_90"},
        )


# ═════════════════════════════════════════════════════════════════════════════
# BACKWARD-COMPATIBLE check_and_award_achievements (v1 API preserved)
# ═════════════════════════════════════════════════════════════════════════════

async def check_and_award_achievements(
    user_id: uuid.UUID, db: AsyncSession, *, _precomputed_streak: int | None = None,
) -> list[dict]:
    """Check all achievement conditions and award any newly earned ones.

    v2: Uses AchievementValidator internally but maintains v1 API signature.
    Note: Narrative achievements that require game_director/trap_service/scoring_service
    will be skipped if those services are not injected. Use create_validator() for full
    achievement checking.

    Returns list of newly awarded achievements.
    """
    # Gather stats (reuse streak if pre-computed to avoid double DB query)
    streak = _precomputed_streak if _precomputed_streak is not None else await calculate_streak(user_id, db)

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

    # Get ManagerProgress for level, skills, deal streak, etc.
    from app.models.progress import ManagerProgress, SessionHistory
    progress_result = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user_id)
    )
    progress = progress_result.scalar_one_or_none()
    user_level = progress.current_level if progress else 1

    stats = {
        "completed_sessions": completed_sessions,
        "best_score": best_score,
        "streak": streak,
        "unique_characters": unique_characters,
        "level": user_level,
    }

    # ── v5: Extended stats for seed-aligned achievements ──
    if progress:
        skills = progress.skills_dict()
        for skill_name, skill_val in skills.items():
            stats[f"skill_{skill_name}"] = skill_val
        stats["current_deal_streak"] = progress.current_deal_streak
        stats["total_training_hours"] = float(progress.total_hours or 0)

    # Total deals
    deals_result = await db.execute(
        select(func.count(SessionHistory.id)).where(
            SessionHistory.user_id == user_id,
            SessionHistory.outcome == "deal",
        )
    )
    stats["total_deals"] = deals_result.scalar() or 0

    # Unique archetypes played
    arch_result = await db.execute(
        select(func.count(func.distinct(SessionHistory.archetype_code))).where(
            SessionHistory.user_id == user_id,
        )
    )
    stats["unique_archetypes"] = arch_result.scalar() or 0

    # Unique scenarios played
    scen_result = await db.execute(
        select(func.count(func.distinct(SessionHistory.scenario_code))).where(
            SessionHistory.user_id == user_id,
        )
    )
    stats["unique_scenarios"] = scen_result.scalar() or 0

    # Sessions this week
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    week_result = await db.execute(
        select(func.count(SessionHistory.id)).where(
            SessionHistory.user_id == user_id,
            SessionHistory.created_at >= week_ago,
        )
    )
    stats["sessions_this_week"] = week_result.scalar() or 0

    # Use validator (without optional services — narrative checks will be skipped)
    validator = AchievementValidator()
    return await validator.check_all(user_id, db, stats)


async def check_and_award_achievements_with_streak(
    user_id: uuid.UUID, db: AsyncSession
) -> tuple[list[dict], int]:
    """Same as check_and_award_achievements but also returns the streak.

    Computes streak ONCE, passes it to achievement check, returns both.
    Eliminates the double calculate_streak() DB query.
    """
    streak = await calculate_streak(user_id, db)
    newly_earned = await check_and_award_achievements(user_id, db, _precomputed_streak=streak)
    return newly_earned, streak


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
    """Generate leaderboard from actual session data.

    Ghost filter: "all" period still limits to last 30 days to exclude inactive users.
    """
    from app.models.user import User

    if period == "week":
        since = datetime.now(timezone.utc) - timedelta(days=7)
    elif period == "month":
        since = datetime.now(timezone.utc) - timedelta(days=30)
    else:
        # "all" — filter out ghosts (inactive >30 days) per audit fix
        since = datetime.now(timezone.utc) - timedelta(days=30)

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

    # Collect all user_ids for batch queries
    user_ids = [row[0] for row in rows]

    # Batch query: ManagerProgress for all users at once
    progress_result = await db.execute(
        select(ManagerProgress.user_id, ManagerProgress.total_xp, ManagerProgress.level).where(
            ManagerProgress.user_id.in_(user_ids)
        )
    )
    progress_lookup = {row[0]: (row[1], row[2]) for row in progress_result.all()}

    # Batch query: KnowledgeQuizSession aggregates grouped by user_id
    from app.models.knowledge import KnowledgeQuizSession, QuizSessionStatus
    arena_result = await db.execute(
        select(
            KnowledgeQuizSession.user_id,
            func.count(KnowledgeQuizSession.id),
            func.coalesce(func.avg(KnowledgeQuizSession.score), 0),
        )
        .where(
            KnowledgeQuizSession.user_id.in_(user_ids),
            KnowledgeQuizSession.status == QuizSessionStatus.completed,
            KnowledgeQuizSession.started_at >= since,
        )
        .group_by(KnowledgeQuizSession.user_id)
    )
    arena_lookup = {row[0]: (row[1], float(row[2])) for row in arena_result.all()}

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

        # Get XP and level from batch lookup
        progress_data = progress_lookup.get(user_id_val)
        entry["total_xp"] = progress_data[0] if progress_data else 0
        entry["level"] = progress_data[1] if progress_data else 1

        # Get arena data from batch lookup
        arena_data = arena_lookup.get(user_id_val)
        arena_sessions = arena_data[0] if arena_data else 0
        arena_avg_score = arena_data[1] if arena_data else 0.0

        # Merge arena data: add sessions count and blend avg_score
        if arena_sessions > 0:
            total_sessions = entry["sessions_count"] + arena_sessions
            # Weighted average of training and arena scores
            entry["avg_score"] = round(
                (entry["avg_score"] * entry["sessions_count"] + arena_avg_score * arena_sessions)
                / total_sessions,
                1,
            )
            entry["sessions_count"] = total_sessions

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

    # ── v5: Extended arena/PvE stats for seed-aligned achievements ──

    # Rank tier string
    if arena_rating:
        stats["arena_rank_tier"] = arena_rating.rank_tier.value if hasattr(arena_rating.rank_tier, 'value') else str(arena_rating.rank_tier)
    else:
        stats["arena_rank_tier"] = "unranked"

    # Categories above 80%
    try:
        category_progress_80 = await get_category_progress(user_id, db)
        stats["categories_above_80"] = sum(
            1 for cp in category_progress_80
            if cp.get("mastery_pct", 0) >= 80
        )
    except Exception:
        stats["categories_above_80"] = 0

    # Arena mode wins (per PvP mode)
    from app.models.pvp import PvPDuel
    mode_wins: dict[str, int] = {}
    try:
        mode_result = await db.execute(
            select(PvPDuel.pve_mode, func.count(PvPDuel.id)).where(
                PvPDuel.winner_id == user_id,
                PvPDuel.pve_mode.isnot(None),
            ).group_by(PvPDuel.pve_mode)
        )
        for mode_val, cnt in mode_result.all():
            if mode_val:
                mode_wins[mode_val] = cnt
    except Exception:
        pass
    stats["arena_mode_wins"] = mode_wins

    # Arena blitz perfect (all correct in a blitz session)
    stats["arena_blitz_perfect"] = False
    for s in blitz_sessions:
        if s.correct_answers and s.total_questions and s.correct_answers == s.total_questions:
            stats["arena_blitz_perfect"] = True
            break

    # Tournament participation and placement
    from app.models.tournament import TournamentParticipant
    tp_result = await db.execute(
        select(
            func.count(TournamentParticipant.id),
            func.min(TournamentParticipant.final_placement),
        ).where(TournamentParticipant.user_id == user_id)
    )
    tp_row = tp_result.one()
    stats["arena_tournaments_participated"] = tp_row[0] or 0
    stats["arena_best_tournament_place"] = tp_row[1] if tp_row[1] is not None else 999

    # Unique opponents
    try:
        from sqlalchemy import or_
        opp_result = await db.execute(
            select(func.count(func.distinct(
                func.case(
                    (PvPDuel.player1_id == user_id, PvPDuel.player2_id),
                    else_=PvPDuel.player1_id,
                )
            ))).where(
                or_(PvPDuel.player1_id == user_id, PvPDuel.player2_id == user_id),
                PvPDuel.completed_at.isnot(None),
            )
        )
        stats["unique_opponents"] = opp_result.scalar() or 0
    except Exception:
        stats["unique_opponents"] = 0

    # PvE stats
    from app.models.pvp import PvELadderRun, PvEBossRun
    # PvE wins (any duel where pve_mode is set and user won)
    try:
        pve_wins_result = await db.execute(
            select(func.count(PvPDuel.id)).where(
                PvPDuel.winner_id == user_id,
                PvPDuel.pve_mode.isnot(None),
            )
        )
        stats["pve_wins"] = pve_wins_result.scalar() or 0
    except Exception:
        stats["pve_wins"] = 0

    # PvE ladder
    try:
        ladder_result = await db.execute(
            select(PvELadderRun).where(
                PvELadderRun.user_id == user_id,
                PvELadderRun.is_complete.is_(True),
            ).order_by(PvELadderRun.cumulative_score.desc()).limit(1)
        )
        best_ladder = ladder_result.scalar_one_or_none()
        stats["pve_ladder_all_defeated"] = best_ladder.all_defeated if best_ladder else False
        stats["pve_ladder_best_score"] = best_ladder.cumulative_score if best_ladder else 0
    except Exception:
        stats["pve_ladder_all_defeated"] = False
        stats["pve_ladder_best_score"] = 0

    # PvE bosses defeated
    try:
        boss_result = await db.execute(
            select(func.count(func.distinct(PvEBossRun.boss_type))).where(
                PvEBossRun.user_id == user_id,
                PvEBossRun.is_defeated.is_(True),
            )
        )
        stats["pve_bosses_defeated"] = boss_result.scalar() or 0
    except Exception:
        stats["pve_bosses_defeated"] = 0

    # PvE training count
    try:
        pve_training_result = await db.execute(
            select(func.count(PvPDuel.id)).where(
                PvPDuel.pve_mode == "training",
                or_(PvPDuel.player1_id == user_id, PvPDuel.player2_id == user_id),
                PvPDuel.completed_at.isnot(None),
            )
        )
        stats["pve_training_count"] = pve_training_result.scalar() or 0
    except Exception:
        stats["pve_training_count"] = 0

    # PvE mirror wins and streak
    try:
        mirror_result = await db.execute(
            select(PvPDuel.winner_id).where(
                PvPDuel.pve_mode == "mirror",
                or_(PvPDuel.player1_id == user_id, PvPDuel.player2_id == user_id),
                PvPDuel.completed_at.isnot(None),
            ).order_by(PvPDuel.completed_at.desc())
        )
        mirror_wins = 0
        mirror_streak = 0
        mirror_best_streak = 0
        for (winner,) in mirror_result.all():
            if winner == user_id:
                mirror_wins += 1
                mirror_streak += 1
                mirror_best_streak = max(mirror_best_streak, mirror_streak)
            else:
                mirror_streak = 0
        stats["pve_mirror_wins"] = mirror_wins
        stats["pve_mirror_best_streak"] = mirror_best_streak
    except Exception:
        stats["pve_mirror_wins"] = 0
        stats["pve_mirror_best_streak"] = 0

    # PvE modes won (count distinct pve_mode where user won)
    try:
        modes_won_result = await db.execute(
            select(func.count(func.distinct(PvPDuel.pve_mode))).where(
                PvPDuel.winner_id == user_id,
                PvPDuel.pve_mode.isnot(None),
            )
        )
        stats["pve_modes_won"] = modes_won_result.scalar() or 0
    except Exception:
        stats["pve_modes_won"] = 0

    # User level for cross-system checks
    if progress:
        stats["level"] = progress.current_level
        # Skills
        skills = progress.skills_dict()
        for skill_name, skill_val in skills.items():
            stats[f"skill_{skill_name}"] = skill_val
        stats["current_deal_streak"] = progress.current_deal_streak
        stats["total_training_hours"] = float(progress.total_hours or 0)
    else:
        stats["level"] = 1

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
