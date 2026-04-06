"""WebSocket endpoint for CRM AI-client chat."""

import asyncio
import logging
import uuid

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.security import decode_token
from app.database import async_session
from app.models.user import User
from app.services.game_crm_service import GameCRMService
from app.core.ws_rate_limiter import game_crm_limiter

logger = logging.getLogger(__name__)


async def _send(ws: WebSocket, msg_type: str, data: dict | None = None) -> None:
    try:
        await ws.send_json({"type": msg_type, "data": data or {}})
    except Exception:
        pass


async def _auth_websocket(ws: WebSocket) -> User | None:
    try:
        msg = await asyncio.wait_for(ws.receive_json(), timeout=10.0)
    except Exception:
        await _send(ws, "auth.error", {"detail": "Auth timeout"})
        return None

    token = msg.get("token") or (msg.get("data") or {}).get("token")
    if msg.get("type") != "auth" or not token:
        await _send(ws, "auth.error", {"detail": "Expected auth message"})
        return None

    try:
        payload = decode_token(token)
        user_id = uuid.UUID(payload["sub"])
    except Exception as exc:
        await _send(ws, "auth.error", {"detail": f"Invalid token: {exc}"})
        return None

    async with async_session() as db:
        user = (await db.execute(select(User).where(User.id == user_id, User.is_active.is_(True)))).scalar_one_or_none()
        if not user:
            await _send(ws, "auth.error", {"detail": "User not found"})
            return None

    await _send(ws, "auth.success", {"user_id": str(user.id), "role": user.role.value})
    return user


def _resolve_owner_id(user: User) -> uuid.UUID | None:
    if user.role.value in ("admin", "methodologist", "rop"):
        return None
    return user.id


async def game_crm_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    user = await _auth_websocket(websocket)
    if not user:
        await websocket.close(code=1008)
        return

    subscribed_story_id: uuid.UUID | None = None
    _rate_limiter = game_crm_limiter()

    try:
        while True:
            try:
                msg = await websocket.receive_json()
            except WebSocketDisconnect:
                break

            if not _rate_limiter.is_allowed():
                await _send(websocket, "error", {"code": "rate_limited", "detail": "Too many messages"})
                continue

            msg_type = msg.get("type")
            data = msg.get("data") or {}

            if msg_type == "ping":
                await _send(websocket, "pong")
                continue

            if msg_type == "story.subscribe":
                story_id_raw = data.get("story_id") or msg.get("story_id")
                if not story_id_raw:
                    await _send(websocket, "error", {"detail": "story_id is required"})
                    continue

                try:
                    story_id = uuid.UUID(str(story_id_raw))
                except (TypeError, ValueError):
                    await _send(websocket, "error", {"detail": "Invalid story_id"})
                    continue

                async with async_session() as db:
                    service = GameCRMService(db)
                    await service.get_story_detail(story_id, user_id=_resolve_owner_id(user))
                subscribed_story_id = story_id
                await _send(websocket, "story.subscribed", {"story_id": str(story_id)})
                continue

            if msg_type == "story.message":
                story_id_raw = data.get("story_id") or msg.get("story_id") or subscribed_story_id
                content = (data.get("content") or msg.get("content") or "").strip()
                narrative_date = data.get("narrative_date") or msg.get("narrative_date")

                if not story_id_raw or not content:
                    await _send(websocket, "error", {"detail": "story_id and content are required"})
                    continue

                try:
                    story_id = uuid.UUID(str(story_id_raw))
                except (TypeError, ValueError):
                    await _send(websocket, "error", {"detail": "Invalid story_id"})
                    continue

                async with async_session() as db:
                    service = GameCRMService(db)
                    result = await service.send_game_message(
                        story_id,
                        _resolve_owner_id(user),
                        user.id,
                        content=content,
                        narrative_date=narrative_date,
                    )
                    await db.commit()

                await _send(websocket, "game_crm.message.created", {
                    "story_id": str(story_id),
                    "manager_event": result.get("event"),
                    "ai_event": (result.get("reply") or {}).get("event"),
                })
                continue

            await _send(websocket, "error", {"detail": f"Unknown message type: {msg_type}"})
    except Exception as exc:
        logger.error("Game CRM WebSocket error: user=%s error=%s", user.id, exc)
        await _send(websocket, "error", {"detail": str(exc)})
