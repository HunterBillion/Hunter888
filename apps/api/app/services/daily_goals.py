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
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
    now = datetime.utcnow()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_week() -> datetime:
    now = datetime.utcnow()
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
            select(TrainingSession.score_details).where(
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
            TrainingSession.story_mode.is_(True),
            TrainingSession.started_at >= week_start,
        )
    )
    # Approximate: count story sessions with call_number >= total_calls
    stories_completed_week = 0
    story_sessions = await db.execute(
        select(TrainingSession.score_details).where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.story_mode.is_(True),
            TrainingSession.started_at >= week_start,
        )
    )
    for (details,) in story_sessions.all():
        if details and isinstance(details, dict):
            call_num = details.get("call_number", 0)
            total = details.get("total_calls", 0)
            if call_num >= total and total >= 3:
                stories_completed_week += 1

    return {
        "sessions_today": sessions_today,
        "best_score_today": best_score_today,
        "max_stages_today": max_stages_today,
        "sessions_week": sessions_week,
        "avg_score_week": round(avg_score_week, 1),
        "stories_completed_week": stories_completed_week,
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
    """
    snapshot = await get_goals_snapshot(user_id, db)
    completed = []

    for progress in snapshot.daily + snapshot.weekly:
        if progress.completed and not progress.xp_awarded:
            completed.append({
                "goal_id": progress.goal_id,
                "label": progress.label,
                "xp": progress.xp,
                "period": progress.period,
            })

    return completed
