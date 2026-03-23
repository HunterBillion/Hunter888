"""REST API endpoints for Agent 8 — PvP Battle system.

Provides:
- Rating queries (personal, leaderboard)
- Duel history
- Anti-cheat status (admin)
- Season management (admin)
- Queue status
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors as err
from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.pvp import (
    AntiCheatLog,
    DuelStatus,
    PvPDuel,
    PvPRating,
    PvPRankTier,
    PvPSeason,
    RANK_DISPLAY_NAMES,
    rank_from_rating,
)
from app.models.user import User, UserFriendship
from app.schemas.pvp import (
    AntiCheatFlagResponse,
    DuelResponse,
    LeaderboardEntry,
    LeaderboardResponse,
    RatingResponse,
    SeasonResponse,
)
from app.services.glicko2 import get_or_create_rating, apply_season_reset
from app.services.pvp_matchmaker import create_pve_duel, get_queue_size, leave_queue
from app.services.pvp_matchmaker import join_queue
from app.ws.notifications import notification_manager

router = APIRouter()


# ---------------------------------------------------------------------------
# Rating
# ---------------------------------------------------------------------------

@router.get("/rating/me", response_model=RatingResponse)
async def get_my_rating(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's PvP rating and rank."""
    rating = await get_or_create_rating(user.id, db)

    return RatingResponse(
        user_id=rating.user_id,
        rating=rating.rating,
        rd=rating.rd,
        volatility=rating.volatility,
        rank_tier=rating.rank_tier.value,
        rank_display=RANK_DISPLAY_NAMES.get(rating.rank_tier, ""),
        wins=rating.wins,
        losses=rating.losses,
        draws=rating.draws,
        total_duels=rating.total_duels,
        placement_done=rating.placement_done,
        placement_count=rating.placement_count,
        peak_rating=rating.peak_rating,
        peak_tier=rating.peak_tier.value,
        current_streak=rating.current_streak,
        best_streak=rating.best_streak,
        last_played=rating.last_played,
    )


@router.get("/rating/{user_id}", response_model=RatingResponse)
async def get_user_rating(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Get another user's PvP rating (public info only)."""
    result = await db.execute(
        select(PvPRating).where(PvPRating.user_id == user_id)
    )
    rating = result.scalar_one_or_none()

    if not rating:
        raise HTTPException(status_code=404, detail=err.RATING_NOT_FOUND)

    return RatingResponse(
        user_id=rating.user_id,
        rating=rating.rating,
        rd=rating.rd,
        volatility=rating.volatility,
        rank_tier=rating.rank_tier.value,
        rank_display=RANK_DISPLAY_NAMES.get(rating.rank_tier, ""),
        wins=rating.wins,
        losses=rating.losses,
        draws=rating.draws,
        total_duels=rating.total_duels,
        placement_done=rating.placement_done,
        placement_count=rating.placement_count,
        peak_rating=rating.peak_rating,
        peak_tier=rating.peak_tier.value,
        current_streak=rating.current_streak,
        best_streak=rating.best_streak,
        last_played=rating.last_played,
    )


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    tier: PvPRankTier | None = None,
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Get PvP leaderboard, optionally filtered by rank tier."""
    stmt = (
        select(PvPRating, User)
        .join(User, User.id == PvPRating.user_id)
        .where(PvPRating.placement_done.is_(True))
    )

    if tier:
        stmt = stmt.where(PvPRating.rank_tier == tier)

    stmt = stmt.order_by(desc(PvPRating.rating)).offset(offset).limit(limit)
    result = await db.execute(stmt)
    rows = result.all()

    # Total count
    count_stmt = select(func.count(PvPRating.id)).where(
        PvPRating.placement_done.is_(True)
    )
    if tier:
        count_stmt = count_stmt.where(PvPRating.rank_tier == tier)
    total = (await db.execute(count_stmt)).scalar() or 0

    entries = []
    for i, (rating, user) in enumerate(rows, start=offset + 1):
        entries.append(
            LeaderboardEntry(
                rank=i,
                user_id=rating.user_id,
                username=user.full_name or user.email or str(user.id)[:8],
                avatar_url=user.avatar_url,
                rating=rating.rating,
                rank_tier=rating.rank_tier.value,
                rank_display=RANK_DISPLAY_NAMES.get(rating.rank_tier, ""),
                wins=rating.wins,
                losses=rating.losses,
                total_duels=rating.total_duels,
                current_streak=rating.current_streak,
            )
        )

    # Get active season name
    season_result = await db.execute(
        select(PvPSeason).where(PvPSeason.is_active.is_(True)).limit(1)
    )
    season = season_result.scalar_one_or_none()

    return LeaderboardResponse(
        season=season.name if season else None,
        entries=entries,
        total_players=total,
    )


# ---------------------------------------------------------------------------
# Duel history
# ---------------------------------------------------------------------------

@router.get("/duels/me", response_model=list[DuelResponse])
async def get_my_duels(
    limit: int = Query(default=20, le=50),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's duel history."""
    stmt = (
        select(PvPDuel)
        .where(
            (PvPDuel.player1_id == user.id) | (PvPDuel.player2_id == user.id)
        )
        .order_by(desc(PvPDuel.created_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    duels = result.scalars().all()

    return [
        DuelResponse(
            id=d.id,
            player1_id=d.player1_id,
            player2_id=d.player2_id,
            status=d.status.value,
            difficulty=d.difficulty.value,
            round_number=d.round_number,
            player1_total=d.player1_total,
            player2_total=d.player2_total,
            winner_id=d.winner_id,
            is_draw=d.is_draw,
            is_pve=d.is_pve,
            duration_seconds=d.duration_seconds,
            round_1_data=d.round_1_data,
            round_2_data=d.round_2_data,
            anti_cheat_flags=d.anti_cheat_flags,
            replay_url=d.replay_url,
            player1_rating_delta=d.player1_rating_delta,
            player2_rating_delta=d.player2_rating_delta,
            rating_change_applied=d.rating_change_applied,
            created_at=d.created_at,
            completed_at=d.completed_at,
        )
        for d in duels
    ]


@router.get("/duels/{duel_id}", response_model=DuelResponse)
async def get_duel(
    duel_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get details of a specific duel."""
    result = await db.execute(
        select(PvPDuel).where(PvPDuel.id == duel_id)
    )
    duel = result.scalar_one_or_none()

    if not duel:
        raise HTTPException(status_code=404, detail=err.DUEL_NOT_FOUND)

    # Only participants or admins can view
    if duel.player1_id != user.id and duel.player2_id != user.id:
        if not hasattr(user, 'role') or user.role.value != 'admin':
            raise HTTPException(status_code=403, detail=err.NOT_A_PARTICIPANT)

    return DuelResponse(
        id=duel.id,
        player1_id=duel.player1_id,
        player2_id=duel.player2_id,
        status=duel.status.value,
        difficulty=duel.difficulty.value,
        round_number=duel.round_number,
        player1_total=duel.player1_total,
        player2_total=duel.player2_total,
        winner_id=duel.winner_id,
        is_draw=duel.is_draw,
        is_pve=duel.is_pve,
        duration_seconds=duel.duration_seconds,
        round_1_data=duel.round_1_data,
        round_2_data=duel.round_2_data,
        anti_cheat_flags=duel.anti_cheat_flags,
        replay_url=duel.replay_url,
        player1_rating_delta=duel.player1_rating_delta,
        player2_rating_delta=duel.player2_rating_delta,
        rating_change_applied=duel.rating_change_applied,
        created_at=duel.created_at,
        completed_at=duel.completed_at,
    )


# ---------------------------------------------------------------------------
# PvE accept (REST fallback when WS pve.accept fails)
# ---------------------------------------------------------------------------

@router.post("/accept-pve")
async def accept_pve(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept PvE duel (AI bot). Use when pve.offer was shown and user clicks «Играть с AI»."""
    await leave_queue(user.id)  # Ensure we're out of PvP queue
    duel = await create_pve_duel(user.id, db)
    await db.commit()
    return {"duel_id": str(duel.id), "is_pve": True, "difficulty": duel.difficulty.value}


@router.post("/challenge/{target_user_id}")
async def challenge_friend(
    target_user_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a direct PvP invitation to a friend and enqueue challenger."""
    if target_user_id == user.id:
        raise HTTPException(status_code=400, detail="Нельзя вызвать себя")

    target = (await db.execute(select(User).where(User.id == target_user_id, User.is_active.is_(True)))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Игрок не найден")

    friendship = (
        await db.execute(
            select(UserFriendship).where(
                UserFriendship.status == "accepted",
                or_(
                    (UserFriendship.requester_id == user.id) & (UserFriendship.addressee_id == target_user_id),
                    (UserFriendship.requester_id == target_user_id) & (UserFriendship.addressee_id == user.id),
                ),
            )
        )
    ).scalar_one_or_none()
    if not friendship:
        raise HTTPException(status_code=403, detail="Прямой вызов доступен только друзьям")

    queue_result = await join_queue(user.id, db, create_invitation=True)
    await db.commit()

    await notification_manager.send_to_user(str(target_user_id), {
        "type": "pvp.invitation",
        "data": {
          "challenger_id": str(user.id),
          "challenger_name": user.full_name,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, force=True)

    return {
        "status": "sent",
        "queue": queue_result,
        "target_user_id": str(target_user_id),
    }


# ---------------------------------------------------------------------------
# Queue status
# ---------------------------------------------------------------------------

@router.get("/queue/status")
async def get_queue_status(
    _: User = Depends(get_current_user),
):
    """Get current matchmaking queue size."""
    size = await get_queue_size()
    return {"queue_size": size}


# ---------------------------------------------------------------------------
# Anti-cheat (admin)
# ---------------------------------------------------------------------------

@router.get("/admin/anti-cheat/flags", response_model=list[AntiCheatFlagResponse])
async def get_anti_cheat_flags(
    user_id: uuid.UUID | None = None,
    flagged_only: bool = True,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """Get anti-cheat flags (admin only)."""
    stmt = select(AntiCheatLog).order_by(desc(AntiCheatLog.created_at))

    if user_id:
        stmt = stmt.where(AntiCheatLog.user_id == user_id)
    if flagged_only:
        stmt = stmt.where(AntiCheatLog.flagged.is_(True))

    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    logs = result.scalars().all()

    return [
        AntiCheatFlagResponse(
            id=log.id,
            user_id=log.user_id,
            duel_id=log.duel_id,
            check_type=log.check_type.value,
            score=log.score,
            flagged=log.flagged,
            action_taken=log.action_taken.value,
            details=log.details,
            resolution=log.resolution,
            created_at=log.created_at,
        )
        for log in logs
    ]


@router.put("/admin/anti-cheat/resolve/{flag_id}")
async def resolve_anti_cheat_flag(
    flag_id: uuid.UUID,
    resolution: str,  # "clean" | "cheating_confirmed" | "false_positive"
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """Resolve an anti-cheat flag (admin only)."""
    result = await db.execute(
        select(AntiCheatLog).where(AntiCheatLog.id == flag_id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail=err.FLAG_NOT_FOUND)

    log.resolution = resolution
    log.resolved_by = admin.id
    log.resolved_at = datetime.now(timezone.utc)
    db.add(log)

    return {"status": "resolved", "resolution": resolution}


# ---------------------------------------------------------------------------
# Season management (admin)
# ---------------------------------------------------------------------------

@router.post("/admin/season/create", response_model=SeasonResponse)
async def create_season(
    name: str,
    start_date: datetime,
    end_date: datetime,
    rewards: dict | None = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """Create a new PvP season (admin only)."""
    # Deactivate previous season
    result = await db.execute(
        select(PvPSeason).where(PvPSeason.is_active.is_(True))
    )
    for old_season in result.scalars().all():
        old_season.is_active = False
        db.add(old_season)

    season = PvPSeason(
        name=name,
        start_date=start_date,
        end_date=end_date,
        rewards=rewards,
        is_active=True,
    )
    db.add(season)
    await db.flush()

    # Apply soft reset
    reset_count = await apply_season_reset(db, season.id)

    return SeasonResponse(
        id=season.id,
        name=season.name,
        start_date=season.start_date,
        end_date=season.end_date,
        is_active=season.is_active,
        rewards=season.rewards,
    )


@router.get("/season/active", response_model=SeasonResponse | None)
async def get_active_season(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Get current active PvP season."""
    result = await db.execute(
        select(PvPSeason).where(PvPSeason.is_active.is_(True)).limit(1)
    )
    season = result.scalar_one_or_none()

    if not season:
        return None

    return SeasonResponse(
        id=season.id,
        name=season.name,
        start_date=season.start_date,
        end_date=season.end_date,
        is_active=season.is_active,
        rewards=season.rewards,
    )
