"""Daily and weekly goal system for training gamification.

Goals reset daily/weekly and provide structured XP incentives.
Progress is tracked per-user and period, stored in Redis for speed.

Integration:
  - Called after each session completion (update_goal_progress)
  - Dashboard displays current goals with progress bars
  - XP awarded immediately when goal is met
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.morning_drill import MorningDrillSession
from app.models.training import TrainingSession, SessionStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Goal definitions
# ---------------------------------------------------------------------------

@dataclass
class GoalDef:
    id: str
    label: str
    description: str
    target: int | float
    xp: int
    period: str  # "daily" | "weekly"
    metric: str  # Key used to track progress
    icon: str = "target"


DAILY_GOALS: list[GoalDef] = [
    # 2026-04-20: warm-up is first — it's the lightest action of the day
    # (2 min, no shame on <5/5) and gates the psychological "я начал день".
    GoalDef(
        id="daily_warmup",
        label="Пройди утреннюю разминку",
        description="Ответь на 5 коротких вопросов. Важен факт завершения, не 5/5.",
        target=1,
        xp=20,
        period="daily",
        metric="warmups_today",
        icon="coffee",
    ),
    GoalDef(
        id="daily_session",
        label="Пройди 1 тренировку",
        description="Завершите хотя бы одну тренировочную сессию сегодня",
        target=1,
        xp=30,
        period="daily",
        metric="sessions_today",
        icon="phone",
    ),
    GoalDef(
        id="daily_score_70",
        label="Набери 70+ баллов",
        description="Получите 70 или более баллов в любой тренировке сегодня",
        target=70,
        xp=50,
        period="daily",
        metric="best_score_today",
        icon="star",
    ),
    GoalDef(
        id="daily_stage_all",
        label="Пройди все 7 стадий",
        description="Пройдите все 7 этапов скрипта продажи в одной сессии",
        target=7,
        xp=40,
        period="daily",
        metric="max_stages_today",
        icon="list-checks",
    ),
]

WEEKLY_GOALS: list[GoalDef] = [
    GoalDef(
        id="weekly_sessions_5",
        label="5 тренировок за неделю",
        description="Завершите 5 тренировок на этой неделе",
        target=5,
        xp=100,
        period="weekly",
        metric="sessions_week",
        icon="calendar",
    ),
    GoalDef(
        id="weekly_story",
        label="Пройди 1 multi-call историю",
        description="Завершите полную multi-call историю на этой неделе",
        target=1,
        xp=80,
        period="weekly",
        metric="stories_completed_week",
        icon="git-branch",
    ),
    GoalDef(
        id="weekly_avg_75",
        label="Средний балл 75+ за неделю",
        description="Достигните среднего балла 75+ по всем сессиям этой недели",
        target=75,
        xp=120,
        period="weekly",
        metric="avg_score_week",
        icon="trending-up",
    ),
]

ALL_GOALS: list[GoalDef] = DAILY_GOALS + WEEKLY_GOALS

_GOALS_BY_ID: dict[str, GoalDef] = {g.id: g for g in ALL_GOALS}


# ---------------------------------------------------------------------------
# Goal progress data
# ---------------------------------------------------------------------------

@dataclass
class GoalProgress:
    goal_id: str
    label: str
    description: str
    target: int | float
    current: int | float
    xp: int
    period: str
    icon: str
    completed: bool = False
    xp_awarded: bool = False

    @property
    def progress_pct(self) -> float:
        if self.target <= 0:
            return 100.0
        return min(100.0, (self.current / self.target) * 100)


@dataclass
class GoalsSnapshot:
    daily: list[GoalProgress] = field(default_factory=list)
    weekly: list[GoalProgress] = field(default_factory=list)
    total_xp_available: int = 0
    total_xp_earned: int = 0


# ---------------------------------------------------------------------------
# Core service
# ---------------------------------------------------------------------------

def _start_of_today() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_week() -> datetime:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=now.weekday())
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


async def _gather_metrics(
    user_id: uuid.UUID, db: AsyncSession
) -> dict[str, int | float]:
    """Gather all metrics needed for goal progress evaluation."""
    today_start = _start_of_today()
    week_start = _start_of_week()

    # Today's sessions
    today_result = await db.execute(
        select(
            func.count(TrainingSession.id),
            func.max(TrainingSession.score_total),
        ).where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= today_start,
        )
    )
    row = today_result.one()
    sessions_today = row[0] or 0
    best_score_today = float(row[1]) if row[1] is not None else 0.0

    # Max stages completed today
    max_stages_today = 0
    if sessions_today > 0:
        stages_result = await db.execute(
            select(TrainingSession.scoring_details).where(
                TrainingSession.user_id == user_id,
                TrainingSession.status == SessionStatus.completed,
                TrainingSession.started_at >= today_start,
            )
        )
        for (details,) in stages_result.all():
            if details and isinstance(details, dict):
                stages = details.get("stages_completed")
                if isinstance(stages, int):
                    max_stages_today = max(max_stages_today, stages)
                elif isinstance(stages, list):
                    max_stages_today = max(max_stages_today, len(stages))

    # Weekly sessions
    week_result = await db.execute(
        select(
            func.count(TrainingSession.id),
            func.avg(TrainingSession.score_total),
        ).where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= week_start,
        )
    )
    week_row = week_result.one()
    sessions_week = week_row[0] or 0
    avg_score_week = float(week_row[1]) if week_row[1] is not None else 0.0

    # Stories completed this week (sessions with story_mode and final call)
    stories_result = await db.execute(
        select(func.count(TrainingSession.id)).where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.client_story_id.isnot(None),
            TrainingSession.started_at >= week_start,
        )
    )
    # Approximate: count story sessions with call_number >= total_calls
    stories_completed_week = 0
    story_sessions = await db.execute(
        select(TrainingSession.scoring_details).where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.client_story_id.isnot(None),
            TrainingSession.started_at >= week_start,
        )
    )
    for (details,) in story_sessions.all():
        if details and isinstance(details, dict):
            call_num = details.get("call_number_in_story", 0)
            total = details.get("total_calls_planned", 0)
            if call_num >= total and total >= 3:
                stories_completed_week += 1

    # 2026-04-20: daily_warmup metric — count of completed morning drills
    # on today's LOCAL date. We COUNT(*) on (user_id, date) which uses the
    # ix_morning_drill_sessions_user_date index. `MorningDrillSession.date`
    # is stored in the local business tz (see morning_drill.py /complete).
    from app.utils.local_time import local_today
    today_local = local_today()
    warmup_result = await db.execute(
        select(func.count(MorningDrillSession.id)).where(
            MorningDrillSession.user_id == user_id,
            MorningDrillSession.date == today_local,
            MorningDrillSession.completed_at.isnot(None),
        )
    )
    warmups_today = warmup_result.scalar() or 0

    return {
        "sessions_today": sessions_today,
        "best_score_today": best_score_today,
        "max_stages_today": max_stages_today,
        "sessions_week": sessions_week,
        "avg_score_week": round(avg_score_week, 1),
        "stories_completed_week": stories_completed_week,
        "warmups_today": warmups_today,
    }


async def get_goals_snapshot(
    user_id: uuid.UUID, db: AsyncSession
) -> GoalsSnapshot:
    """Get current progress for all daily and weekly goals."""
    metrics = await _gather_metrics(user_id, db)

    snapshot = GoalsSnapshot()

    for goal_def in ALL_GOALS:
        current = metrics.get(goal_def.metric, 0)
        completed = current >= goal_def.target

        progress = GoalProgress(
            goal_id=goal_def.id,
            label=goal_def.label,
            description=goal_def.description,
            target=goal_def.target,
            current=current,
            xp=goal_def.xp,
            period=goal_def.period,
            icon=goal_def.icon,
            completed=completed,
        )

        if goal_def.period == "daily":
            snapshot.daily.append(progress)
        else:
            snapshot.weekly.append(progress)

        snapshot.total_xp_available += goal_def.xp
        if completed:
            snapshot.total_xp_earned += goal_def.xp

    return snapshot


async def check_goal_completions(
    user_id: uuid.UUID, db: AsyncSession
) -> list[dict]:
    """Check which goals were just completed. Returns list of newly completed goals with XP.

    Call this after session completion to detect and award goal XP.
    Only returns goals that haven't been awarded yet (checked via GoalCompletionLog).
    """
    from app.models.progress import GoalCompletionLog

    snapshot = await get_goals_snapshot(user_id, db)
    completed = []

    # Determine period dates for dedup
    today_start = _start_of_today()
    week_start = _start_of_week()

    for progress in snapshot.daily + snapshot.weekly:
        if not progress.completed:
            continue

        period_date = today_start if progress.period == "daily" else week_start

        # Check if already awarded
        existing = await db.execute(
            select(GoalCompletionLog.id).where(
                GoalCompletionLog.user_id == user_id,
                GoalCompletionLog.goal_id == progress.goal_id,
                GoalCompletionLog.period_date == period_date,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue  # Already awarded this period

        completed.append({
            "goal_id": progress.goal_id,
            "label": progress.label,
            "xp": progress.xp,
            "period": progress.period,
        })

    return completed


async def award_goal_xp(
    user_id: uuid.UUID, goal: dict, db: AsyncSession
) -> bool:
    """Award XP for a completed goal. Returns True if XP was awarded (not duplicate).

    Creates GoalCompletionLog entry and updates ManagerProgress.total_xp + XPLog.
    """
    from app.models.progress import GoalCompletionLog, ManagerProgress
    from app.models.xp_log import XPLog, SP_RATES

    goal_id = goal["goal_id"]
    xp = goal["xp"]
    period = goal["period"]
    period_date = _start_of_today() if period == "daily" else _start_of_week()

    # Atomic dedup: SELECT FOR UPDATE prevents TOCTOU race (concurrent event processing)
    existing = await db.execute(
        select(GoalCompletionLog.id).where(
            GoalCompletionLog.user_id == user_id,
            GoalCompletionLog.goal_id == goal_id,
            GoalCompletionLog.period_date == period_date,
        ).with_for_update()
    )
    if existing.scalar_one_or_none() is not None:
        return False

    # 1. Record completion
    log_entry = GoalCompletionLog(
        user_id=user_id,
        goal_id=goal_id,
        period_date=period_date,
        xp_awarded=xp,
    )
    db.add(log_entry)

    # 2. Update ManagerProgress.total_xp
    from sqlalchemy import update
    await db.execute(
        update(ManagerProgress)
        .where(ManagerProgress.user_id == user_id)
        .values(total_xp=ManagerProgress.total_xp + xp)
    )

    # 3. Write XPLog entry
    sp_source = "daily_goal" if period == "daily" else "weekly_goal"
    sp_amount = SP_RATES.get(sp_source, 5)
    xp_log = XPLog(
        user_id=user_id,
        source=sp_source,
        amount=xp,
        multiplier=1.0,
        season_points=sp_amount,
    )
    db.add(xp_log)

    logger.info("Awarded %d XP for goal %s to user %s", xp, goal_id, user_id)
    return True
