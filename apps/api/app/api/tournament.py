"""Tournament API: weekly competitions + bracket/knockout tournaments."""

import uuid
from datetime import datetime, timedelta, timezone

from app.core.rate_limit import limiter
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors as err
from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.tournament import TournamentFormat
from app.models.user import User

from app.services.bracket import (
    broadcast_bracket_event,
    check_and_process_timeouts,
    complete_bracket_match,
    generate_bracket,
    get_bracket_view,
    get_bracket_visualization,
    get_participants,
    process_forfeit,
    register_participant,
    schedule_round_matches,
    start_bracket_match,
)
from app.services.tournament import (
    create_weekly_tournament,
    get_active_tournament,
    get_tournament_leaderboard,
    submit_entry,
)

router = APIRouter()


class TournamentResponse(BaseModel):
    id: str
    title: str
    description: str
    scenario_id: str
    week_start: str
    week_end: str
    max_attempts: int
    bonus_xp_first: int
    bonus_xp_second: int
    bonus_xp_third: int


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    full_name: str
    avatar_url: str | None = None
    best_score: float
    attempts: int
    is_podium: bool


class SubmitEntryRequest(BaseModel):
    session_id: str = Field(..., min_length=36, max_length=36)
    score: float = Field(..., ge=0.0, le=200.0)


@router.get("/active")
async def get_active(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current active tournament. Returns null if none."""
    t = await get_active_tournament(db)
    if not t:
        return {"tournament": None}

    leaderboard = await get_tournament_leaderboard(t.id, db, limit=10)

    return {
        "tournament": {
            "id": str(t.id),
            "title": t.title,
            "description": t.description,
            "scenario_id": str(t.scenario_id),
            "format": t.format,
            "week_start": t.week_start.isoformat(),
            "week_end": t.week_end.isoformat(),
            "max_attempts": t.max_attempts,
            "bonus_xp": [t.bonus_xp_first, t.bonus_xp_second, t.bonus_xp_third],
            "registration_end": t.registration_end.isoformat() if t.registration_end else None,
            "current_round": t.current_round_num,
            "bracket_size": t.bracket_size,
        },
        "leaderboard": leaderboard,
    }


@router.post("/submit")
@limiter.limit("10/minute")
async def submit(
    request: Request,
    body: SubmitEntryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a training session score to the active tournament."""
    t = await get_active_tournament(db)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err.NO_ACTIVE_TOURNAMENT)

    entry = await submit_entry(
        tournament_id=t.id,
        user_id=user.id,
        session_id=uuid.UUID(body.session_id),
        score=body.score,
        db=db,
    )

    if not entry:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err.TOURNAMENT_MAX_ATTEMPTS)

    return {
        "entry_id": str(entry.id),
        "attempt": entry.attempt_number,
        "score": entry.score,
    }


@router.get("/leaderboard/{tournament_id}", response_model=list[LeaderboardEntry])
async def leaderboard(
    tournament_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get tournament leaderboard."""
    return await get_tournament_leaderboard(tournament_id, db)


@router.post("/create-weekly")
@limiter.limit("3/minute")
async def create_weekly(
    request: Request,
    user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Admin: manually create this week's tournament."""
    t = await create_weekly_tournament(db)
    if not t:
        return {"message": err.TOURNAMENT_ALREADY_EXISTS}
    return {"id": str(t.id), "title": t.title, "week_start": t.week_start.isoformat()}


# ─── Bracket / knockout endpoints ─────────────────────────────────────────────


class CreateBracketRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=300)
    description: str = Field("", max_length=2000)
    scenario_id: str = Field(..., min_length=36, max_length=36)
    registration_hours: int = Field(24, gt=0, le=720)
    bracket_size: int | None = Field(None, ge=4, le=64)

    @field_validator("scenario_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError("Некорректный UUID для scenario_id")
        return v

    @field_validator("bracket_size")
    @classmethod
    def validate_power_of_2(cls, v: int | None) -> int | None:
        if v is not None and (v & (v - 1)) != 0:
            raise ValueError("bracket_size должен быть степенью 2 (4, 8, 16, 32, 64)")
        return v


class ReportMatchRequest(BaseModel):
    match_id: str = Field(..., min_length=36, max_length=36)
    winner_id: str = Field(..., min_length=36, max_length=36)
    player1_score: float = Field(..., ge=0.0, le=200.0)
    player2_score: float = Field(..., ge=0.0, le=200.0)
    duel_id: str | None = Field(None, min_length=36, max_length=36)


@router.post("/bracket/create")
@limiter.limit("3/minute")
async def create_bracket_tournament(
    request: Request,
    body: CreateBracketRequest,
    user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Admin: create a bracket/knockout tournament."""
    from app.models.tournament import Tournament

    now = datetime.now(timezone.utc)
    reg_end = now + timedelta(hours=body.registration_hours)

    t = Tournament(
        title=body.title,
        description=body.description or f"Турнир на выбывание: {body.title}",
        scenario_id=uuid.UUID(body.scenario_id),
        week_start=now,
        week_end=reg_end + timedelta(days=3),  # 3 days for bracket play
        format=TournamentFormat.bracket.value,
        registration_end=reg_end,
        bracket_size=body.bracket_size,
    )
    db.add(t)
    await db.flush()

    return {
        "id": str(t.id),
        "title": t.title,
        "format": t.format,
        "registration_end": reg_end.isoformat(),
    }


@router.post("/bracket/{tournament_id}/register")
@limiter.limit("5/minute")
async def bracket_register(
    request: Request,
    tournament_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register for a bracket tournament with anti-cheat fingerprint."""
    # Record fingerprint on tournament registration
    try:
        from app.services.anti_cheat import record_fingerprint, check_multi_account
        _ip = request.client.host if request.client else "unknown"
        _ua = request.headers.get("user-agent")
        await record_fingerprint(user_id=user.id, ip_address=_ip, user_agent=_ua, event_type="tournament_register", db=db)

        # Multi-account check — block if same IP/UA registered another account
        multi = await check_multi_account(user.id, db)
        if multi.get("is_suspicious") and multi.get("confidence", 0) > 0.8:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Подозрение на мульти-аккаунт. Обратитесь к администратору.",
            )
    except HTTPException:
        raise
    except Exception:
        pass  # Don't block registration on fingerprint failure

    p = await register_participant(tournament_id, user.id, db)
    if not p:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Регистрация закрыта или вы уже зарегистрированы",
        )
    return {
        "participant_id": str(p.id),
        "seed": p.seed,
        "rating_snapshot": p.rating_snapshot,
    }


@router.post("/bracket/{tournament_id}/generate")
@limiter.limit("3/minute")
async def bracket_generate(
    request: Request,
    tournament_id: uuid.UUID,
    user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Admin: close registration and generate the bracket."""
    matches = await generate_bracket(tournament_id, db)
    if not matches:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось создать сетку (мало участников или неверный формат)",
        )
    return {"matches_created": len(matches)}


@router.get("/bracket/{tournament_id}")
async def bracket_view(
    tournament_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full bracket visualization data."""
    data = await get_bracket_view(tournament_id, db)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Турнир не найден")
    return data


@router.post("/bracket/match/result")
@limiter.limit("10/minute")
async def bracket_match_result(
    request: Request,
    body: ReportMatchRequest,
    user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Admin: report the result of a bracket match."""
    match = await complete_bracket_match(
        match_id=uuid.UUID(body.match_id),
        winner_id=uuid.UUID(body.winner_id),
        player1_score=body.player1_score,
        player2_score=body.player2_score,
        duel_id=uuid.UUID(body.duel_id) if body.duel_id else None,
        db=db,
    )
    if not match:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось записать результат",
        )
    return {
        "match_id": str(match.id),
        "winner_id": str(match.winner_id),
        "status": match.status,
    }


@router.get("/bracket/{tournament_id}/participants")
async def bracket_participants(
    tournament_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get list of registered participants."""
    participants = await get_participants(tournament_id, db)
    return [
        {
            "user_id": str(p.user_id),
            "seed": p.seed,
            "rating_snapshot": p.rating_snapshot,
            "eliminated_at_round": p.eliminated_at_round,
            "final_placement": p.final_placement,
        }
        for p in participants
    ]


class StartMatchRequest(BaseModel):
    match_id: str = Field(..., min_length=36, max_length=36)


@router.post("/bracket/match/start")
@limiter.limit("10/minute")
async def bracket_match_start(
    request: Request,
    body: StartMatchRequest,
    user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Admin: create a PvP duel for a pending bracket match."""
    match = await start_bracket_match(uuid.UUID(body.match_id), db)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Матч не готов (игроки не определены или статус неверный)",
        )
    await db.commit()
    return {
        "match_id": str(match.id),
        "duel_id": str(match.duel_id),
        "status": match.status,
    }


# ─── Advanced bracket features: forfeit, timeouts, visualization ─────────────


class ForfeitRequest(BaseModel):
    match_id: str = Field(..., min_length=36, max_length=36)


@router.post("/bracket/{tournament_id}/forfeit")
@limiter.limit("5/minute")
async def bracket_forfeit(
    request: Request,
    tournament_id: uuid.UUID,
    body: ForfeitRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Player forfeits their bracket match."""
    from app.services.bracket import process_forfeit

    match = await db.get(
        __import__("app.models.tournament", fromlist=["BracketMatch"]).BracketMatch,
        uuid.UUID(body.match_id),
    )
    if not match or match.tournament_id != tournament_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Матч не найден")

    # Check if user is in the match
    if user.id not in (match.player1_id, match.player2_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы не участвуете в этом матче",
        )

    result_match = await process_forfeit(match.id, user.id, db)
    if not result_match:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось обработать поражение по неявке",
        )

    await db.commit()

    return {
        "match_id": str(result_match.id),
        "winner_id": str(result_match.winner_id),
        "status": result_match.status,
    }


@router.post("/bracket/{tournament_id}/check-timeouts")
@limiter.limit("3/minute")
async def bracket_check_timeouts(
    request: Request,
    tournament_id: uuid.UUID,
    user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Admin: process all timeout forfeits for pending matches."""
    from app.services.bracket import check_and_process_timeouts

    from app.models.tournament import Tournament as TournamentModel
    t = await db.get(TournamentModel, tournament_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Турнир не найден")

    result = await check_and_process_timeouts(tournament_id, db)
    await db.commit()

    return {
        "auto_forfeits": result["auto_forfeits"],
        "mutual_no_shows": result["mutual_no_shows"],
    }


@router.get("/bracket/{tournament_id}/visualization")
async def bracket_visualization(
    tournament_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get enhanced bracket visualization for frontend rendering."""
    from app.services.bracket import get_bracket_visualization

    data = await get_bracket_visualization(tournament_id, db)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Турнир не найден")

    return data


# ─── Tournament history + prizes ─────────────────────────────────────────────


@router.get("/history")
async def tournament_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get list of past tournaments with user's placement."""
    from sqlalchemy import select as sa_select, func as sa_func
    from app.models.tournament import Tournament, TournamentEntry, TournamentParticipant

    # Past tournaments (inactive)
    result = await db.execute(
        sa_select(Tournament)
        .where(Tournament.is_active == False)  # noqa: E712
        .order_by(Tournament.week_end.desc())
        .limit(20)
    )
    tournaments = list(result.scalars().all())

    history = []
    for t in tournaments:
        # Check if user participated (leaderboard entry or bracket participant)
        entry_result = await db.execute(
            sa_select(
                sa_func.max(TournamentEntry.score).label("best_score"),
                sa_func.count(TournamentEntry.id).label("attempts"),
            ).where(
                TournamentEntry.tournament_id == t.id,
                TournamentEntry.user_id == user.id,
            )
        )
        entry_row = entry_result.one()

        # Bracket placement
        placement = None
        if t.format == "bracket":
            p_result = await db.execute(
                sa_select(TournamentParticipant.final_placement).where(
                    TournamentParticipant.tournament_id == t.id,
                    TournamentParticipant.user_id == user.id,
                )
            )
            placement = p_result.scalar_one_or_none()

        # User's leaderboard rank (for weekly format)
        rank = None
        if entry_row.best_score:
            rank_result = await db.execute(
                sa_select(sa_func.count()).select_from(
                    sa_select(TournamentEntry.user_id)
                    .where(TournamentEntry.tournament_id == t.id)
                    .group_by(TournamentEntry.user_id)
                    .having(sa_func.max(TournamentEntry.score) > entry_row.best_score)
                    .subquery()
                )
            )
            rank = (rank_result.scalar() or 0) + 1

        history.append({
            "id": str(t.id),
            "title": t.title,
            "format": t.format,
            "week_start": t.week_start.isoformat(),
            "week_end": t.week_end.isoformat(),
            "participated": entry_row.best_score is not None or placement is not None,
            "best_score": round(float(entry_row.best_score), 1) if entry_row.best_score else None,
            "attempts": entry_row.attempts or 0,
            "rank": rank,
            "bracket_placement": placement,
        })

    return {"history": history}


@router.post("/bracket/{tournament_id}/award-prizes")
@limiter.limit("3/minute")
async def bracket_award_prizes(
    request: Request,
    tournament_id: uuid.UUID,
    user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Admin: award XP prizes to bracket tournament top-3 finishers."""
    from app.models.tournament import Tournament, TournamentParticipant
    from app.models.user import User as UserModel

    t = await db.get(Tournament, tournament_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Турнир не найден")
    if t.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Турнир ещё не завершён")

    # Get top-3 participants
    result = await db.execute(
        select(TournamentParticipant, UserModel.full_name)
        .join(UserModel, UserModel.id == TournamentParticipant.user_id)
        .where(
            TournamentParticipant.tournament_id == tournament_id,
            TournamentParticipant.final_placement.isnot(None),
            TournamentParticipant.final_placement <= 3,
        )
        .order_by(TournamentParticipant.final_placement)
    )
    rows = result.all()

    xp_tiers = [t.bonus_xp_first, t.bonus_xp_second, t.bonus_xp_third]
    prizes = []

    for participant, name in rows:
        place = participant.final_placement
        xp = xp_tiers[place - 1] if place <= len(xp_tiers) else 0

        # Award XP to user
        u = await db.get(UserModel, participant.user_id)
        if u and xp > 0:
            u.xp = (u.xp or 0) + xp
            db.add(u)

        prizes.append({
            "user_id": str(participant.user_id),
            "full_name": name,
            "placement": place,
            "bonus_xp": xp,
        })

    await db.commit()
    return {"prizes": prizes, "tournament_id": str(tournament_id)}
