"""User CRUD endpoints: profile, password change, listing, stats, avatar."""

import glob as globmod
import io
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, require_role
from app.core.security import hash_password, verify_password
from app.database import get_db
from app.models.analytics import UserAchievement
from app.models.training import TrainingSession
from app.models.user import User, UserFriendship

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "avatars"
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_VIDEO_SIZE = 15 * 1024 * 1024  # 15MB

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────


class UserProfileResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    team_name: str | None = None
    is_active: bool
    avatar_url: str | None = None
    created_at: datetime
    total_sessions: int = 0
    avg_score: float | None = None

    model_config = {"from_attributes": True}


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class UserPreferencesRequest(BaseModel):
    team: str | None = Field(None, max_length=200)
    experience_level: str | None = Field(None, pattern="^(beginner|intermediate|advanced)$")
    tts_enabled: bool | None = None
    notifications: bool | None = None
    training_mode: str | None = Field(None, pattern="^(voice|text|mixed|structured|freestyle|challenge)$")
    # UI customization
    pipeline_columns: list[str] | None = None
    pipeline_layout: str | None = Field(None, pattern="^(grid|board)$")
    pipeline_card_fields: list[str] | None = None
    compact_mode: bool | None = None
    accent_color: str | None = Field(None, pattern="^(violet|blue|emerald|amber|rose)$")

    model_config = {"from_attributes": True}


class TeamStatsResponse(BaseModel):
    team_name: str
    total_members: int
    active_members: int
    total_sessions: int
    completed_sessions: int
    avg_score: float | None
    best_performer: str | None
    sessions_this_week: int


class UserListItem(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    team_name: str | None = None
    is_active: bool
    avatar_url: str | None = None
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


class FriendItemResponse(BaseModel):
    friendship_id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    email: str
    avatar_url: str | None = None
    role: str
    status: str
    direction: str
    created_at: datetime
    accepted_at: datetime | None = None


class FriendRequestBody(BaseModel):
    user_id: uuid.UUID


class FriendSearchResponse(BaseModel):
    items: list[FriendItemResponse]


def _friend_to_response(friendship: UserFriendship, viewer_id: uuid.UUID) -> FriendItemResponse:
    other_user = friendship.addressee if friendship.requester_id == viewer_id else friendship.requester
    direction = "outgoing" if friendship.requester_id == viewer_id else "incoming"
    return FriendItemResponse(
        friendship_id=friendship.id,
        user_id=other_user.id,
        full_name=other_user.full_name,
        email=other_user.email,
        avatar_url=other_user.avatar_url,
        role=other_user.role.value,
        status=friendship.status,
        direction=direction,
        created_at=friendship.created_at,
        accepted_at=friendship.accepted_at,
    )


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
    user_with_team = result.scalar_one_or_none()
    if not user_with_team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Basic stats
    stats_result = await db.execute(
        select(
            func.count(TrainingSession.id),
            func.avg(TrainingSession.total_score),
        ).where(TrainingSession.user_id == user.id)
    )
    row = stats_result.one()
    total_sessions = row[0] or 0
    avg_score = round(float(row[1]), 1) if row[1] else None

    return UserProfileResponse(
        id=user_with_team.id,
        email=user_with_team.email,
        full_name=user_with_team.full_name,
        role=user_with_team.role.value,
        team_name=user_with_team.team.name if user_with_team.team else None,
        is_active=user_with_team.is_active,
        avatar_url=user_with_team.avatar_url,
        created_at=user_with_team.created_at,
        total_sessions=total_sessions,
        avg_score=avg_score,
    )


@router.get("/friends", response_model=list[FriendItemResponse])
async def get_my_friends(
    status_filter: str = Query(default="accepted", pattern="^(accepted|pending|all)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(UserFriendship)
        .options(
            selectinload(UserFriendship.requester),
            selectinload(UserFriendship.addressee),
        )
        .where(
            or_(
                UserFriendship.requester_id == user.id,
                UserFriendship.addressee_id == user.id,
            )
        )
        .order_by(UserFriendship.created_at.desc())
    )
    if status_filter != "all":
        stmt = stmt.where(UserFriendship.status == status_filter)

    friendships = (await db.execute(stmt)).scalars().all()
    return [_friend_to_response(friendship, user.id) for friendship in friendships]


@router.get("/friends/search", response_model=FriendSearchResponse)
async def search_users_for_friends(
    q: str = Query(min_length=1, max_length=80),
    limit: int = Query(default=8, ge=1, le=20),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    term = f"%{q.strip()}%"
    stmt = (
        select(User)
        .where(
            User.id != user.id,
            User.is_active.is_(True),
            or_(
                User.full_name.ilike(term),
                User.email.ilike(term),
            ),
        )
        .order_by(User.full_name.asc())
        .limit(limit)
    )
    users = (await db.execute(stmt)).scalars().all()
    if not users:
        return FriendSearchResponse(items=[])

    user_ids = [u.id for u in users]
    friendship_stmt = (
        select(UserFriendship)
        .options(
            selectinload(UserFriendship.requester),
            selectinload(UserFriendship.addressee),
        )
        .where(
            or_(
                and_(UserFriendship.requester_id == user.id, UserFriendship.addressee_id.in_(user_ids)),
                and_(UserFriendship.addressee_id == user.id, UserFriendship.requester_id.in_(user_ids)),
            )
        )
    )
    existing = (await db.execute(friendship_stmt)).scalars().all()
    existing_map: dict[uuid.UUID, UserFriendship] = {}
    for friendship in existing:
        other_id = friendship.addressee_id if friendship.requester_id == user.id else friendship.requester_id
        existing_map[other_id] = friendship

    items: list[FriendItemResponse] = []
    for found in users:
        friendship = existing_map.get(found.id)
        if friendship:
            items.append(_friend_to_response(friendship, user.id))
            continue
        items.append(FriendItemResponse(
            friendship_id=uuid.uuid4(),
            user_id=found.id,
            full_name=found.full_name,
            email=found.email,
            avatar_url=found.avatar_url,
            role=found.role.value,
            status="none",
            direction="none",
            created_at=found.created_at,
            accepted_at=None,
        ))
    return FriendSearchResponse(items=items)


@router.post("/friends", response_model=FriendItemResponse)
async def send_friend_request(
    body: FriendRequestBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.user_id == user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя добавить себя")

    target = (await db.execute(select(User).where(User.id == body.user_id, User.is_active.is_(True)))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    existing = (
        await db.execute(
            select(UserFriendship)
            .options(
                selectinload(UserFriendship.requester),
                selectinload(UserFriendship.addressee),
            )
            .where(
                or_(
                    and_(UserFriendship.requester_id == user.id, UserFriendship.addressee_id == body.user_id),
                    and_(UserFriendship.requester_id == body.user_id, UserFriendship.addressee_id == user.id),
                )
            )
        )
    ).scalar_one_or_none()
    if existing:
        if existing.status == "accepted":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Уже в друзьях")
        if existing.addressee_id == user.id:
            existing.status = "accepted"
            existing.accepted_at = datetime.now(timezone.utc)
            db.add(existing)
            await db.flush()
            await db.refresh(existing)
            return _friend_to_response(existing, user.id)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Заявка уже отправлена")

    friendship = UserFriendship(
        requester_id=user.id,
        addressee_id=body.user_id,
        status="pending",
    )
    db.add(friendship)
    await db.flush()
    await db.refresh(friendship)
    friendship = (
        await db.execute(
            select(UserFriendship)
            .options(
                selectinload(UserFriendship.requester),
                selectinload(UserFriendship.addressee),
            )
            .where(UserFriendship.id == friendship.id)
        )
    ).scalar_one()
    return _friend_to_response(friendship, user.id)


@router.post("/friends/{friendship_id}/accept", response_model=FriendItemResponse)
async def accept_friend_request(
    friendship_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    friendship = (
        await db.execute(
            select(UserFriendship)
            .options(
                selectinload(UserFriendship.requester),
                selectinload(UserFriendship.addressee),
            )
            .where(UserFriendship.id == friendship_id)
        )
    ).scalar_one_or_none()
    if not friendship:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")
    if friendship.addressee_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    friendship.status = "accepted"
    friendship.accepted_at = datetime.now(timezone.utc)
    db.add(friendship)
    await db.flush()
    return _friend_to_response(friendship, user.id)


@router.delete("/friends/{friendship_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_friend(
    friendship_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    friendship = (
        await db.execute(
            select(UserFriendship).where(UserFriendship.id == friendship_id)
        )
    ).scalar_one_or_none()
    if not friendship:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Связь не найдена")
    if friendship.requester_id != user.id and friendship.addressee_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    await db.delete(friendship)
    await db.flush()
    # 204 No Content — nothing to return


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
    role: str | None = None,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """List all users. Only accessible by ROP and admin roles.

    Optional filter: ?role=manager to get only managers.
    """
    query = (
        select(User)
        .options(selectinload(User.team))
        .order_by(User.created_at.desc())
        .offset(skip)
        .limit(min(limit, 200))
    )
    # Filter by role if specified
    if role:
        from app.models.user import UserRole
        try:
            role_enum = UserRole(role)
            query = query.where(User.role == role_enum)
        except ValueError:
            pass  # ignore invalid role values
    # ROP can only see users from their own team
    if user.role.value == "rop" and user.team_id:
        query = query.where(User.team_id == user.team_id)

    result = await db.execute(query)
    users = result.scalars().all()

    return [
        UserListItem(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role.value,
            team_name=u.team.name if u.team else None,
            is_active=u.is_active,
            avatar_url=u.avatar_url,
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


@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload an avatar image (JPEG/PNG/WebP/GIF) or short video (MP4/WebM)."""
    content_type = file.content_type or ""
    is_image = content_type in ALLOWED_IMAGE_TYPES
    is_video = content_type in ALLOWED_VIDEO_TYPES

    if not is_image and not is_video:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Формат не поддерживается. Допустимы: JPEG, PNG, WebP, GIF, MP4, WebM",
        )

    max_size = MAX_VIDEO_SIZE if is_video else MAX_IMAGE_SIZE
    data = await file.read()

    # Validate file magic bytes to prevent content-type spoofing
    _MAGIC_BYTES = {
        b"\xff\xd8\xff": "image/jpeg",
        b"\x89PNG": "image/png",
        b"RIFF": "image/webp",  # WebP starts with RIFF
        b"GIF8": "image/gif",
        b"\x00\x00\x00": "video",  # MP4/WebM ftyp box
    }
    header = data[:8]
    magic_match = False
    for magic, expected in _MAGIC_BYTES.items():
        if header.startswith(magic):
            if expected == "video" and is_video:
                magic_match = True
            elif expected == content_type:
                magic_match = True
            break
    if not magic_match:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Содержимое файла не соответствует заявленному формату",
        )

    if len(data) > max_size:
        limit_mb = max_size // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Файл слишком большой. Максимум {limit_mb}MB",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Remove old avatar files for this user
    for old in globmod.glob(str(UPLOAD_DIR / f"{user.id}.*")):
        Path(old).unlink(missing_ok=True)

    if is_image and content_type != "image/gif":
        # Resize to 256x256, convert to WebP
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB")
        img.thumbnail((256, 256), Image.LANCZOS)
        ext = "webp"
        out_path = UPLOAD_DIR / f"{user.id}.{ext}"
        img.save(out_path, "WEBP", quality=85)
    elif content_type == "image/gif":
        # Save GIF as-is (preserve animation)
        ext = "gif"
        out_path = UPLOAD_DIR / f"{user.id}.{ext}"
        out_path.write_bytes(data)
    else:
        # Video: save as-is
        ext = content_type.split("/")[1]  # mp4 or webm
        out_path = UPLOAD_DIR / f"{user.id}.{ext}"
        out_path.write_bytes(data)

    avatar_url = f"/api/uploads/avatars/{user.id}.{ext}"
    user.avatar_url = avatar_url
    db.add(user)
    await db.commit()
    return {"avatar_url": avatar_url}


@router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT)
async def delete_avatar(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete the current user's avatar."""
    for old in globmod.glob(str(UPLOAD_DIR / f"{user.id}.*")):
        Path(old).unlink(missing_ok=True)

    user.avatar_url = None
    db.add(user)
    await db.commit()


@router.post("/me/preferences", status_code=status.HTTP_200_OK)
async def update_preferences(
    body: UserPreferencesRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save user preferences from onboarding or profile settings.

    If team name is provided, creates or links to existing team.
    """
    from app.models.user import Team

    # Handle team assignment
    if body.team:
        team_result = await db.execute(select(Team).where(Team.name == body.team))
        team = team_result.scalar_one_or_none()
        if not team:
            team = Team(name=body.team)
            db.add(team)
            await db.flush()
        user.team_id = team.id

    current_prefs = dict(user.preferences or {})
    update_data = body.model_dump(exclude_none=True, exclude={"team"})
    current_prefs.update(update_data)
    user.preferences = current_prefs
    user.onboarding_completed = True
    db.add(user)
    return {"preferences": current_prefs, "onboarding_completed": True}


@router.get("/me/team-stats", response_model=TeamStatsResponse)
async def get_team_stats(
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """ROP dashboard: aggregated team statistics."""
    from app.models.user import Team

    if not user.team_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User has no team")

    # Team info
    team_result = await db.execute(select(Team).where(Team.id == user.team_id))
    team = team_result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    # Team members
    members_result = await db.execute(
        select(func.count(User.id)).where(User.team_id == user.team_id)
    )
    total_members = members_result.scalar() or 0

    active_result = await db.execute(
        select(func.count(User.id)).where(User.team_id == user.team_id, User.is_active == True)  # noqa: E712
    )
    active_members = active_result.scalar() or 0

    # Team sessions
    team_user_ids = select(User.id).where(User.team_id == user.team_id)

    sessions_result = await db.execute(
        select(
            func.count(TrainingSession.id),
            func.avg(TrainingSession.score_total),
        ).where(TrainingSession.user_id.in_(team_user_ids))
    )
    row = sessions_result.one()
    total_sessions = row[0] or 0
    avg_score = round(float(row[1]), 2) if row[1] is not None else None

    completed_result = await db.execute(
        select(func.count(TrainingSession.id)).where(
            TrainingSession.user_id.in_(team_user_ids),
            TrainingSession.status == "completed",
        )
    )
    completed_sessions = completed_result.scalar() or 0

    # Sessions this week
    week_start = datetime.now(timezone.utc) - timedelta(days=7)
    week_result = await db.execute(
        select(func.count(TrainingSession.id)).where(
            TrainingSession.user_id.in_(team_user_ids),
            TrainingSession.started_at >= week_start,
        )
    )
    sessions_this_week = week_result.scalar() or 0

    # Best performer
    best_result = await db.execute(
        select(User.full_name, func.avg(TrainingSession.score_total).label("avg"))
        .join(TrainingSession, TrainingSession.user_id == User.id)
        .where(User.team_id == user.team_id, TrainingSession.status == "completed")
        .group_by(User.full_name)
        .order_by(func.avg(TrainingSession.score_total).desc())
        .limit(1)
    )
    best_row = best_result.one_or_none()
    best_performer = best_row[0] if best_row else None

    return TeamStatsResponse(
        team_name=team.name,
        total_members=total_members,
        active_members=active_members,
        total_sessions=total_sessions,
        completed_sessions=completed_sessions,
        avg_score=avg_score,
        best_performer=best_performer,
        sessions_this_week=sessions_this_week,
    )
