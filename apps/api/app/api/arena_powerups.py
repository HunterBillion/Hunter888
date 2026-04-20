"""REST endpoints for Arena power-ups (×2 XP, shield, ...).

Phase C (2026-04-20). Companion to ``arena_lifelines``. Same rate-limit
shape — every endpoint runs through ``limiter.limit`` so a malicious
client can't replay ``activate`` across many session IDs.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.deps import get_current_user
from app.core.rate_limit import limiter
from app.models.user import User
from app.services.arena.powerups import (
    POWERUP_DEFS,
    activate,
    get_remaining,
    init_for_match,
    peek_active,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/arena/powerup", tags=["arena"])


Mode = Literal["arena", "duel", "rapid", "pve", "tournament"]
Kind = Literal["doublexp"]


class InitRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    mode: Mode


class RemainingResponse(BaseModel):
    doublexp: int
    # When more kinds are added, extend here.
    active: str | None = None  # currently armed kind


class ActivateRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    kind: Kind


class ActivateResponse(BaseModel):
    activated: bool
    active: str | None
    remaining: RemainingResponse


async def _compose_remaining(session_id: str, user_id: str) -> RemainingResponse:
    counts = await get_remaining(session_id=session_id, user_id=user_id)
    active = await peek_active(session_id=session_id, user_id=user_id)
    return RemainingResponse(
        doublexp=int(counts.get("doublexp", 0)),
        active=active,
    )


@router.post("/init", response_model=RemainingResponse)
@limiter.limit("20/minute")
async def init_powerups(
    request: Request,
    body: InitRequest,
    user: User = Depends(get_current_user),
):
    await init_for_match(session_id=body.session_id, user_id=str(user.id), mode=body.mode)
    return await _compose_remaining(body.session_id, str(user.id))


@router.get("/remaining", response_model=RemainingResponse)
@limiter.limit("60/minute")
async def remaining(
    request: Request,
    session_id: str,
    user: User = Depends(get_current_user),
):
    return await _compose_remaining(session_id, str(user.id))


@router.post("/activate", response_model=ActivateResponse)
@limiter.limit("30/minute")
async def activate_powerup(
    request: Request,
    body: ActivateRequest,
    user: User = Depends(get_current_user),
):
    """Arm a power-up for the NEXT answer.

    Returns 409 only on logical errors (no quota, already armed). Redis
    transient errors are fail-open — activation appears to succeed from
    the client side; scoring treats a missing arm as multiplier=1.0.
    """

    # Quick sanity: the kind must be one we actually support on server.
    if body.kind not in POWERUP_DEFS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown power-up kind: {body.kind}",
        )

    consumed, reason = await activate(
        session_id=body.session_id, user_id=str(user.id), kind=body.kind,
    )
    if not consumed:
        if reason == "no_quota":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нет зарядов этого усиления в этом матче.",
            )
        if reason == "already_armed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Другое усиление уже активно — подожди следующего раунда.",
            )
        # storage_error / unknown_kind — return 503 (user can retry)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Не удалось активировать усиление. Попробуй ещё раз.",
        )

    remaining_ = await _compose_remaining(body.session_id, str(user.id))
    return ActivateResponse(
        activated=True,
        active=remaining_.active,
        remaining=remaining_,
    )
