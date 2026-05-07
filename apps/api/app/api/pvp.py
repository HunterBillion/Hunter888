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

from app.core.rate_limit import limiter
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors as err
from app.core.deps import get_current_user, require_role
from app.services.arena_gates import can_access_mode, can_access_feature, FEATURE_LEVEL_GATES
from app.database import get_db
from app.models.pvp import (
    AntiCheatLog,
    DuelDifficulty,
    DuelStatus,
    GauntletRun,
    PvEBossRun,
    PvELadderRun,
    PvEMode,
    PvPDuel,
    PvPRating,
    PvPRankTier,
    PvPSeason,
    PvPTeam,
    RapidFireMatch,
    RANK_DISPLAY_NAMES,
)
from app.models.progress import ManagerProgress
from app.models.user import User, UserFriendship
from app.schemas.pvp import (
    AntiCheatFlagResponse,
    AvailableCharacter,
    AvailableCharactersResponse,
    DuelResponse,
    GauntletCooldownResponse,
    GauntletCreateRequest,
    GauntletCreateResponse,
    LeaderboardEntry,
    LeaderboardResponse,
    PvEBossCreateResponse,
    PvELadderCreateResponse,
    PvEMirrorCreateResponse,
    RapidFireCreateResponse,
    RatingResponse,
    SeasonResponse,
    TeamCreateRequest,
    TeamCreateResponse,
)
from app.services.glicko2 import get_or_create_rating, apply_season_reset
from app.services.pvp_matchmaker import (
    QUEUE_META_KEY,
    check_gauntlet_cooldown,
    create_pve_duel,
    get_queue_size,
    join_queue,
    leave_queue,
    set_gauntlet_cooldown,
)
from app.core.redis_pool import get_redis as _redis
from app.ws.notifications import notification_manager

router = APIRouter()


# ---------------------------------------------------------------------------
# Rating
# ---------------------------------------------------------------------------

@router.get("/rating/me", response_model=RatingResponse)
async def get_my_rating(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    rating_type: str = Query("training_duel", description="Rating type: training_duel | knowledge_arena | team_battle | rapid_fire"),
):
    """Get current user's PvP rating and rank."""
    rating = await get_or_create_rating(user.id, db, rating_type=rating_type)

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
    scope: str = Query(default="active", pattern="^(active|all_time)$"),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Get PvP leaderboard, optionally filtered by rank tier.

    scope=active: only players active in last 30 days (default).
    scope=all_time: all placed players regardless of activity.
    """
    from datetime import timedelta

    from app.models.user import UserRole

    # B5-11: PvP leaderboard is the *manager* player cohort. Without
    # the role filter, an admin running smoke duels lands at the top
    # of the public ranking (audit found "Администратор" rank=1 on
    # prod). Restrict to ``role='manager'`` here and in the count
    # below so the FE leaderboard matches what users expect.
    stmt = (
        select(PvPRating, User)
        .join(User, User.id == PvPRating.user_id)
        .where(PvPRating.placement_done.is_(True))
        .where(User.role == UserRole.manager)
    )

    # S3-04: Filter inactive players (no game in 30 days)
    if scope == "active":
        active_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        stmt = stmt.where(PvPRating.last_played > active_cutoff)

    if tier:
        stmt = stmt.where(PvPRating.rank_tier == tier)

    stmt = stmt.order_by(desc(PvPRating.rating)).offset(offset).limit(limit)
    result = await db.execute(stmt)
    rows = result.all()

    # Total count (same filters — must mirror the SELECT exactly).
    count_stmt = (
        select(func.count(PvPRating.id))
        .join(User, User.id == PvPRating.user_id)
        .where(PvPRating.placement_done.is_(True))
        .where(User.role == UserRole.manager)
    )
    if scope == "active":
        active_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        count_stmt = count_stmt.where(PvPRating.last_played > active_cutoff)
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

    # Hide anti-cheat flags from non-admin users
    ac_flags = duel.anti_cheat_flags if (hasattr(user, 'role') and user.role.value == 'admin') else None

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
        anti_cheat_flags=ac_flags,
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
@limiter.limit("10/minute")
async def accept_pve(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept PvE duel (AI bot). Use when pve.offer was shown and user clicks «Играть с AI»."""
    # Capture CharacterPicker selection from queue meta BEFORE
    # leave_queue wipes it, so PvE-fallback respects user's choice.
    cid: uuid.UUID | None = None
    try:
        raw_cid = await _redis().hget(QUEUE_META_KEY.format(user_id=user.id), "character_id")
        if raw_cid:
            cid = uuid.UUID(raw_cid if isinstance(raw_cid, str) else raw_cid.decode())
    except (TypeError, ValueError, AttributeError):
        cid = None
    await leave_queue(user.id)  # Ensure we're out of PvP queue
    duel = await create_pve_duel(user.id, db, character_id=cid)
    await db.commit()
    return {"duel_id": str(duel.id), "is_pve": True, "difficulty": duel.difficulty.value}


# ---------------------------------------------------------------------------
# Dispute verdict (PR-C 2026-05-05)
#
# User on prod: "нельзя оспорить" — DuelStatus.disputed enum value already
# existed (models/pvp.py:40, "Under manual review") but no endpoint or WS
# command ever set it. The judge was final.
#
# This endpoint flips the duel to ``disputed`` status and stamps the user's
# reason into ``pve_metadata["dispute"]`` for the methodology team to
# review. Re-judging through a different LLM provider is intentionally
# deferred to a follow-up — the priority for this PR is closing the user's
# explicit "нельзя оспорить" complaint with a working button + audit trail.
#
# Constraints: only completed duels can be disputed; only the participants;
# only once per duel; rate-limited to prevent abuse.
# ---------------------------------------------------------------------------

@router.post("/duels/{duel_id}/dispute")
@limiter.limit("3/hour")
async def dispute_duel(
    request: Request,
    duel_id: uuid.UUID,
    payload: dict | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """File a dispute against the AI judge's verdict on a completed duel.

    Body (optional): ``{"reason": "<user-provided text up to 500 chars>"}``

    Returns 202 with a confirmation message; the methodology team reviews
    flagged duels manually. No second judge run is performed in this PR
    — that's a follow-up that needs careful handling around rating recalc.
    """
    result = await db.execute(select(PvPDuel).where(PvPDuel.id == duel_id))
    duel = result.scalar_one_or_none()
    if not duel:
        raise HTTPException(status_code=404, detail=err.DUEL_NOT_FOUND)
    if duel.player1_id != user.id and duel.player2_id != user.id:
        raise HTTPException(status_code=403, detail=err.NOT_A_PARTICIPANT)
    if duel.status != DuelStatus.completed:
        # Only completed duels carry a verdict to dispute. Cancelled /
        # disputed / in-flight rows return 409 so the FE can show a clear
        # "this duel doesn't have a verdict yet / can't be disputed" toast.
        raise HTTPException(
            status_code=409,
            detail="Оспорить можно только завершённую дуэль с вердиктом.",
        )

    # Idempotency: if dispute already filed, surface the existing record.
    existing = (duel.pve_metadata or {}).get("dispute") if isinstance(duel.pve_metadata, dict) else None
    if existing:
        return {
            "duel_id": str(duel.id),
            "status": "already_disputed",
            "filed_at": existing.get("filed_at"),
        }

    reason = ""
    if isinstance(payload, dict):
        raw = payload.get("reason")
        if isinstance(raw, str):
            reason = raw.strip()[:500]

    # Stamp dispute metadata. We DO NOT clear winner_id / totals — those
    # remain as the original verdict; only `status` flips so downstream
    # dashboards can filter "duels under review".
    meta = duel.pve_metadata if isinstance(duel.pve_metadata, dict) else {}
    meta = dict(meta)  # JSONB mutation safety
    meta["dispute"] = {
        "filed_by": str(user.id),
        "filed_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason or None,
        "status": "pending",
    }
    duel.pve_metadata = meta
    duel.status = DuelStatus.disputed
    db.add(duel)
    await db.commit()

    return {
        "duel_id": str(duel.id),
        "status": "dispute_filed",
        "message": "Спор отправлен на ручной разбор. Команда методологии"
                   " свяжется с тобой через приложение.",
    }


@router.post("/challenge/{target_user_id}")
@limiter.limit("10/minute")
async def challenge_friend(
    request: Request,
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


_VALID_RESOLUTIONS = {"clean", "cheating_confirmed", "false_positive"}


@router.put("/admin/anti-cheat/resolve/{flag_id}")
@limiter.limit("10/minute")
async def resolve_anti_cheat_flag(
    request: Request,
    flag_id: uuid.UUID,
    resolution: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """Resolve an anti-cheat flag (admin only)."""
    if resolution not in _VALID_RESOLUTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid resolution. Must be one of: {', '.join(sorted(_VALID_RESOLUTIONS))}",
        )

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
    await db.commit()

    return {"status": "resolved", "resolution": resolution}


# ---------------------------------------------------------------------------
# Season management (admin)
# ---------------------------------------------------------------------------

@router.post("/admin/season/create", response_model=SeasonResponse)
@limiter.limit("3/minute")
async def create_season(
    request: Request,
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


# ---------------------------------------------------------------------------
# PvE Modes (DOC_10: Ladder, Boss Rush, Mirror Match)
# ---------------------------------------------------------------------------

_PVE_BOT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

_LADDER_BOT_CONFIGS = [
    {"archetype": "passive", "difficulty_offset": -1, "label": "Бот 1 — Лёгкий"},
    {"archetype": "pragmatic", "difficulty_offset": 0, "label": "Бот 2 — Средний"},
    {"archetype": "aggressive", "difficulty_offset": 1, "label": "Бот 3 — Сложный"},
    {"archetype": "know_it_all", "difficulty_offset": 2, "label": "Бот 4 — Экспертный"},
    {"archetype": "manipulator", "difficulty_offset": 3, "label": "Бот 5 — Экстремальный"},
]

_BOSS_CONFIGS = [
    {
        "boss_type": "lawyer_perfectionist",
        "archetype": "know_it_all",
        "label": "Юрист-перфекционист",
        "mechanic": "legal_penalty",
        "description": "Каждая юридическая ошибка = мгновенно -10 баллов",
    },
    {
        "boss_type": "emotional_vampire",
        "archetype": "desperate",
        "label": "Эмоциональный вампир",
        "mechanic": "composure_drain",
        "description": "Самообладание клиента падает с каждым сообщением",
    },
    {
        "boss_type": "chameleon",
        "archetype": "sarcastic",
        "label": "Хамелеон",
        "mechanic": "archetype_shift",
        "description": "Меняет архетип каждые 2 сообщения",
    },
]

_DIFFICULTY_LEVELS = ["easy", "medium", "hard"]


def _base_difficulty_for_rating(rating_val: float) -> DuelDifficulty:
    if rating_val < 1600:
        return DuelDifficulty.easy
    elif rating_val < 2200:
        return DuelDifficulty.medium
    return DuelDifficulty.hard


@router.post("/pve/ladder/create", response_model=PvELadderCreateResponse)
async def create_pve_ladder(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a PvE Bot Ladder run (Level 9+). 5 sequential bots."""
    mp = (await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user.id)
    )).scalar_one_or_none()
    user_level = mp.current_level if mp else 1
    if user_level < 9:
        raise HTTPException(status_code=403, detail="Доступно с уровня 9")

    active_run = (await db.execute(
        select(PvELadderRun).where(
            PvELadderRun.user_id == user.id,
            PvELadderRun.is_complete == False,  # noqa: E712
        )
    )).scalar_one_or_none()
    if active_run:
        raise HTTPException(status_code=409, detail="Активная лестница уже существует")

    rating = await get_or_create_rating(user.id, db)
    base_diff = _base_difficulty_for_rating(rating.rating)
    base_idx = _DIFFICULTY_LEVELS.index(base_diff.value)

    bot_configs = []
    for cfg in _LADDER_BOT_CONFIGS:
        eff = min(2, max(0, base_idx + cfg["difficulty_offset"]))
        bot_configs.append({
            **cfg,
            "base_difficulty": base_diff.value,
            "effective_difficulty": _DIFFICULTY_LEVELS[eff],
        })

    first_duel = PvPDuel(
        player1_id=user.id,
        player2_id=_PVE_BOT_ID,
        status=DuelStatus.pending,
        difficulty=base_diff,
        is_pve=True,
        pve_mode=PvEMode.ladder.value,
        pve_metadata={"ladder_bot_index": 0, "archetype": bot_configs[0]["archetype"]},
    )
    db.add(first_duel)
    await db.flush()

    ladder_run = PvELadderRun(
        user_id=user.id,
        current_bot_index=0,
        bots_defeated=0,
        cumulative_score=0.0,
        bot_configs=bot_configs,
        duel_ids=[str(first_duel.id)],
    )
    db.add(ladder_run)
    await db.commit()

    return PvELadderCreateResponse(
        run_id=ladder_run.id,
        total_bots=5,
        current_bot_index=0,
        first_duel_id=first_duel.id,
    )


@router.post("/pve/boss/create", response_model=PvEBossCreateResponse)
async def create_pve_boss(
    boss_index: int = Query(0, ge=0, le=2),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a PvE Boss Rush run (Level 10+). 3 unique boss bots."""
    mp = (await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user.id)
    )).scalar_one_or_none()
    user_level = mp.current_level if mp else 1
    if user_level < 10:
        raise HTTPException(status_code=403, detail="Доступно с уровня 10")

    boss_cfg = _BOSS_CONFIGS[boss_index]

    duel = PvPDuel(
        player1_id=user.id,
        player2_id=_PVE_BOT_ID,
        status=DuelStatus.pending,
        difficulty=DuelDifficulty.hard,
        is_pve=True,
        pve_mode=PvEMode.boss.value,
        pve_metadata={
            "boss_type": boss_cfg["boss_type"],
            "archetype": boss_cfg["archetype"],
            "mechanic": boss_cfg["mechanic"],
            "boss_index": boss_index,
        },
    )
    db.add(duel)
    await db.flush()

    boss_run = PvEBossRun(
        user_id=user.id,
        boss_index=boss_index,
        boss_type=boss_cfg["boss_type"],
        duel_id=duel.id,
        special_mechanics_log={"mechanic": boss_cfg["mechanic"], "events": []},
    )
    db.add(boss_run)
    await db.commit()

    return PvEBossCreateResponse(
        run_id=boss_run.id,
        boss_index=boss_index,
        boss_type=boss_cfg["boss_type"],
        duel_id=duel.id,
        message=f"Boss Rush: {boss_cfg['label']} — {boss_cfg['description']}",
    )


@router.post("/pve/mirror/create", response_model=PvEMirrorCreateResponse)
async def create_pve_mirror(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a PvE Mirror Match (Level 15+). AI mimics your style."""
    mp = (await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user.id)
    )).scalar_one_or_none()
    user_level = mp.current_level if mp else 1
    if user_level < 15:
        raise HTTPException(status_code=403, detail="Доступно с уровня 15")

    style_summary: dict = {"sessions_analyzed": 0, "avg_messages": 0, "sample_messages": []}
    try:
        from app.models.training import TrainingSession
        past_sessions = (await db.execute(
            select(TrainingSession)
            .where(TrainingSession.user_id == user.id)
            .order_by(TrainingSession.created_at.desc())
            .limit(20)
        )).scalars().all()

        total_msgs = 0
        sample_messages: list[str] = []
        for sess in past_sessions:
            if hasattr(sess, "history") and sess.history:
                user_msgs = [m for m in (sess.history or []) if m.get("role") == "user"]
                total_msgs += len(user_msgs)
                for m in user_msgs[:1]:
                    if len(sample_messages) < 5:
                        sample_messages.append(m.get("content", "")[:200])

        style_summary = {
            "sessions_analyzed": len(past_sessions),
            "avg_messages": total_msgs // max(len(past_sessions), 1),
            "sample_messages": sample_messages,
        }
    except Exception:
        pass

    duel = PvPDuel(
        player1_id=user.id,
        player2_id=_PVE_BOT_ID,
        status=DuelStatus.pending,
        difficulty=DuelDifficulty.hard,
        is_pve=True,
        pve_mode=PvEMode.mirror.value,
        pve_metadata={"mirror_style": style_summary, "archetype": "mirror"},
    )
    db.add(duel)
    await db.commit()

    return PvEMirrorCreateResponse(
        duel_id=duel.id,
        style_summary=style_summary,
    )


# ===========================================================================
# DOC_09: New PvP Mode Endpoints — Rapid Fire, Gauntlet, Team 2v2
# ===========================================================================


# ---------------------------------------------------------------------------
# Rapid Fire
# ---------------------------------------------------------------------------

@router.post("/rapid-fire/create", response_model=RapidFireCreateResponse)
@limiter.limit("10/minute")
async def create_rapid_fire(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create and start a Rapid Fire match (5 mini-rounds, seller only, AI client).

    Returns match_id. Client should then connect via WS and send
    {type: "rapid_fire.start", match_id: "<id>"}.
    """
    mp = (await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user.id)
    )).scalar_one_or_none()
    user_level = mp.current_level if mp else 1
    if not can_access_feature(user_level, "pvp_rapid_fire"):
        raise HTTPException(
            status_code=403,
            detail=f"Rapid Fire доступен с уровня {FEATURE_LEVEL_GATES['pvp_rapid_fire']}",
        )
    match = RapidFireMatch(
        player1_id=user.id,
        is_pve=True,
    )
    db.add(match)
    await db.flush()
    await db.commit()

    return RapidFireCreateResponse(
        match_id=match.id,
        total_rounds=5,
        time_per_round=120,
        messages_per_round=5,
    )


# ---------------------------------------------------------------------------
# Gauntlet
# ---------------------------------------------------------------------------

@router.get("/gauntlet/cooldown", response_model=GauntletCooldownResponse)
async def get_gauntlet_cooldown_status(
    user: User = Depends(get_current_user),
):
    """Check gauntlet cooldown for current user (6h between attempts)."""
    status = await check_gauntlet_cooldown(user.id)
    return GauntletCooldownResponse(**status)


@router.post("/gauntlet/create", response_model=GauntletCreateResponse)
@limiter.limit("5/minute")
async def create_gauntlet(
    request: Request,
    body: GauntletCreateRequest = GauntletCreateRequest(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Gauntlet run (3-5 PvE duels with progressive difficulty).

    Enforces 6-hour cooldown between attempts.
    Returns run_id. Client should then connect via WS and send
    {type: "gauntlet.start", run_id: "<id>"}.
    """
    mp = (await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user.id)
    )).scalar_one_or_none()
    user_level = mp.current_level if mp else 1
    if not can_access_feature(user_level, "pvp_gauntlet"):
        raise HTTPException(
            status_code=403,
            detail=f"Gauntlet доступен с уровня {FEATURE_LEVEL_GATES['pvp_gauntlet']}",
        )
    # Check cooldown
    cooldown = await check_gauntlet_cooldown(user.id)
    if cooldown["on_cooldown"]:
        hours_left = cooldown["seconds_remaining"] / 3600
        raise HTTPException(
            status_code=429,
            detail=f"Испытание на перезарядке. Осталось {hours_left:.1f} ч.",
        )

    rating = await get_or_create_rating(user.id, db)
    base_difficulty = "easy" if rating.rating < 1600 else ("medium" if rating.rating < 2200 else "hard")

    run = GauntletRun(
        user_id=user.id,
        total_duels=body.total_duels,
    )
    db.add(run)
    await db.flush()

    # Set cooldown
    await set_gauntlet_cooldown(user.id)
    await db.commit()

    return GauntletCreateResponse(
        run_id=run.id,
        total_duels=run.total_duels,
        base_difficulty=base_difficulty,
    )


# ---------------------------------------------------------------------------
# Team 2v2
# ---------------------------------------------------------------------------

@router.post("/team/create", response_model=TeamCreateResponse)
@limiter.limit("10/minute")
async def create_team_battle(
    request: Request,
    body: TeamCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Team 2v2 battle. Requires a partner_id (must be a friend).

    Returns team_id. Both players should connect via WS and send
    {type: "team.start", team_id: "<id>"}.
    """
    mp = (await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user.id)
    )).scalar_one_or_none()
    user_level = mp.current_level if mp else 1
    if not can_access_feature(user_level, "team_battle_2v2"):
        raise HTTPException(
            status_code=403,
            detail=f"Командный бой 2v2 доступен с уровня {FEATURE_LEVEL_GATES['team_battle_2v2']}",
        )
    if body.partner_id == user.id:
        raise HTTPException(status_code=400, detail="Нельзя создать команду с самим собой")

    # Check partner exists
    partner = (await db.execute(
        select(User).where(User.id == body.partner_id, User.is_active.is_(True))
    )).scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=404, detail="Партнёр не найден")

    # Check friendship
    friendship = (
        await db.execute(
            select(UserFriendship).where(
                UserFriendship.status == "accepted",
                or_(
                    (UserFriendship.requester_id == user.id) & (UserFriendship.addressee_id == body.partner_id),
                    (UserFriendship.requester_id == body.partner_id) & (UserFriendship.addressee_id == user.id),
                ),
            )
        )
    ).scalar_one_or_none()
    if not friendship:
        raise HTTPException(status_code=403, detail="Командная битва доступна только друзьям")

    # Get average rating
    r1 = await get_or_create_rating(user.id, db, rating_type="team_battle")
    r2 = await get_or_create_rating(body.partner_id, db, rating_type="team_battle")
    avg_rating = (r1.rating + r2.rating) / 2.0

    team = PvPTeam(
        player1_id=user.id,
        player2_id=body.partner_id,
        avg_rating=avg_rating,
    )
    db.add(team)
    await db.flush()
    await db.commit()

    # Notify partner
    await notification_manager.send_to_user(str(body.partner_id), {
        "type": "team.invitation",
        "data": {
            "team_id": str(team.id),
            "creator_id": str(user.id),
            "creator_name": user.full_name,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, force=True)

    return TeamCreateResponse(
        team_id=team.id,
        player1_id=user.id,
        player2_id=body.partner_id,
    )


# ─── Content→Arena PR-4: custom characters in /pvp lobby ──────────────────


@router.get("/characters/available", response_model=AvailableCharactersResponse)
async def get_available_characters(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200, description="Max items per bucket"),
):
    """Return custom characters the current user can pick for a duel.

    Two buckets:
    * ``own``    — presets the user created (always visible).
    * ``shared`` — other users' presets with ``is_shared=True``, capped
      to ``limit`` rows ordered by recency. Excludes presets the user
      already owns to avoid duplicates across the two buckets.

    Used by the frontend matchmaking lobby to render a "pick a client"
    grid before pressing "Найти соперника" / "Сыграть с ботом". When a
    character is picked, the FE forwards its id in ``pve.accept`` /
    ``queue.join`` payload (extension landing in PR-4 follow-up); the
    server resolves it to the duel's archetype and persona.

    The endpoint is intentionally a plain REST GET (not part of the WS
    flow) so it can be cached by the FE for the lifetime of the lobby
    open and pre-fetched on hover.
    """
    from app.models.custom_character import CustomCharacter

    own_rows = (
        await db.execute(
            select(CustomCharacter)
            .where(CustomCharacter.user_id == user.id)
            .order_by(desc(CustomCharacter.last_played_at), desc(CustomCharacter.created_at))
            .limit(limit)
        )
    ).scalars().all()

    shared_rows = (
        await db.execute(
            select(CustomCharacter)
            .where(CustomCharacter.is_shared.is_(True))
            .where(CustomCharacter.user_id != user.id)
            .order_by(desc(CustomCharacter.created_at))
            .limit(limit)
        )
    ).scalars().all()

    def _to_card(c: "CustomCharacter", *, is_own: bool) -> AvailableCharacter:
        return AvailableCharacter(
            id=c.id,
            name=c.name,
            archetype=c.archetype,
            profession=c.profession,
            difficulty=c.difficulty,
            description=c.description,
            is_own=is_own,
            is_shared=bool(c.is_shared),
            play_count=int(c.play_count or 0),
            avg_score=c.avg_score,
        )

    own = [_to_card(c, is_own=True) for c in own_rows]
    shared = [_to_card(c, is_own=False) for c in shared_rows]
    return AvailableCharactersResponse(
        own=own,
        shared=shared,
        total=len(own) + len(shared),
    )
