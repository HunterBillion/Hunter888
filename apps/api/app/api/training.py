import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.consent import check_consent_accepted
from app.core.deps import get_current_user
from app.database import get_db
from app.models.training import Message, SessionStatus, TrainingSession
from app.models.user import User
from app.schemas.training import (
    MessageResponse,
    SessionResponse,
    SessionResultResponse,
    SessionStartRequest,
)

router = APIRouter()


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def start_session(
    body: SessionStartRequest,
    user: User = Depends(check_consent_accepted),
    db: AsyncSession = Depends(get_db),
):
    session = TrainingSession(
        user_id=user.id,
        scenario_id=body.scenario_id,
    )
    db.add(session)
    await db.flush()
    return session


@router.get("/sessions/{session_id}", response_model=SessionResultResponse)
async def get_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.id == session_id,
            TrainingSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    messages_result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.sequence_number)
    )
    messages = messages_result.scalars().all()

    return SessionResultResponse(
        session=SessionResponse.model_validate(session),
        messages=[MessageResponse.model_validate(m) for m in messages],
        score_breakdown=session.scoring_details,
    )


@router.post("/sessions/{session_id}/end", response_model=SessionResponse)
async def end_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.id == session_id,
            TrainingSession.user_id == user.id,
            TrainingSession.status == SessionStatus.active,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active session not found")

    session.status = SessionStatus.completed
    await db.flush()
    return session


@router.get("/history", response_model=list[SessionResponse])
async def training_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
):
    result = await db.execute(
        select(TrainingSession)
        .where(TrainingSession.user_id == user.id)
        .order_by(TrainingSession.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()
