"""WebSocket handler for real-time training sessions.

Protocol (from TZ section 7.8):
- Client sends: session.start, audio.chunk, text.message, session.end
- Server sends: session.ready, session.started, transcription.result,
                character.response, emotion.update, session.ended, error

Full implementation with STT, session management, emotion tracking, and
reconnection/timeout handling.
"""

import asyncio
import base64
import json
import logging
import time
import uuid

from fastapi import WebSocket, WebSocketDisconnect, status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import decode_token
from app.database import async_session
from app.models.character import Character, EmotionState
from app.models.scenario import Scenario
from app.models.training import MessageRole, SessionStatus, TrainingSession
from app.models.user import User
import redis.asyncio as aioredis

from app.services.emotion import get_emotion, init_emotion, transition_emotion
from app.services.session_manager import (
    RateLimitError,
    SessionError,
    add_message,
    check_message_limit,
    end_session,
    get_message_history,
    start_session,
    update_activity,
)
from app.services.stt import STTError, transcribe_audio

logger = logging.getLogger(__name__)

SILENCE_TIMEOUT_SEC = 30


async def _send(ws: WebSocket, msg_type: str, data: dict) -> None:
    """Helper to send a typed JSON message to the client."""
    try:
        await ws.send_json({"type": msg_type, "data": data})
    except Exception:
        logger.debug("Failed to send message type=%s", msg_type)


async def _send_error(ws: WebSocket, message: str, code: str = "error") -> None:
    await _send(ws, "error", {"message": message, "code": code})


async def _silence_watchdog(
    ws: WebSocket,
    session_id: uuid.UUID,
    stop_event: asyncio.Event,
) -> None:
    """Background task: detect prolonged silence and warn/close."""
    while not stop_event.is_set():
        await asyncio.sleep(5)
        if stop_event.is_set():
            break

        from app.services.session_manager import check_silence_timeout

        timed_out = await check_silence_timeout(session_id, SILENCE_TIMEOUT_SEC)
        if timed_out:
            await _send(ws, "session.timeout", {
                "message": "No activity detected. Session will close.",
                "timeout_seconds": SILENCE_TIMEOUT_SEC,
            })
            # End the session due to timeout
            async with async_session() as db:
                await end_session(session_id, db, status=SessionStatus.abandoned)
                await db.commit()
            stop_event.set()
            break


async def _handle_session_start(
    ws: WebSocket,
    data: dict,
    state: dict,
) -> None:
    """Handle session.start: resume existing session or create a new one.

    Accepts either:
    - session_id: Resume session created via REST POST /training/sessions
    - scenario_id + user_id: Create a new session via WebSocket
    """
    session_id_str = data.get("session_id")

    if session_id_str:
        # Resume existing session created via REST
        try:
            session_id = uuid.UUID(session_id_str)
        except ValueError:
            await _send_error(ws, "Invalid session_id format", "invalid_field")
            return

        async with async_session() as db:
            result = await db.execute(
                select(TrainingSession).where(TrainingSession.id == session_id)
            )
            session = result.scalar_one_or_none()
            if session is None:
                await _send_error(ws, "Session not found", "not_found")
                return

            # Load scenario + character
            scenario_result = await db.execute(
                select(Scenario).where(Scenario.id == session.scenario_id)
            )
            scenario = scenario_result.scalar_one_or_none()

            character = None
            if scenario and scenario.character_id:
                char_result = await db.execute(
                    select(Character).where(Character.id == scenario.character_id)
                )
                character = char_result.scalar_one_or_none()

            initial_emotion = EmotionState.cold
            if character and character.initial_emotion:
                initial_emotion = character.initial_emotion

            # Initialize emotion in Redis for this session
            await init_emotion(session.id, initial_emotion)

            # Initialize Redis session state
            r = aioredis.from_url(settings.redis_url, decode_responses=True)
            try:
                state_key = f"session:{session.id}:state"
                redis_state = json.dumps({
                    "user_id": str(session.user_id),
                    "scenario_id": str(session.scenario_id),
                    "status": "active",
                    "started_at": time.time(),
                    "message_count": 0,
                    "last_activity": time.time(),
                })
                await r.set(state_key, redis_state, ex=3600)
            except Exception:
                logger.warning("Failed to init Redis for resumed session %s", session.id)
            finally:
                await r.aclose()

            # Update handler state
            state["session_id"] = session.id
            state["user_id"] = session.user_id
            state["scenario_id"] = session.scenario_id
            state["character_prompt_path"] = character.prompt_path if character else None
            state["active"] = True

        await _send(ws, "session.started", {
            "session_id": str(session.id),
            "character_name": character.name if character else "Клиент",
            "initial_emotion": initial_emotion.value,
            "scenario_title": scenario.title if scenario else "Тренировка",
        })
        return

    # Create new session via WS (original flow with scenario_id + user_id)
    scenario_id_str = data.get("scenario_id")
    if not scenario_id_str:
        await _send_error(ws, "scenario_id or session_id is required", "missing_field")
        return

    try:
        scenario_id = uuid.UUID(scenario_id_str)
    except ValueError:
        await _send_error(ws, "Invalid scenario_id format", "invalid_field")
        return

    user_id_str = data.get("user_id")
    if not user_id_str:
        await _send_error(ws, "user_id is required", "missing_field")
        return

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        await _send_error(ws, "Invalid user_id format", "invalid_field")
        return

    async with async_session() as db:
        result = await db.execute(
            select(Scenario).where(Scenario.id == scenario_id, Scenario.is_active == True)  # noqa: E712
        )
        scenario = result.scalar_one_or_none()
        if scenario is None:
            await _send_error(ws, "Scenario not found or inactive", "not_found")
            return

        char_result = await db.execute(
            select(Character).where(Character.id == scenario.character_id)
        )
        character = char_result.scalar_one_or_none()
        if character is None:
            await _send_error(ws, "Character not found", "not_found")
            return

        initial_emotion = character.initial_emotion or EmotionState.cold

        try:
            session = await start_session(
                user_id=user_id,
                scenario_id=scenario_id,
                initial_emotion=initial_emotion,
                db=db,
            )
        except RateLimitError as e:
            await _send_error(ws, str(e), "rate_limit")
            return
        except SessionError as e:
            await _send_error(ws, str(e), "session_error")
            return

        await db.commit()

    state["session_id"] = session.id
    state["user_id"] = user_id
    state["scenario_id"] = scenario_id
    state["character_prompt_path"] = character.prompt_path if character else None
    state["active"] = True

    await _send(ws, "session.started", {
        "session_id": str(session.id),
        "character_name": character.name,
        "initial_emotion": initial_emotion.value,
        "scenario_title": scenario.title,
    })


async def _handle_audio_chunk(
    ws: WebSocket,
    data: dict,
    state: dict,
) -> None:
    """Handle audio.chunk: forward to STT, return transcription."""
    session_id = state.get("session_id")
    if not session_id:
        await _send_error(ws, "No active session. Send session.start first.", "no_session")
        return

    await update_activity(session_id)

    # Audio is sent as base64-encoded bytes
    audio_b64 = data.get("audio")
    if not audio_b64:
        await _send_error(ws, "audio field is required (base64-encoded)", "missing_field")
        return

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception:
        await _send_error(ws, "Invalid base64 audio data", "invalid_data")
        return

    # Check message limit
    try:
        await check_message_limit(session_id)
    except RateLimitError as e:
        await _send_error(ws, str(e), "rate_limit")
        return

    # Transcribe via STT
    try:
        stt_result = await transcribe_audio(audio_bytes)
    except STTError as e:
        logger.warning("STT unavailable for session %s: %s", session_id, e)
        await _send(ws, "stt.unavailable", {
            "message": "Распознавание речи недоступно. Используйте текстовый ввод.",
        })
        return

    if not stt_result.text.strip():
        await _send(ws, "transcription.result", {
            "text": "",
            "confidence": 0.0,
            "is_empty": True,
        })
        return

    # Send transcription result
    await _send(ws, "transcription.result", {
        "text": stt_result.text,
        "confidence": stt_result.confidence,
        "language": stt_result.language,
        "duration_ms": stt_result.duration_ms,
        "is_empty": False,
    })

    # Save user message to DB
    current_emotion = await get_emotion(session_id)
    async with async_session() as db:
        await add_message(
            session_id=session_id,
            role=MessageRole.user,
            content=stt_result.text,
            db=db,
            audio_duration_ms=stt_result.duration_ms,
            stt_confidence=stt_result.confidence,
            emotion_state=current_emotion.value,
        )
        await db.commit()

    # TODO: In Phase 2, send transcribed text to LLM for character response
    # For now, echo back a stub character response
    await _send(ws, "character.response", {
        "content": f"[STT OK] Received: {stt_result.text[:100]}",
        "emotion": current_emotion.value,
        "is_stub": True,
    })


async def _handle_text_message(
    ws: WebSocket,
    data: dict,
    state: dict,
) -> None:
    """Handle text.message: accept text input directly (fallback for no mic)."""
    session_id = state.get("session_id")
    if not session_id:
        await _send_error(ws, "No active session. Send session.start first.", "no_session")
        return

    await update_activity(session_id)

    content = data.get("content", "").strip()
    if not content:
        await _send_error(ws, "content field is required", "missing_field")
        return

    # Check message limit
    try:
        await check_message_limit(session_id)
    except RateLimitError as e:
        await _send_error(ws, str(e), "rate_limit")
        return

    current_emotion = await get_emotion(session_id)

    # Save user message
    async with async_session() as db:
        await add_message(
            session_id=session_id,
            role=MessageRole.user,
            content=content,
            db=db,
            emotion_state=current_emotion.value,
        )
        await db.commit()

    # TODO: In Phase 2, integrate with LLM for real character response
    # For now, return a stub response and update emotion
    new_emotion = await transition_emotion(session_id, "good_response")

    await _send(ws, "character.response", {
        "content": f"[Stub] Received: {content[:100]}",
        "emotion": new_emotion.value,
        "is_stub": True,
    })

    if new_emotion.value != current_emotion.value:
        await _send(ws, "emotion.update", {
            "previous": current_emotion.value,
            "current": new_emotion.value,
        })


async def _handle_session_end(
    ws: WebSocket,
    data: dict,
    state: dict,
) -> None:
    """Handle session.end: finalize session, save to DB, cleanup Redis."""
    session_id = state.get("session_id")
    if not session_id:
        await _send_error(ws, "No active session", "no_session")
        return

    async with async_session() as db:
        session = await end_session(session_id, db, status=SessionStatus.completed)
        await db.commit()

    state["active"] = False
    state["session_id"] = None

    result_data = {"message": "Session ended successfully"}
    if session:
        result_data.update({
            "session_id": str(session.id),
            "duration_seconds": session.duration_seconds,
            "status": session.status.value,
        })

    await _send(ws, "session.ended", result_data)


async def _authenticate_ws(websocket: WebSocket) -> uuid.UUID | None:
    """Validate JWT token from query parameter. Returns user_id or None."""
    token = websocket.query_params.get("token")
    if not token:
        return None

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        return None

    user_id_str = payload.get("sub")
    if not user_id_str:
        return None

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        return None

    # Verify user exists and is active
    async with async_session() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            return None

    return user_id


async def training_websocket(websocket: WebSocket) -> None:
    """Handle a training session WebSocket connection.

    Protocol:
    - Client sends JSON: {"type": "...", "data": {...}}
    - Server sends JSON: {"type": "...", "data": {...}}
    """
    # Authenticate before accepting
    user_id = await _authenticate_ws(websocket)
    if user_id is None:
        await websocket.close(code=http_status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    # Connection state
    state: dict = {
        "session_id": None,
        "user_id": user_id,
        "scenario_id": None,
        "character_prompt_path": None,
        "active": False,
    }

    watchdog_task: asyncio.Task | None = None
    stop_event = asyncio.Event()

    try:
        # Send ready signal
        await _send(websocket, "session.ready", {
            "message": "WebSocket connected. Send session.start to begin.",
        })

        while True:
            # Receive message with timeout for cleanup
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=SILENCE_TIMEOUT_SEC + 10,
                )
            except asyncio.TimeoutError:
                # Hard timeout — close connection
                if state.get("session_id"):
                    async with async_session() as db:
                        await end_session(
                            state["session_id"], db, status=SessionStatus.abandoned
                        )
                        await db.commit()
                await _send(websocket, "session.timeout", {
                    "message": "Connection timed out due to inactivity",
                })
                break

            # Check if watchdog triggered closure
            if stop_event.is_set():
                break

            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await _send_error(websocket, "Invalid JSON", "parse_error")
                continue

            msg_type = message.get("type")
            msg_data = message.get("data", {})

            if msg_type == "session.start":
                await _handle_session_start(websocket, msg_data, state)
                # Start silence watchdog after session starts
                if state.get("session_id") and watchdog_task is None:
                    watchdog_task = asyncio.create_task(
                        _silence_watchdog(websocket, state["session_id"], stop_event)
                    )

            elif msg_type == "audio.chunk":
                await _handle_audio_chunk(websocket, msg_data, state)

            elif msg_type == "text.message":
                await _handle_text_message(websocket, msg_data, state)

            elif msg_type == "session.end":
                await _handle_session_end(websocket, msg_data, state)
                stop_event.set()
                break

            elif msg_type == "ping":
                # Keep-alive / reconnection probe
                if state.get("session_id"):
                    await update_activity(state["session_id"])
                await _send(websocket, "pong", {})

            else:
                await _send_error(
                    websocket,
                    f"Unknown message type: {msg_type}",
                    "unknown_type",
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for session %s", state.get("session_id"))
        # Clean up abandoned session
        if state.get("session_id"):
            try:
                async with async_session() as db:
                    await end_session(
                        state["session_id"], db, status=SessionStatus.abandoned
                    )
                    await db.commit()
            except Exception:
                logger.error(
                    "Failed to cleanup session %s on disconnect", state.get("session_id")
                )
    except Exception:
        logger.exception("Unexpected error in training WebSocket")
        if state.get("session_id"):
            try:
                async with async_session() as db:
                    await end_session(
                        state["session_id"], db, status=SessionStatus.error
                    )
                    await db.commit()
            except Exception:
                logger.error("Failed to mark session %s as error", state.get("session_id"))
    finally:
        # Cancel watchdog
        stop_event.set()
        if watchdog_task and not watchdog_task.done():
            watchdog_task.cancel()
            try:
                await watchdog_task
            except asyncio.CancelledError:
                pass
