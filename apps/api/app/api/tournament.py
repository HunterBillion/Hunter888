"""Tournament API: weekly competitions."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.user import User
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
    session_id: str
    score: float


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
            "week_start": t.week_start.isoformat(),
            "week_end": t.week_end.isoformat(),
            "max_attempts": t.max_attempts,
            "bonus_xp": [t.bonus_xp_first, t.bonus_xp_second, t.bonus_xp_third],
        },
        "leaderboard": leaderboard,
    }


@router.post("/submit")
async def submit(
    body: SubmitEntryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a training session score to the active tournament."""
    t = await get_active_tournament(db)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active tournament")

    entry = await submit_entry(
        tournament_id=t.id,
        user_id=user.id,
        session_id=uuid.UUID(body.session_id),
        score=body.score,
        db=db,
    )

    if not entry:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Max attempts reached or tournament ended")

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
async def create_weekly(
    user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Admin: manually create this week's tournament."""
    t = await create_weekly_tournament(db)
    if not t:
        return {"message": "Tournament already exists for this week or no scenarios available"}
    return {"id": str(t.id), "title": t.title, "week_start": t.week_start.isoformat()}
