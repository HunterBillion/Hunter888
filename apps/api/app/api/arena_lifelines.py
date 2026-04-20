"""REST endpoints for Arena lifelines (hint / skip / 50-50).

Sprint 4 (2026-04-20). WebSocket-only routing would mean patching 5
game loops (arena, duel, rapid, gauntlet, tournament). REST keeps the
integration flat: client calls POST /api/arena/lifeline/* with the
match context, gets JSON back, renders.

Skip lifeline is still advisory — the client must also emit a
``pvp.answer`` (empty or "__skip__") to the match WS so the server-side
round clock ends cleanly. This endpoint just debits the token and
returns confirmation.
"""

from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.deps import get_current_user
from app.core.rate_limit import limiter
from app.models.user import User
from app.services.arena.lifelines import (
    DEFAULT_QUOTAS,
    consume,
    generate_hint,
    get_remaining,
    init_for_match,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/arena/lifeline", tags=["arena"])


Mode = Literal["arena", "duel", "rapid", "pve", "tournament"]


class InitRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    mode: Mode


class LifelineRemainingResponse(BaseModel):
    hints: int
    skips: int
    fiftys: int


class HintRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    question_text: str = Field(..., min_length=4, max_length=2000)


class HintResponse(BaseModel):
    consumed: bool
    text: str
    article: str | None
    confidence: float
    remaining: LifelineRemainingResponse


class SkipRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)


class SkipResponse(BaseModel):
    consumed: bool
    remaining: LifelineRemainingResponse


class FiftyFiftyRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)


class FiftyFiftyResponse(BaseModel):
    consumed: bool
    remaining: LifelineRemainingResponse


@router.post("/init", response_model=LifelineRemainingResponse)
@limiter.limit("20/minute")
async def init_lifelines(
    request: Request,
    body: InitRequest,
    user: User = Depends(get_current_user),
):
    """Initialise lifeline counters for this (session, user, mode)."""

    quota = await init_for_match(
        session_id=body.session_id, user_id=str(user.id), mode=body.mode,
    )
    return LifelineRemainingResponse(
        hints=quota.hints, skips=quota.skips, fiftys=quota.fiftys,
    )


@router.get("/remaining", response_model=LifelineRemainingResponse)
@limiter.limit("60/minute")
async def remaining(
    request: Request,
    session_id: str,
    user: User = Depends(get_current_user),
):
    data = await get_remaining(session_id=session_id, user_id=str(user.id))
    return LifelineRemainingResponse(**data)


@router.post("/hint", response_model=HintResponse)
@limiter.limit("10/minute")
async def use_hint(
    request: Request,
    body: HintRequest,
    user: User = Depends(get_current_user),
):
    """Consume a hint and return a short RAG-grounded pointer.

    Rate-limited aggressively: hint consumes an LLM + RAG round-trip. Even
    with the per-match quota cap (``DEFAULT_QUOTAS``), a malicious client
    could replay ``init`` + ``hint`` across many match IDs to burn tokens.
    10/min is comfortably above any legitimate gameplay pattern.
    """

    consumed = await consume(
        session_id=body.session_id, user_id=str(user.id), kind="hint",
    )
    if not consumed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="У тебя нет свободных подсказок в этом матче.",
        )

    payload = await generate_hint(question_text=body.question_text)
    remaining_ = await get_remaining(
        session_id=body.session_id, user_id=str(user.id),
    )
    logger.info(
        "lifeline.hint user=%s session=%s article=%s",
        user.id, body.session_id, payload.article,
    )
    return HintResponse(
        consumed=True,
        text=payload.text,
        article=payload.article,
        confidence=payload.confidence,
        remaining=LifelineRemainingResponse(**remaining_),
    )


@router.post("/skip", response_model=SkipResponse)
@limiter.limit("30/minute")
async def use_skip(
    request: Request,
    body: SkipRequest,
    user: User = Depends(get_current_user),
):
    """Debit a skip. Client must still emit a ``pvp.answer`` on its WS
    with a sentinel payload so the round clock closes."""

    consumed = await consume(
        session_id=body.session_id, user_id=str(user.id), kind="skip",
    )
    if not consumed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="У тебя нет свободных пропусков в этом матче.",
        )
    remaining_ = await get_remaining(
        session_id=body.session_id, user_id=str(user.id),
    )
    return SkipResponse(consumed=True, remaining=LifelineRemainingResponse(**remaining_))


@router.post("/fifty", response_model=FiftyFiftyResponse)
@limiter.limit("30/minute")
async def use_fifty_fifty(
    request: Request,
    body: FiftyFiftyRequest,
    user: User = Depends(get_current_user),
):
    consumed = await consume(
        session_id=body.session_id, user_id=str(user.id), kind="fifty",
    )
    if not consumed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="У тебя нет свободных 50/50 в этом матче.",
        )
    remaining_ = await get_remaining(
        session_id=body.session_id, user_id=str(user.id),
    )
    return FiftyFiftyResponse(consumed=True, remaining=LifelineRemainingResponse(**remaining_))
