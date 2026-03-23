"""WebSocket handler for real-time training sessions (v5 with multi-call stories).

Protocol (TZ section 7.8 + v5 extensions):
- Auth: JWT token sent in FIRST message (not URL query param)
- Client sends: auth, session.start, audio.chunk, audio.end, text.message, session.end, ping
- v5 client sends: story.start, story.next_call, story.end
- Server sends: session.ready, auth.success, auth.error, session.started,
                avatar.typing, transcription.result, character.response,
                emotion.update, score.update, session.ended,
                silence.warning, silence.timeout, error
- v5 server sends: story.started, story.between_calls, story.pre_call_brief,
                    story.call_ready, story.call_report, story.progress,
                    story.completed

v5 features:
- Multi-call story sessions (2-5 calls per story)
- Episodic memory (written by [MEMORY:...] stage directions)
- Between-call CRM event simulation
- OCEAN/PAD personality injection via inject_human_factors()
- Two-pass stage direction parsing ([MEMORY:...], [STORYLET:...], [CONSEQUENCE:...], [FACTOR:...])
- FactorInteractionMatrix for human factor interactions
- Auto-generated post-call reports via LLM

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
import re
import time
import uuid

from fastapi import WebSocket, WebSocketDisconnect, status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import errors as err
from app.core.security import decode_token
from app.database import async_session
from app.models.character import Character, EmotionState, LEGACY_MAP
from app.models.scenario import Scenario
from app.models.training import MessageRole, SessionStatus, TrainingSession
from app.models.user import User

from app.services.emotion import (
    get_emotion, init_emotion, init_emotion_v3,
    transition_emotion, transition_emotion_v3,
    get_fake_prompt,
)
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
from app.services.llm import (
    LLMError,
    FactorInteractionMatrix,
    build_multi_call_prompt,
    generate_personality_profile,
    generate_response,
    get_context_budget_manager,
    inject_human_factors,
    load_prompt,
)
from app.services.scenario_engine import (
    apply_between_calls_context,
    generate_pre_call_brief,
    generate_session_report,
    parse_stage_directions_v2,
)
from app.services.scoring import calculate_realtime_scores, calculate_scores
from app.services.stt import STTError, transcribe_audio
from app.services.tts import (
    TTSError,
    TTSQuotaExhausted,
    get_tts_audio_b64,
    is_tts_available,
    pick_voice_for_session,
    release_session_voice,
)

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

# ── Stage direction stripping ──
# Three layers of stripping:
#   1. *text between asterisks* — any italicized action/narration
#   2. *(text in parens with asterisks)* — *(Голос дрожит)*
#   3. (keyword stage direction) — (плачет), (кричит), (пауза) etc.
#   4. *text starting with asterisk but no closing — *Резко выдыхает

# Pattern 1: Full *italic action text* (any text between asterisks)
_ASTERISK_ACTION_RE = re.compile(r'\*[^*]+\*')

# Pattern 2: Unclosed asterisk at start of text or after newline: *Резко выдыхает...
_UNCLOSED_ASTERISK_RE = re.compile(r'(?:^|\n)\*[^*\n]+(?:\n|$)', re.MULTILINE)

# Pattern 3: (keyword stage directions) without asterisks
_PAREN_STAGE_DIR_RE = re.compile(
    r'\('
    r'(?:'
    r'[Гг]олос|[Пп]ауз|[Тт]их|[Кк]рич|[Пп]лач|[Шш][её]пот|'
    r'[Вв]здох|[Сс]мех|[Вв]схлип|[Зз]лоб|[Рр]аздраж|[Нн]ервн|'
    r'[Сс]покойн|[Уу]верен|[Рр]ешительн|[Гг]ромк|[Бб]ыстр|[Мм]едленн|'
    r'[Оо]бижен|[Сс]аркастич|[Хх]олодн|[Рр]езк|[Мм]ягк|[Ии]спуган|'
    r'[Дд]рожащ|[Вв]ешает|[Сс]брос|[Дд]ушит|[Дд]авит|[Зз]амолкает|'
    r'[Вв]ыдыхает|[Вв]здыхает|[Мм]олчит|[Оо]глядывается|[Бб]ормоч|'
    r'[Тт]рубк|[Бб]росает|[Сс]тучит|[Хх]лопает'
    r')'
    r'[^)]*'
    r'\)',
    re.IGNORECASE,
)


def _strip_stage_directions(text: str) -> str:
    """Remove ALL stage directions / action narration from LLM output.

    Strips three formats:
    - *Italicized action text* (any text between asterisks)
    - *Unclosed asterisk actions at line start
    - (keyword stage directions) in parentheses

    These should not appear in the chat or be spoken by TTS.
    """
    # Step 1: Remove *asterisk-wrapped actions*
    cleaned = _ASTERISK_ACTION_RE.sub('', text)
    # Step 2: Remove *unclosed asterisk lines
    cleaned = _UNCLOSED_ASTERISK_RE.sub('', cleaned)
    # Step 3: Remove (keyword stage directions)
    cleaned = _PAREN_STAGE_DIR_RE.sub('', cleaned)
    # Step 4: Clean up whitespace
    cleaned = re.sub(r'  +', ' ', cleaned)
    cleaned = re.sub(r'\n\s*\n', '\n', cleaned)
    cleaned = cleaned.strip()
    return cleaned


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
        await _send(ws, "auth.error", {"message": err.WS_INVALID_JSON})
        return None

    if message.get("type") != "auth":
        await _send(ws, "auth.error", {"message": err.WS_FIRST_MESSAGE_AUTH})
        return None

    token = message.get("data", {}).get("token")
    if not token:
        await _send(ws, "auth.error", {"message": err.WS_TOKEN_REQUIRED})
        return None

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        await _send(ws, "auth.error", {"message": err.WS_INVALID_OR_EXPIRED_TOKEN})
        return None

    user_id_str = payload.get("sub")
    if not user_id_str:
        await _send(ws, "auth.error", {"message": err.WS_INVALID_TOKEN_PAYLOAD})
        return None

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        await _send(ws, "auth.error", {"message": err.WS_INVALID_USER_ID})
        return None

    # Verify user exists and is active
    async with async_session() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            await _send(ws, "auth.error", {"message": err.WS_USER_NOT_FOUND})
            return None

    # Check if user was logged out (token blacklisted)
    from app.core.deps import _is_user_blacklisted
    if await _is_user_blacklisted(user_id_str):
        await _send(ws, "auth.error", {"message": err.WS_TOKEN_REVOKED})
        return None

    return user_id


async def _generate_character_reply(
    ws: WebSocket,
    session_id: uuid.UUID,
    state: dict,
) -> None:
    """Build message history, call LLM, send character.response, update emotion.

    v3: Uses V3 emotion engine with trigger detection and fake transition prompts.
    """
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
    archetype_code = state.get("archetype_code")
    client_profile_prompt = state.get("client_profile_prompt", "")

    # Build extended system prompt if client profile is available
    extra_system = ""
    if client_profile_prompt:
        extra_system = client_profile_prompt

    # Inject next objection from chain (dynamic per-turn)
    try:
        from app.services.objection_chain import get_next_objection_prompt, advance_chain
        chain_prompt = await get_next_objection_prompt(session_id)
        if chain_prompt:
            extra_system += "\n\n" + chain_prompt
            # Advance chain after injecting (LLM will use current step)
            await advance_chain(session_id)
    except Exception:
        pass  # Chain is optional

    # Inject fake transition prompt if present (from V3 engine)
    if state.get("fake_transition_prompt"):
        extra_system += "\n\n" + state["fake_transition_prompt"]

    try:
        llm_result = await generate_response(
            system_prompt=extra_system,
            messages=messages,
            emotion_state=current_emotion,
            character_prompt_path=prompt_path,
        )
    except LLMError as e:
        logger.error("LLM failed for session %s: %s", session_id, e)
        await _send(ws, "avatar.typing", {"is_typing": False})
        await _send(ws, "character.response", {
            "content": "Секунду... мне нужно собраться с мыслями.",
            "emotion": current_emotion,
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
            emotion_state=current_emotion,
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

    # ─── V3 Emotion Engine with Trigger Detection ───
    new_emotion = current_emotion
    emotion_meta = {}
    trigger_result = None

    try:
        from app.services.trigger_detector import detect_triggers

        # Get the manager's message that triggered this response
        manager_message = messages[-1]["content"] if messages else ""

        trigger_result = await detect_triggers(
            manager_message=manager_message,
            client_message=llm_result.content,
            archetype_code=archetype_code or "skeptic",
            emotion_state=current_emotion,
            response_time_ms=llm_result.latency_ms,
            client_name=state.get("client_name"),
        )

        # Use V3 engine with detected triggers
        if archetype_code and trigger_result and trigger_result.triggers:
            new_emotion, emotion_meta = await transition_emotion_v3(
                session_id, archetype_code, trigger_result.triggers
            )
        elif archetype_code:
            # Fallback: no triggers detected, apply decay only
            new_emotion, emotion_meta = await transition_emotion_v3(
                session_id, archetype_code, []
            )
        else:
            # V1 fallback for no archetype
            response_quality = "good_response" if not llm_result.is_fallback else "bad_response"
            new_emotion = await transition_emotion(session_id, response_quality)
            emotion_meta = {}

    except Exception as e:
        logger.warning("V3 emotion engine failed for session %s, falling back to V1: %s", session_id, e)
        # Fallback to V1 behavior
        response_quality = "good_response" if not llm_result.is_fallback else "bad_response"
        new_emotion = await transition_emotion(session_id, response_quality)
        emotion_meta = {}

    # Check for fake transition prompt and inject into NEXT LLM call
    try:
        fake_prompt = await get_fake_prompt(session_id, archetype_code or "skeptic")
        if fake_prompt:
            state["fake_transition_prompt"] = fake_prompt
        else:
            state.pop("fake_transition_prompt", None)
    except Exception:
        pass  # Fake prompt is optional

    # Track last character message for trap detection
    state["last_character_message"] = llm_result.content

    # ─── v5: Two-pass stage direction parsing ───
    # Parse v1+v2 stage directions BEFORE stripping for analytics
    clean_v5, stage_directions = parse_stage_directions_v2(llm_result.content)

    # Process parsed stage directions
    story_id = state.get("story_id")
    if stage_directions and story_id:
        latest_consequence = None
        state_changed = False
        for sd in stage_directions:
            # Write episodic memories
            if sd.direction_type == "memory":
                try:
                    from app.models.roleplay import EpisodicMemory
                    async with async_session() as mem_db:
                        mem = EpisodicMemory(
                            story_id=story_id,
                            session_id=session_id,
                            call_number=state.get("call_number", 1),
                            memory_type=sd.payload.get("type", "fact"),
                            content=sd.payload.get("content", ""),
                            salience=sd.payload.get("salience", 5),
                            valence=sd.payload.get("valence", 0.0),
                            token_count=len(sd.payload.get("content", "")) // 4,
                        )
                        mem_db.add(mem)
                        await mem_db.commit()
                except Exception:
                    logger.debug("Failed to save episodic memory for story %s", story_id)

            # Track consequences
            elif sd.direction_type == "consequence":
                consequences = state.get("accumulated_consequences", [])
                latest_consequence = {
                    "call": state.get("call_number", 1),
                    "type": sd.payload.get("type", "unknown"),
                    "severity": sd.payload.get("severity", 0.5),
                    "detail": sd.payload.get("detail", ""),
                }
                consequences.append(latest_consequence)
                state["accumulated_consequences"] = consequences
                state_changed = True

            # Activate/update human factors
            elif sd.direction_type == "factor":
                active_factors = state.get("active_factors", [])
                factor_name = sd.payload.get("factor", "")
                intensity = sd.payload.get("intensity", 0.5)
                # Update existing or add new
                updated = False
                for f in active_factors:
                    if f["factor"] == factor_name:
                        f["intensity"] = min(1.0, f["intensity"] + intensity * 0.3)
                        updated = True
                        break
                if not updated:
                    active_factors.append({
                        "factor": factor_name,
                        "intensity": intensity,
                        "since_call": state.get("call_number", 1),
                    })
                # Apply interaction matrix
                active_factors = FactorInteractionMatrix.apply_interactions(active_factors)
                state["active_factors"] = active_factors
                state_changed = True

        # Save stage directions for analytics
        try:
            from app.models.roleplay import StoryStageDirection, StageDirectionType
            async with async_session() as sd_db:
                for sd in stage_directions:
                    try:
                        dtype = StageDirectionType(sd.direction_type)
                    except ValueError:
                        dtype = StageDirectionType.action
                    record = StoryStageDirection(
                        story_id=story_id,
                        session_id=session_id,
                        call_number=state.get("call_number", 1),
                        message_sequence=len(messages),
                        direction_type=dtype,
                        raw_tag=sd.raw_tag,
                        parsed_payload=sd.payload,
                        was_applied=sd.confidence >= 0.5,
                    )
                    sd_db.add(record)
                await sd_db.commit()
        except Exception:
            logger.debug("Failed to save stage directions for story %s", story_id)

        if state_changed:
            active_hf = [
                {
                    "factor": af.get("factor", af.get("name", "unknown")),
                    "intensity": af.get("intensity", 0.5),
                    "since_call": af.get("since_call", 1),
                }
                for af in state.get("active_factors", [])
            ]
            await _send(ws, "story.state_delta", {
                "story_id": str(story_id),
                "call_number": state.get("call_number", 1),
                "active_factors": active_hf,
                "new_consequence": latest_consequence,
                "consequences_count": len(state.get("accumulated_consequences", [])),
                "tension": round(len(state.get("accumulated_consequences", [])) * 0.15, 2),
            })

    # Strip stage directions from LLM output before sending to chat/TTS
    # Uses v5 parsed output if available, falls back to v1 stripping
    clean_content = _strip_stage_directions(clean_v5) if clean_v5 else _strip_stage_directions(llm_result.content)

    await _send(ws, "character.response", {
        "content": clean_content,
        "emotion": new_emotion,
        "model": llm_result.model,
        "latency_ms": llm_result.latency_ms,
        "is_fallback": llm_result.is_fallback,
    })

    # TTS: convert AI response to natural speech audio (ElevenLabs)
    # Respects user preference tts_enabled (default: True).
    # Runs after character.response so text appears immediately.
    user_tts_pref = state.get("user_prefs", {}).get("tts_enabled", True)
    tts_available = is_tts_available()
    tts_enabled = settings.elevenlabs_enabled and user_tts_pref
    logger.info(
        "TTS_CHECK | session=%s | is_tts_available=%s | elevenlabs_enabled=%s",
        session_id, tts_available, tts_enabled,
    )
    if tts_available and tts_enabled:
        try:
            # get_tts_audio_b64 returns a DICT: {"audio": b64_str, "format", "emotion", "voice_params", "duration_ms"}
            tts_result = await get_tts_audio_b64(clean_content, str(session_id), emotion=new_emotion)
            logger.info("TTS_RESULT | session=%s | audio_received=%s | audio_len=%d",
                        session_id, tts_result is not None,
                        len(tts_result["audio"]) if tts_result else 0)
            if tts_result and tts_result.get("audio"):
                await _send(ws, "tts.audio", {
                    "audio_b64": tts_result["audio"],
                    "format": tts_result.get("format", "mp3"),
                    "emotion": tts_result.get("emotion"),
                    "voice_params": tts_result.get("voice_params"),
                    "duration_ms": tts_result.get("duration_ms"),
                    "text": clean_content,  # for subtitle sync
                })
        except TTSQuotaExhausted:
            logger.warning("TTS quota exhausted for session %s, frontend fallback", session_id)
            await _send(ws, "tts.fallback", {"reason": "quota_exhausted"})
        except TTSError as e:
            logger.error("TTS error for session %s: %s", session_id, e)
            # Notify frontend to use browser fallback immediately (don't wait 3s timer)
            await _send(ws, "tts.fallback", {"reason": f"tts_error: {e}"})

    if new_emotion != current_emotion:
        await _send(ws, "emotion.update", {
            "previous": current_emotion,
            "current": new_emotion,
            "triggers": trigger_result.triggers if trigger_result else [],
            "energy": emotion_meta.get("energy_after", 0),
            "is_fake": emotion_meta.get("is_fake", False),
            "rollback": emotion_meta.get("rollback", False),
        })

    # ── Real-time score hint (L1-L8) — every 3rd message to avoid spam ──
    msg_count = state.get("message_count", 0)
    if msg_count > 0 and msg_count % 3 == 0:
        try:
            async with async_session() as db:
                rt_scores = await calculate_realtime_scores(session_id, db)
            await _send(ws, "score.hint", rt_scores)
        except Exception:
            logger.debug("Real-time score hint failed for %s", session_id)


async def _silence_watchdog(
    ws: WebSocket,
    session_id: uuid.UUID,
    state: dict,
    stop_event: asyncio.Event,
    state_lock: asyncio.Lock | None = None,
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
            if state_lock:
                async with state_lock:
                    state["active"] = False
            else:
                state["active"] = False
            stop_event.set()
            break

        elif elapsed >= SILENCE_WARNING_SEC and not warned:
            # 30s — avatar says "Алло?"
            import random
            phrase = random.choice(SILENCE_AVATAR_PHRASES)
            # Send both silence.warning (for UI indicator) and character.response (for chat)
            await _send(ws, "silence.warning", {
                "content": phrase,
                "seconds_silent": int(elapsed),
            })
            await _send(ws, "character.response", {
                "content": phrase,
                "emotion": "cold",
                "is_silence_prompt": True,
            })
            # TTS for silence prompt
            if is_tts_available() and settings.elevenlabs_enabled:
                try:
                    tts_result = await get_tts_audio_b64(phrase, str(session_id))
                    if tts_result and tts_result.get("audio"):
                        await _send(ws, "tts.audio", {
                            "audio_b64": tts_result["audio"],
                            "format": tts_result.get("format", "mp3"),
                            "text": phrase,
                        })
                except TTSError:
                    pass  # Silent fallback
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


# ─── Hint & Soft Skills background tasks (Wave 2) ───────────────────────────

HINT_OBJECTION_DELAY_SEC = 60   # Show objection category hint after 60s
HINT_CHECKPOINT_DELAY_SEC = 180  # Show checkpoint hint after 3 min
SOFT_SKILLS_INTERVAL_SEC = 120   # Send soft_skills.update every 2 min


async def _hint_scheduler(
    ws: WebSocket,
    session_id: uuid.UUID,
    state: dict,
    stop_event: asyncio.Event,
    state_lock: asyncio.Lock | None = None,
) -> None:
    """Background task: send progressive hints to the frontend.

    - 60s  → hint.objection (if assistant messages contain objection patterns)
    - 180s → hint.checkpoint (check script progress, suggest next checkpoint)
    """
    # ── Wait 60s, then send objection category hint ──
    for _ in range(HINT_OBJECTION_DELAY_SEC // 5):
        if stop_event.is_set():
            return
        await asyncio.sleep(5)

    if stop_event.is_set() or not state.get("active"):
        return

    # Analyze messages for objection category
    try:
        from app.services.session_manager import get_message_history
        messages = await get_message_history(session_id)
        assistant_msgs = [m for m in messages if m.get("role") == "assistant"]

        # Simple pattern matching for objection categories
        objection_categories = {
            "trust": ["не верю", "мошенники", "обман", "развод", "не доверяю"],
            "price": ["дорого", "стоимость", "бесплатно", "сколько стоит", "цена"],
            "time": ["подумаю", "перезвоню", "не сейчас", "потом", "нет времени"],
            "need": ["не нужно", "зачем", "не надо", "без вас", "сам разберусь"],
            "competitor": ["юрист", "другие", "уже есть", "обращался", "другая компания"],
        }

        detected_category = None
        for msg in assistant_msgs:
            content = msg.get("content", "").lower()
            for cat, patterns in objection_categories.items():
                if any(p in content for p in patterns):
                    detected_category = cat
                    break
            if detected_category:
                break

        if detected_category:
            category_labels = {
                "trust": "доверие",
                "price": "стоимость",
                "time": "время / отложить",
                "need": "отсутствие потребности",
                "competitor": "конкуренты / альтернативы",
            }
            await _send(ws, "hint.objection", {
                "category": detected_category,
                "message": f"Возражение: {category_labels.get(detected_category, detected_category)}",
            })
    except Exception:
        logger.debug("Failed to send objection hint for session %s", session_id)

    # ── Wait until 180s total, then send checkpoint hint ──
    remaining = HINT_CHECKPOINT_DELAY_SEC - HINT_OBJECTION_DELAY_SEC
    for _ in range(remaining // 5):
        if stop_event.is_set():
            return
        await asyncio.sleep(5)

    if stop_event.is_set() or not state.get("active"):
        return

    try:
        # Check which checkpoints are not yet reached
        from app.core.redis_pool import get_redis as _get_redis_pool
        r = _get_redis_pool()
        try:
            script_key = f"session:{session_id}:script_progress"
            progress_raw = await r.get(script_key)
            # If no progress tracked yet, suggest first checkpoint
            checkpoint_name = "Квалификация"
            checkpoint_status = "not_reached"

            if progress_raw:
                progress = json.loads(progress_raw)
                # Find first un-hit checkpoint
                for cp in progress.get("checkpoints", []):
                    if not cp.get("hit", False):
                        checkpoint_name = cp.get("name", "Следующий этап")
                        break
                    checkpoint_status = "in_progress"
        except Exception:
            pass  # Checkpoint hint is non-critical

        await _send(ws, "hint.checkpoint", {
            "checkpoint": checkpoint_name,
            "status": checkpoint_status,
        })
    except Exception:
        logger.debug("Failed to send checkpoint hint for session %s", session_id)


async def _soft_skills_tracker(
    ws: WebSocket,
    session_id: uuid.UUID,
    state: dict,
    stop_event: asyncio.Event,
    state_lock: asyncio.Lock | None = None,
) -> None:
    """Background task: send soft_skills.update every 2 minutes.

    Tracks: talk_ratio, avg_response_time, name_usage_count.
    """
    while not stop_event.is_set():
        # Wait interval
        for _ in range(SOFT_SKILLS_INTERVAL_SEC // 5):
            if stop_event.is_set():
                return
            await asyncio.sleep(5)

        if stop_event.is_set() or not state.get("active"):
            return

        try:
            from app.services.session_manager import get_message_history
            messages = await get_message_history(session_id)

            user_msgs = [m for m in messages if m.get("role") == "user"]
            assistant_msgs = [m for m in messages if m.get("role") == "assistant"]

            # Talk ratio: user message length / total message length
            user_chars = sum(len(m.get("content", "")) for m in user_msgs)
            total_chars = user_chars + sum(len(m.get("content", "")) for m in assistant_msgs)
            talk_ratio = round(user_chars / total_chars, 2) if total_chars > 0 else 0.5

            # Average response time (estimated from message timestamps)
            avg_response_time = 0.0
            if len(user_msgs) >= 2:
                timestamps = [m.get("timestamp", 0) for m in user_msgs if m.get("timestamp")]
                if len(timestamps) >= 2:
                    gaps = [timestamps[i] - timestamps[i - 1] for i in range(1, len(timestamps))]
                    avg_response_time = round(sum(gaps) / len(gaps), 1)

            # Name usage: check if client name appears in user messages
            client_name = state.get("client_name", "")
            name_count = 0
            if client_name:
                first_name = client_name.split()[0].lower() if client_name else ""
                for m in user_msgs:
                    content = m.get("content", "").lower()
                    if first_name and first_name in content:
                        name_count += 1

            await _send(ws, "soft_skills.update", {
                "talk_ratio": talk_ratio,
                "avg_response_time": avg_response_time,
                "name_count": name_count,
            })
        except Exception:
            logger.debug("Failed to send soft_skills.update for session %s", session_id)


def _build_client_profile_prompt(profile) -> str:
    """Build extra system prompt context from generated client profile.

    This text gets appended to the character prompt + guardrails,
    giving the LLM specific details about WHO the client is.
    The manager doesn't see this — only the LLM does.
    """
    parts = [
        "\n## Контекст клиента (скрыт от менеджера)",
        f"Имя: {profile.full_name}, {profile.age} лет, {profile.city}.",
    ]

    if profile.fears:
        fears_text = ", ".join(profile.fears[:4])
        parts.append(f"Главные страхи: {fears_text}.")

    if profile.soft_spot:
        parts.append(f"Мягкая точка (что может убедить): {profile.soft_spot}.")

    if profile.breaking_point:
        parts.append(f"Точка перелома (триггер согласия): {profile.breaking_point}.")

    if profile.total_debt:
        parts.append(f"Общий долг: {profile.total_debt:,.0f} руб.")

    if profile.income:
        parts.append(f"Доход: {profile.income:,.0f} руб/мес ({profile.income_type or 'официальный'}).")

    if profile.trust_level is not None:
        parts.append(f"Начальный уровень доверия: {profile.trust_level}/10.")

    if profile.resistance_level is not None:
        parts.append(f"Уровень сопротивления: {profile.resistance_level}/10.")

    parts.append(
        "\nИспользуй эти данные для реалистичных ответов. "
        "НЕ раскрывай менеджеру свои страхи и мягкую точку напрямую — "
        "дай ему возможность выяснить это через диалог."
    )

    return "\n".join(parts)


async def _clone_story_profile_for_session(
    story_id: uuid.UUID,
    session_id: uuid.UUID,
    db: AsyncSession,
):
    """Clone the canonical story client profile onto a concrete TrainingSession.

    Story mode needs a stable client identity across calls, while results/review
    still expect a session-bound ClientProfile row.
    """
    from app.models.roleplay import ClientProfile, ClientStory

    story_result = await db.execute(
        select(ClientStory).where(ClientStory.id == story_id)
    )
    story = story_result.scalar_one_or_none()
    if story is None or story.client_profile_id is None:
        return None

    profile_result = await db.execute(
        select(ClientProfile).where(ClientProfile.id == story.client_profile_id)
    )
    base_profile = profile_result.scalar_one_or_none()
    if base_profile is None:
        return None

    cloned = ClientProfile(
        session_id=session_id,
        full_name=base_profile.full_name,
        age=base_profile.age,
        gender=base_profile.gender,
        city=base_profile.city,
        archetype_code=base_profile.archetype_code,
        profession_id=base_profile.profession_id,
        education_level=base_profile.education_level,
        legal_literacy=base_profile.legal_literacy,
        total_debt=base_profile.total_debt,
        creditors=base_profile.creditors,
        income=base_profile.income,
        income_type=base_profile.income_type,
        property_list=base_profile.property_list,
        fears=base_profile.fears,
        soft_spot=base_profile.soft_spot,
        trust_level=base_profile.trust_level,
        resistance_level=base_profile.resistance_level,
        lead_source=base_profile.lead_source,
        call_history=base_profile.call_history,
        crm_notes=base_profile.crm_notes,
        hidden_objections=base_profile.hidden_objections,
        trap_ids=base_profile.trap_ids,
        chain_id=base_profile.chain_id,
        cascade_ids=base_profile.cascade_ids,
        breaking_point=base_profile.breaking_point,
    )
    db.add(cloned)
    await db.flush()
    return cloned


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

            # Verify session belongs to this user
            if session.user_id != state.get("user_id"):
                await _send_error(ws, "Session belongs to another user", "forbidden")
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

            # Init Redis session state (uses shared pool)
            try:
                from app.core.redis_pool import get_redis as _get_redis_pool2
                r = _get_redis_pool2()
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

            # Check for custom_params from CharacterBuilder
            custom_params = session.custom_params or {}
            custom_archetype = custom_params.get("archetype")
            custom_difficulty = custom_params.get("difficulty")

            # If custom archetype provided, override character slug for profile generation
            effective_archetype = custom_archetype or (character.slug if character else None)

            state["session_id"] = session.id
            state["user_id"] = session.user_id
            state["scenario_id"] = session.scenario_id
            state["script_id"] = scenario.script_id if scenario else None
            state["character_prompt_path"] = character.prompt_path if character else None
            state["archetype_code"] = effective_archetype
            state["client_profile_prompt"] = ""
            state["active"] = True
            state["stt_failure_count"] = 0
            state["custom_params"] = custom_params

            # Load or generate client profile
            client_card = None
            client_gender = ""
            try:
                from app.models.roleplay import ClientProfile
                cp_result = await db.execute(
                    select(ClientProfile).where(ClientProfile.session_id == session.id)
                )
                existing_profile = cp_result.scalar_one_or_none()

                if existing_profile:
                    # Resume — profile already exists
                    state["client_profile_prompt"] = _build_client_profile_prompt(existing_profile)
                    from app.services.client_generator import get_crm_card
                    client_card = get_crm_card(existing_profile)
                    client_gender = getattr(existing_profile, "gender", "") or ""
                else:
                    # First connection — generate new client profile
                    from app.services.client_generator import generate_client_profile, get_crm_card
                    profile = await generate_client_profile(
                        session_id=session.id,
                        scenario=scenario,
                        character=character,
                        difficulty=custom_difficulty or (scenario.difficulty if scenario else 5),
                        db=db,
                        custom_archetype=custom_archetype,
                        custom_profession=custom_params.get("profession"),
                        custom_lead_source=custom_params.get("lead_source"),
                    )
                    client_card = get_crm_card(profile)
                    client_gender = getattr(profile, "gender", "") or ""
                    state["client_profile_prompt"] = _build_client_profile_prompt(profile)
                    await db.commit()
            except Exception:
                logger.warning("Failed to load/generate client profile for session %s", session.id, exc_info=True)

            # Pick voice (sync function — no await)
            try:
                voice_id = pick_voice_for_session(
                    session_id=str(session.id),
                    archetype=effective_archetype or "skeptic",
                    gender=client_gender or None,
                )
                if voice_id:
                    state["tts_voice_id"] = voice_id
                    logger.info("TTS voice %s assigned to resumed session %s (archetype=%s)", voice_id, session.id, effective_archetype)
            except Exception:
                logger.debug("Voice pick failed for session %s", session.id)

        response_data = {
            "session_id": str(session.id),
            "character_name": character.name if character else "Клиент",
            "initial_emotion": initial_emotion.value,
            "scenario_title": scenario.title if scenario else "Тренировка",
        }
        if client_card:
            response_data["client_card"] = client_card

        await _send(ws, "session.started", response_data)
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

    # Load user preferences for this session
    async with async_session() as pref_db:
        user_result = await pref_db.execute(select(User).where(User.id == user_id))
        pref_user = user_result.scalar_one_or_none()
        user_prefs = (pref_user.preferences or {}) if pref_user else {}
    state["user_prefs"] = user_prefs

    client_card = None
    client_profile_prompt = ""
    client_gender = ""  # "male" or "female" — used for TTS voice matching
    story_id = state.get("story_id")
    active_traps = []
    raw_custom_params = data.get("custom_params") or state.get("story_custom_params") or {}
    custom_params = raw_custom_params if isinstance(raw_custom_params, dict) else {}
    custom_archetype = custom_params.get("archetype")
    custom_difficulty = custom_params.get("difficulty")
    if isinstance(custom_difficulty, str):
        try:
            custom_difficulty = int(custom_difficulty)
        except ValueError:
            custom_difficulty = None

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

        if story_id:
            session.client_story_id = story_id
            session.call_number_in_story = state.get("call_number", 1)
        if custom_params:
            session.custom_params = custom_params
            await db.flush()

        # ── Generate unique client profile (Roleplay v2) ──
        try:
            from app.services.client_generator import generate_client_profile, get_crm_card
            profile = None
            if story_id:
                profile = await _clone_story_profile_for_session(story_id, session.id, db)

            if profile is None:
                profile = await generate_client_profile(
                    session_id=session.id,
                    scenario=scenario,
                    character=character,
                    difficulty=custom_difficulty or scenario.difficulty,
                    db=db,
                    custom_archetype=custom_archetype,
                    custom_profession=custom_params.get("profession"),
                    custom_lead_source=custom_params.get("lead_source"),
                )
                if story_id:
                    from app.models.roleplay import ClientStory

                    story_result = await db.execute(
                        select(ClientStory).where(ClientStory.id == story_id)
                    )
                    story = story_result.scalar_one_or_none()
                    if story and story.client_profile_id is None:
                        story.client_profile_id = profile.id
            client_card = get_crm_card(profile)
            client_gender = getattr(profile, "gender", "") or ""

            # Build extra system prompt context from profile
            # This gets injected into the LLM system prompt alongside character prompt
            client_profile_prompt = _build_client_profile_prompt(profile)

            # Load traps assigned to this client profile
            active_traps = []
            if profile.trap_ids:
                from app.models.roleplay import Trap
                trap_result = await db.execute(
                    select(Trap).where(
                        Trap.id.in_([uuid.UUID(tid) for tid in profile.trap_ids]),
                        Trap.is_active == True,  # noqa: E712
                    )
                )
                trap_objs = trap_result.scalars().all()
                active_traps = [
                    {
                        "id": str(t.id),
                        "name": t.name,
                        "category": t.category,
                        "client_phrase": t.client_phrase,
                        "wrong_response_keywords": t.wrong_response_keywords,
                        "correct_response_keywords": t.correct_response_keywords,
                        "correct_response_example": t.correct_response_example,
                        "penalty": t.penalty,
                        "bonus": t.bonus,
                    }
                    for t in trap_objs
                ]

                # Inject trap phrases into LLM system prompt
                from app.services.trap_detector import build_trap_injection_prompt
                trap_prompt = build_trap_injection_prompt(active_traps)
                if trap_prompt:
                    client_profile_prompt += "\n\n" + trap_prompt

            # Initialize objection chain if assigned
            if profile.chain_id:
                from app.models.roleplay import ObjectionChain
                from app.services.objection_chain import init_chain, build_chain_system_prompt
                chain_result = await db.execute(
                    select(ObjectionChain).where(ObjectionChain.id == profile.chain_id)
                )
                chain_obj = chain_result.scalar_one_or_none()
                if chain_obj and chain_obj.steps:
                    await init_chain(session.id, chain_obj.id, chain_obj.steps)
                    chain_prompt = build_chain_system_prompt(chain_obj.steps)
                    if chain_prompt:
                        client_profile_prompt += "\n\n" + chain_prompt

        except Exception:
            # Client generation is non-critical — session works without it
            logger.warning("Client profile generation failed for session %s, continuing without", session.id, exc_info=True)
            client_card = None
            client_profile_prompt = ""
            active_traps = []

        await db.commit()

    state["session_id"] = session.id
    state["user_id"] = user_id
    state["scenario_id"] = scenario_id
    state["script_id"] = scenario.script_id  # For real-time checkpoint tracking
    state["character_prompt_path"] = character.prompt_path if character else None
    state["archetype_code"] = custom_archetype or (character.slug if character else None)
    state["client_profile_prompt"] = client_profile_prompt
    state["client_name"] = client_card.get("full_name", "") if client_card else ""
    state["client_gender"] = client_gender
    state["active_traps"] = active_traps if "active_traps" in dir() else []
    state["last_character_message"] = ""
    state["fake_transition_prompt"] = ""
    state["active"] = True
    state["stt_failure_count"] = 0
    state["custom_params"] = custom_params

    # Assign TTS voice for this session — matched to client gender + archetype
    # Only if user has TTS enabled in preferences (default: True)
    session_archetype = custom_archetype or (character.slug if character else None)
    tts_voice_id = None
    user_tts_pref = state.get("user_prefs", {}).get("tts_enabled", True)
    if is_tts_available() and user_tts_pref:
        try:
            tts_voice_id = pick_voice_for_session(
                str(session.id),
                gender=client_gender,
                archetype=session_archetype,
            )
            state["tts_voice_id"] = tts_voice_id
            logger.info("TTS voice %s assigned to session %s (gender=%s, archetype=%s)", tts_voice_id, session.id, client_gender, session_archetype)
        except TTSError as e:
            logger.warning("TTS voice assignment failed: %s", e)

    started_data = {
        "session_id": str(session.id),
        "character_name": character.name,
        "initial_emotion": initial_emotion.value,
        "scenario_title": scenario.title,
    }
    if client_card:
        started_data["client_card"] = client_card
    if tts_voice_id:
        started_data["tts_enabled"] = True

    await _send(ws, "session.started", started_data)


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

    # Limit audio size to 5MB (base64 encoded)
    MAX_AUDIO_B64_SIZE = 5 * 1024 * 1024
    if len(audio_b64) > MAX_AUDIO_B64_SIZE:
        await _send_error(ws, "Audio data too large (max 5MB)", "payload_too_large")
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
            emotion_state=current_emotion,
        )
        await db.commit()

    # Check traps and update script score before generating character reply
    await _check_traps_after_user_message(ws, session_id, stt_result.text, state)
    await _send_score_update(ws, session_id, stt_result.text, state)

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


async def _send_score_update(
    ws: WebSocket,
    session_id: uuid.UUID,
    user_text: str,
    state: dict,
) -> None:
    """Check script checkpoint progress and send score.update to frontend.

    Called after each user message. Uses script_checker to evaluate
    which checkpoints have been reached.
    """
    script_id = state.get("script_id")
    if not script_id:
        return

    try:
        from app.services.script_checker import check_all_checkpoints

        results = await check_all_checkpoints(user_text, script_id)
        if not results:
            return

        total = len(results)
        hit = sum(1 for r in results if r["matched"])

        # Calculate weighted progress percentage
        total_weight = sum(r.get("weight", 1.0) for r in results)
        hit_weight = sum(r.get("weight", 1.0) for r in results if r["matched"])
        progress = (hit_weight / total_weight * 100) if total_weight > 0 else 0

        # Build checkpoint details for frontend
        checkpoints = [
            {
                "id": r["checkpoint_id"],
                "title": r["title"],
                "order": r["order_index"],
                "hit": r["matched"],
                "score": r["score"],
            }
            for r in results
        ]

        await _send(ws, "score.update", {
            "script_score": round(progress, 1),
            "checkpoints_hit": hit,
            "checkpoints_total": total,
            "checkpoints": checkpoints,
        })
    except Exception:
        logger.debug("Score update failed for session %s", session_id, exc_info=True)


async def _check_traps_after_user_message(
    ws: WebSocket,
    session_id: uuid.UUID,
    manager_message: str,
    state: dict,
) -> None:
    """Check if the manager's response fell into or dodged a trap.

    Called after every user message, before generating character reply.
    Sends trap.triggered WS event if a trap was activated.
    """
    active_traps = state.get("active_traps")
    last_character_msg = state.get("last_character_message", "")

    if not active_traps or not last_character_msg:
        return

    try:
        from app.services.trap_detector import detect_traps

        results = await detect_traps(
            session_id=session_id,
            character_message=last_character_msg,
            manager_message=manager_message,
            active_traps=active_traps,
        )

        for result in results:
            if result.status == "not_activated":
                continue

            await _send(ws, "trap.triggered", {
                "trap_name": result.trap_name,
                "category": result.category,
                "status": result.status,  # fell | dodged | partial
                "score_delta": result.score_delta,
                "wrong_keywords": result.wrong_keywords_found,
                "correct_keywords": result.correct_keywords_found,
                # Post-session review data
                "client_phrase": result.client_phrase,
                "correct_example": result.correct_example,
            })

    except Exception:
        logger.warning("Trap detection failed for session %s", session_id, exc_info=True)


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
            emotion_state=current_emotion,
        )
        await db.commit()

    # Check traps and update script score before generating character reply
    await _check_traps_after_user_message(ws, session_id, content, state)
    await _send_score_update(ws, session_id, content, state)

    await _generate_character_reply(ws, session_id, state)


async def _get_client_reveal_card(
    session_id: uuid.UUID,
    state: dict,
    db: AsyncSession,
) -> dict | None:
    """Build full client card with hidden fields for post-session reveal."""
    try:
        from app.models.roleplay import ClientProfile
        from app.services.client_generator import get_full_reveal_card

        result = await db.execute(
            select(ClientProfile).where(ClientProfile.session_id == session_id)
        )
        profile = result.scalar_one_or_none()
        if profile:
            return get_full_reveal_card(profile)
    except Exception:
        logger.debug("Could not load client profile for reveal, session %s", session_id)
    return None


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
            session.score_human_factor = scores.human_factor
            session.score_narrative = scores.narrative_progression
            session.score_legal = scores.legal_accuracy
            session.score_total = scores.total

            # Inject v5 metadata into scoring_details for results page
            enriched_details = dict(scores.details) if scores.details else {}
            enriched_details["_skill_radar"] = scores.skill_radar
            enriched_details["_scoring_version"] = "v5"

            # Save client name for soft_skills name_usage calculation
            client_name = state.get("client_name", "")
            if client_name:
                enriched_details["_client_name"] = client_name

            # Save full client card with hidden fields for post-session reveal
            # During training only CRM card is shown; after session we reveal psychology
            try:
                reveal_card = await _get_client_reveal_card(session_id, state, db)
                if reveal_card:
                    enriched_details["_client_card_reveal"] = reveal_card
            except Exception:
                logger.debug("Failed to build reveal card for session %s", session_id)

            session.scoring_details = enriched_details

        await db.commit()

    # Cleanup Redis state
    try:
        from app.services.trap_detector import cleanup_trap_state
        from app.services.objection_chain import cleanup_chain
        await cleanup_trap_state(session_id)
        await cleanup_chain(session_id)
    except Exception:
        logger.debug("Redis cleanup failed for session %s", session_id)

    # Release TTS voice assignment
    release_session_voice(str(session_id))

    state["last_ended_session_id"] = session_id
    state["active"] = False
    state["session_id"] = None

    result_data = {"message": err.WS_SESSION_ENDED}
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


# ===========================================================================
# v5: Multi-call story handlers
# ===========================================================================

async def _handle_story_start(
    ws: WebSocket,
    data: dict,
    state: dict,
) -> None:
    """Handle story.start: create a new multi-call story arc.

    Creates ClientStory, generates personality profile, and starts first call.
    Data: {scenario_id, total_calls?: 3, custom_params?: {...}}
    """
    user_id = state.get("user_id")
    if not user_id:
        await _send_error(ws, "Not authenticated", "auth_error")
        return

    scenario_id_str = data.get("scenario_id")
    if not scenario_id_str:
        await _send_error(ws, "scenario_id is required", "missing_field")
        return

    total_calls = data.get("total_calls", 3)
    total_calls = max(2, min(5, total_calls))  # Clamp to 2-5
    custom_params = data.get("custom_params") if isinstance(data.get("custom_params"), dict) else {}

    try:
        scenario_id = uuid.UUID(scenario_id_str)
    except ValueError:
        await _send_error(ws, "Invalid scenario_id format", "invalid_field")
        return

    async with async_session() as db:
        # Load scenario + character
        from app.models.scenario import Scenario
        result = await db.execute(
            select(Scenario).where(Scenario.id == scenario_id, Scenario.is_active == True)  # noqa: E712
        )
        scenario = result.scalar_one_or_none()
        if not scenario:
            await _send_error(ws, "Scenario not found", "not_found")
            return

        from app.models.character import Character
        char_result = await db.execute(
            select(Character).where(Character.id == scenario.character_id)
        )
        character = char_result.scalar_one_or_none()
        if not character:
            await _send_error(ws, "Character not found", "not_found")
            return

        archetype_code = (custom_params.get("archetype") or character.slug or "skeptic")

        # Generate personality profile correlated with archetype
        personality_profile = generate_personality_profile(archetype_code)

        # Create ClientStory
        from app.models.roleplay import ClientStory
        story = ClientStory(
            user_id=user_id,
            story_name=f"Story: {scenario.title}",
            total_calls_planned=total_calls,
            current_call_number=0,
            personality_profile=personality_profile,
            active_factors=[],
            between_call_events=[],
            consequences=[],
        )
        db.add(story)
        await db.flush()

        state["story_id"] = story.id
        state["total_calls"] = total_calls
        state["personality_profile"] = personality_profile
        state["active_factors"] = []
        state["accumulated_consequences"] = []
        state["between_call_events"] = []
        state["archetype_code"] = archetype_code
        state["scenario_id"] = scenario_id
        state["scenario"] = scenario
        state["character"] = character
        state["story_custom_params"] = custom_params

        await db.commit()

    await _send(ws, "story.started", {
        "story_id": str(story.id),
        "story_name": story.story_name,
        "total_calls": total_calls,
        "client_name": state.get("client_name", "Клиент"),
        "personality_profile": personality_profile,
    })

    # Auto-start first call
    await _handle_story_next_call(ws, data, state)


async def _handle_story_next_call(
    ws: WebSocket,
    data: dict,
    state: dict,
) -> None:
    """Handle story.next_call: start the next call in the multi-call story.

    Generates between-call events, pre-call brief, and initiates a new
    TrainingSession linked to the story.
    """
    story_id = state.get("story_id")
    if not story_id:
        await _send_error(ws, "No active story. Send story.start first.", "no_story")
        return

    total_calls = state.get("total_calls", 3)
    current_call = state.get("call_number", 0) + 1

    if current_call > total_calls:
        await _send_error(ws, "Story complete — all calls done", "story_complete")
        return

    state["call_number"] = current_call
    archetype_code = state.get("archetype_code", "skeptic")

    # Generate between-call events (skip for call 1)
    between_events = []
    if current_call > 1:
        previous_outcome = state.get("last_call_outcome")
        previous_emotion = state.get("last_call_emotion", "cold")
        existing_events = state.get("between_call_events", [])

        between_events = apply_between_calls_context(
            call_number=current_call,
            archetype_code=archetype_code,
            previous_outcome=previous_outcome,
            previous_emotion=previous_emotion,
            existing_events=existing_events,
        )

        # Accumulate events
        all_events = existing_events + [
            {"after_call": current_call - 1, **evt} for evt in between_events
        ]
        state["between_call_events"] = all_events

        # Send between-call context to frontend
        # Map backend event format to frontend contract:
        # Backend: {event, impact, description, emotion_shift}
        # Frontend: {event_type, title, content, severity}
        frontend_events = []
        for evt in between_events:
            # Derive severity from impact string (e.g. "anxiety+30" → 0.3)
            severity_val = None
            impact_str = evt.get("impact", "")
            if impact_str:
                import re as _re
                _m = _re.search(r"[+-](\d+)", impact_str)
                severity_val = int(_m.group(1)) / 100.0 if _m else 0.5
            frontend_events.append({
                "event_type": evt.get("event", "unknown"),
                "title": evt.get("event", "Событие").replace("_", " ").capitalize(),
                "content": evt.get("description", ""),
                "severity": severity_val,
            })
        await _send(ws, "story.between_calls", {
            "story_id": str(story_id),
            "events": frontend_events,
        })

    # Generate pre-call brief
    client_name = state.get("client_name", "Клиент")
    # Load episodic memories for brief
    key_memories = []
    try:
        from app.models.roleplay import EpisodicMemory
        async with async_session() as mem_db:
            mem_result = await mem_db.execute(
                select(EpisodicMemory)
                .where(EpisodicMemory.story_id == story_id)
                .order_by(EpisodicMemory.salience.desc())
                .limit(5)
            )
            memories = mem_result.scalars().all()
            key_memories = [
                {"content": m.content, "type": m.memory_type, "salience": m.salience}
                for m in memories
            ]
    except Exception:
        pass

    pre_call_brief = generate_pre_call_brief(
        call_number=current_call,
        client_name=client_name,
        archetype_code=archetype_code,
        previous_outcome=state.get("last_call_outcome"),
        previous_emotion=state.get("last_call_emotion", "cold"),
        between_events=between_events,
        key_memories=key_memories,
    )

    state["pre_call_brief"] = pre_call_brief
    state["episodic_memories"] = key_memories

    # Send structured pre-call brief matching frontend PreCallBrief interface
    scenario = state.get("scenario")
    scenario_title = scenario.title if scenario else "Сценарий"

    # Build active_factors for frontend HumanFactor[] contract
    active_hf = []
    for af in state.get("active_factors", []):
        active_hf.append({
            "factor": af.get("factor", af.get("name", "unknown")),
            "intensity": af.get("intensity", 0.5),
            "since_call": af.get("since_call", 1),
        })

    # Build previous_consequences for frontend ConsequenceEvent[] contract
    prev_consequences = []
    for c in state.get("accumulated_consequences", []):
        prev_consequences.append({
            "call": c.get("call", current_call - 1),
            "type": c.get("type", "unknown"),
            "severity": c.get("severity", 0.5),
            "detail": c.get("detail", ""),
        })

    await _send(ws, "story.pre_call_brief", {
        "story_id": str(story_id),
        "call_number": current_call,
        "total_calls": total_calls,
        "client_name": client_name,
        "scenario_title": scenario_title,
        "context": pre_call_brief,  # markdown brief as context text
        "active_factors": active_hf,
        "previous_consequences": prev_consequences,
        "personality_hint": state.get("personality_profile", {}).get("hint"),
        "suggested_approach": state.get("personality_profile", {}).get("suggested_approach"),
    })

    # Now start the actual call session via existing session.start mechanism
    # The client should follow up with session.start containing the scenario_id
    await _send(ws, "story.call_ready", {
        "story_id": str(story_id),
        "call_number": current_call,
        "session_id": str(state.get("session_id", "")),
    })


async def _handle_story_call_end(
    ws: WebSocket,
    data: dict,
    state: dict,
) -> None:
    """Handle end of a single call within a multi-call story.

    Saves call record, generates report, updates story state.
    Called after session.end when story_id is present.
    """
    story_id = state.get("story_id")
    session_id = state.get("last_ended_session_id") or state.get("session_id")
    if not story_id or not session_id:
        return

    call_number = state.get("call_number", 1)
    current_emotion = await get_emotion(session_id)

    # Save call record
    try:
        from app.models.training import CallRecord
        async with async_session() as db:
            record = CallRecord(
                story_id=story_id,
                session_id=session_id,
                call_number=call_number,
                pre_call_brief=state.get("pre_call_brief"),
                applied_events=state.get("between_call_events", []),
                simulated_days_gap=state.get("simulated_days_gap", 1),
                starting_emotion=state.get("call_starting_emotion", "cold"),
                starting_trust=state.get("call_starting_trust", 3),
                outcome=data.get("outcome", "unknown"),
                emotion_trajectory=state.get("emotion_trajectory", []),
                active_factors=state.get("active_factors", []),
                system_prompt_tokens=state.get("last_system_prompt_tokens"),
            )
            db.add(record)

            # Update ClientStory
            from app.models.roleplay import ClientStory
            story_result = await db.execute(
                select(ClientStory).where(ClientStory.id == story_id)
            )
            story = story_result.scalar_one_or_none()
            if story:
                story.current_call_number = call_number
                story.active_factors = state.get("active_factors", [])
                story.consequences = state.get("accumulated_consequences", [])
                story.between_call_events = state.get("between_call_events", [])

                # Compress older calls if needed
                if call_number >= 3:
                    mgr = get_context_budget_manager()
                    # Get message history for older calls
                    call_messages = await get_message_history(session_id)
                    call_msg_list = [
                        {"role": m["role"], "content": m["content"]}
                        for m in call_messages
                    ]
                    story.compressed_history = await mgr.compress_old_calls(
                        call_msg_list, story.compressed_history
                    )

                if call_number >= state.get("total_calls", 3):
                    story.is_completed = True
                    from datetime import datetime, timezone
                    story.ended_at = datetime.now(timezone.utc)

            await db.commit()
    except Exception:
        logger.warning("Failed to save call record for story %s call %d", story_id, call_number)

    # Generate post-call report
    try:
        from app.services.scenario_engine import SessionConfig
        messages = await get_message_history(session_id)
        msg_list = [{"role": m["role"], "content": m["content"]} for m in messages]

        # Build a minimal config for report generation
        config = SessionConfig(
            scenario_code=state.get("scenario_code", "unknown"),
            scenario_name=state.get("scenario_name", "Unknown"),
            template_id=uuid.uuid4(),
            archetype=state.get("archetype_code", "skeptic"),
            initial_emotion="cold",
            client_awareness="low",
            client_motivation="none",
        )

        is_final = call_number >= state.get("total_calls", 3)
        report_data = await generate_session_report(
            messages=msg_list,
            config=config,
            emotion_trajectory=state.get("emotion_trajectory"),
            call_number=call_number,
            is_story_final=is_final,
        )

        # Save report
        from app.models.training import SessionReport
        async with async_session() as db:
            report = SessionReport(
                story_id=story_id,
                session_id=session_id,
                call_number=call_number,
                report_type="story_summary" if is_final else "post_call",
                content=report_data,
                score_total=report_data.get("score_breakdown", {}).get("total"),
                is_final=is_final,
            )
            db.add(report)
            await db.commit()

        # Send report to frontend matching WSStoryCallReport contract
        # Extract score from score_breakdown or LLM report
        score_total = report_data.get("score_breakdown", {}).get("total", 0)
        if not score_total and isinstance(report_data.get("score"), (int, float)):
            score_total = report_data["score"]

        # key_moments: flatten to string[] for frontend
        raw_moments = report_data.get("key_moments", [])
        key_moments_list = []
        for km in raw_moments:
            if isinstance(km, dict):
                key_moments_list.append(km.get("detail", str(km)))
            else:
                key_moments_list.append(str(km))

        # consequences: from accumulated state, already in frontend format
        consequences_list = [
            {
                "call": c.get("call", call_number),
                "type": c.get("type", "unknown"),
                "severity": c.get("severity", 0.5),
                "detail": c.get("detail", ""),
            }
            for c in state.get("accumulated_consequences", [])
        ]

        # Count episodic memories created during this call
        memories_created = len(state.get("episodic_memories", []))

        await _send(ws, "story.call_report", {
            "story_id": str(story_id),
            "call_number": call_number,
            "score": score_total,
            "key_moments": key_moments_list,
            "consequences": consequences_list,
            "memories_created": memories_created,
        })

    except Exception:
        logger.warning("Failed to generate report for story %s call %d", story_id, call_number)

    # Store outcome for next call
    state["last_call_outcome"] = data.get("outcome", "unknown")
    state["last_call_emotion"] = current_emotion

    # Notify frontend about story progress
    total_calls = state.get("total_calls", 3)
    if call_number < total_calls:
        await _send(ws, "story.progress", {
            "story_id": str(story_id),
            "call_number": call_number,
            "total_calls": total_calls,
            "game_status": "in_process",
            "tension": len(state.get("accumulated_consequences", [])) * 0.15,
        })
    else:
        # Compute final score from last report if available
        last_report_score = 0
        try:
            from app.models.training import SessionReport
            async with async_session() as score_db:
                final_report = await score_db.execute(
                    select(SessionReport)
                    .where(SessionReport.story_id == story_id, SessionReport.is_final.is_(True))
                    .order_by(SessionReport.call_number.desc())
                    .limit(1)
                )
                fr = final_report.scalar_one_or_none()
                if fr and fr.score_total:
                    last_report_score = fr.score_total
        except Exception:
            pass

        await _send(ws, "story.completed", {
            "story_id": str(story_id),
            "final_status": "completed",
            "total_score": last_report_score,
            "calls_completed": call_number,
        })


async def training_websocket(websocket: WebSocket) -> None:
    """Handle a training session WebSocket connection.

    Auth flow: accept first, then authenticate via first message (not URL).
    v5: Added story.start, story.next_call message handlers for multi-call stories.
    """
    await websocket.accept()

    # Wait for auth message (10s timeout)
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
    except asyncio.TimeoutError:
        await _send(websocket, "auth.error", {"message": err.WS_AUTH_TIMEOUT})
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
    state_lock = asyncio.Lock()

    watchdog_task: asyncio.Task | None = None
    hint_task: asyncio.Task | None = None
    soft_skills_task: asyncio.Task | None = None
    stop_event = asyncio.Event()

    try:
        await _send(websocket, "session.ready", {
            "message": err.WS_AUTHENTICATED,
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
                    "message": err.WS_INACTIVITY_TIMEOUT,
                })
                break

            if stop_event.is_set():
                break

            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await _send_error(websocket, err.WS_INVALID_JSON, "parse_error")
                continue

            msg_type = message.get("type")
            msg_data = message.get("data", {})

            if msg_type == "session.start":
                await _handle_session_start(websocket, msg_data, state)
                if state.get("session_id") and watchdog_task is None:
                    sid = state["session_id"]
                    watchdog_task = asyncio.create_task(
                        _silence_watchdog(websocket, sid, state, stop_event, state_lock)
                    )
                    hint_task = asyncio.create_task(
                        _hint_scheduler(websocket, sid, state, stop_event, state_lock)
                    )
                    soft_skills_task = asyncio.create_task(
                        _soft_skills_tracker(websocket, sid, state, stop_event, state_lock)
                    )

            elif msg_type == "audio.chunk":
                await _handle_audio_chunk(websocket, msg_data, state)

            elif msg_type == "audio.end":
                await _handle_audio_end(websocket, msg_data, state)

            elif msg_type == "text.message":
                await _handle_text_message(websocket, msg_data, state)

            elif msg_type == "session.end":
                await _handle_session_end(websocket, msg_data, state)
                # v5: If this is part of a story, handle call-level end
                if state.get("story_id"):
                    await _handle_story_call_end(websocket, msg_data, state)
                    # Don't break — story may have more calls
                else:
                    stop_event.set()
                    break

            # ── v5: Multi-call story messages ──
            elif msg_type == "story.start":
                await _handle_story_start(websocket, msg_data, state)

            elif msg_type == "story.next_call":
                await _handle_story_next_call(websocket, msg_data, state)

            elif msg_type == "story.end":
                # Force-end the entire story
                if state.get("story_id"):
                    try:
                        from app.models.roleplay import ClientStory
                        async with async_session() as db:
                            story_result = await db.execute(
                                select(ClientStory).where(
                                    ClientStory.id == state["story_id"]
                                )
                            )
                            story = story_result.scalar_one_or_none()
                            if story:
                                story.is_completed = True
                                from datetime import datetime, timezone
                                story.ended_at = datetime.now(timezone.utc)
                            await db.commit()
                    except Exception:
                        logger.warning("Failed to end story %s", state.get("story_id"))
                    await _send(websocket, "story.completed", {
                        "story_id": str(state["story_id"]),
                        "forced": True,
                    })
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
        for task in (watchdog_task, hint_task, soft_skills_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        # Release TTS voice on disconnect
        sid = state.get("session_id")
        if sid:
            release_session_voice(str(sid))
