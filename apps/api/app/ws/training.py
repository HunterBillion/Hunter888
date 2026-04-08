"""WebSocket handler for real-time training sessions (v5 with multi-call stories).

Protocol (TZ section 7.8 + v5 extensions):
- Auth: JWT token sent in FIRST message (not URL query param)
- Client sends: auth, session.start, audio.chunk, audio.end, text.message, session.end, ping
- v5 client sends: story.start, story.next_call, story.end
- v6 client sends: session.resume, auth.refresh
- Server sends: session.ready, auth.success, auth.error, session.started,
                avatar.typing, transcription.result, character.response,
                emotion.update, score.update, session.ended,
                silence.warning, silence.timeout, error
- v5 server sends: story.started, story.between_calls, story.pre_call_brief,
                    story.call_ready, story.call_report, story.progress,
                    story.completed
- v6 server sends: session.resumed, message.replay, auth.refreshed, auth.refresh_error

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
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.database import async_session
from app.models.character import Character, EmotionState, LEGACY_MAP
from app.models.scenario import Scenario, ScenarioTemplate, ScenarioType
from app.models.training import MessageRole, SessionStatus, TrainingSession
from app.models.user import User

from app.services.emotion import (
    get_emotion, init_emotion, init_emotion_v3,
    transition_emotion, transition_emotion_v3,
    get_fake_prompt, save_journey_snapshot,
)
from app.services.emotion_v6 import compute_intensity, detect_compound_emotion
from app.services.session_manager import (
    RateLimitError,
    SessionError,
    add_message,
    check_message_limit,
    end_session,
    get_message_history,
    get_message_history_db,
    get_session_state,
    refresh_session_ttl,
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
    SessionConfig,
    apply_between_calls_context,
    generate_pre_call_brief,
    generate_session_report,
    parse_stage_directions_v2,
)
from app.services.adaptive_difficulty import IntraSessionAdapter, ReplyQuality
from app.services.scoring import (
    calculate_realtime_scores,
    calculate_scores,
    generate_layer_explanations,
    layer_explanations_to_dict,
)
from app.services.stage_tracker import StageTracker
from app.services.stt import STTError, transcribe_audio
from app.services.stt_deepgram import DeepgramStreamingSTT
from app.core.ws_rate_limiter import training_limiter
from app.services.tts import (
    TTSError,
    TTSQuotaExhausted,
    get_tts_audio_b64,
    is_tts_available,
    pick_voice_for_session,
    release_session_voice,
)

logger = logging.getLogger(__name__)


async def _resolve_scenario(db, scenario_id: "uuid.UUID") -> Scenario | None:
    """Look up a scenario by ID, checking both legacy `scenarios` table and
    `scenario_templates`. If the ID matches a template but not a legacy row,
    auto-create a Scenario row (same logic as REST POST /training/sessions)."""
    result = await db.execute(
        select(Scenario).where(Scenario.id == scenario_id, Scenario.is_active == True)  # noqa: E712
    )
    scenario = result.scalar_one_or_none()
    if scenario is not None:
        return scenario

    # Fallback: check scenario_templates
    tpl_result = await db.execute(
        select(ScenarioTemplate).where(
            ScenarioTemplate.id == scenario_id, ScenarioTemplate.is_active == True  # noqa: E712
        )
    )
    tpl = tpl_result.scalar_one_or_none()
    if tpl is None:
        return None

    # Map template code prefix to legacy ScenarioType
    code = tpl.code or ""
    if code.startswith("cold"):
        legacy_type = ScenarioType.cold_call
    elif code.startswith("warm"):
        legacy_type = ScenarioType.warm_call
    elif code.startswith("in_"):
        legacy_type = ScenarioType.consultation
    else:
        legacy_type = ScenarioType.objection_handling

    # Find a default character for FK
    char_result = await db.execute(select(Character.id).limit(1))
    default_char_id = char_result.scalar_one_or_none()
    if default_char_id is None:
        return None

    new_scenario = Scenario(
        id=tpl.id,
        title=tpl.name,
        description=tpl.description,
        scenario_type=legacy_type,
        character_id=default_char_id,
        template_id=tpl.id,
        difficulty=getattr(tpl, "difficulty", 5),
        estimated_duration_minutes=tpl.typical_duration_minutes,
    )
    db.add(new_scenario)
    await db.flush()
    return new_scenario


SILENCE_WARNING_SEC = 30  # Avatar says "Алло?"
SILENCE_TIMEOUT_SEC = 60  # Modal "Continue?"
MAX_STT_FAILURES = 3

# ── Emotion-aware silence phrases ──
# Organized by emotion → list of phrases.
# Picked intelligently based on current client emotion and silence count.
SILENCE_PHRASES_BY_EMOTION: dict[str, list[str]] = {
    "cold": [
        "Алло? Вы ещё здесь?",
        "Алло? Вы слышите меня?",
        "Мне кажется, связь прервалась...",
    ],
    "hostile": [
        "Ну? Я жду.",
        "Вы собираетесь что-то сказать или мне повесить трубку?",
        "Я не буду ждать вечно.",
    ],
    "guarded": [
        "Алло? Вы там?",
        "Я всё ещё на линии...",
        "Если вам нужно время подумать — скажите.",
    ],
    "curious": [
        "Вы задумались? Я могу подождать.",
        "Не торопитесь, я на линии.",
        "Если есть вопросы — спрашивайте.",
    ],
    "considering": [
        "Я понимаю, есть над чем подумать...",
        "Не торопитесь с решением.",
        "Нужно время? Я подожду.",
    ],
    "negotiating": [
        "Вы обдумываете предложение?",
        "Я жду вашего ответа.",
        "Если нужны уточнения — я здесь.",
    ],
    "deal": [
        "Алло? Мы продолжаем?",
        "Вы записываете? Я подожду.",
    ],
    "testing": [
        "Ну, я слушаю...",
        "Вы проверяете моё терпение?",
        "Алло?",
    ],
}
# Fallback for unknown emotions
_SILENCE_FALLBACK = ["Алло? Вы ещё здесь?", "Алло?", "Мне кажется, связь прервалась..."]


def _pick_silence_phrase(emotion: str, silence_count: int = 0) -> str:
    """Pick an emotion-aware silence phrase.

    - First silence: gentle/neutral variant
    - Second silence: more insistent
    - Third+: urgent / final warning tone
    """
    import random as _rnd

    pool = SILENCE_PHRASES_BY_EMOTION.get(emotion, _SILENCE_FALLBACK)
    # Escalation: pick later phrases on repeated silences
    idx = min(silence_count, len(pool) - 1)
    # Add slight randomness within the escalation band
    band_start = max(0, idx - 1)
    band_end = min(len(pool), idx + 2)
    return _rnd.choice(pool[band_start:band_end])

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
    # Sanitize: truncate and strip potential internal details (stack traces, paths)
    safe_message = str(message)[:200]
    # Remove file paths that might leak server internals
    import re as _re
    safe_message = _re.sub(r'/[\w/.-]+\.py\b', '[internal]', safe_message)
    safe_message = _re.sub(r'line \d+', '', safe_message)
    await _send(ws, "error", {"message": safe_message, "code": code})


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


# ─── WS Session Lock (mutex for single-connection-per-session) ─────────────

_WS_LOCK_KEY = "ws:lock:{session_id}"
_WS_LOCK_TTL = 60  # seconds, refreshed on heartbeat


async def _acquire_session_lock(
    session_id: uuid.UUID, ws_id: str
) -> bool:
    """Try to acquire exclusive WS lock for a session. Returns True if acquired."""
    from app.core.redis_pool import get_redis
    r = get_redis()
    try:
        key = _WS_LOCK_KEY.format(session_id=session_id)
        acquired = await r.set(key, ws_id, nx=True, ex=_WS_LOCK_TTL)
        return bool(acquired)
    except Exception:
        logger.error("Failed to acquire WS lock for session %s — rejecting connection", session_id)
        return False  # Fail-CLOSED: reject if lock cannot be verified (security > availability)


async def _refresh_session_lock(session_id: uuid.UUID, ws_id: str) -> bool:
    """Refresh lock TTL on heartbeat. Only refreshes if we still own the lock.

    Uses Lua script for atomic check-and-expire to prevent TOCTOU race.
    Returns True if lock was refreshed, False if lost.
    """
    from app.core.redis_pool import get_redis
    r = get_redis()
    try:
        key = _WS_LOCK_KEY.format(session_id=session_id)
        # Atomic: only expire if we still own the lock
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        result = await r.eval(lua_script, 1, key, ws_id, str(_WS_LOCK_TTL))
        # BUG-7 fix: detect lost lock instead of silently continuing
        if not result:
            logger.warning(
                "WS lock lost for session %s (ws_id=%s) — another connection may have taken over",
                session_id, ws_id,
            )
            return False
        return True
    except Exception as e:
        logger.warning("Failed to refresh WS lock for session %s: %s", session_id, e)
        return True  # On Redis error, assume we still hold (fail-open for heartbeat)


async def _release_session_lock(session_id: uuid.UUID, ws_id: str) -> None:
    """Release WS lock on disconnect (only if we own it).

    Uses Lua script for atomic check-and-delete to avoid TOCTOU race
    where another connection acquires the lock between our GET and DELETE.
    """
    from app.core.redis_pool import get_redis
    r = get_redis()
    try:
        key = _WS_LOCK_KEY.format(session_id=session_id)
        # Atomic: only delete if we still own the lock
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        await r.eval(lua_script, 1, key, ws_id)
    except Exception as e:
        logger.debug("Failed to release WS lock for session %s: %s", session_id, e)


# ─── Session Resume Handler ─────────────────────────────────────────────────

_REPLAY_LIMIT = 20


async def _handle_session_resume(
    ws: WebSocket, data: dict, state: dict, ws_id: str
) -> None:
    """Resume a previously active session after reconnection.

    Restores state from Redis (with DB fallback), replays missed messages,
    and re-sends current emotion / elapsed time.
    """
    session_id_str = data.get("session_id")
    last_seq = data.get("last_sequence_number")

    if not session_id_str:
        await _send(ws, "error", {"code": "missing_session_id"})
        return

    # 0. Blacklist check — prevent resumed sessions for logged-out users
    from app.core.deps import _is_user_blacklisted
    user_id_str = str(state.get("user_id", ""))
    if await _is_user_blacklisted(user_id_str):
        await _send(ws, "auth.error", {"message": err.WS_TOKEN_REVOKED})
        return

    try:
        session_id = uuid.UUID(session_id_str)
    except ValueError:
        await _send(ws, "error", {"code": "invalid_session_id"})
        return

    # 1. Verify session exists and belongs to user
    async with async_session() as db:
        result = await db.execute(
            select(TrainingSession).where(TrainingSession.id == session_id)
        )
        session = result.scalar_one_or_none()

    if not session or session.user_id != state["user_id"]:
        await _send(ws, "error", {"code": "session_not_found"})
        return

    # 2. Check session is still active
    if session.status not in (SessionStatus.active, SessionStatus.paused):
        await _send(ws, "error", {"code": "session_completed"})
        return

    # 3. Acquire exclusive lock
    locked = await _acquire_session_lock(session_id, ws_id)
    if not locked:
        await _send(ws, "error", {"code": "session_locked"})
        return

    # 4. Restore state from Redis
    redis_state = await get_session_state(session_id)
    if redis_state:
        state["session_id"] = session_id
        state["scenario_id"] = redis_state.get("scenario_id")
        state["active"] = True
        state["message_count"] = redis_state.get("message_count", 0)
    else:
        # Redis lost state — minimal recovery from DB
        state["session_id"] = session_id
        state["scenario_id"] = str(session.scenario_id) if session.scenario_id else None
        state["active"] = True
        state["message_count"] = 0  # Will be corrected from message history below

    # 4b. Restore full session context from DB (scenario, character, client profile, traps)
    # Without this, LLM calls get no character prompt, trap detection fails,
    # scoring features break, and adaptive difficulty uses wrong base_difficulty.
    async with async_session() as db_resume:
        # Load scenario
        scenario = None
        scenario_id_val = state.get("scenario_id")
        if scenario_id_val:
            try:
                sc_result = await db_resume.execute(
                    select(Scenario).where(Scenario.id == uuid.UUID(str(scenario_id_val)))
                )
                scenario = sc_result.scalar_one_or_none()
            except Exception:
                logger.warning("Failed to load scenario for resume session %s", session_id)

        # Load character from scenario
        character = None
        if scenario and scenario.character_id:
            try:
                ch_result = await db_resume.execute(
                    select(Character).where(Character.id == scenario.character_id)
                )
                character = ch_result.scalar_one_or_none()
            except Exception:
                logger.warning("Failed to load character for resume session %s", session_id)

        # Restore custom_params from session record
        custom_params = session.custom_params or {}
        state["custom_params"] = custom_params
        custom_archetype = custom_params.get("archetype")
        custom_difficulty = custom_params.get("difficulty")

        state["character_prompt_path"] = character.prompt_path if character else None
        state["archetype_code"] = custom_archetype or (character.slug if character else None)
        state["base_difficulty"] = custom_difficulty or (scenario.difficulty if scenario else 5)
        state["script_id"] = scenario.script_id if scenario else None
        state["matched_checkpoints"] = set()  # Past matches already scored; fresh set for remainder
        state["last_character_message"] = ""
        state["fake_transition_prompt"] = ""
        state["stt_failure_count"] = 0

        # Restore template_checkpoints for scenarios without script_id
        state["template_checkpoints"] = None
        if scenario and not scenario.script_id and scenario.template_id:
            try:
                from app.models.scenario import ScenarioTemplate
                tmpl_result = await db_resume.execute(
                    select(ScenarioTemplate).where(ScenarioTemplate.id == scenario.template_id)
                )
                tmpl = tmpl_result.scalar_one_or_none()
                if tmpl and tmpl.stages:
                    from app.services.script_checker import generate_checkpoints_from_template
                    state["template_checkpoints"] = generate_checkpoints_from_template(tmpl.stages)
            except Exception:
                logger.debug("Failed to restore template checkpoints for resumed session %s", session_id)

        # Restore client profile, traps, and LLM system prompt context
        client_profile_prompt = ""
        active_traps = []
        client_name = ""
        client_gender = ""
        try:
            from app.models.roleplay import ClientProfile
            from app.services.client_generator import get_crm_card
            cp_result = await db_resume.execute(
                select(ClientProfile).where(ClientProfile.session_id == session_id)
            )
            profile = cp_result.scalar_one_or_none()
            if profile:
                client_card = get_crm_card(profile)
                client_name = client_card.get("full_name", "") if client_card else ""
                client_gender = getattr(profile, "gender", "") or ""
                client_profile_prompt = _build_client_profile_prompt(profile)

                # Reload active traps
                if profile.trap_ids:
                    from app.models.roleplay import Trap
                    trap_result = await db_resume.execute(
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

                    # Re-inject trap phrases into system prompt
                    from app.services.trap_detector import build_trap_injection_prompt
                    trap_prompt = build_trap_injection_prompt(active_traps)
                    if trap_prompt:
                        client_profile_prompt += "\n\n" + trap_prompt

                # Restore objection chain prompt injection
                if profile.chain_id:
                    try:
                        from app.models.roleplay import ObjectionChain
                        from app.services.objection_chain import build_chain_system_prompt
                        chain_result = await db_resume.execute(
                            select(ObjectionChain).where(ObjectionChain.id == profile.chain_id)
                        )
                        chain_obj = chain_result.scalar_one_or_none()
                        if chain_obj and chain_obj.steps:
                            chain_prompt = build_chain_system_prompt(chain_obj.steps)
                            if chain_prompt:
                                client_profile_prompt += "\n\n" + chain_prompt
                    except Exception:
                        logger.debug("Failed to restore objection chain for session %s", session_id)
        except Exception:
            logger.warning("Failed to restore client profile for resumed session %s", session_id, exc_info=True)

        state["client_profile_prompt"] = client_profile_prompt
        state["active_traps"] = active_traps
        state["client_name"] = client_name
        state["client_gender"] = client_gender

        # Restore whisper and TTS preferences
        _user_prefs = state.get("user_prefs", {})
        _whisper_pref = _user_prefs.get("whispers_enabled")
        if _whisper_pref is not None:
            state["whispers_enabled"] = bool(_whisper_pref)
        else:
            try:
                from app.models.progress import ManagerProgress
                _mp_result = await db_resume.execute(
                    select(ManagerProgress.current_level).where(ManagerProgress.user_id == state["user_id"])
                )
                _level = _mp_result.scalar() or 1
                state["whispers_enabled"] = _level <= 5
            except Exception:
                state["whispers_enabled"] = True

        # Restore TTS voice assignment
        user_tts_pref = _user_prefs.get("tts_enabled", True)
        session_archetype = state.get("archetype_code")
        if is_tts_available() and user_tts_pref:
            try:
                tts_voice_id = pick_voice_for_session(
                    str(session_id),
                    gender=client_gender,
                    archetype=session_archetype,
                )
                state["tts_voice_id"] = tts_voice_id
            except TTSError as e:
                logger.debug("TTS voice pick failed for session %s: %s", session_id, e)

    logger.info("Session %s: full state restored (character=%s, traps=%d, difficulty=%s)",
                session_id, state.get("character_prompt_path"), len(active_traps), state.get("base_difficulty"))

    # 5. Send current emotion
    emotion = await get_emotion(session_id)
    await _send(ws, "emotion.update", {"current": str(emotion)})

    # 6. Stage tracking (optional — only if StageTracker is available)
    try:
        from app.core.redis_pool import get_redis as _get_redis_resume_st
        _r_resume_st = _get_redis_resume_st()
        _st_resume = StageTracker(str(session_id), _r_resume_st)
        _stage_state = await _st_resume.get_state()
        if _stage_state and _stage_state.current_stage:
            await _send(ws, "stage.update", _st_resume.build_ws_payload(_stage_state))
    except Exception as e:
        logger.debug("Stage tracking restore skipped for session %s: %s", session_id, e)

    # 6b. Restore adaptive difficulty state (optional)
    try:
        from app.services.adaptive_difficulty import IntraSessionAdapter as _ISA
        from app.core.redis_pool import get_redis as _get_redis_resume_diff
        _r_diff = _get_redis_resume_diff()
        _ada = _ISA(_r_diff)
        _ad_state = await _ada.get_state(str(session_id))
        if _ad_state and _ad_state.current_turn > 0:
            base_diff = state.get("base_difficulty", 5)
            await _send(ws, "difficulty.update", _ada.build_ws_payload(_ad_state, base_diff))
    except Exception as e:
        logger.debug("Difficulty tracking restore skipped for session %s: %s", session_id, e)

    # 7. Replay missed messages
    messages = await get_message_history(session_id)
    if not messages:
        # Redis empty — fallback to DB
        async with async_session() as db:
            messages = await get_message_history_db(session_id, db)

    # Correct message_count from actual history when Redis state was missing
    if not redis_state and messages:
        state["message_count"] = len(messages)

    if last_seq is not None:
        replay_messages = [
            m for m in messages
            if (m.get("sequence_number") or 0) > last_seq
        ]
    else:
        # No last_seq — send last 5 as context
        replay_messages = messages[-5:]

    # Limit replay to prevent heavy payloads
    if len(replay_messages) > _REPLAY_LIMIT:
        replay_messages = replay_messages[-_REPLAY_LIMIT:]

    for msg in replay_messages:
        await _send(ws, "message.replay", {
            "role": msg.get("role", "assistant"),
            "content": msg.get("content", ""),
            "emotion": msg.get("emotion_state"),
            "sequence_number": msg.get("sequence_number"),
            "timestamp": msg.get("timestamp"),
        })

    # 8. Calculate elapsed time
    elapsed = 0.0
    if session.started_at:
        from datetime import datetime, timezone
        started = session.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()

    # 9. Confirm resume
    await _send(ws, "session.resumed", {
        "session_id": str(session_id),
        "elapsed_seconds": elapsed,
        "message_count": len(messages),
        "emotion": str(emotion),
    })

    # Refresh Redis TTLs
    await refresh_session_ttl(session_id)

    state["resumed"] = True
    logger.info("Session %s resumed by user %s", session_id, state["user_id"])


# ─── Auth Refresh via WS Handler ────────────────────────────────────────────

async def _handle_auth_refresh(ws: WebSocket, data: dict, state: dict) -> None:
    """Handle proactive token refresh over existing WS connection.

    This avoids the need to close and reconnect when the access token expires.
    """
    import jwt as pyjwt

    refresh_token = data.get("refresh_token")
    if not refresh_token:
        await _send(ws, "auth.refresh_error", {"reason": "no_token"})
        return

    try:
        payload = pyjwt.decode(
            refresh_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        if payload.get("type") != "refresh":
            await _send(ws, "auth.refresh_error", {"reason": "invalid_token_type"})
            return

        user_id_str = payload.get("sub")
        if not user_id_str:
            await _send(ws, "auth.refresh_error", {"reason": "invalid_token"})
            return

        # Verify this refresh is for the authenticated user
        if str(state["user_id"]) != user_id_str:
            await _send(ws, "auth.refresh_error", {"reason": "user_mismatch"})
            return

        # Create new tokens
        new_access_token = create_access_token({"sub": user_id_str})
        new_refresh_token = create_refresh_token({"sub": user_id_str})

        await _send(ws, "auth.refreshed", {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
        })

        logger.debug("Token refreshed via WS for user %s", user_id_str)

    except pyjwt.ExpiredSignatureError:
        await _send(ws, "auth.refresh_error", {"reason": "refresh_expired"})
    except Exception:
        await _send(ws, "auth.refresh_error", {"reason": "invalid_token"})


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
    except Exception as e:
        logger.debug("Objection chain injection failed for session %s: %s", session_id, e)

    # Inject comprehensive stage-aware behavior rules into AI client prompt
    try:
        from app.core.redis_pool import get_redis as _get_redis_sp
        _r_sp = _get_redis_sp()
        _st_prompt = StageTracker(str(session_id), _r_sp)
        _stage_st = await _st_prompt.get_state()
        extra_system += _st_prompt.build_stage_prompt(_stage_st)

        # If there are pending skip reactions (from previous process_message),
        # inject them as a directive for the AI to challenge the manager
        _skip_reactions = state.get("_pending_skip_reactions", [])
        if _skip_reactions:
            extra_system += (
                "\n\n[SKIP_REACTION: Менеджер пропустил важный этап! "
                "Начни свой ответ с одной из этих фраз (выбери наиболее уместную), "
                "затем продолжи отвечать по существу:\n"
                + "\n".join(f'  — "{r}"' for r in _skip_reactions)
                + "]"
            )
            # Clear skip reactions after injecting (one-shot)
            state.pop("_pending_skip_reactions", None)
    except Exception as e:
        logger.debug("Stage context injection failed for session %s: %s", session_id, e)

    # Inject fake transition prompt if present (from V3 engine)
    if state.get("fake_transition_prompt"):
        extra_system += "\n\n" + state["fake_transition_prompt"]

    # ── Game Director 3-tier context injection (Tier 1: identity, Tier 2: memory) ──
    # Tier 3 is already injected ad-hoc in _prepare_next_call_context.
    # This adds OCEAN/PAD/factors (Tier 1) and episodic memories/consequences (Tier 2)
    # for multi-call stories, giving the AI character deeper personality awareness.
    _story_id = state.get("story_id")
    if _story_id and state.get("message_count", 0) <= 1:
        # Inject full context only on the first exchange of each call
        # to stay within token budget (~1300 tokens for Tier 1+2).
        try:
            from app.services.game_director import game_director as _gd
            async with async_session() as _gd_db:
                _ctx = await _gd.build_context_injection(str(_story_id), _gd_db)
                if _ctx.tier1_identity:
                    extra_system += "\n\n" + _ctx.tier1_identity
                if _ctx.tier2_memory:
                    extra_system += "\n\n" + _ctx.tier2_memory
                logger.debug(
                    "GD context injected for story %s: ~%d tokens (T1+T2)",
                    _story_id, int(_ctx.total_tokens or 0),
                )
        except Exception:
            logger.debug("Game Director context injection failed for story %s", _story_id, exc_info=True)

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
        fallback_content = "Секунду... мне нужно собраться с мыслями."
        await _send(ws, "character.response", {
            "content": fallback_content,
            "emotion": current_emotion,
            "is_fallback": True,
        })
        # Save fallback message to DB to keep history consistent
        # (user message was already saved, so assistant must follow)
        try:
            async with async_session() as db:
                await add_message(
                    session_id=session_id,
                    role=MessageRole.assistant,
                    content=fallback_content,
                    db=db,
                    emotion_state=current_emotion,
                    llm_model="fallback",
                    llm_latency_ms=0,
                )
                await db.commit()
        except Exception as db_err:
            logger.error("Failed to save fallback message for session %s: %s", session_id, db_err)
        return

    # Stop typing indicator
    await _send(ws, "avatar.typing", {"is_typing": False})

    # ── Security: filter AI output before sending to user ──
    from app.services.content_filter import filter_ai_output
    llm_result.content, ai_violations = filter_ai_output(llm_result.content)
    if ai_violations:
        logger.info("AI output filtered in session %s: %s", session_id, ai_violations)

    # Save assistant message to DB
    async with async_session() as db:
        _saved_msg = await add_message(
            session_id=session_id,
            role=MessageRole.assistant,
            content=llm_result.content,
            db=db,
            emotion_state=current_emotion,
            llm_model=llm_result.model,
            llm_latency_ms=llm_result.latency_ms,
        )
        state["message_count"] = _saved_msg.sequence_number
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

        # ── Merge trap-originated emotion triggers (fell/dodged) ──
        trap_emotion_triggers = state.pop("_trap_emotion_triggers", [])
        all_triggers = list(trigger_result.triggers) if (trigger_result and trigger_result.triggers) else []
        if trap_emotion_triggers:
            all_triggers.extend(trap_emotion_triggers)
            logger.debug("Merged trap emotion triggers into V3 engine: %s", trap_emotion_triggers)

        # Use V3 engine with detected + trap triggers
        if archetype_code and all_triggers:
            new_emotion, emotion_meta = await transition_emotion_v3(
                session_id, archetype_code, all_triggers
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

    # ─── HANGUP WARNING ───
    # If emotion transitioned TO hostile (not already hostile before), warn the manager.
    # This gives them a chance to de-escalate before the client actually hangs up.
    if new_emotion == "hostile" and current_emotion != "hostile":
        _warning_phrases = [
            "Если вы продолжите в таком тоне, я повешу трубку.",
            "Я начинаю терять терпение.",
            "Мне не нравится этот разговор.",
            "Давайте перейдём к делу, или я заканчиваю.",
            "Я не обязан это слушать.",
        ]
        import random as _wrng
        await _send(ws, "client.hangup_warning", {
            "message": _wrng.choice(_warning_phrases),
            "emotion": "hostile",
            "severity": round(abs(emotion_meta.get("energy_after", -0.5)), 2),
        })

    # ─── HANGUP DETECTION ───
    # If emotion transitioned to "hangup" → client hangs up the phone.
    # Send a final phrase, notify frontend, and stop the conversation.
    if new_emotion == "hangup":
        import random as _rng

        # Try LLM-generated hangup phrase based on conversation context
        hangup_phrase = None
        try:
            _last_msgs = messages[-4:] if len(messages) >= 4 else messages
            _context = " | ".join(f"{m['role']}: {m['content'][:80]}" for m in _last_msgs)
            _hangup_prompt = (
                "Ты клиент, который решил бросить трубку. "
                "Скажи короткую финальную фразу (1-2 предложения), "
                "выражающую раздражение или разочарование, учитывая контекст разговора. "
                "Контекст последних реплик: " + _context
            )
            _hangup_llm = await generate_response(
                system_prompt=_hangup_prompt,
                messages=[],
                emotion_state="hangup",
            )
            if _hangup_llm and _hangup_llm.content and len(_hangup_llm.content) < 200:
                hangup_phrase = _strip_stage_directions(_hangup_llm.content)
        except Exception as e:
            logger.debug("LLM hangup phrase generation failed for session %s: %s", session_id, e)

        # Fallback to hardcoded if LLM failed
        if not hangup_phrase:
            _hangup_phrases = [
                "Знаете, я не намерен это слушать. Всего доброго.",
                "Перезвоните, когда будете готовы нормально разговаривать.",
                "Я думаю, нам не о чем разговаривать. До свидания.",
                "Нет, спасибо. Больше не звоните мне.",
                "Вы меня не убедили. Не перезванивайте.",
                "Я нашёл другую компанию. Удачи.",
                "Хватит, я устал от этого разговора.",
                "Мне это неинтересно. Прощайте.",
                "Я не собираюсь тратить на это время.",
                "Достаточно. Я повешу трубку.",
            ]
            hangup_phrase = _rng.choice(_hangup_phrases)

        # Determine reason from triggers
        _triggers = trigger_result.triggers if trigger_result else []
        if "insult" in _triggers:
            hangup_reason = "Клиент оскорблён вашим поведением"
        elif "counter_aggression" in _triggers:
            hangup_reason = "Клиент ответил на вашу агрессию"
        elif emotion_meta.get("forced_hangup"):
            hangup_reason = "Клиент потерял терпение (слишком много неудачных ответов)"
        else:
            hangup_reason = "Клиент решил прекратить разговор"

        # Send hangup phrase as the final character.response
        await _send(ws, "character.response", {
            "content": hangup_phrase,
            "emotion": "hangup",
            "is_hangup": True,
        })

        # TTS for the hangup phrase (best-effort)
        _user_tts_pref = state.get("user_prefs", {}).get("tts_enabled", True)
        if is_tts_available() and settings.elevenlabs_enabled and _user_tts_pref:
            try:
                _tts_res = await get_tts_audio_b64(hangup_phrase, str(session_id), emotion="hangup")
                if _tts_res and _tts_res.get("audio"):
                    await _send(ws, "tts.audio", {
                        "audio_b64": _tts_res["audio"],
                        "format": _tts_res.get("format", "mp3"),
                        "emotion": "hangup",
                        "voice_params": _tts_res.get("voice_params"),
                        "duration_ms": _tts_res.get("duration_ms"),
                        "text": hangup_phrase,
                    })
            except Exception:
                logger.debug("TTS failed for hangup phrase, session %s", session_id)

        # Send client.hangup event
        is_multi_call = state.get("story_id") is not None
        await _send(ws, "client.hangup", {
            "reason": hangup_reason,
            "emotion": "hangup",
            "hangup_phrase": hangup_phrase,
            "call_can_continue": is_multi_call,
            "triggers": _triggers,
        })

        # Save hangup outcome in state
        state["call_outcome"] = "hangup"
        state["hangup_reason"] = hangup_reason

        if is_multi_call:
            # Multi-call: do NOT end session — mark call as failed,
            # set penalties for next call, wait for story.next_call
            state["trust_penalty"] = -2
            state["next_call_emotion"] = "hostile"
            logger.info("HANGUP multi-call | session=%s | reason=%s", session_id, hangup_reason)
        else:
            # Single call: end session
            logger.info("HANGUP single | session=%s | reason=%s", session_id, hangup_reason)
            await _handle_session_end(ws, {}, state)

        return  # Stop — do not continue with normal flow
    # ─── END HANGUP DETECTION ───

    # Check for fake transition prompt and inject into NEXT LLM call
    try:
        fake_prompt = await get_fake_prompt(session_id, archetype_code or "skeptic")
        if fake_prompt:
            state["fake_transition_prompt"] = fake_prompt
        else:
            state.pop("fake_transition_prompt", None)
    except Exception as e:
        logger.debug("Fake transition prompt failed for session %s: %s", session_id, e)

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

    # ── Stage tracking: update quality score from AI client response ──
    try:
        from app.core.redis_pool import get_redis as _get_redis_asr
        _r_asr = _get_redis_asr()
        _st_assist = StageTracker(str(session_id), _r_asr)
        # Returns (state, changed, skipped) — we discard; assistant msgs only update quality scores
        _ = await _st_assist.process_message(clean_content, state.get("message_count", 0), "assistant")
    except Exception as e:
        logger.debug("Stage tracker update for assistant message failed, session %s: %s", session_id, e)

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
        _em_msg = {
            "previous": current_emotion,
            "current": new_emotion,
            "triggers": trigger_result.triggers if trigger_result else [],
            "energy": emotion_meta.get("energy_after", 0),
            "is_fake": emotion_meta.get("is_fake", False),
            "rollback": emotion_meta.get("rollback", False),
        }
        # v6 extensions: intensity + compound emotion
        try:
            _energy_val = emotion_meta.get("energy_after", 0.0)
            _thresh_pos = emotion_meta.get("threshold_pos", 1.0)
            _thresh_neg = emotion_meta.get("threshold_neg", -1.0)
            _intensity_level, _intensity_norm = compute_intensity(
                _energy_val, _thresh_pos, _thresh_neg,
            )
            _em_msg["intensity"] = _intensity_level.value  # "low"/"medium"/"high"

            _recent = [current_emotion, new_emotion]
            _compound = detect_compound_emotion(
                current_state=new_emotion,
                intensity=_intensity_level,
                intensity_value=_intensity_norm,
                recent_states=_recent,
                fake_active=emotion_meta.get("is_fake", False),
                ocean_profile=state.get("ocean_profile"),
                recent_triggers=[t for t in (trigger_result.triggers if trigger_result else [])],
            )
            _em_msg["compound"] = _compound.code if _compound else None
        except Exception:
            logger.debug("v6 emotion extensions failed for session %s", session_id)
        await _send(ws, "emotion.update", _em_msg)

    # ── Real-time score hint (L1-L8) — every 3rd message to avoid spam ──
    msg_count = state.get("message_count", 0)
    if msg_count > 0 and msg_count % 3 == 0:
        try:
            async with async_session() as db:
                rt_scores = await calculate_realtime_scores(session_id, db)
            await _send(ws, "score.hint", rt_scores)
        except Exception:
            logger.debug("Real-time score hint failed for %s", session_id)

    # ── Coaching Whisper: contextual hint for the manager ──
    if state.get("whispers_enabled", True):
        try:
            from app.services.whisper_engine import WhisperEngine
            from app.core.redis_pool import get_redis as _get_redis_wh
            _r_wh = _get_redis_wh()
            _whisper_engine = WhisperEngine(redis_client=_r_wh)
            _whisper = await _whisper_engine.generate_whisper(
                session_id=str(session_id),
                current_stage=state.get("current_stage_name", "greeting"),
                client_emotion=new_emotion,
                last_client_message=clean_content,  # AI client's response
                last_manager_message=messages[-1]["content"] if messages else "",
                manager_message_count=msg_count,
                difficulty=state.get("base_difficulty", 5),
                whispers_enabled=state.get("whispers_enabled", True),
            )
            if _whisper:
                await _send(ws, "whisper.coaching", _whisper)

                # Fire async RAG enrichment for legal whispers (non-blocking)
                if _whisper.get("type") == "legal":
                    async def _enrich_legal():
                        enriched = await _whisper_engine.generate_legal_enrichment(
                            query=clean_content,
                            session_id=str(session_id),
                            current_stage=state.get("current_stage_name", "greeting"),
                        )
                        if enriched:
                            try:
                                await _send(ws, "whisper.coaching", enriched)
                            except Exception as e:
                                logger.debug("Failed to send whisper coaching for session %s: %s", session_id, e)
                    _t = asyncio.create_task(_enrich_legal())
                    _bg_tasks.append(_t)
        except Exception:
            logger.debug("Whisper engine failed for session %s", session_id, exc_info=True)

    # ── Adaptive difficulty: process reply + send difficulty.update ──
    try:
        from app.core.redis_pool import get_redis as _get_redis_ad
        _r_ad = _get_redis_ad()
        adapter = IntraSessionAdapter(_r_ad)
        base_diff = state.get("base_difficulty", 5)

        # Determine reply quality from realtime scores
        try:
            async with async_session() as ad_db:
                _ad_scores = await calculate_realtime_scores(session_id, ad_db)
            estimate = _ad_scores.get("realtime_estimate", 0)

            if estimate >= 35:
                quality = ReplyQuality.GOOD
            elif estimate >= 20:
                quality = ReplyQuality.NEUTRAL
            else:
                quality = ReplyQuality.BAD
        except Exception:
            quality = ReplyQuality.NEUTRAL  # Fallback if scoring fails

        action = await adapter.process_reply(str(session_id), quality, base_diff)
        ad_state = await adapter.get_state(str(session_id))

        # Send difficulty.update to frontend
        await _send(ws, "difficulty.update", adapter.build_ws_payload(ad_state, base_diff))

        # Check if adaptive difficulty triggers hangup (bad_streak >= 15 + mercy failed)
        if adapter.should_hangup(ad_state) and new_emotion != "hangup":
            logger.info(
                "Adaptive difficulty triggered hangup | session=%s | bad_streak=%d",
                session_id, ad_state.bad_streak,
            )
    except Exception:
        logger.debug("Adaptive difficulty failed for session %s", session_id)


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
            # 30s — avatar says emotion-aware silence prompt
            _cur_emotion = await get_emotion(session_id) if session_id else "cold"
            _silence_count = state.get("_silence_count", 0)
            phrase = _pick_silence_phrase(str(_cur_emotion), _silence_count)
            state["_silence_count"] = _silence_count + 1
            # Send both silence.warning (for UI indicator) and character.response (for chat)
            await _send(ws, "silence.warning", {
                "content": phrase,
                "seconds_silent": int(elapsed),
            })
            await _send(ws, "character.response", {
                "content": phrase,
                "emotion": str(_cur_emotion),
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
                except TTSError as e:
                    logger.debug("TTS failed for hangup phrase, session %s: %s", session_id, e)
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
        # Check which checkpoints are not yet reached (reads from Redis, written by _send_score_update)
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
                # Find first un-hit checkpoint from persisted data
                for cp in progress.get("checkpoints", []):
                    if not cp.get("hit", False):
                        checkpoint_name = cp.get("title", cp.get("name", "Следующий этап"))
                        checkpoint_status = "not_reached"
                        break
                else:
                    # All checkpoints hit
                    checkpoint_status = "in_progress"
                    checkpoint_name = "Все чекпоинты пройдены"
        except Exception as e:
            logger.debug("Checkpoint hint lookup failed for session %s: %s", session_id, e)

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

            # Apply deferred starting emotion from story.next_call (e.g. hostile after hangup)
            _deferred_em = state.get("_deferred_start_emotion")
            if _deferred_em:
                initial_emotion = _deferred_em
                state.pop("_deferred_start_emotion", None)

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
            state["matched_checkpoints"] = set()  # Accumulation set for checkpoint IDs

            # Fallback: generate virtual checkpoints from template when no script_id
            state["template_checkpoints"] = None
            if scenario and not scenario.script_id and scenario.template_id:
                try:
                    from app.models.scenario import ScenarioTemplate
                    tmpl_result = await db.execute(
                        select(ScenarioTemplate).where(ScenarioTemplate.id == scenario.template_id)
                    )
                    tmpl = tmpl_result.scalar_one_or_none()
                    if tmpl and tmpl.stages:
                        from app.services.script_checker import generate_checkpoints_from_template
                        state["template_checkpoints"] = generate_checkpoints_from_template(tmpl.stages)
                except Exception:
                    logger.debug("Failed to generate template checkpoints for story session %s", session.id, exc_info=True)

            state["character_prompt_path"] = character.prompt_path if character else None
            state["archetype_code"] = effective_archetype
            state["client_profile_prompt"] = ""
            state["active"] = True
            state["stt_failure_count"] = 0
            state["custom_params"] = custom_params
            state["base_difficulty"] = custom_difficulty or (scenario.difficulty if scenario else 5)

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

        # ── Init stage tracker for resumed session ──
        try:
            from app.core.redis_pool import get_redis as _get_redis_stage_r
            r_stage = _get_redis_stage_r()
            stage_tracker = StageTracker(str(session.id), r_stage)
            existing_stage = await stage_tracker.get_state()
            if existing_stage.current_stage == 1 and not existing_stage.stages_completed:
                # First time — initialize
                existing_stage = await stage_tracker.init_state()
            await _send(ws, "stage.update", stage_tracker.build_ws_payload(existing_stage))
        except Exception:
            logger.debug("Stage tracker init failed for resumed session %s", session.id)

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
        scenario = await _resolve_scenario(db, scenario_id)
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
    state["matched_checkpoints"] = set()  # Accumulation set for checkpoint IDs

    # Fallback: generate virtual checkpoints from template stages when no script_id
    state["template_checkpoints"] = None
    if not scenario.script_id and scenario.template_id:
        try:
            from app.models.scenario import ScenarioTemplate
            async with async_session() as _db_tmpl:
                tmpl_result = await _db_tmpl.execute(
                    select(ScenarioTemplate).where(ScenarioTemplate.id == scenario.template_id)
                )
                tmpl = tmpl_result.scalar_one_or_none()
            if tmpl and tmpl.stages:
                from app.services.script_checker import generate_checkpoints_from_template
                state["template_checkpoints"] = generate_checkpoints_from_template(tmpl.stages)
                logger.info("Generated %d template checkpoints for session %s (no script_id)",
                            len(state["template_checkpoints"]), session.id)
        except Exception:
            logger.debug("Failed to generate template checkpoints for session %s", session.id, exc_info=True)

    state["character_prompt_path"] = character.prompt_path if character else None
    state["archetype_code"] = custom_archetype or (character.slug if character else None)
    state["client_profile_prompt"] = client_profile_prompt
    state["client_name"] = client_card.get("full_name", "") if client_card else ""
    state["client_gender"] = client_gender
    state["active_traps"] = active_traps  # Always defined above (line 1807 or [] in except block)
    state["last_character_message"] = ""
    state["fake_transition_prompt"] = ""
    state["active"] = True
    state["stt_failure_count"] = 0
    state["custom_params"] = custom_params
    state["base_difficulty"] = custom_difficulty or scenario.difficulty

    # Whisper coaching: enabled by default for lower levels, disabled for experienced managers
    _user_prefs = state.get("user_prefs", {})
    _whisper_pref = _user_prefs.get("whispers_enabled")
    if _whisper_pref is not None:
        state["whispers_enabled"] = bool(_whisper_pref)
    else:
        # Default: enabled for levels 1-5, disabled for 6+
        try:
            from app.models.progress import ManagerProgress
            async with async_session() as _db_wp:
                _mp_result = await _db_wp.execute(
                    select(ManagerProgress.current_level).where(ManagerProgress.user_id == user_id)
                )
                _level = _mp_result.scalar() or 1
            state["whispers_enabled"] = _level <= 5
        except Exception:
            state["whispers_enabled"] = True

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

    # ── Init stage tracker ──
    try:
        from app.core.redis_pool import get_redis as _get_redis_stage
        r_stage = _get_redis_stage()
        stage_tracker = StageTracker(str(session.id), r_stage)
        init_stage = await stage_tracker.init_state()
        await _send(ws, "stage.update", stage_tracker.build_ws_payload(init_stage))
    except Exception:
        logger.debug("Stage tracker init failed for session %s", session.id)


async def _handle_deepgram_streaming(
    ws: WebSocket,
    audio_bytes: bytes,
    state: dict,
    session_id,
    is_final: bool,
) -> "STTResult | None":
    """Handle audio via Deepgram streaming STT.

    Sends audio chunks to Deepgram WebSocket in real-time. Returns:
    - None if this was an interim chunk (interim result sent to client)
    - STTResult if this was the final chunk and we have a complete transcript
    - None with error sent if all STT failed

    Falls back to batch transcription (Whisper) if streaming is unavailable.
    """
    from app.services.stt import STTResult

    dg: DeepgramStreamingSTT | None = state.get("deepgram_stt")

    # Lazily initialize Deepgram streaming connection
    if dg is None:
        dg = DeepgramStreamingSTT()
        connected = await dg.start_stream(
            language=settings.deepgram_language,
            model=settings.deepgram_model,
        )
        if connected:
            state["deepgram_stt"] = dg
            logger.info("Deepgram streaming STT started for session %s", session_id)
        else:
            # WS unavailable — try REST fallback for this chunk
            logger.info(
                "Deepgram streaming unavailable for session %s — using batch fallback",
                session_id,
            )
            state["deepgram_stt"] = None
            try:
                from app.services.stt_deepgram import transcribe_with_fallback
                result = await transcribe_with_fallback(audio_bytes)
                state["stt_failure_count"] = 0
                return result
            except STTError as e:
                state["stt_failure_count"] = state.get("stt_failure_count", 0) + 1
                logger.warning("Deepgram batch fallback failed for %s: %s", session_id, e)
                # Final fallback: Whisper
                try:
                    result = await transcribe_audio(audio_bytes)
                    state["stt_failure_count"] = 0
                    return result
                except STTError as e2:
                    _count = state["stt_failure_count"]
                    if _count >= MAX_STT_FAILURES:
                        await _send(ws, "stt.error", {
                            "message": "Не удаётся распознать речь. Проверьте микрофон или используйте текстовый ввод.",
                            "failure_count": _count,
                            "suggest_text_input": True,
                        })
                    else:
                        await _send(ws, "stt.unavailable", {
                            "message": "Не удалось распознать. Попробуйте ещё раз.",
                            "failure_count": _count,
                        })
                    return None

    # Send audio chunk to Deepgram WebSocket
    try:
        await dg.send_audio(audio_bytes)
    except STTError:
        # Connection lost — close and retry via batch
        logger.warning("Deepgram WS lost for session %s — falling back to batch", session_id)
        await dg.close()
        state["deepgram_stt"] = None
        try:
            from app.services.stt_deepgram import transcribe_with_fallback
            result = await transcribe_with_fallback(audio_bytes)
            state["stt_failure_count"] = 0
            return result
        except STTError:
            try:
                result = await transcribe_audio(audio_bytes)
                state["stt_failure_count"] = 0
                return result
            except STTError as e:
                state["stt_failure_count"] = state.get("stt_failure_count", 0) + 1
                await _send(ws, "stt.unavailable", {
                    "message": "Не удалось распознать. Попробуйте ещё раз.",
                    "failure_count": state["stt_failure_count"],
                })
                return None

    # Get latest transcript (interim or final)
    transcript = await dg.get_transcript()

    if transcript.text and not is_final:
        # Send interim result for real-time feedback (UI shows partial text)
        await _send(ws, "transcription.interim", {
            "text": transcript.text,
            "confidence": round(transcript.confidence, 3),
            "is_final": False,
        })
        return None  # Not final yet — wait for more chunks

    if is_final:
        # Finalize: get complete result and close/reset the stream
        stt_result = await dg.get_final_result()
        dg.reset()
        state["stt_failure_count"] = 0

        if not stt_result.text.strip():
            # Empty result — try batch fallback with full audio
            logger.debug("Deepgram streaming returned empty — trying batch for session %s", session_id)
            try:
                from app.services.stt_deepgram import transcribe_with_fallback
                stt_result = await transcribe_with_fallback(audio_bytes)
            except STTError as e:
                logger.debug("STT batch fallback also failed for session %s: %s", session_id, e)

        return stt_result

    # No text yet, not final — still accumulating
    return None


async def _handle_audio_chunk(
    ws: WebSocket,
    data: dict,
    state: dict,
) -> None:
    """Handle audio.chunk: forward to STT, return transcription.

    If stt_provider == "deepgram" and streaming is available:
    - Sends raw audio chunks directly to Deepgram WebSocket
    - Sends interim transcription results for real-time UI feedback
    - On audio.end (is_final=True), finalizes and processes the result

    Otherwise falls back to batch Whisper transcription.
    """
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

    is_final = data.get("is_final", False)

    # ── Deepgram streaming path ──
    if settings.stt_provider == "deepgram" and settings.deepgram_api_key:
        stt_result = await _handle_deepgram_streaming(
            ws, audio_bytes, state, session_id, is_final,
        )
        if stt_result is None:
            # Interim chunk sent — no final result yet, or error handled
            return
    else:
        # ── Whisper batch path (original) ──
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
        _saved_msg = await add_message(
            session_id=session_id,
            role=MessageRole.user,
            content=stt_result.text,
            db=db,
            audio_duration_ms=stt_result.duration_ms,
            stt_confidence=stt_result.confidence,
            emotion_state=current_emotion,
        )
        state["message_count"] = _saved_msg.sequence_number
        await db.commit()

    # ── WPM (words per minute) tracking ──
    try:
        word_count = len(stt_result.text.split())
        duration_sec = (stt_result.duration_ms or 0) / 1000.0
        wpm = round(word_count / max(duration_sec / 60, 0.01)) if duration_sec > 0 else 0

        # Accumulate in state for session-level analytics
        wpm_history: list = state.setdefault("wpm_history", [])
        wpm_history.append(wpm)
        state["total_user_words"] = state.get("total_user_words", 0) + word_count
        state["total_user_speech_ms"] = state.get("total_user_speech_ms", 0) + (stt_result.duration_ms or 0)

        # Calculate session average WPM
        avg_wpm = round(sum(wpm_history) / len(wpm_history)) if wpm_history else 0

        # Send speech analytics to frontend
        await _send(ws, "speech.analytics", {
            "wpm": wpm,
            "avg_wpm": avg_wpm,
            "word_count": word_count,
            "total_words": state["total_user_words"],
            "total_speech_ms": state["total_user_speech_ms"],
        })
    except Exception as e:
        logger.debug("Speech analytics failed for session %s: %s", session_id, e)

    # Check traps and update script score before generating character reply
    await _check_traps_after_user_message(ws, session_id, stt_result.text, state)
    await _send_score_update(ws, session_id, stt_result.text, state)

    # ── Stage tracking: detect stage by content (audio path) ──
    try:
        from app.core.redis_pool import get_redis as _get_redis_sta
        r_sta = _get_redis_sta()
        st = StageTracker(str(session_id), r_sta)
        msg_count = state.get("message_count", 0)
        stage_state, stage_changed, skipped = await st.process_message(stt_result.text, msg_count, "user")
        if stage_changed:
            await _send(ws, "stage.update", st.build_ws_payload(stage_state))
        if skipped:
            # Track cumulative skips for escalating frustration
            state["cumulative_skips"] = state.get("cumulative_skips", 0) + len(skipped)
            reactions = st.get_skip_reactions(stage_state, skipped)
            if reactions:
                state["_pending_skip_reactions"] = reactions
    except Exception:
        logger.debug("Stage tracking failed for session %s (audio)", session_id, exc_info=True)

    # Generate character response
    await _generate_character_reply(ws, session_id, state)


async def _handle_audio_end(
    ws: WebSocket,
    data: dict,
    state: dict,
) -> None:
    """Handle audio.end: process complete audio recording.

    For Deepgram streaming: signals is_final=True to finalize the transcript.
    For Whisper batch: same as audio.chunk (processes full recording).
    """
    # Mark as final so Deepgram streaming path finalizes the transcript
    data["is_final"] = True
    await _handle_audio_chunk(ws, data, state)


async def _send_score_update(
    ws: WebSocket,
    session_id: uuid.UUID,
    user_text: str,
    state: dict,
) -> None:
    """Check script checkpoint progress and send score.update to frontend.

    Called after each user message. Uses accumulation: previously matched
    checkpoints are preserved, only remaining ones are checked against
    the current message.

    Writes progress to Redis for hint_scheduler and WS reconnect persistence.
    Sends new_checkpoint field when a checkpoint is newly matched.
    """
    script_id = state.get("script_id")
    template_checkpoints = state.get("template_checkpoints")

    if not script_id and not template_checkpoints:
        return

    try:
        # Get or initialize accumulation set
        matched_ids: set[str] = state.get("matched_checkpoints", set())

        if script_id:
            # Primary path: script with DB checkpoints
            from app.services.script_checker import check_checkpoints_with_accumulation

            all_results, new_matches = await check_checkpoints_with_accumulation(
                user_text=user_text,
                script_id=script_id,
                already_matched=matched_ids,
            )
        elif template_checkpoints:
            # Fallback path: virtual checkpoints from ScenarioTemplate stages
            from app.services.script_checker import (
                _get_similarity, _keyword_similarity,
                SIMILARITY_THRESHOLD, KEYWORD_THRESHOLD,
            )
            remaining = [cp for cp in template_checkpoints if cp["checkpoint_id"] not in matched_ids]
            new_matches = []
            for cp in remaining:
                score = await _get_similarity(user_text, cp["description"])
                if score is not None:
                    matched = score >= SIMILARITY_THRESHOLD
                else:
                    score = _keyword_similarity(user_text, cp["keywords"])
                    matched = score >= KEYWORD_THRESHOLD
                if matched:
                    new_matches.append({
                        "checkpoint_id": cp["checkpoint_id"],
                        "title": cp["title"],
                        "order_index": cp["order_index"],
                        "score": round(score, 3),
                        "matched": True,
                        "weight": cp["weight"],
                    })

            all_matched_ids = matched_ids | {m["checkpoint_id"] for m in new_matches}
            all_results = []
            for cp in template_checkpoints:
                nm = next((m for m in new_matches if m["checkpoint_id"] == cp["checkpoint_id"]), None)
                all_results.append({
                    "checkpoint_id": cp["checkpoint_id"],
                    "title": cp["title"],
                    "order_index": cp["order_index"],
                    "score": nm["score"] if nm else (1.0 if cp["checkpoint_id"] in all_matched_ids else 0.0),
                    "matched": cp["checkpoint_id"] in all_matched_ids,
                    "weight": cp["weight"],
                })
            all_results.sort(key=lambda x: x["order_index"])
        else:
            return

        if not all_results:
            return

        # Update accumulation set in state
        if new_matches:
            for nm in new_matches:
                matched_ids.add(nm["checkpoint_id"])
            state["matched_checkpoints"] = matched_ids

        total = len(all_results)
        hit = sum(1 for r in all_results if r["matched"])

        # Calculate weighted progress percentage
        total_weight = sum(r.get("weight", 1.0) for r in all_results)
        hit_weight = sum(r.get("weight", 1.0) for r in all_results if r["matched"])
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
            for r in all_results
        ]

        payload: dict = {
            "script_score": round(progress, 1),
            "checkpoints_hit": hit,
            "checkpoints_total": total,
            "checkpoints": checkpoints,
            "is_preliminary": True,
        }

        # Add new_checkpoint field for frontend toast/flash
        if new_matches:
            payload["new_checkpoint"] = new_matches[0]["title"]

        await _send(ws, "score.update", payload)

        # Persist progress to Redis for hint_scheduler and WS reconnect
        try:
            from app.core.redis_pool import get_redis as _get_redis_score
            r = _get_redis_score()
            await r.set(
                f"session:{session_id}:script_progress",
                json.dumps({"checkpoints": checkpoints, "matched_ids": list(matched_ids)}),
                ex=7200,
            )
        except Exception:
            logger.debug("Failed to persist checkpoint progress to Redis for %s", session_id)

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
        from app.services.trap_detector import detect_traps, get_emotion_triggers

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

        # ── Extract emotion triggers from trap results for the emotion engine ──
        trap_triggers = get_emotion_triggers(results)
        if trap_triggers:
            state["_trap_emotion_triggers"] = [t["trigger"] for t in trap_triggers]
            logger.debug(
                "Trap emotion triggers for session %s: %s",
                session_id,
                [t["trigger"] for t in trap_triggers],
            )

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

    # ── Security: filter user input for jailbreak / profanity / PII ──
    from app.services.content_filter import filter_user_input
    content, input_violations = filter_user_input(content)
    if "jailbreak_attempt" in input_violations:
        logger.warning("Jailbreak attempt in session %s", session_id)

    try:
        await check_message_limit(session_id)
    except RateLimitError as e:
        await _send_error(ws, str(e), "rate_limit")
        return

    current_emotion = await get_emotion(session_id)

    async with async_session() as db:
        _saved_msg = await add_message(
            session_id=session_id,
            role=MessageRole.user,
            content=content,
            db=db,
            emotion_state=current_emotion,
        )
        state["message_count"] = _saved_msg.sequence_number
        await db.commit()

    # Check traps and update script score before generating character reply
    await _check_traps_after_user_message(ws, session_id, content, state)
    await _send_score_update(ws, session_id, content, state)

    # ── Stage tracking: detect stage by content ──
    try:
        from app.core.redis_pool import get_redis as _get_redis_st
        r_st = _get_redis_st()
        st = StageTracker(str(session_id), r_st)
        msg_count = state.get("message_count", 0)
        stage_state, stage_changed, skipped = await st.process_message(content, msg_count, "user")
        if stage_changed:
            await _send(ws, "stage.update", st.build_ws_payload(stage_state))
        if skipped:
            state["cumulative_skips"] = state.get("cumulative_skips", 0) + len(skipped)
            reactions = st.get_skip_reactions(stage_state, skipped)
            if reactions:
                state["_pending_skip_reactions"] = reactions
    except Exception:
        logger.debug("Stage tracking failed for session %s", session_id, exc_info=True)

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

    # Save call_outcome + promises to session before scoring so L5/L9 can read it
    call_outcome = state.get("call_outcome")
    try:
        async with async_session() as pre_db:
            pre_session = await pre_db.get(TrainingSession, session_id)
            if pre_session:
                existing = pre_session.scoring_details or {}
                if call_outcome:
                    existing["call_outcome"] = call_outcome

                # ── 3.2: Inject CRM promises from game_director Tier 2 memory ──
                if pre_session.client_story_id:
                    try:
                        from app.models.roleplay import ClientStory
                        story_result = await pre_db.execute(
                            select(ClientStory).where(ClientStory.id == pre_session.client_story_id)
                        )
                        story = story_result.scalar_one_or_none()
                        if story:
                            promises = (story.memory or {}).get("promises", [])
                            if promises:
                                existing["_promises"] = promises[-10:]  # Last 10 promises
                                # Count kept vs broken for L9
                                kept = sum(1 for p in promises if p.get("fulfilled"))
                                broken = sum(1 for p in promises if not p.get("fulfilled") and p.get("text"))
                                existing["_promise_stats"] = {
                                    "kept": kept,
                                    "broken": broken,
                                    "total": len(promises),
                                }
                    except Exception:
                        logger.debug("Failed to load promises for session %s", session_id)

                pre_session.scoring_details = existing
                await pre_db.commit()
    except Exception:
        logger.debug("Failed to save pre-scoring metadata for %s", session_id)

    scores = None
    try:
        async with async_session() as db:
            scores = await calculate_scores(session_id, db)
    except Exception:
        logger.exception("Failed to calculate scores for session %s", session_id)

    # ── Save emotion journey snapshot BEFORE cleanup (end_session deletes Redis) ──
    _emotion_journey: dict = {}
    try:
        _emotion_journey = await save_journey_snapshot(session_id)
    except Exception:
        logger.debug("Failed to save emotion journey snapshot for %s", session_id)

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

            # ── Store emotion journey snapshot (captured before Redis cleanup) ──
            if _emotion_journey and _emotion_journey.get("timeline"):
                enriched_details["_emotion_journey"] = _emotion_journey

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

            # ── Save stage tracking data ──
            try:
                from app.core.redis_pool import get_redis as _get_redis_stc
                r_stc = _get_redis_stc()
                st_cleanup = StageTracker(str(session_id), r_stc)
                final_stage = await st_cleanup.cleanup()
                enriched_details["_stage_progress"] = st_cleanup.build_scoring_details(final_stage)
            except Exception:
                logger.debug("Stage tracker cleanup failed for session %s", session_id)

            # ── Save session difficulty for AI-Coach frontend ──
            _base_diff = state.get("base_difficulty", 5)
            enriched_details["_session_difficulty"] = _base_diff

            # ── Generate AI-Coach report (cited_moments, stage_analysis, patterns) ──
            try:
                _messages = await get_message_history(session_id)
                _msg_list = [{"role": m["role"], "content": m["content"]} for m in _messages]

                _coach_weak_points = None
                try:
                    from app.services.manager_progress import ManagerProgressService
                    _mp_svc = ManagerProgressService(db)
                    _wp_data = await _mp_svc.get_weak_points(state.get("user_id"))
                    _coach_weak_points = [w.get("skill", "") for w in _wp_data] if _wp_data else None
                except Exception as e:
                    logger.debug("Failed to load manager weak points for session %s: %s", session_id, e)

                # Enrich weak points with RAG feedback data (legal-specific)
                try:
                    from app.services.rag_feedback import get_user_weak_areas
                    _rag_weak = await get_user_weak_areas(db, state["user_id"], days=30)
                    if _rag_weak:
                        _legal_weak = [
                            f"юр.знания:{w['category']} (ошибок {w['error_rate']*100:.0f}%)"
                            for w in _rag_weak[:3] if w.get("error_rate", 0) > 0.3
                        ]
                        if _legal_weak:
                            _coach_weak_points = (_coach_weak_points or []) + _legal_weak
                except Exception as e:
                    logger.debug("Failed to load RAG feedback weak areas for session %s: %s", session_id, e)

                _coach_report = await generate_session_report(
                    messages=_msg_list,
                    config=SessionConfig(
                        scenario_code=state.get("scenario_code", "unknown"),
                        scenario_name=state.get("scenario_name", "Тренировка"),
                        template_id=uuid.uuid4(),
                        archetype=state.get("archetype_code", "skeptic"),
                        initial_emotion="cold",
                        client_awareness="low",
                        client_motivation="none",
                        difficulty=_base_diff,
                    ),
                    score_breakdown=enriched_details,
                    trap_results=enriched_details.get("trap_handling", {}).get("traps"),
                    emotion_trajectory=session.emotion_timeline,
                    stage_progress=enriched_details.get("_stage_progress"),
                    manager_weak_points=_coach_weak_points,
                )

                # Merge coach report fields into scoring_details
                for _field in ("cited_moments", "stage_analysis", "historical_patterns"):
                    if _coach_report.get(_field):
                        enriched_details[f"_{_field}"] = _coach_report[_field]

                # Save feedback_text from report summary
                if _coach_report.get("summary") and not session.feedback_text:
                    _parts = []
                    if _coach_report.get("summary"):
                        _parts.append(f"## Резюме\n{_coach_report['summary']}")
                    if _coach_report.get("strengths"):
                        _parts.append("## Сильные стороны\n" + "\n".join(f"- {s}" for s in _coach_report["strengths"]))
                    if _coach_report.get("weaknesses"):
                        _parts.append("## Слабые стороны\n" + "\n".join(f"- {w}" for w in _coach_report["weaknesses"]))
                    if _coach_report.get("recommendations"):
                        _parts.append("## Рекомендации\n" + "\n".join(f"- {r}" for r in _coach_report["recommendations"]))
                    session.feedback_text = "\n\n".join(_parts)

            except Exception:
                logger.debug("AI-Coach report generation failed for session %s", session_id, exc_info=True)

            # ── Generate per-layer explanations (Task 2.1) ──
            try:
                _msg_result = await db.execute(
                    select(Message)
                    .where(Message.session_id == session_id)
                    .order_by(Message.sequence_number)
                )
                _all_msgs = _msg_result.scalars().all()
                _indexed_msgs = [
                    {"role": m.role.value, "content": m.content, "index": i}
                    for i, m in enumerate(_all_msgs)
                ]
                _explanations = generate_layer_explanations(scores, _indexed_msgs)
                enriched_details["_layer_explanations"] = layer_explanations_to_dict(_explanations)
            except Exception:
                logger.debug("Layer explanations generation failed for session %s", session_id, exc_info=True)

            session.scoring_details = enriched_details

            # ── RAG Feedback Loop: capture legal validation outcomes ──
            try:
                from app.services.rag_feedback import record_training_feedback
                legal_data = enriched_details.get("legal_accuracy", {})
                vector_checks = legal_data.get("vector", {}).get("vector_checks", [])
                if vector_checks and state.get("user_id"):
                    validation_results = []
                    for vc in vector_checks:
                        chunk_id = vc.get("chunk_id")
                        if not chunk_id:
                            continue
                        is_error = vc.get("type") == "error"
                        validation_results.append({
                            "chunk_id": chunk_id,
                            "accuracy": "incorrect" if is_error else "correct",
                            "manager_statement": vc.get("fact", "")[:200],
                            "score_delta": -2.0 if is_error else 0.5,
                            "explanation": vc.get("matched_error", ""),
                        })
                    if validation_results:
                        await record_training_feedback(
                            db,
                            session_id=session_id,
                            user_id=state["user_id"],
                            validation_results=validation_results,
                        )
            except Exception:
                logger.debug("RAG feedback capture failed for session %s", session_id, exc_info=True)

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

    # ── Auto-complete assigned training if this session matches one ──
    try:
        from app.models.training import AssignedTraining
        from datetime import datetime, timezone as _tz
        async with async_session() as _at_db:
            _at_result = await _at_db.execute(
                select(AssignedTraining).where(
                    AssignedTraining.user_id == state.get("user_id"),
                    AssignedTraining.scenario_id == state.get("scenario_id"),
                    AssignedTraining.completed_at.is_(None),
                ).limit(1)
            )
            _at = _at_result.scalar_one_or_none()
            if _at:
                _at.completed_at = datetime.now(_tz.utc)
                await _at_db.commit()
                logger.info("Auto-completed assignment %s for user %s", _at.id, state.get("user_id"))
                # Notify the ROP who assigned it
                try:
                    from app.ws.notifications import send_ws_notification
                    await send_ws_notification(
                        _at.assigned_by,
                        event_type="training.completed",
                        data={
                            "assignment_id": str(_at.id),
                            "user_id": str(state.get("user_id")),
                            "scenario_id": str(state.get("scenario_id")),
                            "score": scores.total if scores else None,
                        },
                    )
                except Exception as e:
                    logger.debug("Failed to send assignment completion notification for session %s: %s", session_id, e)
    except Exception:
        logger.debug("Auto-complete assignment check failed for session %s", session_id)

    # ── GAP-1 fix: Update ManagerProgress (XP, level, skills) ──
    mp_result: dict | None = None
    try:
        from app.services.manager_progress import ManagerProgressService
        from app.models.progress import SessionHistory
        _uid = state.get("user_id")
        if _uid and scores and session:
            async with async_session() as mp_db:
                # Create SessionHistory record
                _trap_details = (scores.details or {}).get("trap_handling", {})
                sh = SessionHistory(
                    user_id=_uid,
                    session_id=session.id,
                    scenario_code=state.get("scenario_code", "unknown"),
                    archetype_code=state.get("archetype_code", "unknown"),
                    difficulty=state.get("base_difficulty", 5),
                    duration_seconds=session.duration_seconds or 0,
                    score_total=int(scores.total or 0),
                    outcome=state.get("call_outcome", "timeout"),
                    score_breakdown={
                        "script_adherence": scores.script_adherence,
                        "objection_handling": scores.objection_handling,
                        "communication": scores.communication,
                        "anti_patterns": scores.anti_patterns,
                        "result": scores.result,
                        "chain_traversal": scores.chain_traversal,
                        "trap_handling": scores.trap_handling,
                    },
                    emotion_peak=state.get("emotion_peak", "cold"),
                    traps_fell=_trap_details.get("fell_count", 0),
                    traps_dodged=_trap_details.get("dodged_count", 0),
                    chain_completed=bool((scores.details or {}).get("chain_completed")),
                    had_comeback=bool(state.get("had_comeback")),
                )
                mp_db.add(sh)
                await mp_db.flush()

                svc = ManagerProgressService(mp_db)
                mp_result = await svc.update_after_session(_uid, sh)

                sh.xp_earned = mp_result.get("xp_breakdown", {}).get("grand_total", 0)
                sh.xp_breakdown = mp_result.get("xp_breakdown", {})
                await mp_db.commit()

                logger.info(
                    "ManagerProgress updated: user=%s xp=+%d level_up=%s",
                    _uid, sh.xp_earned, mp_result.get("level_up"),
                )
    except Exception as e:
        logger.warning("Failed to update ManagerProgress after session: %s", e)

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
        # Include XP/level data from ManagerProgress update
        if mp_result:
            result_data["xp_breakdown"] = mp_result.get("xp_breakdown", {})
            result_data["level_up"] = mp_result.get("level_up", False)
            result_data["new_level"] = mp_result.get("new_level")
            result_data["new_level_name"] = mp_result.get("new_level_name")

    # --- Behavioral Intelligence hooks ---
    try:
        from app.services.behavior_tracker import analyze_session_behavior, save_behavior_snapshot
        from app.services.manager_emotion_profiler import update_emotion_profile

        user_id = state.get("user_id")
        if user_id and session_id:
            async with async_session() as db_beh:
                # Fetch manager messages from this session
                from app.models.training import Message
                msg_result = await db_beh.execute(
                    select(Message)
                    .where(Message.session_id == session_id, Message.role == "user")
                    .order_by(Message.sequence_number)
                )
                user_messages = msg_result.scalars().all()

                messages_for_behavior = [
                    {
                        "role": "user",
                        "content": m.content or "",
                        "response_time_ms": getattr(m, "audio_duration_ms", None),
                        "sequence": m.sequence_number or 0,
                    }
                    for m in user_messages if m.content
                ]

                # Get emotion transitions from Redis session state
                emotion_transitions = state.get("emotion_timeline", [])

                if messages_for_behavior:
                    analysis = analyze_session_behavior(
                        user_id=uuid.UUID(str(user_id)),
                        session_id=uuid.UUID(str(session_id)),
                        session_type="training",
                        messages=messages_for_behavior,
                        emotion_transitions=emotion_transitions,
                    )
                    snapshot = await save_behavior_snapshot(analysis, db_beh)

                    # Update emotion profile with training context
                    await update_emotion_profile(
                        user_id=uuid.UUID(str(user_id)),
                        db=db_beh,
                        session_snapshot=snapshot,
                        session_score=scores.total if scores else None,
                        archetype=state.get("archetype_code"),
                        emotion_peak=state.get("emotion_peak"),
                    )
                    await db_beh.commit()

                    logger.info(
                        "Training behavioral hooks: user=%s confidence=%.0f stress=%.0f adaptability=%.0f",
                        user_id, analysis.confidence_score, analysis.stress_level, analysis.adaptability_score,
                    )
    except Exception as e:
        logger.warning("Behavioral hook error in training session end: %s", e, exc_info=True)

    # ── 3.4: Cross-module smart notifications after session ──
    try:
        from app.ws.notifications import send_typed_notification, NotificationType
        _user_id = state.get("user_id")
        if _user_id and scores:
            # Score record notification
            if scores.total and scores.total >= 85:
                await send_typed_notification(
                    str(_user_id),
                    NotificationType.TRAINING_SCORE_RECORD,
                    f"Отличный результат: {int(scores.total)} баллов!",
                    "Вы показали высокий уровень. Попробуйте отправить результат в турнир.",
                    action_url=f"/results/{session_id}",
                )

            # Weak legal knowledge → quiz nudge
            legal_score = (scores.details or {}).get("legal_accuracy", {}).get("combined_score", 5)
            if legal_score < 0:
                await send_typed_notification(
                    str(_user_id),
                    NotificationType.KNOWLEDGE_WEAK_AREA,
                    "Слабые знания ФЗ-127",
                    "Юридическая точность ниже нормы. Пройдите тест знаний для закрепления.",
                    action_url="/knowledge",
                )
    except Exception:
        logger.debug("Cross-module notification failed for session %s", session_id)

    # Emit EVENT_TRAINING_COMPLETED for EventBus handlers (achievements, goals, SRS)
    # Previously only the REST fallback endpoint did this — WS handler was missing it
    try:
        from app.services.event_bus import event_bus, GameEvent, EVENT_TRAINING_COMPLETED
        _uid = state.get("user_id")
        if _uid and scores:
            async with async_session() as evt_db:
                await event_bus.emit(GameEvent(
                    kind=EVENT_TRAINING_COMPLETED,
                    user_id=_uid,
                    db=evt_db,
                    payload={
                        "session_id": str(session_id),
                        "score": scores.total,
                        "scenario_id": str(state.get("scenario_id", "")),
                        "weak_legal_categories": (scores.details or {}).get("legal_accuracy", {}).get("weak_categories", []),
                    },
                ))
    except Exception as e:
        logger.warning("Failed to emit training_completed event: %s", e)

    # Generate AI recommendations (rule-based + LLM if available)
    try:
        from app.services.scoring import generate_recommendations
        if scores:
            async with async_session() as rec_db:
                feedback = await generate_recommendations(session_id, rec_db, scores)
                if feedback:
                    result_data["feedback_text"] = feedback
                    # Persist to session record
                    async with async_session() as upd_db:
                        from app.models.training import TrainingSession as TS
                        sess_rec = await upd_db.get(TS, session_id)
                        if sess_rec:
                            sess_rec.feedback_text = feedback
                            await upd_db.commit()
    except Exception as e:
        logger.warning("Failed to generate recommendations: %s", e)

    # ── Manager Wiki ingest (Karpathy pattern — async, non-blocking) ──
    try:
        _wiki_uid = state.get("user_id")
        if _wiki_uid and session_id:
            async def _wiki_ingest_task():
                try:
                    from app.services.wiki_ingest_service import ingest_session as wiki_ingest
                    async with async_session() as wiki_db:
                        await wiki_ingest(session_id, wiki_db)
                except Exception as _we:
                    logger.debug("Wiki ingest failed for session %s: %s", session_id, _we)
            asyncio.create_task(_wiki_ingest_task())
    except Exception:
        logger.debug("Failed to schedule wiki ingest for session %s", session_id)

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
        # Load scenario + character (checks both scenarios and scenario_templates)
        scenario = await _resolve_scenario(db, scenario_id)
        if not scenario:
            await _send_error(ws, "Scenario not found", "not_found")
            return

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

    # NOTE: Stage tracker reset is deferred to session.start — at this point
    # the new session hasn't been created yet, so there's no valid session_id.

    # ── Hangup recovery: apply penalties from previous call hangup ──
    previous_hangup = state.get("call_outcome") == "hangup"
    if previous_hangup:
        # Store desired starting emotion — will be applied after session.start
        # creates the new session (init_emotion needs a valid session_id).
        state["_deferred_start_emotion"] = "hostile"

        # Clear hangup state for this new call
        state.pop("call_outcome", None)
        state.pop("hangup_reason", None)

        # Inject hostile context into LLM system prompt for this call
        hangup_context = (
            "\n\n[CONTEXT: Клиент помнит неудачный предыдущий разговор. "
            "Начинай с враждебной позиции. Доверие снижено. "
            "Менеджер должен ВОССТАНОВИТЬ доверие прежде чем продолжать продажу. "
            "Если менеджер извинится и покажет уважение — можно постепенно смягчиться.]"
        )
        prev_prompt = state.get("client_profile_prompt", "")
        state["client_profile_prompt"] = prev_prompt + hangup_context

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
            relationship_score=state.get("relationship_score", 50.0),
            lifecycle_state=state.get("lifecycle_state", "FIRST_CONTACT"),
            active_storylets=state.get("active_storylets", []),
            consequence_log=state.get("consequence_log", []),
        )

        # ── Game Director: read between-call events already generated by advance_story ──
        # NOTE: advance_story() in _handle_story_call_end already created & persisted
        # between-call events. We READ them here instead of generating duplicates.
        gd_events = []
        try:
            from app.models.game_crm import GameClientEvent as _GCE
            async with async_session() as gd_db:
                _evt_result = await gd_db.execute(
                    select(_GCE)
                    .where(_GCE.story_id == story_id)
                    .where(_GCE.source == "game_director")
                    .order_by(_GCE.created_at.desc())
                    .limit(15)
                )
                gd_events = list(_evt_result.scalars().all())
        except Exception:
            logger.debug("Failed to read game director events for story %s", story_id)

        # Inject hangup event into between-call events if previous call was hangup
        if previous_hangup:
            hangup_event = {
                "event": "client_hangup",
                "impact": "trust-30",
                "description": (
                    "В прошлом звонке клиент бросил трубку. "
                    "Начальная эмоция: враждебная. Доверие снижено."
                ),
                "emotion_shift": {"N": 0.3, "P": -0.4, "A": 0.2},
            }
            between_events.insert(0, hangup_event)

        # Accumulate events
        all_events = existing_events + [
            {"after_call": current_call - 1, **evt} for evt in between_events
        ]
        state["between_call_events"] = all_events

        # ── Build frontend event list from all sources ──
        # Merge: scenario_engine events + game_director events (client msgs, storylets, consequences)
        frontend_events = []

        # 1. Scenario engine events (CRM/external)
        for evt in between_events:
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
                "source": "crm",
            })

        # 2. Game director events (client messages, storylet triggers, consequences)
        for gd_evt in gd_events:
            _evt_type_raw = getattr(gd_evt, "event_type", "unknown")
            # event_type may be a GameEventType enum — normalize to string
            _evt_type = _evt_type_raw.value if hasattr(_evt_type_raw, "value") else str(_evt_type_raw)
            _payload = getattr(gd_evt, "payload", {}) or {}
            _severity = getattr(gd_evt, "severity", None)
            if _severity is None:
                if _evt_type == "consequence":
                    _severity = 0.7
                elif _evt_type == "storylet":
                    _severity = _payload.get("priority", 5) / 10.0
            frontend_events.append({
                "event_type": _evt_type,
                "title": getattr(gd_evt, "title", "Событие"),
                "content": getattr(gd_evt, "content", ""),
                "severity": _severity,
                "source": "game_director",
                "payload": _payload,
            })

        # 3. Relationship trajectory indicator (if available from game director)
        _rel_score = state.get("relationship_score", 50.0)
        _lc_state = state.get("lifecycle_state", "FIRST_CONTACT")
        if current_call > 1:
            frontend_events.append({
                "event_type": "status_indicator",
                "title": "Статус отношений",
                "content": f"Доверие: {_rel_score:.0f}/100 | Этап: {_lc_state}",
                "severity": None,
                "source": "system",
            })

        await _send(ws, "story.between_calls", {
            "story_id": str(story_id),
            "events": frontend_events,
            "relationship_score": _rel_score,
            "lifecycle_state": _lc_state,
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
    except Exception as e:
        logger.debug("Failed to load episodic memories for story %s: %s", story_id, e)

    # Extract client messages from game director events
    _client_msgs = []
    for e in gd_events:
        _et = getattr(e, "event_type", "")
        _et_str = _et.value if hasattr(_et, "value") else str(_et)
        if _et_str == "message":
            _client_msgs.append(getattr(e, "content", "") or "")

    # Load manager weak points for coaching section
    _mgr_weak_points = None
    try:
        from app.services.manager_progress import ManagerProgressService
        _uid = state.get("user_id")
        if _uid:
            async with async_session() as _wp_db:
                _wp_svc = ManagerProgressService(_wp_db)
                _wp_data = await _wp_svc.get_weak_points(_uid)
                _mgr_weak_points = [w.get("skill", "") for w in _wp_data] if _wp_data else None
    except Exception as e:
        logger.debug("Failed to load coaching weak points for pre-call brief: %s", e)

    pre_call_brief = generate_pre_call_brief(
        call_number=current_call,
        client_name=client_name,
        archetype_code=archetype_code,
        previous_outcome=state.get("last_call_outcome"),
        previous_emotion=state.get("last_call_emotion", "cold"),
        between_events=between_events,
        key_memories=key_memories,
        relationship_score=state.get("relationship_score", 50.0),
        lifecycle_state=state.get("lifecycle_state", "FIRST_CONTACT"),
        active_storylets=state.get("active_storylets", []),
        manager_weak_points=_mgr_weak_points,
        client_messages=_client_msgs,
    )

    state["pre_call_brief"] = pre_call_brief
    state["episodic_memories"] = key_memories

    # ── Tier 3: Inject situational context into LLM system prompt for this call ──
    # This gives the AI character awareness of between-call events, storylets,
    # and relationship state — so it can react intelligently to the story arc.
    if current_call > 1:
        tier3_parts = []

        # Between-call event awareness
        if between_events:
            _evt_summaries = [e.get("description", e.get("event", "")) for e in between_events]
            tier3_parts.append(
                "Между звонками произошло: " + "; ".join(_evt_summaries) + "."
            )

        # Active storylet awareness
        _storylet_hints = {
            "wife_found_out": "Жена клиента узнала о долгах. Клиент может упоминать семейное давление.",
            "collectors_arrived": "К клиенту приходили коллекторы. Клиент напуган и взволнован.",
            "friend_recommended_lawyer": "Другу клиента порекомендовали юриста. Клиент может сравнивать.",
            "court_order_received": "Клиент получил судебный приказ. Ситуация стала срочной.",
            "salary_garnishment": "Из зарплаты клиента удерживают средства. Финансовое давление растёт.",
            "positive_precedent": "Клиент узнал о успешном банкротстве знакомого. Настроен позитивнее.",
        }
        for s_code in state.get("active_storylets", []):
            hint = _storylet_hints.get(s_code)
            if hint:
                tier3_parts.append(hint)

        # Relationship-driven behavior instruction
        _rel = state.get("relationship_score", 50.0)
        if _rel < 30:
            tier3_parts.append(
                "Уровень доверия к менеджеру ОЧЕНЬ НИЗКИЙ. "
                "Будь скептичен, требуй доказательств, не соглашайся легко."
            )
        elif _rel < 50:
            tier3_parts.append(
                "Уровень доверия НИЖЕ СРЕДНЕГО. "
                "Будь осторожен, задавай уточняющие вопросы."
            )
        elif _rel > 75:
            tier3_parts.append(
                "Уровень доверия ВЫСОКИЙ. "
                "Можешь быть более открытым, задавать конкретные вопросы о процедуре."
            )

        # Client message context (what client "texted" between calls)
        if _client_msgs:
            tier3_parts.append(
                "Клиент написал между звонками: "
                + " | ".join(f'«{m}»' for m in _client_msgs[:2])
            )

        if tier3_parts:
            tier3_context = (
                "\n\n[BETWEEN-CALL CONTEXT (Tier 3 — situational awareness):\n"
                + "\n".join(f"- {p}" for p in tier3_parts)
                + "\nИспользуй этот контекст в реакциях, но не упоминай что тебе дали контекст.]"
            )
            prev_prompt = state.get("client_profile_prompt", "")
            state["client_profile_prompt"] = prev_prompt + tier3_context

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

    # ── Between-Call Intelligence: coaching, narrative, opener ──
    _narrator_data: dict = {}
    if current_call > 1:
        try:
            from app.services.between_call_narrator import (
                generate_between_call_content,
                NarratorContext,
            )
            _narrator_ctx = NarratorContext(
                lifecycle_state=state.get("lifecycle_state", "FIRST_CONTACT"),
                relationship_score=state.get("relationship_score", 50.0),
                call_number=current_call - 1,  # previous call number
                total_calls=total_calls,
                archetype_code=archetype_code,
                client_name=state.get("client_name", "Клиент"),
                last_outcome=state.get("last_call_outcome", "unknown"),
                last_emotion=state.get("last_call_emotion", "cold"),
                last_score=state.get("last_score_total", 0.0),
                key_memories=key_memories,
                active_storylets=state.get("active_storylets", []),
                active_consequences=state.get("accumulated_consequences", []),
                between_events=between_events,
                manager_weak_points=_mgr_weak_points or [],
            )
            _narrator_result = await generate_between_call_content(_narrator_ctx)
            _narrator_data = {
                "coaching_tips": _narrator_result.coaching_tips,
                "narrative_summary": _narrator_result.narrative_summary,
                "emotional_forecast": _narrator_result.emotional_forecast,
                "suggested_opener": _narrator_result.suggested_opener,
                "narrator_source": _narrator_result.source,
            }
            # If narrator generated a client message and game_director didn't,
            # add it to the between-call events
            if _narrator_result.client_message:
                _has_client_msg = any(
                    e.get("event_type") == "client_message"
                    for e in frontend_events
                )
                if not _has_client_msg:
                    frontend_events.append({
                        "event_type": "client_message",
                        "title": "Сообщение от клиента",
                        "content": _narrator_result.client_message,
                        "severity": 0.4,
                        "source": _narrator_result.source,
                    })
        except Exception:
            logger.debug("Between-call narrator failed", exc_info=True)

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
        # v2: Between-Call Intelligence enrichments
        "coaching_tips": _narrator_data.get("coaching_tips", []),
        "narrative_summary": _narrator_data.get("narrative_summary", ""),
        "emotional_forecast": _narrator_data.get("emotional_forecast", ""),
        "suggested_opener": _narrator_data.get("suggested_opener", ""),
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

    # ── Game Director: advance story state (lifecycle, relationship, storylets) ──
    try:
        from app.services.game_director import game_director, SessionResult
        session_result = SessionResult(
            session_id=str(session_id),
            client_story_id=str(story_id),
            final_emotion_state=str(current_emotion),
            score_total=state.get("last_score_total", 0.0),
            score_breakdown=state.get("last_score_breakdown", {}),
            traps_fell=state.get("traps_fell", []),
            traps_dodged=state.get("traps_dodged", []),
            promises_made=state.get("promises_made", []),
            promises_broken=state.get("promises_broken", []),
            key_moments=state.get("key_moments", []),
            stage_directions=state.get("stage_directions_parsed", []),
            duration_seconds=int(state.get("session_duration_sec", 0)),
            empathy_detected=state.get("empathy_detected", False),
            rudeness_detected=state.get("rudeness_detected", False),
            legal_errors=state.get("legal_errors", []),
        )
        async with async_session() as gd_db:
            gd_changes = await game_director.advance_story(session_result, gd_db)
            await gd_db.commit()

        # Propagate game director state back to WS state for next call
        if isinstance(gd_changes, dict) and "error" not in gd_changes:
            state["_gd_changes"] = gd_changes
            # Update relationship score in state for between-call generation
            async with async_session() as _rel_db:
                from app.models.roleplay import ClientStory as _CS
                _story_row = await _rel_db.get(_CS, story_id)
                if _story_row:
                    state["relationship_score"] = _story_row.relationship_score or 50.0
                    state["lifecycle_state"] = _story_row.lifecycle_state or "FIRST_CONTACT"
                    state["active_storylets"] = _story_row.active_storylets or []
                    state["consequence_log"] = _story_row.consequence_log or []
            logger.info(
                "Game director advanced story %s: rel=%.0f, state=%s, changes=%d",
                story_id,
                state.get("relationship_score", 50),
                state.get("lifecycle_state", "?"),
                len(gd_changes.get("changes", [])),
            )
    except Exception:
        logger.warning("Game director advance_story failed for story %s", story_id, exc_info=True)

    # ── Detect hangup recovery: previous call was hangup but this one succeeded ──
    # Check if this call is a recovery from a previous hangup
    _prev_was_hangup = state.get("story_had_hangup", False)
    _this_outcome = data.get("outcome", "unknown")
    _current_em = str(current_emotion)

    if _prev_was_hangup and _this_outcome != "hangup" and _current_em not in ("hangup", "hostile"):
        # Recovery! Manager successfully recovered client after a hangup
        state["had_hangup_recovery"] = True
        # Save to session scoring_details for L5/L9 bonus
        try:
            async with async_session() as _rec_db:
                _rec_session = await _rec_db.get(TrainingSession, session_id)
                if _rec_session:
                    _sd = _rec_session.scoring_details or {}
                    _sd["had_hangup_recovery"] = True
                    _rec_session.scoring_details = _sd
                    await _rec_db.commit()
        except Exception:
            logger.debug("Failed to save hangup recovery flag for session %s", session_id)

    # Track if THIS call was a hangup (for next call's recovery detection)
    if state.get("call_outcome") == "hangup" or _this_outcome == "hangup":
        state["story_had_hangup"] = True

    # Save last call outcome/emotion for between-call generation
    state["last_call_outcome"] = _this_outcome if _this_outcome != "unknown" else state.get("call_outcome", "unknown")
    state["last_call_emotion"] = _current_em

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

        # Gather AI-Coach context: manager weak points and skill history
        _coach_weak_points = None
        _coach_skill_history = None
        try:
            from app.services.manager_progress import ManagerProgressService
            _user_id = state.get("user_id")
            if _user_id:
                async with async_session() as _mp_db:
                    _mp_svc = ManagerProgressService(_mp_db)
                    _wp_data = await _mp_svc.get_weak_points(_user_id)
                    _coach_weak_points = [w.get("skill", "") for w in _wp_data] if _wp_data else None
        except Exception as e:
            logger.debug("Failed to load manager progress weak points for report: %s", e)

        report_data = await generate_session_report(
            messages=msg_list,
            config=config,
            emotion_trajectory=state.get("emotion_trajectory"),
            call_number=call_number,
            is_story_final=is_final,
            stage_progress=state.get("_last_stage_progress"),
            manager_weak_points=_coach_weak_points,
            manager_skill_history=_coach_skill_history,
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

    # NOTE: last_call_outcome and last_call_emotion are already set above
    # (lines ~3560-3561) with smarter fallback logic. Do NOT overwrite them here.

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
        except Exception as e:
            logger.debug("Failed to load final report score for story %s: %s", story_id, e)

        await _send(ws, "story.completed", {
            "story_id": str(story_id),
            "final_status": "completed",
            "total_score": last_report_score,
            "calls_completed": call_number,
        })

        # BUG-2 fix: emit EVENT_STORY_COMPLETED for achievement tracking
        try:
            from app.services.event_bus import event_bus, GameEvent, EVENT_STORY_COMPLETED
            user_id = state.get("user_id")
            if user_id:
                async with async_session() as evt_db:
                    await event_bus.emit(GameEvent(
                        kind=EVENT_STORY_COMPLETED,
                        user_id=user_id,
                        db=evt_db,
                        payload={
                            "story_id": str(story_id),
                            "total_score": last_report_score,
                            "calls_completed": call_number,
                        },
                    ))
        except Exception as e:
            logger.warning("Failed to emit story_completed event: %s", e)


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

    # Unique ID for this WS connection (used for session mutex)
    ws_id = str(uuid.uuid4())

    # Connection state
    state: dict = {
        "session_id": None,
        "user_id": user_id,
        "scenario_id": None,
        "character_prompt_path": None,
        "active": False,
        "stt_failure_count": 0,
        "ws_id": ws_id,
        "deepgram_stt": None,  # DeepgramStreamingSTT instance (if streaming mode)
    }
    state_lock = asyncio.Lock()

    watchdog_task: asyncio.Task | None = None
    hint_task: asyncio.Task | None = None
    soft_skills_task: asyncio.Task | None = None
    # Track fire-and-forget background tasks for cleanup on disconnect
    _bg_tasks: list[asyncio.Task] = []
    stop_event = asyncio.Event()
    _rate_limiter = training_limiter()

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

            # Per-connection rate limit: 60 messages / 10 seconds (allows audio streaming)
            if not _rate_limiter.is_allowed():
                await _send_error(websocket, "Too many messages. Slow down.", "rate_limited")
                continue

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
                _story_id = state.get("story_id")
                if _story_id:
                    try:
                        from app.models.roleplay import ClientStory
                        async with async_session() as db:
                            story_result = await db.execute(
                                select(ClientStory).where(
                                    ClientStory.id == _story_id
                                )
                            )
                            story = story_result.scalar_one_or_none()
                            if story:
                                story.is_completed = True
                                from datetime import datetime, timezone
                                story.ended_at = datetime.now(timezone.utc)
                            await db.commit()
                    except Exception as _story_err:
                        logger.error("Failed to end story %s: %s", _story_id, _story_err, exc_info=True)
                    await _send(websocket, "story.completed", {
                        "story_id": str(_story_id),
                        "forced": True,
                    })
                    # BUG-2 fix: emit EVENT_STORY_COMPLETED for forced endings too
                    try:
                        from app.services.event_bus import event_bus, GameEvent, EVENT_STORY_COMPLETED
                        _uid = state.get("user_id")
                        if _uid:
                            async with async_session() as evt_db:
                                await event_bus.emit(GameEvent(
                                    kind=EVENT_STORY_COMPLETED,
                                    user_id=_uid,
                                    db=evt_db,
                                    payload={"story_id": str(_story_id), "forced": True},
                                ))
                    except Exception:
                        logger.warning("Failed to emit story_completed for forced end")
                stop_event.set()
                break

            # ── v6: Session resume + token refresh ──
            elif msg_type == "session.resume":
                await _handle_session_resume(websocket, msg_data, state, ws_id)
                # Re-start background tasks if session was restored
                if state.get("session_id") and state.get("resumed") and watchdog_task is None:
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

            elif msg_type == "auth.refresh":
                await _handle_auth_refresh(websocket, msg_data, state)

            elif msg_type == "ping":
                if state.get("session_id"):
                    await update_activity(state["session_id"])
                    # Refresh WS mutex lock on heartbeat
                    lock_ok = await _refresh_session_lock(state["session_id"], ws_id)
                    if not lock_ok:
                        # BUG-7 fix: lock was hijacked — notify client and disconnect
                        await _send(websocket, "error", {
                            "code": "session_hijacked",
                            "message": "Сессия перехвачена другим подключением",
                        })
                        await websocket.close(code=4002)
                        return
                await _send(websocket, "pong", {})

            elif msg_type == "silence.continue":
                # User chose to continue after silence modal
                if state.get("session_id"):
                    await update_activity(state["session_id"])

            elif msg_type == "whisper.toggle":
                # Toggle coaching whispers on/off
                enabled = msg_data.get("enabled", True)
                state["whispers_enabled"] = bool(enabled)
                await _send(websocket, "whisper.toggle_ack", {"enabled": state["whispers_enabled"]})

            else:
                # Sanitize: don't reflect raw user input back in error messages
                safe_type = str(msg_type)[:50].replace("<", "&lt;").replace(">", "&gt;") if msg_type else "null"
                await _send_error(
                    websocket,
                    f"Unknown message type: {safe_type}",
                    "unknown_type",
                )

    except WebSocketDisconnect:
        # v6: Do NOT end session on disconnect — allow client to resume.
        # Session will be cleaned up by Redis TTL expiry (2h) if not resumed,
        # or by silence timeout if the watchdog fires before that.
        logger.info(
            "WebSocket disconnected for session %s (kept active for resume)",
            state.get("session_id"),
        )
    except Exception:
        logger.exception("Unexpected error in training WebSocket")
        _err_session_id = state.get("session_id")
        if _err_session_id:
            try:
                async with async_session() as db:
                    await end_session(
                        _err_session_id, db, status=SessionStatus.error
                    )
                    await db.commit()
            except Exception:
                logger.error("Failed to mark session %s as error", _err_session_id)
    finally:
        stop_event.set()
        for task in (watchdog_task, hint_task, soft_skills_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        # Cancel tracked background tasks (e.g. _enrich_legal)
        for bt in _bg_tasks:
            if bt and not bt.done():
                bt.cancel()
                try:
                    await bt
                except (asyncio.CancelledError, Exception):
                    pass
        _bg_tasks.clear()
        # Close Deepgram streaming STT if active
        dg_stt = state.get("deepgram_stt")
        if dg_stt:
            try:
                await dg_stt.close()
            except Exception:
                logger.debug("Failed to close Deepgram STT for session %s", state.get("session_id"))

        # Release WS mutex lock so another connection can resume
        sid = state.get("session_id")
        if sid:
            await _release_session_lock(sid, ws_id)
            release_session_voice(str(sid))
