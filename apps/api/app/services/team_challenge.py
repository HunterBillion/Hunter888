"""Team challenge system: ROP vs ROP competitions — S3-01 PostgreSQL persistence.

A ROP creates a challenge: "My team vs Team Petrova, scenario X, by Friday".
Each manager completes 1 session. Team average score determines winner.
Winning team gets bonus XP.

Integration:
  - ROP creates challenge via API
  - Managers see assigned challenge on dashboard
  - Session completion updates challenge progress (on_session_complete hook)
  - When all members complete or deadline passes → determine winner
  - Winner bonus XP applied via gamification service
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team_challenge import (
    TeamChallenge,
    TeamChallengeProgress,
    ChallengeStatus,
    ChallengeType,
)
from app.models.training import TrainingSession, SessionStatus
from app.models.user import User, Team

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response dataclasses (kept for API compatibility)
# ---------------------------------------------------------------------------

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
# Core operations
# ---------------------------------------------------------------------------

async def create_challenge(
    creator_id: uuid.UUID,
    team_a_id: uuid.UUID,
    team_b_id: uuid.UUID,
    db: AsyncSession,
    scenario_code: str | None = None,
    deadline_days: int = 5,
    bonus_xp: int = 100,
) -> TeamChallengeInfo:
    """ROP creates a team challenge. Persisted to PostgreSQL."""
    # Validate teams exist
    team_a_result = await db.execute(select(Team).where(Team.id == team_a_id))
    team_a = team_a_result.scalar_one_or_none()
    team_b_result = await db.execute(select(Team).where(Team.id == team_b_id))
    team_b = team_b_result.scalar_one_or_none()

    if not team_a or not team_b:
        raise ValueError("One or both teams not found")

    if team_a_id == team_b_id:
        raise ValueError("Cannot challenge your own team")

    # Check for existing active challenge between these teams
    existing = await db.execute(
        select(TeamChallenge).where(
            TeamChallenge.status == ChallengeStatus.active.value,
            ((TeamChallenge.team_a_id == team_a_id) & (TeamChallenge.team_b_id == team_b_id))
            | ((TeamChallenge.team_a_id == team_b_id) & (TeamChallenge.team_b_id == team_a_id)),
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("Active challenge already exists between these teams")

    deadline = datetime.now(timezone.utc) + timedelta(days=deadline_days)

    challenge = TeamChallenge(
        created_by=creator_id,
        team_a_id=team_a_id,
        team_b_id=team_b_id,
        challenge_type=ChallengeType.score_avg.value,
        status=ChallengeStatus.active.value,
        scenario_code=scenario_code,
        bonus_xp=bonus_xp,
        deadline=deadline,
    )
    db.add(challenge)

    # Pre-create progress rows for both teams
    for tid in (team_a_id, team_b_id):
        # Count team members
        member_count_r = await db.execute(
            select(func.count(User.id)).where(
                User.team_id == tid, User.is_active == True,
            )
        )
        member_count = member_count_r.scalar() or 0

        progress = TeamChallengeProgress(
            challenge_id=challenge.id,
            team_id=tid,
            total_members=member_count,
        )
        db.add(progress)

    await db.flush()

    logger.info(
        "Team challenge created: %s (%s vs %s), deadline %s",
        challenge.id, team_a.name, team_b.name, deadline.isoformat(),
    )

    return TeamChallengeInfo(
        id=str(challenge.id),
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
    challenge_id: str, db: AsyncSession,
) -> ChallengeResult | None:
    """Get current progress for a challenge, resolving if deadline passed."""
    try:
        cid = uuid.UUID(challenge_id)
    except ValueError:
        return None

    result = await db.execute(
        select(TeamChallenge).where(TeamChallenge.id == cid)
    )
    challenge = result.scalar_one_or_none()
    if not challenge:
        return None

    # Get live stats from training_sessions
    team_a_stats = await _get_team_stats(
        challenge.team_a_id, challenge.created_at, challenge.scenario_code, db,
    )
    team_b_stats = await _get_team_stats(
        challenge.team_b_id, challenge.created_at, challenge.scenario_code, db,
    )

    # Update progress rows
    await _update_progress(challenge.id, challenge.team_a_id, team_a_stats, db)
    await _update_progress(challenge.id, challenge.team_b_id, team_b_stats, db)

    # Auto-resolve if deadline passed
    status = ChallengeStatus(challenge.status)
    winner_id = None
    winner_name = None

    if status == ChallengeStatus.active:
        now = datetime.now(timezone.utc)
        if now >= challenge.deadline:
            winner_id, winner_name = await _resolve_challenge(
                challenge, team_a_stats, team_b_stats, db,
            )
            status = ChallengeStatus(challenge.status)

    # Resolve names from relationships
    team_a_name = challenge.team_a.name if challenge.team_a else "?"
    team_b_name = challenge.team_b.name if challenge.team_b else "?"
    if challenge.winner_team_id:
        winner_id = str(challenge.winner_team_id)
        winner_name = (
            team_a_name if challenge.winner_team_id == challenge.team_a_id
            else team_b_name
        )

    return ChallengeResult(
        challenge_id=str(challenge.id),
        status=status,
        team_a_id=str(challenge.team_a_id),
        team_b_id=str(challenge.team_b_id),
        team_a_name=team_a_name,
        team_b_name=team_b_name,
        team_a_avg=team_a_stats["avg_score"],
        team_b_avg=team_b_stats["avg_score"],
        team_a_completed=team_a_stats["completed"],
        team_b_completed=team_b_stats["completed"],
        winner_team_id=winner_id,
        winner_team_name=winner_name,
        bonus_xp=challenge.bonus_xp,
    )


async def get_active_challenges(
    team_id: uuid.UUID, db: AsyncSession,
) -> list[dict]:
    """Get all active challenges for a team."""
    result = await db.execute(
        select(TeamChallenge).where(
            TeamChallenge.status == ChallengeStatus.active.value,
            (TeamChallenge.team_a_id == team_id) | (TeamChallenge.team_b_id == team_id),
        ).order_by(TeamChallenge.deadline.asc())
    )
    challenges = result.scalars().all()

    out = []
    for c in challenges:
        team_a_name = c.team_a.name if c.team_a else "?"
        team_b_name = c.team_b.name if c.team_b else "?"
        out.append({
            "id": str(c.id),
            "creator_id": str(c.created_by) if c.created_by else None,
            "team_a_id": str(c.team_a_id),
            "team_a_name": team_a_name,
            "team_b_id": str(c.team_b_id),
            "team_b_name": team_b_name,
            "scenario_code": c.scenario_code,
            "deadline": c.deadline.isoformat(),
            "status": c.status,
            "bonus_xp": c.bonus_xp,
        })
    return out


async def cancel_challenge(
    challenge_id: str, user_id: uuid.UUID, db: AsyncSession,
) -> bool:
    """Cancel a challenge (only creator can cancel)."""
    try:
        cid = uuid.UUID(challenge_id)
    except ValueError:
        return False

    result = await db.execute(
        select(TeamChallenge)
        .where(TeamChallenge.id == cid)
        .with_for_update()
    )
    challenge = result.scalar_one_or_none()
    if not challenge:
        return False
    if challenge.created_by != user_id:
        return False
    if challenge.status != ChallengeStatus.active.value:
        return False

    challenge.status = ChallengeStatus.cancelled.value
    await db.flush()

    logger.info("Team challenge %s cancelled by %s", challenge_id, user_id)
    return True


async def on_session_complete(
    user_id: uuid.UUID, db: AsyncSession,
) -> None:
    """Hook called when a training session completes.

    Updates progress for all active challenges the user's team participates in.
    Called from session completion flow in training WS handler.
    """
    # Find user's team
    user_r = await db.execute(select(User.team_id).where(User.id == user_id))
    team_id = user_r.scalar_one_or_none()
    if not team_id:
        return

    # Find active challenges for this team
    active = await db.execute(
        select(TeamChallenge).where(
            TeamChallenge.status == ChallengeStatus.active.value,
            (TeamChallenge.team_a_id == team_id) | (TeamChallenge.team_b_id == team_id),
        )
    )
    challenges = active.scalars().all()

    for challenge in challenges:
        stats = await _get_team_stats(
            team_id, challenge.created_at, challenge.scenario_code, db,
        )
        await _update_progress(challenge.id, team_id, stats, db)

        # Check if deadline passed and auto-resolve
        now = datetime.now(timezone.utc)
        if now >= challenge.deadline and challenge.status == ChallengeStatus.active.value:
            other_team_id = (
                challenge.team_b_id if team_id == challenge.team_a_id
                else challenge.team_a_id
            )
            other_stats = await _get_team_stats(
                other_team_id, challenge.created_at, challenge.scenario_code, db,
            )
            if team_id == challenge.team_a_id:
                await _resolve_challenge(challenge, stats, other_stats, db)
            else:
                await _resolve_challenge(challenge, other_stats, stats, db)


async def expire_overdue_challenges(db: AsyncSession) -> int:
    """Background task: expire active challenges past deadline.

    Called periodically (e.g., every hour) to ensure challenges don't linger.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(TeamChallenge).where(
            TeamChallenge.status == ChallengeStatus.active.value,
            TeamChallenge.deadline < now,
        )
    )
    overdue = result.scalars().all()
    resolved = 0

    for challenge in overdue:
        team_a_stats = await _get_team_stats(
            challenge.team_a_id, challenge.created_at, challenge.scenario_code, db,
        )
        team_b_stats = await _get_team_stats(
            challenge.team_b_id, challenge.created_at, challenge.scenario_code, db,
        )
        await _resolve_challenge(challenge, team_a_stats, team_b_stats, db)
        resolved += 1

    if resolved:
        await db.flush()
        logger.info("Expired %d overdue team challenges", resolved)

    return resolved


# ---------------------------------------------------------------------------
# Internal helpers
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


async def _update_progress(
    challenge_id: uuid.UUID,
    team_id: uuid.UUID,
    stats: dict,
    db: AsyncSession,
) -> None:
    """Upsert progress row for a team in a challenge."""
    result = await db.execute(
        select(TeamChallengeProgress).where(
            TeamChallengeProgress.challenge_id == challenge_id,
            TeamChallengeProgress.team_id == team_id,
        )
    )
    progress = result.scalar_one_or_none()

    if progress:
        progress.completed_sessions = stats["completed"]
        progress.avg_score = stats["avg_score"]
    else:
        # Shouldn't happen if create_challenge pre-creates rows, but be safe
        member_count_r = await db.execute(
            select(func.count(User.id)).where(
                User.team_id == team_id, User.is_active == True,
            )
        )
        progress = TeamChallengeProgress(
            challenge_id=challenge_id,
            team_id=team_id,
            completed_sessions=stats["completed"],
            avg_score=stats["avg_score"],
            total_members=member_count_r.scalar() or 0,
        )
        db.add(progress)


async def _resolve_challenge(
    challenge: TeamChallenge,
    team_a_stats: dict,
    team_b_stats: dict,
    db: AsyncSession,
) -> tuple[str | None, str | None]:
    """Determine winner and update challenge status.

    Returns (winner_team_id_str, winner_team_name) or (None, None) for tie.
    """
    winner_id: uuid.UUID | None = None
    winner_name: str | None = None

    if team_a_stats["avg_score"] > team_b_stats["avg_score"]:
        winner_id = challenge.team_a_id
        winner_name = challenge.team_a.name if challenge.team_a else None
    elif team_b_stats["avg_score"] > team_a_stats["avg_score"]:
        winner_id = challenge.team_b_id
        winner_name = challenge.team_b.name if challenge.team_b else None
    # else: tie — no winner

    challenge.status = ChallengeStatus.completed.value
    challenge.winner_team_id = winner_id

    # Apply bonus XP to winning team members
    if winner_id and challenge.bonus_xp > 0:
        await _apply_winner_bonus(winner_id, challenge.bonus_xp, db)

    await db.flush()

    logger.info(
        "Challenge %s resolved: winner=%s (A=%.1f vs B=%.1f)",
        challenge.id, winner_name or "TIE",
        team_a_stats["avg_score"], team_b_stats["avg_score"],
    )

    return (str(winner_id) if winner_id else None, winner_name)


async def _apply_winner_bonus(
    team_id: uuid.UUID, bonus_xp: int, db: AsyncSession,
) -> None:
    """Apply bonus XP to all active members of the winning team.

    Uses the same FOR UPDATE pattern as arena_xp to prevent race conditions.
    """
    from app.models.progress import ManagerProgress
    from app.services.gamification import xp_for_level

    members_r = await db.execute(
        select(User.id).where(User.team_id == team_id, User.is_active == True)
    )
    member_ids = [row[0] for row in members_r.fetchall()]

    for uid in member_ids:
        try:
            # S3-02: Route through daily cap (exempt, but tracked for display)
            from app.services.xp_daily_cap import apply_daily_cap
            effective_xp = await apply_daily_cap(uid, bonus_xp, source="team_challenge_win")

            result = await db.execute(
                select(ManagerProgress)
                .where(ManagerProgress.user_id == uid)
                .with_for_update()
            )
            progress = result.scalar_one_or_none()

            if progress is None:
                progress = ManagerProgress(user_id=uid)
                db.add(progress)
                await db.flush()

            progress.total_xp += effective_xp
            progress.current_xp += effective_xp

            # Level up check
            next_level_xp = xp_for_level(progress.current_level + 1)
            while progress.total_xp >= next_level_xp and next_level_xp > 0:
                progress.current_level += 1
                next_level_xp = xp_for_level(progress.current_level + 1)

        except Exception as e:
            logger.warning("Failed to apply challenge bonus XP to %s: %s", uid, e)
