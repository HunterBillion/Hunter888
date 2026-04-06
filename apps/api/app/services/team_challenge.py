"""Team challenge system: ROP vs ROP competitions.

A ROP creates a challenge: "My team vs Team Petrova, scenario X, by Friday".
Each manager completes 1 session. Team average score determines winner.
Winning team gets bonus XP.

Integration:
  - ROP creates challenge via API
  - Managers see assigned challenge on dashboard
  - Session completion updates challenge progress
  - When all members complete or deadline passes → determine winner
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.training import TrainingSession, SessionStatus
from app.models.user import User, Team

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class ChallengeStatus(str, Enum):
    pending = "pending"          # Created, waiting for acceptance
    active = "active"            # Both teams participating
    completed = "completed"      # Winner determined
    expired = "expired"          # Deadline passed without completion
    cancelled = "cancelled"


@dataclass
class ChallengeResult:
    challenge_id: str
    status: ChallengeStatus
    team_a_id: str
    team_b_id: str
    team_a_name: str
    team_b_name: str
    team_a_avg: float
    team_b_avg: float
    team_a_completed: int
    team_b_completed: int
    winner_team_id: str | None = None
    winner_team_name: str | None = None
    bonus_xp: int = 0


@dataclass
class TeamChallengeInfo:
    """Info about a team challenge for display."""
    id: str
    creator_id: str
    team_a_id: str
    team_a_name: str
    team_b_id: str
    team_b_name: str
    scenario_code: str | None
    deadline: datetime
    status: str
    bonus_xp: int
    team_a_progress: dict = field(default_factory=dict)
    team_b_progress: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# In-memory challenge store (replace with DB model in production)
# ---------------------------------------------------------------------------

# Simple in-memory store. For production, create a TeamChallenge SQLAlchemy model.
_challenges: dict[str, dict] = {}


async def create_challenge(
    creator_id: uuid.UUID,
    team_a_id: uuid.UUID,
    team_b_id: uuid.UUID,
    db: AsyncSession,
    scenario_code: str | None = None,
    deadline_days: int = 5,
    bonus_xp: int = 100,
) -> TeamChallengeInfo:
    """ROP creates a team challenge.

    Args:
        creator_id: ROP user ID
        team_a_id: Challenger team
        team_b_id: Opponent team
        scenario_code: Optional specific scenario
        deadline_days: Days until deadline
        bonus_xp: XP bonus for winning team (per member)
    """
    # Validate teams exist
    team_a_result = await db.execute(select(Team).where(Team.id == team_a_id))
    team_a = team_a_result.scalar_one_or_none()
    team_b_result = await db.execute(select(Team).where(Team.id == team_b_id))
    team_b = team_b_result.scalar_one_or_none()

    if not team_a or not team_b:
        raise ValueError("One or both teams not found")

    if team_a_id == team_b_id:
        raise ValueError("Cannot challenge your own team")

    challenge_id = str(uuid.uuid4())
    deadline = datetime.utcnow() + timedelta(days=deadline_days)

    challenge = {
        "id": challenge_id,
        "creator_id": str(creator_id),
        "team_a_id": str(team_a_id),
        "team_b_id": str(team_b_id),
        "team_a_name": team_a.name,
        "team_b_name": team_b.name,
        "scenario_code": scenario_code,
        "deadline": deadline,
        "status": ChallengeStatus.active.value,
        "bonus_xp": bonus_xp,
        "created_at": datetime.utcnow(),
    }
    _challenges[challenge_id] = challenge

    logger.info(
        "Team challenge created: %s (%s vs %s), deadline %s",
        challenge_id, team_a.name, team_b.name, deadline.isoformat(),
    )

    return TeamChallengeInfo(
        id=challenge_id,
        creator_id=str(creator_id),
        team_a_id=str(team_a_id),
        team_a_name=team_a.name,
        team_b_id=str(team_b_id),
        team_b_name=team_b.name,
        scenario_code=scenario_code,
        deadline=deadline,
        status=ChallengeStatus.active.value,
        bonus_xp=bonus_xp,
    )


async def get_challenge_progress(
    challenge_id: str, db: AsyncSession
) -> ChallengeResult | None:
    """Get current progress for a challenge."""
    challenge = _challenges.get(challenge_id)
    if not challenge:
        return None

    team_a_id = uuid.UUID(challenge["team_a_id"])
    team_b_id = uuid.UUID(challenge["team_b_id"])
    created_at = challenge["created_at"]

    # Get team A stats
    team_a_stats = await _get_team_stats(team_a_id, created_at, challenge.get("scenario_code"), db)
    team_b_stats = await _get_team_stats(team_b_id, created_at, challenge.get("scenario_code"), db)

    # Check if challenge should be resolved
    status = ChallengeStatus(challenge["status"])
    winner_id = None
    winner_name = None

    if status == ChallengeStatus.active:
        now = datetime.utcnow()
        if now >= challenge["deadline"]:
            # Deadline passed — determine winner
            if team_a_stats["avg_score"] > team_b_stats["avg_score"]:
                winner_id = challenge["team_a_id"]
                winner_name = challenge["team_a_name"]
            elif team_b_stats["avg_score"] > team_a_stats["avg_score"]:
                winner_id = challenge["team_b_id"]
                winner_name = challenge["team_b_name"]
            # else: tie, no winner

            challenge["status"] = ChallengeStatus.completed.value
            status = ChallengeStatus.completed

    return ChallengeResult(
        challenge_id=challenge_id,
        status=status,
        team_a_id=challenge["team_a_id"],
        team_b_id=challenge["team_b_id"],
        team_a_name=challenge["team_a_name"],
        team_b_name=challenge["team_b_name"],
        team_a_avg=team_a_stats["avg_score"],
        team_b_avg=team_b_stats["avg_score"],
        team_a_completed=team_a_stats["completed"],
        team_b_completed=team_b_stats["completed"],
        winner_team_id=winner_id,
        winner_team_name=winner_name,
        bonus_xp=challenge["bonus_xp"],
    )


async def get_active_challenges(
    team_id: uuid.UUID,
) -> list[dict]:
    """Get all active challenges for a team."""
    team_str = str(team_id)
    return [
        c for c in _challenges.values()
        if c["status"] == ChallengeStatus.active.value
        and (c["team_a_id"] == team_str or c["team_b_id"] == team_str)
    ]


async def cancel_challenge(
    challenge_id: str, user_id: uuid.UUID
) -> bool:
    """Cancel a challenge (only creator can cancel)."""
    challenge = _challenges.get(challenge_id)
    if not challenge:
        return False
    if challenge["creator_id"] != str(user_id):
        return False
    if challenge["status"] != ChallengeStatus.active.value:
        return False

    challenge["status"] = ChallengeStatus.cancelled.value
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_team_stats(
    team_id: uuid.UUID,
    since: datetime,
    scenario_code: str | None,
    db: AsyncSession,
) -> dict:
    """Get team session stats since a given date."""
    query = (
        select(
            func.count(TrainingSession.id).label("completed"),
            func.coalesce(func.avg(TrainingSession.score_total), 0).label("avg_score"),
        )
        .join(User, User.id == TrainingSession.user_id)
        .where(
            User.team_id == team_id,
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= since,
        )
    )

    if scenario_code:
        from app.models.scenario import Scenario
        query = query.join(Scenario, Scenario.id == TrainingSession.scenario_id).where(
            Scenario.code == scenario_code
        )

    result = await db.execute(query)
    row = result.one()

    return {
        "completed": row[0] or 0,
        "avg_score": round(float(row[1]), 1),
    }
