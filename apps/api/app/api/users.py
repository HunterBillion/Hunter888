"""User CRUD endpoints: profile, password change, listing, stats."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, require_role
from app.core.security import hash_password, verify_password
from app.database import get_db
from app.models.analytics import UserAchievement
from app.models.training import TrainingSession
from app.models.user import User

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────


class UserProfileResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    team_name: str | None = None
    is_active: bool
    created_at: datetime
    total_sessions: int = 0
    avg_score: float | None = None

    model_config = {"from_attributes": True}


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class UserListItem(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    team_name: str | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserStatsResponse(BaseModel):
    total_sessions: int
    completed_sessions: int
    avg_score: float | None
    best_score: float | None
    sessions_this_week: int
    total_duration_minutes: int
    achievements_count: int


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/me/profile", response_model=UserProfileResponse)
async def get_my_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current user's detailed profile with team name and basic stats."""
    # Reload with team relationship
    result = await db.execute(
        select(User).options(selectinload(User.team)).where(User.id == user.id)
    )
    user_with_team = result.scalar_one()

    # Basic stats
    sessions_result = await db.execute(
        select(
            func.count(TrainingSession.id),
            func.avg(TrainingSession.score_total),
        ).where(TrainingSession.user_id == user.id)
    )
    row = sessions_result.one()
    total_sessions = row[0] or 0
    avg_score = round(float(row[1]), 2) if row[1] is not None else None

    return UserProfileResponse(
        id=user_with_team.id,
        email=user_with_team.email,
        full_name=user_with_team.full_name,
        role=user_with_team.role.value,
        team_name=user_with_team.team.name if user_with_team.team else None,
        is_active=user_with_team.is_active,
        created_at=user_with_team.created_at,
        total_sessions=total_sessions,
        avg_score=avg_score,
    )


@router.put("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password. Requires the old password for verification."""
    if not verify_password(body.old_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    user.hashed_password = hash_password(body.new_password)
    user.must_change_password = False
    db.add(user)
    # commit handled by get_db context manager


@router.get("/", response_model=list[UserListItem])
async def list_users(
    skip: int = 0,
    limit: int = 50,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """List all users. Only accessible by ROP and admin roles."""
    result = await db.execute(
        select(User)
        .options(selectinload(User.team))
        .order_by(User.created_at.desc())
        .offset(skip)
        .limit(min(limit, 200))
    )
    users = result.scalars().all()

    return [
        UserListItem(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role.value,
            team_name=u.team.name if u.team else None,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in users
    ]


@router.get("/{user_id}/stats", response_model=UserStatsResponse)
async def get_user_stats(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get stats for a user. Accessible by the user themselves, or by ROP/admin."""
    # Permission check: self or elevated role
    if current_user.id != user_id and current_user.role.value not in ("rop", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own stats",
        )

    # Verify target user exists
    target = await db.execute(select(User).where(User.id == user_id))
    if target.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Aggregate session stats
    stats_result = await db.execute(
        select(
            func.count(TrainingSession.id),
            func.avg(TrainingSession.score_total),
            func.max(TrainingSession.score_total),
            func.sum(TrainingSession.duration_seconds),
        ).where(TrainingSession.user_id == user_id)
    )
    row = stats_result.one()
    total_sessions = row[0] or 0
    avg_score = round(float(row[1]), 2) if row[1] is not None else None
    best_score = round(float(row[2]), 2) if row[2] is not None else None
    total_duration_sec = row[3] or 0

    # Completed sessions
    completed_result = await db.execute(
        select(func.count(TrainingSession.id)).where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == "completed",
        )
    )
    completed_sessions = completed_result.scalar() or 0

    # Sessions this week
    week_start = datetime.now(timezone.utc) - timedelta(days=7)
    week_result = await db.execute(
        select(func.count(TrainingSession.id)).where(
            TrainingSession.user_id == user_id,
            TrainingSession.started_at >= week_start,
        )
    )
    sessions_this_week = week_result.scalar() or 0

    # Achievements count
    achievements_result = await db.execute(
        select(func.count(UserAchievement.id)).where(UserAchievement.user_id == user_id)
    )
    achievements_count = achievements_result.scalar() or 0

    return UserStatsResponse(
        total_sessions=total_sessions,
        completed_sessions=completed_sessions,
        avg_score=avg_score,
        best_score=best_score,
        sessions_this_week=sessions_this_week,
        total_duration_minutes=total_duration_sec // 60,
        achievements_count=achievements_count,
    )
