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
        if payload is None or payload.get("type") != "access":
            await _send(ws, "auth.error", {"detail": "Invalid token"})
            await ws.close(code=4001, reason="Invalid token")
            return None
        user_id = uuid.UUID(payload["sub"])
    except Exception:
        await _send(ws, "auth.error", {"detail": "Invalid token"})
        return None

    async with async_session() as db:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if not user or not user.is_active:
            await _send(ws, "auth.error", {"detail": "User not found"})
            await ws.close(code=4003, reason="User inactive")
            return None

    # Check if user was logged out or token revoked
    from app.core.deps import _is_user_blacklisted, _is_token_revoked
    if await _is_user_blacklisted(str(user_id)):
        await _send(ws, "auth.error", {"detail": "Token has been revoked"})
        return None
    jti = payload.get("jti")
    if jti and await _is_token_revoked(jti):
        await _send(ws, "auth.error", {"detail": "Token has been revoked"})
        return None

    await _send(ws, "auth.success", {"user_id": str(user.id), "role": user.role.value})
    return user


def _resolve_owner_id(user: User) -> uuid.UUID | None:
    if user.role.value in ("admin", "rop"):
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

            # L6c fix: per-user rate limit across all connections (Redis).
            from app.core.ws_rate_limiter import check_user_rate_limit
            if not await check_user_rate_limit(str(user.id), scope="game_crm"):
                await _send(websocket, "error", {
                    "code": "rate_limited_user",
                    "detail": "Слишком много сообщений со всех ваших сессий.",
                })
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
                # T2 fix: bound WS text input at 10KB to prevent DoS via
                # oversized LLM prompt (same as training.py).
                _WS_MAX_TEXT_CHARS = 10_000
                raw_content = (data.get("content") or msg.get("content") or "").strip()
                if len(raw_content) > _WS_MAX_TEXT_CHARS:
                    logger.warning(
                        "WS game_crm story.message truncated from %d to %d chars",
                        len(raw_content), _WS_MAX_TEXT_CHARS,
                    )
                content = raw_content[:_WS_MAX_TEXT_CHARS]
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
    except WebSocketDisconnect:
        logger.info("Game CRM WebSocket disconnected: user=%s", user.id)
    except Exception as exc:
        logger.error("Game CRM WebSocket error: user=%s error=%s", user.id, exc, exc_info=True)
        try:
            await _send(websocket, "error", {"detail": "Internal server error"})
        except Exception:
            pass
    finally:
        try:
            await websocket.close(code=1000)
        except Exception:
            pass
