"""Arena tutorial endpoints — first-match onboarding.

Phase C (2026-04-20). A tiny router covering:

  GET  /api/tutorial/arena/status    — has this user finished the Arena
                                       tutorial? returns {completed, at}.
  POST /api/tutorial/arena/complete  — mark tutorial as done. Idempotent —
                                       a second call is a no-op (keeps the
                                       original completion timestamp so we
                                       don't reset analytics).

The scripted 3-round content lives entirely on the frontend
(``/pvp/tutorial`` route) — backend only owns the completion bookmark.
This keeps LLM cost at zero for first-time users: no bot duel spin-up, no
judge round-trip.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/api/tutorial", tags=["tutorial"])


class ArenaTutorialStatus(BaseModel):
    completed: bool
    completed_at: Optional[datetime] = None


class ArenaTutorialCompleteResponse(BaseModel):
    completed: bool
    completed_at: datetime
    first_time: bool


@router.get("/arena/status", response_model=ArenaTutorialStatus)
@limiter.limit("60/minute")
async def get_arena_tutorial_status(
    request: Request,
    user: User = Depends(get_current_user),
) -> ArenaTutorialStatus:
    ts = user.arena_tutorial_completed_at
    return ArenaTutorialStatus(
        completed=ts is not None,
        completed_at=ts,
    )


@router.post("/arena/complete", response_model=ArenaTutorialCompleteResponse)
@limiter.limit("10/minute")
async def complete_arena_tutorial(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ArenaTutorialCompleteResponse:
    """Mark the Arena tutorial as completed for the current user.

    Idempotent: if already completed, preserves the original timestamp.
    ``first_time`` in the response tells the client whether this call was
    the one that set the flag — useful for triggering the "Поехали на
    арену!" celebratory animation only once.
    """

    now = datetime.now(timezone.utc)
    already = user.arena_tutorial_completed_at is not None

    if not already:
        # Single UPDATE — avoids loading the user twice.
        await db.execute(
            update(User)
            .where(User.id == user.id)
            .values(arena_tutorial_completed_at=now)
        )
        await db.commit()
        return ArenaTutorialCompleteResponse(
            completed=True,
            completed_at=now,
            first_time=True,
        )

    return ArenaTutorialCompleteResponse(
        completed=True,
        completed_at=user.arena_tutorial_completed_at,  # type: ignore[arg-type]
        first_time=False,
    )
