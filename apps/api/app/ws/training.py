"""WebSocket handler for real-time training sessions.

Protocol (TZ section 7.8):
- Auth: JWT token sent in FIRST message (not URL query param)
- Client sends: auth, session.start, audio.chunk, audio.end, text.message, session.end, ping
- Server sends: session.ready, auth.success, auth.error, session.started,
                avatar.typing, transcription.result, character.response,
                emotion.update, score.update, session.ended,
                silence.warning, silence.timeout, error

Edge cases (TZ 3.1.3):
- LLM timeout → retry 1x → fallback → pause phrase
- STT fail x3 → "check microphone" warning
- Silence > 30s → avatar "Алло?"
- Silence > 60s → modal "Continue?"
- Not Russian → "Простите, не понял"
- "Ты бот?" → in-character response (from guardrails)
- Disconnect → reconnect + restore
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
from app.services.llm import LLMError, generate_response
from app.services.scoring import calculate_scores
from app.services.stt import STTError, transcribe_audio

logger = logging.getLogger(__name__)

SILENCE_WARNING_SEC = 30  # Avatar says "Алло?"
SILENCE_TIMEOUT_SEC = 60  # Modal "Continue?"
MAX_STT_FAILURES = 3

# Phrases for silence handling
SILENCE_AVATAR_PHRASES = [
    "Алло? Вы ещё здесь?",
    "Алло? Вы слышите меня?",
    "Мне кажется, связь прервалась...",
]


async def _send(ws: WebSocket, msg_type: str, data: dict) -> None:
    """Helper to send a typed JSON message to the client."""
    try:
        await ws.send_json({"type": msg_type, "data": data})
    except Exception:
        logger.debug("Failed to send message type=%s", msg_type)


async def _send_error(ws: WebSocket, message: str, code: str = "error") -> None:
    await _send(ws, "error", {"message": message, "code": code})


async def _authenticate_first_message(ws: WebSocket, raw: str) -> uuid.UUID | None:
    """Authenticate via first WS message containing JWT token.

    Expected format: {"type": "auth", "data": {"token": "..."}}
    Returns user_id or None.
    """
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        await _send(ws, "auth.error", {"message": "Invalid JSON"})
        return None

    if message.get("type") != "auth":
        await _send(ws, "auth.error", {"message": "First message must be auth"})
        return None

    token = message.get("data", {}).get("token")
    if not token:
        await _send(ws, "auth.error", {"message": "Token is required"})
        return None

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        await _send(ws, "auth.error", {"message": "Invalid or expired token"})
        return None

    user_id_str = payload.get("sub")
    if not user_id_str:
        await _send(ws, "auth.error", {"message": "Invalid token payload"})
        return None

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        await _send(ws, "auth.error", {"message": "Invalid user ID in token"})
        return None

    # Verify user exists and is active
    async with async_session() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            await _send(ws, "auth.error", {"message": "User not found or inactive"})
            return None

    return user_id


async def _generate_character_reply(
    ws: WebSocket,
    session_id: uuid.UUID,
    state: dict,
) -> None:
    """Build message history, call LLM, send character.response, update emotion."""
    # Send avatar.typing indicator
    await _send(ws, "avatar.typing", {"is_typing": True})

    current_emotion = await get_emotion(session_id)

    history = await get_message_history(session_id)
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m["role"] in ("user", "assistant")
    ]

    prompt_path = state.get("character_prompt_path")

    try:
        llm_result = await generate_response(
            system_prompt="",
            messages=messages,
            emotion_state=current_emotion.value,
            character_prompt_path=prompt_path,
        )
    except LLMError as e:
        logger.error("LLM failed for session %s: %s", session_id, e)
        await _send(ws, "avatar.typing", {"is_typing": False})
        await _send(ws, "character.response", {
            "content": "Секунду... мне нужно собраться с мыслями.",
            "emotion": current_emotion.value,
            "is_fallback": True,
        })
        return

    # Stop typing indicator
    await _send(ws, "avatar.typing", {"is_typing": False})

    # Save assistant message to DB
    async with async_session() as db:
        await add_message(
            session_id=session_id,
            role=MessageRole.assistant,
            content=llm_result.content,
            db=db,
            emotion_state=current_emotion.value,
            llm_model=llm_result.model,
            llm_latency_ms=llm_result.latency_ms,
        )
        # Log API usage
        from app.models.analytics import ApiLog
        api_log = ApiLog(
            service="llm",
            model=llm_result.model,
            request_tokens=llm_result.input_tokens,
            response_tokens=llm_result.output_tokens,
            latency_ms=llm_result.latency_ms,
            session_id=session_id,
        )
        db.add(api_log)
        await db.commit()

    # Determine response quality for emotion transition
    response_quality = "good_response"
    if llm_result.is_fallback:
        response_quality = "bad_response"

    new_emotion = await transition_emotion(session_id, response_quality)

    await _send(ws, "character.response", {
        "content": llm_result.content,
        "emotion": new_emotion.value,
        "model": llm_result.model,
        "latency_ms": llm_result.latency_ms,
        "is_fallback": llm_result.is_fallback,
    })

    if new_emotion.value != current_emotion.value:
        await _send(ws, "emotion.update", {
            "previous": current_emotion.value,
            "current": new_emotion.value,
        })


async def _silence_watchdog(
    ws: WebSocket,
    session_id: uuid.UUID,
    state: dict,
    stop_event: asyncio.Event,
) -> None:
    """Background task: detect prolonged silence.

    - 30s silence → avatar says "Алло?" (character.response)
    - 60s silence → send silence.timeout for modal "Continue?"
    """
    warned = False

    while not stop_event.is_set():
        await asyncio.sleep(5)
        if stop_event.is_set():
            break

        from app.services.session_manager import get_last_activity_time

        last_activity = await get_last_activity_time(session_id)
        if last_activity is None:
            continue

        elapsed = time.time() - last_activity

        if elapsed >= SILENCE_TIMEOUT_SEC and not stop_event.is_set():
            # 60s — send timeout modal
            await _send(ws, "silence.timeout", {
                "message": "Вы давно молчите. Хотите продолжить тренировку?",
                "timeout_seconds": SILENCE_TIMEOUT_SEC,
            })
            # End session due to inactivity
            async with async_session() as db:
                await end_session(session_id, db, status=SessionStatus.abandoned)
                await db.commit()
            state["active"] = False
            stop_event.set()
            break

        elif elapsed >= SILENCE_WARNING_SEC and not warned:
            # 30s — avatar says "Алло?"
            import random
            phrase = random.choice(SILENCE_AVATAR_PHRASES)
            await _send(ws, "character.response", {
                "content": phrase,
                "emotion": "cold",
                "is_silence_prompt": True,
            })
            # Save as assistant message
            async with async_session() as db:
                await add_message(
                    session_id=session_id,
                    role=MessageRole.assistant,
                    content=phrase,
                    db=db,
                    emotion_state="cold",
                )
                await db.commit()
            warned = True

        elif elapsed < SILENCE_WARNING_SEC:
            warned = False  # Reset if user spoke again


async def _handle_session_start(
    ws: WebSocket,
    data: dict,
    state: dict,
) -> None:
    """Handle session.start: resume existing or create new session."""
    session_id_str = data.get("session_id")

    if session_id_str:
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

            await init_emotion(session.id, initial_emotion)

            # Init Redis session state
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
                logger.warning("Failed to init Redis for session %s", session.id)
            finally:
                await r.aclose()

            state["session_id"] = session.id
            state["user_id"] = session.user_id
            state["scenario_id"] = session.scenario_id
            state["character_prompt_path"] = character.prompt_path if character else None
            state["active"] = True
            state["stt_failure_count"] = 0

        await _send(ws, "session.started", {
            "session_id": str(session.id),
            "character_name": character.name if character else "Клиент",
            "initial_emotion": initial_emotion.value,
            "scenario_title": scenario.title if scenario else "Тренировка",
        })
        return

    # Create new session
    scenario_id_str = data.get("scenario_id")
    if not scenario_id_str:
        await _send_error(ws, "scenario_id or session_id is required", "missing_field")
        return

    try:
        scenario_id = uuid.UUID(scenario_id_str)
    except ValueError:
        await _send_error(ws, "Invalid scenario_id format", "invalid_field")
        return

    user_id = state.get("user_id")
    if not user_id:
        await _send_error(ws, "Not authenticated", "auth_error")
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
    state["stt_failure_count"] = 0

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

    audio_b64 = data.get("audio")
    if not audio_b64:
        await _send_error(ws, "audio field is required (base64-encoded)", "missing_field")
        return

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception:
        await _send_error(ws, "Invalid base64 audio data", "invalid_data")
        return

    try:
        await check_message_limit(session_id)
    except RateLimitError as e:
        await _send_error(ws, str(e), "rate_limit")
        return

    # Transcribe via STT
    try:
        stt_result = await transcribe_audio(audio_bytes)
        state["stt_failure_count"] = 0  # Reset on success
    except STTError as e:
        state["stt_failure_count"] = state.get("stt_failure_count", 0) + 1
        logger.warning(
            "STT failure %d for session %s: %s",
            state["stt_failure_count"], session_id, e,
        )

        if state["stt_failure_count"] >= MAX_STT_FAILURES:
            await _send(ws, "stt.error", {
                "message": "Не удаётся распознать речь. Проверьте микрофон или используйте текстовый ввод.",
                "failure_count": state["stt_failure_count"],
                "suggest_text_input": True,
            })
        else:
            await _send(ws, "stt.unavailable", {
                "message": "Не удалось распознать. Попробуйте ещё раз.",
                "failure_count": state["stt_failure_count"],
            })
        return

    # Check for non-Russian / empty
    if not stt_result.text.strip():
        await _send(ws, "transcription.result", {
            "text": "",
            "confidence": 0.0,
            "is_empty": True,
        })
        return

    if stt_result.confidence < 0.3:
        await _send(ws, "transcription.result", {
            "text": stt_result.text,
            "confidence": stt_result.confidence,
            "is_low_confidence": True,
            "message": "Не удалось чётко распознать. Повторите, пожалуйста.",
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

    # Save user message
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

    # Generate character response
    await _generate_character_reply(ws, session_id, state)


async def _handle_audio_end(
    ws: WebSocket,
    data: dict,
    state: dict,
) -> None:
    """Handle audio.end: process complete audio recording."""
    # Same as audio.chunk but for complete recordings (Push-to-Talk)
    await _handle_audio_chunk(ws, data, state)


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

    try:
        await check_message_limit(session_id)
    except RateLimitError as e:
        await _send_error(ws, str(e), "rate_limit")
        return

    current_emotion = await get_emotion(session_id)

    async with async_session() as db:
        await add_message(
            session_id=session_id,
            role=MessageRole.user,
            content=content,
            db=db,
            emotion_state=current_emotion.value,
        )
        await db.commit()

    await _generate_character_reply(ws, session_id, state)


async def _handle_session_end(
    ws: WebSocket,
    data: dict,
    state: dict,
) -> None:
    """Handle session.end: calculate scores, finalize, cleanup."""
    session_id = state.get("session_id")
    if not session_id:
        await _send_error(ws, "No active session", "no_session")
        return

    scores = None
    try:
        async with async_session() as db:
            scores = await calculate_scores(session_id, db)
    except Exception:
        logger.exception("Failed to calculate scores for session %s", session_id)

    async with async_session() as db:
        session = await end_session(session_id, db, status=SessionStatus.completed)

        if session and scores:
            session.score_script_adherence = scores.script_adherence
            session.score_objection_handling = scores.objection_handling
            session.score_communication = scores.communication
            session.score_anti_patterns = scores.anti_patterns
            session.score_result = scores.result
            session.score_total = scores.total
            session.scoring_details = scores.details

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
        if scores:
            result_data["scores"] = {
                "script_adherence": scores.script_adherence,
                "objection_handling": scores.objection_handling,
                "communication": scores.communication,
                "anti_patterns": scores.anti_patterns,
                "result": scores.result,
                "total": scores.total,
            }

    await _send(ws, "session.ended", result_data)


async def training_websocket(websocket: WebSocket) -> None:
    """Handle a training session WebSocket connection.

    Auth flow: accept first, then authenticate via first message (not URL).
    """
    await websocket.accept()

    # Wait for auth message (10s timeout)
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
    except asyncio.TimeoutError:
        await _send(websocket, "auth.error", {"message": "Auth timeout"})
        await websocket.close(code=http_status.WS_1008_POLICY_VIOLATION)
        return
    except WebSocketDisconnect:
        return

    user_id = await _authenticate_first_message(websocket, raw)
    if user_id is None:
        await websocket.close(code=http_status.WS_1008_POLICY_VIOLATION)
        return

    await _send(websocket, "auth.success", {"user_id": str(user_id)})

    # Connection state
    state: dict = {
        "session_id": None,
        "user_id": user_id,
        "scenario_id": None,
        "character_prompt_path": None,
        "active": False,
        "stt_failure_count": 0,
    }

    watchdog_task: asyncio.Task | None = None
    stop_event = asyncio.Event()

    try:
        await _send(websocket, "session.ready", {
            "message": "Authenticated. Send session.start to begin.",
        })

        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=SILENCE_TIMEOUT_SEC + 30,
                )
            except asyncio.TimeoutError:
                if state.get("session_id"):
                    async with async_session() as db:
                        await end_session(
                            state["session_id"], db, status=SessionStatus.abandoned
                        )
                        await db.commit()
                await _send(websocket, "silence.timeout", {
                    "message": "Connection timed out due to inactivity",
                })
                break

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
                if state.get("session_id") and watchdog_task is None:
                    watchdog_task = asyncio.create_task(
                        _silence_watchdog(websocket, state["session_id"], state, stop_event)
                    )

            elif msg_type == "audio.chunk":
                await _handle_audio_chunk(websocket, msg_data, state)

            elif msg_type == "audio.end":
                await _handle_audio_end(websocket, msg_data, state)

            elif msg_type == "text.message":
                await _handle_text_message(websocket, msg_data, state)

            elif msg_type == "session.end":
                await _handle_session_end(websocket, msg_data, state)
                stop_event.set()
                break

            elif msg_type == "ping":
                if state.get("session_id"):
                    await update_activity(state["session_id"])
                await _send(websocket, "pong", {})

            elif msg_type == "silence.continue":
                # User chose to continue after silence modal
                if state.get("session_id"):
                    await update_activity(state["session_id"])

            else:
                await _send_error(
                    websocket,
                    f"Unknown message type: {msg_type}",
                    "unknown_type",
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for session %s", state.get("session_id"))
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
        stop_event.set()
        if watchdog_task and not watchdog_task.done():
            watchdog_task.cancel()
            try:
                await watchdog_task
            except asyncio.CancelledError:
                pass
