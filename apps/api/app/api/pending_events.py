"""HTTP polling fallback for WsOutboxEvent (Roadmap §10.3).

The WS outbox drains on reconnect, but some clients (mobile Safari, flaky
corporate networks) take 10-30 s to re-establish the WebSocket. Expose a
dedupable HTTP pull so the UI can grab missed critical events while the
WS reconnects.

Caller flow:
  GET  /me/pending-events        → { events: [...] }
  POST /me/pending-events/ack    { ids: [...] } → { acknowledged: N }
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.user import User
from app.services import ws_delivery

router = APIRouter()


class PendingEventOut(BaseModel):
    id: uuid.UUID
    event_type: str
    payload: dict
    correlation_id: str | None
    created_at: str
    expires_at: str


class PendingEventsResponse(BaseModel):
    events: list[PendingEventOut] = Field(default_factory=list)


class AckRequest(BaseModel):
    ids: list[uuid.UUID] = Field(..., max_length=100)


class AckResponse(BaseModel):
    acknowledged: int


@router.get("/me/pending-events", response_model=PendingEventsResponse)
# F-L6-3 fix: a buggy client hot-looping on reconnect could DOS the
# endpoint; 30 req/min per IP is ample for the WS-reconnect use case
# (frontend polls at most every few seconds during disconnect).
@limiter.limit("30/minute")
async def get_pending_events(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PendingEventsResponse:
    pending = await ws_delivery.list_pending_for_user(db, user.id, limit=50)
    return PendingEventsResponse(
        events=[
            PendingEventOut(
                id=event.id,
                event_type=event.event_type,
                payload=event.payload or {},
                correlation_id=event.correlation_id,
                created_at=event.created_at.isoformat() if event.created_at else "",
                expires_at=event.expires_at.isoformat() if event.expires_at else "",
            )
            for event in pending
        ],
    )


@router.post("/me/pending-events/ack", response_model=AckResponse)
@limiter.limit("60/minute")
async def ack_pending_events(
    request: Request,
    body: AckRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AckResponse:
    if len(body.ids) > 100:
        raise HTTPException(status_code=400, detail="too many ids")
    count = await ws_delivery.mark_delivered_by_ids(db, user_id=user.id, ids=body.ids)
    await db.commit()
    return AckResponse(acknowledged=count)
