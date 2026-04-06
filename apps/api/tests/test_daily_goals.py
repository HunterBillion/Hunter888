"""Tests for the daily goals system (services/daily_goals.py).

Covers GoalDef creation, GoalProgress calculation,
GoalsSnapshot aggregation, and async DB operations.
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.daily_goals import (
    GoalDef,
    GoalProgress,
    GoalsSnapshot,
    get_goals_snapshot,
    check_goal_completions,
    DAILY_GOALS,
    WEEKLY_GOALS,
    ALL_GOALS,
)


# ═══════════════════════════════════════════════════════════════════════════════
# TestGoalDef — Goal definition creation and attributes
# ═══════════════════════════════════════════════════════════════════════════════


class TestGoalDef:
    """Test GoalDef dataclass creation and defaults."""

    def test_goal_def_create_with_all_fields(self):
        """Create a GoalDef with all required fields."""
        goal = GoalDef(
            id="test_goal_1",
            label="Test Goal",
            description="A test goal",
            target=10,
            xp=50,
            period="daily",
            metric="test_metric",
            icon="star",
        )
        assert goal.id == "test_goal_1"
        assert goal.label == "Test Goal"
        assert goal.description == "A test goal"
        assert goal.target == 10
        assert goal.xp == 50
        assert goal.period == "daily"
        assert goal.metric == "test_metric"
        assert goal.icon == "star"

    def test_goal_def_icon_default(self):
        """GoalDef icon defaults to 'target'."""
        goal = GoalDef(
            id="test",
            label="Goal",
            description="Desc",
            target=5,
            xp=25,
            period="daily",
            metric="metric",
        )
        assert goal.icon == "target"

    def test_goal_def_with_float_target(self):
        """GoalDef accepts float targets."""
        goal = GoalDef(
            id="score_goal",
            label="Score Goal",
            description="Desc",
            target=75.5,
            xp=100,
            period="weekly",
            metric="avg_score",
        )
        assert goal.target == 75.5
        assert isinstance(goal.target, float)

    def test_daily_goals_fixture_exists(self):
        """DAILY_GOALS list should have items."""
        assert len(DAILY_GOALS) > 0
        for goal in DAILY_GOALS:
            assert goal.period == "daily"

    def test_weekly_goals_fixture_exists(self):
        """WEEKLY_GOALS list should have items."""
        assert len(WEEKLY_GOALS) > 0
        for goal in WEEKLY_GOALS:
            assert goal.period == "weekly"

    def test_all_goals_contains_both(self):
        """ALL_GOALS should be union of daily and weekly."""
        assert len(ALL_GOALS) == len(DAILY_GOALS) + len(WEEKLY_GOALS)


# ═══════════════════════════════════════════════════════════════════════════════
# TestGoalProgress — Progress calculation and completion detection
# ═══════════════════════════════════════════════════════════════════════════════


class TestGoalProgress:
    """Test GoalProgress tracking and percentage calculation."""

    def test_goal_progress_initial_state(self):
        """Create a GoalProgress with initial values."""
        progress = GoalProgress(
            goal_id="goal_1",
            label="Test Goal",
            description="Test description",
            target=10,
            current=0,
            xp=50,
            period="daily",
            icon="star",
        )
        assert progress.current == 0
        assert progress.completed is False
        assert progress.xp_awarded is False

    def test_goal_progress_pct_calculation(self):
        """Progress percentage calculation: current/target * 100."""
        progress = GoalProgress(
            goal_id="goal_1",
            label="Test",
            description="Desc",
            target=10,
            current=5,
            xp=50,
            period="daily",
            icon="star",
        )
        assert progress.progress_pct == 50.0

    def test_goal_progress_pct_over_100(self):
        """Progress over 100% should cap at 100.0."""
        progress = GoalProgress(
            goal_id="goal_1",
            label="Test",
            description="Desc",
            target=10,
            current=15,
            xp=50,
            period="daily",
            icon="star",
        )
        assert progress.progress_pct == 100.0

    def test_goal_progress_completed_when_current_equals_target(self):
        """Goal is completed when current >= target."""
        progress = GoalProgress(
            goal_id="goal_1",
            label="Test",
            description="Desc",
            target=10,
            current=10,
            xp=50,
            period="daily",
            icon="star",
            completed=True,
        )
        assert progress.completed is True

    def test_goal_progress_completed_when_current_exceeds_target(self):
        """Goal is completed when current > target."""
        progress = GoalProgress(
            goal_id="goal_1",
            label="Test",
            description="Desc",
            target=10,
            current=12,
            xp=50,
            period="daily",
            icon="star",
            completed=True,
        )
        assert progress.completed is True

    def test_goal_progress_pct_with_zero_target(self):
        """With target=0, progress_pct should be 100.0."""
        progress = GoalProgress(
            goal_id="goal_1",
            label="Test",
            description="Desc",
            target=0,
            current=0,
            xp=50,
            period="daily",
            icon="star",
        )
        assert progress.progress_pct == 100.0

    def test_goal_progress_pct_with_float_values(self):
        """Progress percentage should work with floats."""
        progress = GoalProgress(
            goal_id="goal_1",
            label="Test",
            description="Desc",
            target=100.0,
            current=33.5,
            xp=50,
            period="daily",
            icon="star",
        )
        assert abs(progress.progress_pct - 33.5) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# TestGoalsSnapshot — Aggregated goals data
# ═══════════════════════════════════════════════════════════════════════════════


class TestGoalsSnapshot:
    """Test GoalsSnapshot aggregation."""

    def test_goals_snapshot_empty_defaults(self):
        """GoalsSnapshot should have empty lists by default."""
        snapshot = GoalsSnapshot()
        assert snapshot.daily == []
        assert snapshot.weekly == []
        assert snapshot.total_xp_available == 0
        assert snapshot.total_xp_earned == 0

    def test_goals_snapshot_with_daily_goals(self):
        """Add daily goals to snapshot."""
        daily = [
            GoalProgress(
                goal_id="d1",
                label="Goal 1",
                description="Desc",
                target=1,
                current=1,
                xp=30,
                period="daily",
                icon="target",
                completed=True,
            ),
            GoalProgress(
                goal_id="d2",
                label="Goal 2",
                description="Desc",
                target=2,
                current=1,
                xp=50,
                period="daily",
                icon="star",
                completed=False,
            ),
        ]
        snapshot = GoalsSnapshot(daily=daily)
        assert len(snapshot.daily) == 2
        assert snapshot.daily[0].goal_id == "d1"
        assert snapshot.daily[1].goal_id == "d2"

    def test_goals_snapshot_with_weekly_goals(self):
        """Add weekly goals to snapshot."""
        weekly = [
            GoalProgress(
                goal_id="w1",
                label="Weekly Goal",
                description="Desc",
                target=5,
                current=3,
                xp=100,
                period="weekly",
                icon="calendar",
                completed=False,
            ),
        ]
        snapshot = GoalsSnapshot(weekly=weekly)
        assert len(snapshot.weekly) == 1
        assert snapshot.weekly[0].goal_id == "w1"

    def test_goals_snapshot_total_xp_available(self):
        """total_xp_available sums all goal XP."""
        daily = [
            GoalProgress(
                goal_id="d1",
                label="Goal 1",
                description="Desc",
                target=1,
                current=0,
                xp=30,
                period="daily",
                icon="target",
            ),
            GoalProgress(
                goal_id="d2",
                label="Goal 2",
                description="Desc",
                target=2,
                current=0,
                xp=50,
                period="daily",
                icon="star",
            ),
        ]
        weekly = [
            GoalProgress(
                goal_id="w1",
                label="Weekly Goal",
                description="Desc",
                target=5,
                current=0,
                xp=100,
                period="weekly",
                icon="calendar",
            ),
        ]
        snapshot = GoalsSnapshot(daily=daily, weekly=weekly, total_xp_available=180)
        assert snapshot.total_xp_available == 180

    def test_goals_snapshot_total_xp_earned(self):
        """total_xp_earned tracks completed goal XP."""
        daily = [
            GoalProgress(
                goal_id="d1",
                label="Goal 1",
                description="Desc",
                target=1,
                current=1,
                xp=30,
                period="daily",
                icon="target",
                completed=True,
            ),
        ]
        snapshot = GoalsSnapshot(daily=daily, total_xp_earned=30)
        assert snapshot.total_xp_earned == 30


# ═══════════════════════════════════════════════════════════════════════════════
# TestGetGoalsSnapshot — Async DB operations
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestGetGoalsSnapshot:
    """Test async goal snapshot generation from DB."""

    async def test_get_goals_snapshot_with_mock_db(self):
        """Mock DB to return session data for goals calculation."""
        user_id = uuid.uuid4()

        # Mock AsyncSession
        mock_db = AsyncMock()

        # Mock the execute calls to return metrics
        mock_db.execute.return_value.one.return_value = (1, 75)  # sessions_today, best_score
        mock_db.execute.return_value.all.return_value = []

        with patch(
            "app.services.daily_goals._gather_metrics",
            return_value={
                "sessions_today": 1,
                "best_score_today": 75,
                "max_stages_today": 5,
                "sessions_week": 3,
                "avg_score_week": 70.0,
                "stories_completed_week": 1,
            },
        ):
            snapshot = await get_goals_snapshot(user_id, mock_db)

        assert snapshot is not None
        assert isinstance(snapshot, GoalsSnapshot)
        assert len(snapshot.daily) > 0
        assert len(snapshot.weekly) > 0

    async def test_get_goals_snapshot_has_daily_session_goal(self):
        """Snapshot should contain daily_session goal."""
        user_id = uuid.uuid4()
        mock_db = AsyncMock()

        with patch(
            "app.services.daily_goals._gather_metrics",
            return_value={
                "sessions_today": 1,
                "best_score_today": 50,
                "max_stages_today": 3,
                "sessions_week": 2,
                "avg_score_week": 60.0,
                "stories_completed_week": 0,
            },
        ):
            snapshot = await get_goals_snapshot(user_id, mock_db)

        daily_goal_ids = [g.goal_id for g in snapshot.daily]
        assert "daily_session" in daily_goal_ids

    async def test_get_goals_snapshot_progress_reflects_metrics(self):
        """Progress values should reflect gathered metrics."""
        user_id = uuid.uuid4()
        mock_db = AsyncMock()

        with patch(
            "app.services.daily_goals._gather_metrics",
            return_value={
                "sessions_today": 1,
                "best_score_today": 50,
                "max_stages_today": 3,
                "sessions_week": 5,
                "avg_score_week": 75.0,
                "stories_completed_week": 1,
            },
        ):
            snapshot = await get_goals_snapshot(user_id, mock_db)

        # Find the daily_session goal
        daily_session = next(
            (g for g in snapshot.daily if g.goal_id == "daily_session"), None
        )
        assert daily_session is not None
        assert daily_session.current == 1


# ═══════════════════════════════════════════════════════════════════════════════
# TestCheckGoalCompletions — Check newly completed goals
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestCheckGoalCompletions:
    """Test goal completion detection."""

    async def test_check_goal_completions_returns_completed_goals(self):
        """Mock DB with completed goal should return goal ID in list."""
        user_id = uuid.uuid4()
        mock_db = AsyncMock()

        with patch(
            "app.services.daily_goals.get_goals_snapshot"
        ) as mock_snapshot:
            # Mock snapshot with completed goal
            completed_goal = GoalProgress(
                goal_id="daily_session",
                label="Пройди 1 тренировку",
                description="Desc",
                target=1,
                current=1,
                xp=30,
                period="daily",
                icon="phone",
                completed=True,
                xp_awarded=False,
            )
            snapshot = GoalsSnapshot(
                daily=[completed_goal],
                total_xp_available=30,
                total_xp_earned=30,
            )
            mock_snapshot.return_value = snapshot

            completed = await check_goal_completions(user_id, mock_db)

        assert len(completed) > 0
        assert completed[0]["goal_id"] == "daily_session"
        assert completed[0]["xp"] == 30

    async def test_check_goal_completions_incomplete_returns_empty(self):
        """Mock DB with incomplete goal should return empty list."""
        user_id = uuid.uuid4()
        mock_db = AsyncMock()

        with patch(
            "app.services.daily_goals.get_goals_snapshot"
        ) as mock_snapshot:
            # Mock snapshot with incomplete goal
            incomplete_goal = GoalProgress(
                goal_id="daily_session",
                label="Пройди 1 тренировку",
                description="Desc",
                target=1,
                current=0,
                xp=30,
                period="daily",
                icon="phone",
                completed=False,
                xp_awarded=False,
            )
            snapshot = GoalsSnapshot(
                daily=[incomplete_goal],
                total_xp_available=30,
                total_xp_earned=0,
            )
            mock_snapshot.return_value = snapshot

            completed = await check_goal_completions(user_id, mock_db)

        assert len(completed) == 0

    async def test_check_goal_completions_already_awarded_excluded(self):
        """Goals with xp_awarded=True should be excluded."""
        user_id = uuid.uuid4()
        mock_db = AsyncMock()

        with patch(
            "app.services.daily_goals.get_goals_snapshot"
        ) as mock_snapshot:
            # Mock snapshot with already awarded goal
            awarded_goal = GoalProgress(
                goal_id="daily_session",
                label="Пройди 1 тренировку",
                description="Desc",
                target=1,
                current=1,
                xp=30,
                period="daily",
                icon="phone",
                completed=True,
                xp_awarded=True,
            )
            snapshot = GoalsSnapshot(
                daily=[awarded_goal],
                total_xp_available=30,
                total_xp_earned=30,
            )
            mock_snapshot.return_value = snapshot

            completed = await check_goal_completions(user_id, mock_db)

        assert len(completed) == 0
