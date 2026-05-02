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
import html
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
from app.models.client import ClientInteraction, InteractionType
from app.models.scenario import Scenario, ScenarioTemplate, ScenarioType
from app.models.training import MessageRole, SessionStatus, TrainingSession
from app.models.user import User

from app.services.emotion import (
    get_emotion, init_emotion, init_emotion_v3,
    transition_emotion, transition_emotion_v3,
    get_fake_prompt, save_journey_snapshot,
)
from app.services.crm_followup import ensure_followup_for_session
from app.services.client_domain import log_training_real_case_summary
from app.services.session_state import normalize_session_outcome
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
    LLMResponse,
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
from app.services.stage_tracker import (
    STAGE_BEHAVIOR,
    STAGE_LABELS,
    STAGE_ORDER,
    StageTracker,
)
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


async def _apply_call_scrub_gate(
    raw_sentence: str,
    *,
    ws,
    session_id,
) -> str | None:
    """Run the AI-tell sentence gate before launching a TTS task.

    Returns the text that should actually be synthesised, or ``None`` if
    the caller should skip the TTS launch (mode=drop, or strip with empty
    residue). Emits a ``character.ai_tell_detected`` WS event for
    observability whenever a match is found, regardless of mode — so the
    front-end can surface a small admin badge without changing audio.

    No-op when ``CALL_HUMANIZED_V2`` is OFF: returns the input unchanged
    and skips the scan entirely. The scrubber import is local so the
    legacy code path doesn't pay the import cost when the flag is off.
    """
    if not settings.call_humanized_v2:
        return raw_sentence
    try:
        from app.services.ai_tell_scrubber import scrub  # local import on hot path
        result = scrub(raw_sentence, mode=settings.call_humanized_v2_scrub_mode)
    except Exception:
        # Defensive: if the scrubber raises (corrupt lexicon, bad mode
        # string, anything) we MUST NOT blackhole the audio. Pass through.
        logger.warning(
            "ai_tell_scrubber failed for session=%s — passing audio unchanged",
            session_id, exc_info=True,
        )
        return raw_sentence

    if result.matches:
        try:
            await _send(ws, "character.ai_tell_detected", {
                "matches": list(result.matches),
                "action": result.action,
                "mode": settings.call_humanized_v2_scrub_mode,
                # Truncate to avoid leaking full sentence to UI logs.
                "preview": raw_sentence[:80],
            })
        except Exception:
            # Cosmetic event; never let it break the call path.
            logger.debug(
                "Could not emit ai_tell_detected event session=%s",
                session_id, exc_info=True,
            )
        logger.info(
            "ai_tell_detected session=%s mode=%s action=%s matches=%s",
            session_id,
            settings.call_humanized_v2_scrub_mode,
            result.action,
            list(result.matches),
        )

    if result.action == "dropped":
        return None
    # warn → original; stripped → residue.
    return result.text or raw_sentence


def _call_tts_factors(state: dict) -> list[dict] | None:
    """Return active_factors for a TTS call when call humanisation V2 is on.

    The factors are already maintained in ``state["active_factors"]`` by
    the main handler (seed at first turn, refresh via
    ``FactorInteractionMatrix``). Until Sprint 0 only one of the six TTS
    call sites actually forwarded them — the others passed ``emotion``
    only and the existing ``inject_hesitations`` / factor-specific
    breathing path was effectively dead in voice mode.

    This helper lets every TTS site opt in as a single branch. When
    ``CALL_HUMANIZED_V2`` is OFF we return ``None`` so pre-Sprint-0
    audible behaviour is preserved bit-for-bit. When ON we return the
    live list so the humaniser actually fires.

    Note: this is a *read* of ``state`` — callers must not mutate the
    returned list (the matrix recomputes it each turn).
    """
    if not settings.call_humanized_v2:
        return None
    return list(state.get("active_factors") or [])


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
MAX_STT_FAILURES = 10  # 2026-04-22: bumped 3→10 — Whisper cold-starts look like failures but recover; don't kick user to text mode prematurely

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


# Sprint 0 §6 — auto-opener phrases (Bug B fix). When V2 is on and a
# call session starts, the AI emits one of these in the first second so
# the manager isn't greeted by silence. Five short variants picked at
# random; emotion-neutral on purpose because the persona's emotional
# arc starts at "cold" and a long opening "Не желаю с вами разговаривать"
# would be its own AI-tell. Real humans answer the phone neutrally.
CALL_AUTO_OPENERS: tuple[str, ...] = (
    "Алло?",
    "Да, слушаю.",
    "Алло, говорите.",
    "Да?",
    "Слушаю вас.",
)


def _pick_call_auto_opener() -> str:
    """Return one of the auto-opener phrases at random."""
    import random as _rnd
    return _rnd.choice(CALL_AUTO_OPENERS)


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


_WS_OUTGOING_MAX = 100  # Safety net: max queued messages per connection

async def _send(ws: WebSocket, msg_type: str, data: dict) -> None:
    """Helper to send a typed JSON message to the client.
    Includes backpressure safety: drops if outgoing queue exceeds limit.
    """
    try:
        # Starlette WebSocket doesn't expose queue size directly,
        # but we can use a simple counter per-connection via ws.state
        count = getattr(ws.state, "_outgoing_count", 0)
        if count > _WS_OUTGOING_MAX:
            logger.warning("WS outgoing queue overflow (%d), dropping %s", count, msg_type)
            return
        ws.state._outgoing_count = count + 1
        await ws.send_json({"type": msg_type, "data": data})
        ws.state._outgoing_count = max(0, count)  # Decrement after successful send
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
    from app.core.deps import _is_user_blacklisted, _is_token_revoked
    if await _is_user_blacklisted(user_id_str):
        await _send(ws, "auth.error", {"message": err.WS_TOKEN_REVOKED})
        return None

    # S1-diag: Check per-token JTI revocation (e.g. refresh rotation invalidated this token)
    jti = payload.get("jti")
    if jti and await _is_token_revoked(jti):
        await _send(ws, "auth.error", {"message": err.WS_TOKEN_REVOKED})
        return None

    return user_id


# ─── WS Session Lock (mutex for single-connection-per-session) ─────────────

_WS_LOCK_KEY = "ws:lock:{session_id}"
_WS_LOCK_OWNER_KEY = "ws:lock:{session_id}:owner"  # user_id of current holder
_WS_LOCK_TTL = 60  # seconds, refreshed on heartbeat


async def _acquire_session_lock(
    session_id: uuid.UUID, ws_id: str, user_id: uuid.UUID | None = None,
) -> bool:
    """Acquire exclusive WS lock for a session.

    Normal path (nx=True): lock is free → we get it.
    Takeover path: lock is held by the SAME user (e.g. React Strict-Mode
    remount, Fast Refresh, or user opened a new tab for the same session).
    We forcibly take it over and the old connection will learn about it on
    its next heartbeat (and redirect to results). This prevents spurious
    "session_hijacked" errors during normal dev/user flows while still
    blocking different-user hijack attempts.
    """
    from app.core.redis_pool import get_redis
    r = get_redis()
    try:
        key = _WS_LOCK_KEY.format(session_id=session_id)
        owner_key = _WS_LOCK_OWNER_KEY.format(session_id=session_id)
        acquired = await r.set(key, ws_id, nx=True, ex=_WS_LOCK_TTL)
        if acquired:
            if user_id is not None:
                await r.set(owner_key, str(user_id), ex=_WS_LOCK_TTL)
            return True
        # Lock held — check if same user; allow takeover
        if user_id is not None:
            existing_owner = await r.get(owner_key)
            if existing_owner and existing_owner.decode() == str(user_id):
                # Same user — force takeover
                await r.set(key, ws_id, ex=_WS_LOCK_TTL)
                await r.set(owner_key, str(user_id), ex=_WS_LOCK_TTL)
                logger.info(
                    "WS lock takeover for session %s by same user %s (new ws_id=%s)",
                    session_id, user_id, ws_id,
                )
                return True
        return False
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
    # NOTE: We access session attributes (user_id, status, scenario_id, custom_params,
    # client_story_id, call_number_in_story) after session close. These are simple columns
    # loaded by the initial query — safe for detached access. If relationship access is
    # ever needed here, add selectinload() or extract data within the async-with block.
    async with async_session() as db:
        result = await db.execute(
            select(TrainingSession).where(TrainingSession.id == session_id)
        )
        session = result.scalar_one_or_none()

    if not session or session.user_id != state["user_id"]:
        await _send(ws, "error", {"code": "session_not_found"})
        return

    # 2. Check session is still active
    if session.status not in (SessionStatus.active,):
        await _send(ws, "error", {"code": "session_completed"})
        return

    # 3. Acquire exclusive lock (same-user takeover allowed — see _acquire_session_lock)
    locked = await _acquire_session_lock(session_id, ws_id, state.get("user_id"))
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
    # C2 fix: init outside async-with so they're available for session.resumed message
    scenario = None
    client_card = None
    client_gender = ""
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
        state["character_name"] = character.name if character else ""
        state["archetype_code"] = custom_archetype or (character.slug if character else None)
        state["base_difficulty"] = custom_difficulty or (scenario.difficulty if scenario else 5)
        state["script_id"] = scenario.script_id if scenario else None
        state["matched_checkpoints"] = set()
        state["last_character_message"] = ""
        state["fake_transition_prompt"] = ""
        state["stt_failure_count"] = 0

        # C2 fix: restore story mode fields from session record.
        # 2026-04-18 audit fix: also restore total_calls, personality profile,
        # relationship_score, lifecycle_state, accumulated events. Without
        # these, a WS reconnect mid-story on call 3 of 5 would leave the
        # client_profile_prompt missing the story context, the HUD showing
        # call?/0, and between-call events empty — the AI would lose all
        # narrative continuity.
        if session.client_story_id:
            state["story_id"] = session.client_story_id
            state["call_number"] = session.call_number_in_story or 1
            try:
                from app.models.roleplay import ClientStory as _CS_resume
                _cs_row = await db_resume.get(_CS_resume, session.client_story_id)
                if _cs_row is not None:
                    state["total_calls"] = _cs_row.total_calls_planned or 3
                    state["personality_profile"] = _cs_row.personality_profile or {}
                    state["active_factors"] = _cs_row.active_factors or []
                    state["accumulated_consequences"] = _cs_row.consequences or []
                    state["between_call_events"] = _cs_row.between_call_events or []
                    state["relationship_score"] = _cs_row.relationship_score or 50.0
                    state["lifecycle_state"] = _cs_row.lifecycle_state or "FIRST_CONTACT"
                    state["active_storylets"] = _cs_row.active_storylets or []
                    state["consequence_log"] = _cs_row.consequence_log or []
                    logger.info(
                        "Resumed story %s at call %d/%d (rel=%.0f state=%s)",
                        session.client_story_id,
                        state["call_number"],
                        state["total_calls"],
                        state["relationship_score"],
                        state["lifecycle_state"],
                    )
            except Exception:
                logger.warning(
                    "Failed to restore ClientStory state on resume for session %s",
                    session_id,
                    exc_info=True,
                )
        else:
            state["story_id"] = None
            state["call_number"] = 1

        # Restore message count from DB if Redis lost it
        if state.get("message_count", 0) == 0:
            try:
                from sqlalchemy import func as _sqf
                msg_count_result = await db_resume.execute(
                    select(_sqf.count(Message.id)).where(Message.session_id == session_id)
                )
                state["message_count"] = msg_count_result.scalar() or 0
            except Exception:
                # FIND-008 fix (2026-04-18): keep session alive on DB blip, log the error so we can see it.
                logger.warning("training.resume: message_count fetch failed for session %s", session_id, exc_info=True)

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
            from app.models.roleplay import ClientProfile, ProfessionProfile
            from app.services.client_generator import get_crm_card
            from sqlalchemy.orm import selectinload
            cp_result = await db_resume.execute(
                select(ClientProfile)
                .options(selectinload(ClientProfile.profession))
                .where(ClientProfile.session_id == session_id)
            )
            profile = cp_result.scalar_one_or_none()
            if profile:
                client_card = get_crm_card(profile)
                client_name = client_card.get("full_name", "") if client_card else ""
                client_gender = getattr(profile, "gender", "") or ""
                client_profile_prompt = _build_client_profile_prompt(profile, ambient_ctx=custom_params)

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

    # 5. Send current emotion (C2 fix: DB fallback if Redis lost state)
    emotion = await get_emotion(session_id)
    if emotion == "cold" and messages:
        # Redis may have lost emotion — recover from last message with emotion_state
        for msg in reversed(messages):
            db_emotion = msg.get("emotion_state")
            if db_emotion and db_emotion != "cold":
                emotion = db_emotion
                # Re-seed Redis so subsequent calls work
                await set_emotion(session_id, emotion)
                logger.info("Session %s: emotion restored from message history: %s", session_id, emotion)
                break
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

    # 9. Confirm resume (C2 fix: send full state to frontend)
    # Use client profile name when available (matches the briefing card)
    _resume_display_name = (client_card.get("full_name") if client_card else None) or state.get("character_name", "")
    _resumed_data: dict = {
        "session_id": str(session_id),
        "elapsed_seconds": elapsed,
        "message_count": len(messages),
        "emotion": str(emotion),
        "character_name": _resume_display_name,
        "archetype_code": state.get("archetype_code", ""),
        "scenario_title": scenario.title if scenario else "Тренировка",
        "character_gender": client_gender or "M",
    }
    if client_card:
        _resumed_data["client_card"] = client_card
    # 2026-04-18 audit fix: ship story context so the frontend HUD bar,
    # PreCallBriefOverlay gating, and StoryCallReportOverlay totalCalls
    # display all work correctly after a WS reconnect mid-story.
    if state.get("story_id"):
        _resumed_data["story_id"] = str(state["story_id"])
        _resumed_data["total_calls"] = int(state.get("total_calls", 3))
        _resumed_data["call_number"] = int(state.get("call_number", 1))
    await _send(ws, "session.resumed", _resumed_data)

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

        # Fetch current role for JWT claim
        from app.models.user import User as UserModel
        from sqlalchemy import select as sa_select
        async with async_session() as _db:
            _role_result = await _db.execute(sa_select(UserModel.role).where(UserModel.id == user_id_str))
            _user_role = _role_result.scalar_one_or_none() or "manager"

        # Create new tokens (S4-01: include role_version)
        from app.core.security import get_role_version
        _rv = await get_role_version(user_id_str)
        new_access_token = create_access_token({"sub": user_id_str, "role": _user_role}, role_version=_rv)
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
    # Send avatar.typing indicator + mark LLM as busy so the silence watchdog
    # pauses while the model is generating (slow local LLMs can take 20–40s).
    state["llm_busy"] = True
    await _send(ws, "avatar.typing", {"is_typing": True})

    current_emotion = await get_emotion(session_id)

    # Check force_hangup flag set by adaptive difficulty on previous turn.
    # If set, the AI will now play a short goodbye line and terminate the call.
    try:
        from app.core.redis_pool import get_redis as _get_redis_fh
        _r_fh = _get_redis_fh()
        _forced = await _r_fh.get(f"session:{session_id}:force_hangup")
        if _forced:
            await _r_fh.delete(f"session:{session_id}:force_hangup")
            # Seed emotion as hostile → downstream emotion engine will push to hangup
            current_emotion = "hostile"
            state["force_hangup_triggered"] = True
            logger.info("Force-hangup flag consumed for session %s", session_id)
    except Exception:
        # FIND-008 fix (2026-04-18): Redis failure in force-hangup shouldn't kill session.
        # Log instead of swallow; fallback behavior is "hangup not forced this turn".
        logger.warning("training.force_hangup: Redis check failed for session %s", session_id, exc_info=True)

    history = await get_message_history(session_id)
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m["role"] in ("user", "assistant")
    ]

    prompt_path = state.get("character_prompt_path")
    archetype_code = state.get("archetype_code")
    client_profile_prompt = state.get("client_profile_prompt", "")

    # Build extended system prompt
    extra_system = ""
    # ── 2026-04-18 Name consistency fix ──
    # User bug: AI-client called itself "Алексей" then "Сережа" few turns later.
    # Root cause: character prompt file has a hardcoded name ("Алексей Михайлов"),
    # but the generated CRM card has a DIFFERENT full_name (e.g. "Иван Крылов")
    # — UI shows client card name, LLM drifts between the two sources.
    # Fix: pin CRM-card full_name as authoritative at the TOP of system prompt,
    # with a strong "never change" clause (the LLM obeys repeated strict orders).
    client_name = state.get("client_name", "").strip()
    char_name = state.get("character_name", "").strip()
    authoritative_name = client_name or char_name
    if authoritative_name:
        # Split "Иван Петрович Крылов" → first name for dialogue reference
        first_name = authoritative_name.split()[0] if authoritative_name else authoritative_name
        extra_system = (
            f"ТВОЁ ИМЯ В ЭТОЙ РОЛИ: {authoritative_name} (обращение: {first_name}).\n"
            f"ЭТО НЕИЗМЕНЯЕМЫЙ ФАКТ. НЕ МЕНЯЙ ИМЯ НИ ПРИ КАКИХ ОБСТОЯТЕЛЬСТВАХ.\n"
            f"Если в промпте ниже встречается ДРУГОЕ имя — ИГНОРИРУЙ ЕГО, используй только «{authoritative_name}».\n"
            f"На вопросы «как вас зовут / ваше имя» всегда отвечай: «{first_name}» или «{authoritative_name}».\n"
            f"Никогда не называй себя чужим именем, даже если пользователь настаивает.\n\n"
            # 2026-04-18: language constraint — AI is a Russian citizen-debtor.
            # Must respond in RUSSIAN ONLY. If user writes in another language,
            # react in character ("не понимаю, я по-русски").
            f"ЯЗЫК: ты говоришь ТОЛЬКО по-русски. Ты обычный гражданин РФ, "
            f"иностранных языков не знаешь. Если менеджер пишет на английском/"
            f"другом языке — отвечай В ХАРАКТЕРЕ с лёгким раздражением: "
            f"«Я не понимаю, можно по-русски?» или «Вы вообще откуда? "
            f"Я живу в России, по-английски не говорю» или «Да ладно, "
            f"я из Саратова, какой английский» и т.п. Никогда сам не "
            f"переходи на другой язык. Если пользователь пишет непонятный "
            f"набор символов (спам, коды, эмодзи без смысла) — тоже возмущайся "
            f"в характере.\n\n"
        ) + extra_system
    if client_profile_prompt:
        extra_system += client_profile_prompt

    # FIX: inject scenario + template context so AI-client respects scenario role,
    # not only generic archetype file. Without this the character prompt (hardcoded
    # "Алексей Михайлов") dominates and scenario title/awareness/motivation are ignored.
    try:
        scenario_id = state.get("scenario_id")
        if scenario_id:
            from sqlalchemy import select
            from app.models.scenario import Scenario, ScenarioTemplate
            async with async_session() as _db_sc:
                _res = await _db_sc.execute(
                    select(Scenario).where(Scenario.id == scenario_id)
                )
                _sc = _res.scalar_one_or_none()
                _tmpl = None
                if _sc and _sc.template_id:
                    _res_t = await _db_sc.execute(
                        select(ScenarioTemplate).where(ScenarioTemplate.id == _sc.template_id)
                    )
                    _tmpl = _res_t.scalar_one_or_none()
            if _sc:
                _sc_lines = [
                    "## КОНТЕКСТ ЗВОНКА (обязательно учитывай)",
                    f"Сценарий: {_sc.title}",
                    f"Сложность: {_sc.difficulty}/10",
                ]
                if _tmpl:
                    if _tmpl.client_awareness:
                        _aw_map = {
                            "zero": "ты не знаешь зачем тебе звонят, не ждал звонка",
                            "low": "ты примерно помнишь что оставил заявку, но деталей не помнишь",
                            "medium": "ты ждёшь звонка, помнишь что обсуждали",
                            "high": "ты ждал звонка, готов обсуждать конкретику",
                        }
                        _aw_desc = _aw_map.get(_tmpl.client_awareness, _tmpl.client_awareness)
                        _sc_lines.append(f"Осведомлённость: {_aw_desc}")
                    if _tmpl.client_motivation:
                        _mot_map = {
                            "very_low": "тебе почти не нужен продукт",
                            "low": "продукт тебе малоинтересен",
                            "medium": "продукт умеренно интересен",
                            "high": "продукт нужен, ты ищешь решение",
                            "very_high": "продукт остро нужен прямо сейчас",
                        }
                        _sc_lines.append(f"Мотивация: {_mot_map.get(_tmpl.client_motivation, _tmpl.client_motivation)}")
                    if _tmpl.initial_emotion:
                        _sc_lines.append(f"Начальная эмоция: {_tmpl.initial_emotion}")
                    if _tmpl.awareness_prompt:
                        _sc_lines.append(f"Дополнительно: {_tmpl.awareness_prompt}")
                    # Current stage info if available
                    _cur_stage_n = state.get("current_stage_order", 1)
                    _stages = _tmpl.stages or []
                    if _stages and isinstance(_stages, list):
                        try:
                            _cur_stage = next((s for s in _stages if s.get("order") == _cur_stage_n), None)
                            if _cur_stage:
                                _sc_lines.append(
                                    f"Текущий этап звонка: {_cur_stage.get('label') or _cur_stage.get('name')} "
                                    f"— менеджер должен {_cur_stage.get('description', '...')}"
                                )
                        except Exception:
                            # FIND-008: stage metadata parse can legitimately fail for legacy scenarios — log to debug only.
                            logger.debug("training.stage_hint: stage metadata unusable for session %s", session_id, exc_info=True)
                extra_system = "\n".join(_sc_lines) + "\n\n" + extra_system
    except Exception:
        logger.debug("Scenario context injection failed", exc_info=True)

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

    # ── P0 (2026-04-29) Call Arc — decouple AI from manager script ────────
    # When CALL_ARC_V1 is on AND session_mode is "call": skip the stage-driven
    # behaviour directives and inject a per-call role contract instead. The
    # AI no longer learns about manager checklist stages. StageTracker keeps
    # running for /results scoring and for the manager-side script panel WS
    # events — only the AI prompt path changes.
    #
    # When CALL_ARC_V1 is off: legacy behaviour bit-for-bit (StageTracker
    # injection runs as before, including skip-reaction handling).
    _arc_active = False
    if settings.call_arc_v1:
        _cp_arc = state.get("custom_params") or {}
        _session_mode_arc = (_cp_arc.get("session_mode") or state.get("session_mode") or "chat").lower()
        _arc_active = _session_mode_arc in ("call", "center")

    if _arc_active:
        # Arc path: inject per-call role + reality block. Skip stage prompt.
        try:
            from app.services.call_arc import build_arc_prompt, get_arc_step
            _call_n = int(state.get("call_number", 1) or 1)
            _total_n = int(state.get("total_calls", 3) or 3)
            _arc_step = get_arc_step(_call_n, _total_n)
            _prev_summary = state.get("compressed_history") or None
            _arc_block = build_arc_prompt(_arc_step, prev_calls_summary=_prev_summary)
            extra_system += "\n\n" + _arc_block
        except Exception:
            logger.debug(
                "Call-arc injection failed for session %s — falling back to no-arc",
                session_id,
                exc_info=True,
            )
        if settings.call_arc_inject_reality:
            try:
                from app.services.llm import load_prompt as _arc_load_prompt
                _reality = _arc_load_prompt("reality_ru_2026.md")
                if _reality:
                    extra_system += "\n\n" + _reality
            except Exception:
                logger.debug(
                    "Reality block injection failed for session %s",
                    session_id,
                    exc_info=True,
                )
        # StageTracker still runs (for UI events emitted elsewhere on
        # process_message), but its prompt is intentionally NOT injected.
        # Skip-reactions are also dropped on the floor — under the arc
        # paradigm the AI reacts to the manager's actual words via persona,
        # not to checklist transitions. Clear the queue so it doesn't leak.
        state.pop("_pending_skip_reactions", None)
    else:
        # Legacy path — preserve byte-for-byte.
        try:
            from app.core.redis_pool import get_redis as _get_redis_sp
            _r_sp = _get_redis_sp()
            _st_prompt = StageTracker(str(session_id), _r_sp)
            _stage_st = await _st_prompt.get_state()
            extra_system += _st_prompt.build_stage_prompt(_stage_st)

            # If there are pending skip reactions (from previous process_message),
            # surface them so the AI can react to a skipped stage. Pre-Sprint-0
            # this was a hard directive ("Начни свой ответ с одной из этих фраз")
            # which produced the "скрипт блокирует" UX bug — every off-script
            # question got slapped back with "Стоп, мы даже не познакомились!"
            # regardless of what the manager actually asked.
            # Sprint 0 §A (User-first 2026-04-29): when V2 is on, surface the
            # skip context as an OPTION, not an order — and only if it's
            # naturally relevant to the manager's actual line.
            _skip_reactions = state.get("_pending_skip_reactions", [])
            if _skip_reactions:
                if settings.call_humanized_v2:
                    extra_system += (
                        "\n\n[SKIP_CONTEXT: Менеджер только что пропустил важный "
                        "этап разговора. Если это реально режет тебе слух — можешь "
                        "коротко это заметить (например: "
                        + "; ".join(f'«{r}»' for r in _skip_reactions)
                        + "). Но только если это уместно в ответ на его конкретную "
                        "фразу. Если он задал нормальный вопрос — отвечай по теме его "
                        "вопроса, не возвращай его насильно на этап.]"
                    )
                else:
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

    # 2026-04-22: Manager-initiated farewell — inject closing instruction.
    # When the manager said "до свидания" / "спасибо за время" etc., the AI
    # should give one short polite closing reply (~10 words). After this turn
    # the WS handler will auto-fire session.end (see _handle_text_message).
    if state.get("user_initiated_farewell") and not state.get("user_farewell_replied"):
        extra_system += (
            "\n\n## ВАЖНО — клиент завершает разговор\n"
            "Менеджер только что попрощался с вами. Ответьте КОРОТКО (одна фраза, "
            "максимум 10 слов) в духе вашего архетипа: вежливо если разговор шёл "
            "хорошо, сухо/недовольно если нет. Примеры: «До свидания», «Хорошо, "
            "до связи», «Угу, бывайте», «Ладно, спасибо». Не задавайте новых "
            "вопросов. Не продолжайте обсуждение. Это ваша последняя реплика."
        )

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

    # ── Narrative + Human Factor trap prompts (story mode only) ──
    if state.get("story_id"):
        try:
            from app.services.narrative_trap_detector import build_narrative_trap_prompt
            from app.services.human_factor_traps import build_human_factor_prompt
            # Load ClientStory once, cache in state for reuse by trap detection
            _nt_story_id = state["story_id"]
            _nt_story = state.get("_cached_client_story")
            if _nt_story is None:
                async with async_session() as _nt_db:
                    from app.models.roleplay import ClientStory as _CS
                    _nt_result = await _nt_db.execute(
                        select(_CS).where(_CS.id == uuid.UUID(str(_nt_story_id)))
                    )
                    _nt_story = _nt_result.scalar_one_or_none()
                    state["_cached_client_story"] = _nt_story
            if _nt_story:
                _nar_prompt = build_narrative_trap_prompt(_nt_story)
                if _nar_prompt:
                    extra_system += "\n\n" + _nar_prompt
            _hf_prompt = build_human_factor_prompt(
                state.get("active_factors", []),
                state.get("_last_hf_results"),
            )
            if _hf_prompt:
                extra_system += "\n\n" + _hf_prompt
        except Exception:
            logger.debug("Narrative/HF prompt injection failed for story %s", state.get("story_id"), exc_info=True)

    # v6: Human tangent injection — AI client occasionally goes off-script with relatable asides
    try:
        from app.services.emotion_v6 import should_ai_add_human_tangent
        _msg_idx = state.get("message_count", 0)
        if should_ai_add_human_tangent(
            emotion_state=current_emotion,
            message_index=_msg_idx,
            archetype_code=state.get("archetype_code", "neutral"),
        ):
            extra_system += (
                "\n\n[HUMAN_MOMENT: В этом ответе добавь короткое личное отступление "
                "(2-3 предложения) — воспоминание, мысль вслух, или бытовую аналогию. "
                "Это должно звучать естественно, как будто клиент на секунду отвлёкся от темы. "
                "Потом плавно вернись к обсуждению.]"
            )
    except Exception:
        # FIND-008: human-moment is purely cosmetic prompt augmentation — debug-log only.
        logger.debug("training.human_moment: injection skipped for session %s", session_id, exc_info=True)

    # Phase 2.4+2.5 (2026-04-18): inject manager-profile and quote sections.
    # Both are strictly additive and fail-closed — if either read errors, we
    # just skip the injection rather than derail the whole turn.
    try:
        from app.services.manager_profile import build_manager_profile_section
        from app.services.quote_reply import build_quote_section

        _story_id = state.get("story_id")
        _pending_quote = state.pop("pending_quoted_message_id", None)

        async with async_session() as _mp_db:
            _mp_section = (
                await build_manager_profile_section(story_id=_story_id, db=_mp_db)
                if _story_id else ""
            )
            _quote_section = await build_quote_section(
                session_id=session_id,
                quoted_message_id=_pending_quote,
                db=_mp_db,
            )

        if _mp_section:
            extra_system = extra_system + "\n\n" + _mp_section
        if _quote_section:
            extra_system = extra_system + "\n\n" + _quote_section
    except Exception:
        logger.debug("manager_profile/quote injection failed", exc_info=True)

    # TZ-8 P0 #2 (audit-call-mode-rag-missing) — the call hot path
    # never touched ``retrieve_all_context``, so methodology
    # playbooks (per team), wiki insights (per manager), and legal
    # context were invisible to the AI client during phone-mode
    # sessions. ``call_rag_cache.get_call_rag_block`` resolves the
    # caller's team_id once per session, runs the four-source RAG
    # fanout, and caches the formatted ``[DATA_START]/[DATA_END]``
    # block with a 60-second TTL. Failure-mode is "" (the call
    # continues without the block; logged at DEBUG, never raises).
    try:
        from app.services.call_rag_cache import get_call_rag_block

        # Latest user (manager) message drives the embedding query.
        # Empty string when the session just opened — RAG returns
        # nothing useful on a cold start anyway, and the cache will
        # be populated on the first real exchange.
        _last_user_msg = ""
        for _m in reversed(messages):
            if _m.get("role") == "user":
                _last_user_msg = (_m.get("content") or "").strip()
                break

        if _last_user_msg:
            async with async_session() as _rag_db:
                _rag_block = await get_call_rag_block(
                    state=state,
                    user_id=state["user_id"],
                    query=_last_user_msg,
                    db=_rag_db,
                    context_type="training",
                    archetype_code=archetype_code,
                    emotion_state=current_emotion,
                )
            if _rag_block:
                extra_system = extra_system + "\n\n" + _rag_block
    except Exception:
        logger.debug(
            "training.call_rag: unified RAG block injection failed "
            "for session %s (call continues without RAG context)",
            session_id, exc_info=True,
        )

    # TZ-4.5 PR 4 — load persona facts from cross-session memory so
    # the LLM sees them in the system prompt. Best-effort: failure
    # falls through to a cold-start (no facts) call. The fresh read
    # picks up anything the extractor wrote on the previous turn.
    _persona_facts: dict | None = None
    try:
        from app.services import persona_memory as _pm_for_facts
        async with async_session() as _db_facts:
            _snap_for_facts = await _pm_for_facts.get_snapshot(
                _db_facts, session_id=session_id,
            )
            if _snap_for_facts is not None and _snap_for_facts.lead_client_id is not None:
                _p = await _pm_for_facts.get_for_lead(
                    _db_facts, lead_client_id=_snap_for_facts.lead_client_id,
                )
                if _p is not None and _p.confirmed_facts:
                    _persona_facts = dict(_p.confirmed_facts)
    except Exception:
        logger.debug("persona_facts load failed — proceeding cold-start", exc_info=True)

    try:
        # H1 fix: route by estimated token count, not call_number
        _est_tokens = len(extra_system) // 2  # rough estimate for Russian text
        _prefer = "local" if _est_tokens < 4000 else "auto"

        # Phase 3.4 (2026-04-19): pull the level-specific temperature hint
        # from ``DIFFICULTY_PARAMS`` and stash it on ``state`` so providers
        # can read it through the existing state dict. We don't rewire the
        # provider signatures (too invasive) — llm.py picks this up when it
        # sees ``state["_llm_temperature_hint"]`` set, otherwise it keeps
        # the legacy per-provider default. This is purely additive.
        try:
            from app.services.adaptive_difficulty import (
                resolve_params as _resolve_diff_params,
            )

            _diff = _resolve_diff_params(state.get("scenario_difficulty"))
            state["_llm_temperature_hint"] = _diff.llm_temperature
            state["_llm_coaching_hints"] = _diff.coaching_hints
            state["_llm_agreement_prob"] = _diff.agreement_base_probability
            state["_llm_objection_density"] = _diff.objection_density
        except Exception:
            logger.debug("difficulty params lookup failed", exc_info=True)

        # Phase 1 streaming: try streaming first, fall back to blocking
        # Phase 3 (streaming TTS): launch per-sentence TTS tasks INSIDE the LLM
        # stream loop so that the first audio arrives ~400ms after the first
        # sentence is complete, not after the entire LLM response.
        from app.services.llm import generate_response_stream
        _streamed_text = ""
        _stream_ok = False
        _stream_tts_used = False  # if True, skip post-LLM sentence TTS block
        # Pre-compute TTS eligibility (same checks as post-LLM block)
        # is_tts_available() returns True for either ElevenLabs OR navy TTS;
        # redundant elevenlabs_enabled gate would block navy-only setups.
        _tts_stream_enabled = (
            is_tts_available()
            and state.get("user_prefs", {}).get("tts_enabled", True)
        )
        try:
            _chunk_buffer = ""
            _tts_sentence_buffer = ""      # accumulates clean text for TTS
            _tts_sent_indices: list[int] = []  # sentence indices dispatched
            _tts_tasks: dict[int, asyncio.Task] = {}  # idx -> TTS task
            _tts_next_to_send = 0
            _tts_disabled_due_to_error = False
            _start_stream = time.monotonic()

            # Regex to strip stage directions (e.g. [PAUSE], *вздыхает*)
            import re as _re_stream
            _STAGE_DIR_RE = _re_stream.compile(r"\[[^\]]*\]|\*[^*]*\*")

            async def _flush_ordered_tts_chunks(*, last_idx: int | None = None) -> None:
                """Send any completed TTS tasks in order, non-blocking for pending ones."""
                nonlocal _tts_next_to_send, _tts_disabled_due_to_error
                while _tts_next_to_send in _tts_tasks:
                    task = _tts_tasks[_tts_next_to_send]
                    if not task.done():
                        break  # wait for earlier sentence before moving on
                    try:
                        result = task.result()
                    except TTSQuotaExhausted:
                        _tts_disabled_due_to_error = True
                        await _send(ws, "tts.fallback", {"reason": "quota_exhausted"})
                        _tts_next_to_send += 1
                        continue
                    except Exception as _tts_err:
                        # Journal #C (silent swallow on critical UX path).
                        # TTS failure here = user hears silence on a call or
                        # chat session. Has to be VISIBLE in prod logs so we
                        # can trace back from user complaints.
                        logger.warning(
                            "Stream TTS task %d failed (sentence dropped, user will miss audio): %s",
                            _tts_next_to_send, _tts_err,
                            exc_info=True,
                        )
                        _tts_next_to_send += 1
                        continue
                    if result and result.get("audio"):
                        is_last = (last_idx is not None and _tts_next_to_send == last_idx)
                        await _send(ws, "tts.audio_chunk", {
                            "audio_b64": result["audio"],
                            "format": result.get("format", "mp3"),
                            "sentence_index": _tts_next_to_send,
                            "is_last": is_last,
                            "text": result.get("text", ""),
                        })
                    _tts_next_to_send += 1

            async def _synth_for_stream(_text: str, _idx: int) -> dict | None:
                """Synthesize one sentence for streaming TTS. Returns dict with `audio` or None.

                Hard timeout prevents a slow TTS provider from hanging the session.
                """
                try:
                    # Per-sentence budget = ElevenLabs timeout + 2s grace (covers Navy fallback)
                    _sent_budget = float(settings.elevenlabs_timeout_seconds) + 2.0
                    r = await asyncio.wait_for(
                        get_tts_audio_b64(
                            _text, str(session_id),
                            emotion=current_emotion,
                            active_factors=_call_tts_factors(state),
                        ),
                        timeout=_sent_budget,
                    )
                    if r:
                        r["text"] = _text  # preserve text for client
                    return r
                except asyncio.TimeoutError:
                    logger.warning("Stream TTS per-sentence timeout idx=%d session=%s", _idx, session_id)
                    return None
                except TTSQuotaExhausted:
                    raise
                except TTSError as _te:
                    logger.debug("Stream TTS synth error: %s", _te)
                    return None

            # ── IL-1 (2026-04-30) Filler audio at sentence_index=0 ──
            # Reserve index 0 for an in-character thinking sound (Ну.../
            # Ммм.../Так-так...). LLM sentences then naturally start at
            # index 1+ via the existing ``len(_tts_sent_indices)`` counter.
            # Fires CONCURRENTLY with the LLM stream so the filler plays
            # while the LLM is still generating real content — kills the
            # 1.7-4.7s of dead air observed in field TTS logs (2026-04-29).
            #
            # Skipped when: flag off, not call/center mode, TTS disabled,
            # or pick_filler() returned text=None (15% silence rate so it
            # doesn't sound like a stuck record on every turn).
            _filler_emitted = False
            _cp_filler = state.get("custom_params") or {}
            _session_mode_filler = (
                _cp_filler.get("session_mode")
                or state.get("session_mode")
                or "chat"
            ).lower()
            if (
                settings.call_filler_v1
                and settings.call_humanized_v2
                and _tts_stream_enabled
                and _session_mode_filler in ("call", "center")
            ):
                try:
                    from app.services.call_filler import pick_filler as _il1_pick
                    _il1_choice = _il1_pick(current_emotion)
                    if _il1_choice.text:
                        _tts_sent_indices.append(0)
                        _tts_tasks[0] = asyncio.create_task(
                            _synth_for_stream(_il1_choice.text, 0),
                        )
                        _filler_emitted = True
                        _stream_tts_used = True
                        logger.debug(
                            "IL-1 filler launched | session=%s | emotion=%s | text=%r",
                            session_id, current_emotion, _il1_choice.text,
                        )
                except Exception:
                    logger.debug(
                        "IL-1 filler scheduling failed for %s",
                        session_id, exc_info=True,
                    )

            # Thread session_mode into the stream so the call-mode prompt
            # modifier (short replies, difficulty-aware, phone register) is
            # actually applied. Without this the stream path silently reverted
            # to chat register even when user clicked "Звонок".
            _cp_s = state.get("custom_params") or {}
            _session_mode_s = _cp_s.get("session_mode") or "chat"
            _tone_s = _cp_s.get("tone")  # constructor v2, 2026-04-21
            async for token in generate_response_stream(
                system_prompt=extra_system,
                messages=messages,
                emotion_state=current_emotion,
                character_prompt_path=prompt_path,
                task_type="roleplay",
                prefer_provider=_prefer,
                session_mode=_session_mode_s,
                tone=_tone_s,
                # 2026-04-22: pass explicit difficulty from state so
                # build_call_mode_modifier sees custom-builder value
                # instead of always defaulting to 5.
                difficulty=state.get("base_difficulty"),
                # 2026-04-29 (TZ-4.5 PR 4): cross-session memory.
                persona_facts=_persona_facts,
            ):
                _streamed_text += token
                _chunk_buffer += token
                _tts_sentence_buffer += token

                # Text chunks to frontend — every ~40 chars or on sentence boundary
                if len(_chunk_buffer) >= 40 or (
                    _chunk_buffer.rstrip()
                    and _chunk_buffer.rstrip()[-1] in ".!?…"
                    and len(_chunk_buffer) > 10
                ):
                    await _send(ws, "character.response_chunk", {
                        "text": _chunk_buffer,
                    })
                    _chunk_buffer = ""

                # Streaming TTS — launch synth on sentence boundary
                if (
                    _tts_stream_enabled
                    and not _tts_disabled_due_to_error
                    and _tts_sentence_buffer.rstrip()
                    and _tts_sentence_buffer.rstrip()[-1] in ".!?…"
                ):
                    # Clean stage directions inline (may span tokens, so strip the whole buffer)
                    _clean_sent = _STAGE_DIR_RE.sub("", _tts_sentence_buffer).strip()
                    # Skip tiny fragments (e.g. "А.", "Да!") — too short for meaningful TTS
                    if len(_clean_sent) >= 10:
                        # Sprint 0 §5: AI-tell gate runs before TTS task launch.
                        # No-op when CALL_HUMANIZED_V2 is OFF (returns input).
                        _gated_sent = await _apply_call_scrub_gate(
                            _clean_sent, ws=ws, session_id=session_id,
                        )
                        if _gated_sent is None:
                            # Mode=drop matched — suppress audio for this sentence
                            # but DO advance the buffer so the next sentence starts fresh.
                            _tts_sentence_buffer = ""
                        else:
                            _idx = len(_tts_sent_indices)
                            _tts_sent_indices.append(_idx)
                            _tts_tasks[_idx] = asyncio.create_task(
                                _synth_for_stream(_gated_sent, _idx)
                            )
                            _tts_sentence_buffer = ""
                            _stream_tts_used = True
                            # Send any ready chunks without blocking the stream
                            await _flush_ordered_tts_chunks()

            # Flush remaining buffer (text)
            if _chunk_buffer:
                await _send(ws, "character.response_chunk", {
                    "text": _chunk_buffer,
                })

            # Flush trailing sentence without punctuation (rare)
            if (
                _tts_stream_enabled
                and not _tts_disabled_due_to_error
                and _tts_sentence_buffer.strip()
            ):
                _clean_sent = _STAGE_DIR_RE.sub("", _tts_sentence_buffer).strip()
                if len(_clean_sent) >= 10:
                    # Sprint 0 §5: AI-tell gate — same gate as the main loop.
                    _gated_sent = await _apply_call_scrub_gate(
                        _clean_sent, ws=ws, session_id=session_id,
                    )
                    if _gated_sent is not None:
                        _idx = len(_tts_sent_indices)
                        _tts_sent_indices.append(_idx)
                        _tts_tasks[_idx] = asyncio.create_task(
                            _synth_for_stream(_gated_sent, _idx)
                        )
                        _stream_tts_used = True

            # Text portion of LLM response is complete — let UI clear the
            # typing spinner NOW, before we wait for any trailing TTS audio.
            # This prevents "infinite loading" if TTS is slow: user sees the
            # response immediately, audio chunks arrive asynchronously.
            if _streamed_text.strip():
                try:
                    await _send(ws, "avatar.typing", {"is_typing": False})
                except Exception:
                    pass

            # Wait for all TTS tasks to finish, emitting in-order as they complete.
            # Hard timeout prevents hanging the session if TTS provider is slow.
            if _stream_tts_used:
                _last_idx = len(_tts_sent_indices) - 1 if _tts_sent_indices else None
                if _tts_tasks:
                    pending = [t for t in _tts_tasks.values() if not t.done()]
                    if pending:
                        # Overall budget for TTS tail: cap at 15s to keep UI responsive.
                        _tail_budget = min(float(settings.elevenlabs_timeout_seconds) * 2, 15.0)
                        try:
                            await asyncio.wait_for(
                                asyncio.gather(*pending, return_exceptions=True),
                                timeout=_tail_budget,
                            )
                        except asyncio.TimeoutError:
                            logger.warning(
                                "Stream TTS tail timeout %.1fs — cancelling %d pending tasks, session=%s",
                                _tail_budget, len(pending), session_id,
                            )
                            for t in pending:
                                if not t.done():
                                    t.cancel()
                            # Drain cancelled without blocking
                            try:
                                await asyncio.wait_for(
                                    asyncio.gather(*pending, return_exceptions=True),
                                    timeout=2.0,
                                )
                            except asyncio.TimeoutError:
                                pass
                await _flush_ordered_tts_chunks(last_idx=_last_idx)

            _stream_latency = int((time.monotonic() - _start_stream) * 1000)
            if _streamed_text.strip():
                _stream_ok = True
                # Build LLMResponse-compatible object for rest of pipeline
                llm_result = LLMResponse(
                    content=_streamed_text,
                    model=settings.local_llm_model if _prefer == "local" else settings.gemini_model,
                    input_tokens=_est_tokens,
                    output_tokens=len(_streamed_text) // 2,
                    latency_ms=_stream_latency,
                    is_fallback=False,
                )
        except Exception as stream_err:
            logger.debug("Streaming failed, falling back to blocking: %s", stream_err)
            _stream_tts_used = False

        if not _stream_ok:
            # Blocking fallback.
            # Phase 1.7 (2026-04-18): if MCP tooling is enabled, route through
            # ``generate_with_tool_dispatch`` so the LLM can invoke registered
            # tools (generate_image, get_geolocation_context, etc.). The
            # helper transparently falls back to a plain call when no tools
            # are registered, so flipping ``mcp_enabled=True`` is zero-risk
            # before Phase 2 ships concrete tools.
            _use_mcp = (
                settings.mcp_enabled
                and _prefer != "local-ollama"  # Ollama has no tool support
            )
            if _use_mcp:
                try:
                    from app.mcp import ToolContext
                    from app.mcp.registry import ToolRegistry
                    from app.services.llm_tools import generate_with_tool_dispatch
                    from app.ws.tool_events import make_tool_emit

                    if ToolRegistry.all():
                        _tool_ctx = ToolContext(
                            session_id=str(session_id),
                            user_id=str(state.get("user_id") or ""),
                            manager_ip=state.get("manager_ip"),
                            request_id=str(session_id),
                        )
                        llm_result = await generate_with_tool_dispatch(
                            system_prompt=extra_system,
                            messages=messages,
                            ctx=_tool_ctx,
                            provider="local" if _prefer == "local" else "openai",
                            emit=make_tool_emit(ws),
                        )
                    else:
                        _use_mcp = False  # fall through to legacy path
                except Exception as _mcp_err:
                    logger.warning(
                        "MCP dispatch failed for session %s, falling back: %s",
                        session_id, _mcp_err, exc_info=True,
                    )
                    _use_mcp = False

            if not _use_mcp:
                # Pass session_mode so llm.py can append the call-mode
                # prompt modifier for phone-call sessions (short, colloquial,
                # interrupting replies with edge-case handling).
                _cp = state.get("custom_params") or {}
                _session_mode = _cp.get("session_mode") or "chat"
                _tone = _cp.get("tone")  # constructor v2, 2026-04-21
                llm_result = await generate_response(
                    system_prompt=extra_system,
                    messages=messages,
                    emotion_state=current_emotion,
                    character_prompt_path=prompt_path,
                    task_type="roleplay",
                    prefer_provider=_prefer,
                    session_mode=_session_mode,
                    tone=_tone,
                    # 2026-04-22: see generate_response_stream call above.
                    difficulty=state.get("base_difficulty"),
                    # 2026-04-29 (TZ-4.5 PR 4): cross-session memory.
                    persona_facts=_persona_facts,
                )
    except LLMError as e:
        logger.error("LLM failed for session %s: %s", session_id, e)
        state["llm_busy"] = False
        await update_activity(session_id)  # reset silence timer so watchdog doesn't fire from our own slow LLM
        await _send(ws, "avatar.typing", {"is_typing": False})
        fallback_content = "Секунду... мне нужно собраться с мыслями."
        await _send(ws, "character.response", {
            "content": fallback_content,
            "emotion": current_emotion,
            "is_fallback": True,
        })
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

    # Stop typing indicator + release silence watchdog + reset user-silence timer
    # (otherwise the next ~60s of user thinking count from BEFORE the LLM started)
    state["llm_busy"] = False
    await update_activity(session_id)
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

        # TZ-4 D7.6 — conversation policy audit hook. Runs after the
        # message is durably saved so a policy-engine outage cannot
        # roll back the user's reply. Side-channel only: writes
        # ``conversation.policy_violation_detected`` events + WS
        # outbox frames + bumps SessionPersonaSnapshot.mutation_
        # blocked_count when the audit catches an identity drift.
        # Never raises into this handler — the hook catches its own
        # exceptions and logs them.
        try:
            from app.services.conversation_audit_hook import (
                audit_and_publish_assistant_reply,
                previous_assistant_replies_from_history,
            )
            _session_mode = (state.get("session_mode") or "chat")
            _user_id = state.get("user_id")
            if _user_id is not None:
                await audit_and_publish_assistant_reply(
                    db,
                    session_id=session_id,
                    user_id=_user_id,
                    reply=llm_result.content,
                    previous_assistant_replies=
                        previous_assistant_replies_from_history(messages, limit=5),
                    mode=_session_mode,
                )
                await db.commit()
        except Exception:
            logger.exception(
                "conversation_audit_hook crashed for session %s — swallowing",
                session_id,
            )

        # TZ-4.5 PR 3 — persona fact extraction. Same post-reply
        # placement as the audit hook above: the manager has already
        # seen the streamed reply by the time we reach this line, so
        # the ~600ms extractor LLM call doesn't block any UX. Facts
        # land in MemoryPersona.confirmed_facts so PR 4 can inject
        # them into the system prompt for the NEXT manager turn —
        # closing the "AI remembers between calls" loop.
        #
        # The extractor is best-effort. No client / timeout / LLM
        # error / optimistic-concurrency conflict → zero facts
        # committed and the call continues unaffected.
        try:
            from app.services.persona_fact_extractor import (
                extract_and_commit_facts_for_turn,
            )
            _user_id = state.get("user_id")
            _manager_message = (
                messages[-1]["content"]
                if messages and messages[-1].get("role") == "user"
                else ""
            )
            if _user_id is not None and _manager_message:
                # Re-load persona — audit_hook may have bumped
                # mutation_blocked_count (snapshot side) but persona
                # state is what lock_slot needs. Fresh read avoids
                # PersonaConflict from the audit-hook's own writes.
                from app.services import persona_memory as _pm
                _snapshot = await _pm.get_snapshot(db, session_id=session_id)
                _persona = (
                    await _pm.get_for_lead(db, lead_client_id=_snapshot.lead_client_id)
                    if _snapshot is not None and _snapshot.lead_client_id is not None
                    else None
                )
                if _persona is not None:
                    await extract_and_commit_facts_for_turn(
                        db,
                        session_id=session_id,
                        user_id=_user_id,
                        manager_message=_manager_message,
                        persona=_persona,
                    )
                    await db.commit()
        except Exception:
            logger.exception(
                "persona_fact_extractor crashed for session %s — swallowing",
                session_id,
            )

    # ─── V3 Emotion Engine with Trigger Detection ───
    new_emotion = current_emotion
    emotion_meta = {}
    trigger_result = None

    try:
        from app.services.trigger_detector import detect_triggers

        # Get the manager's message that triggered this response
        manager_message = messages[-1]["content"] if messages else ""

        # Skip LLM-based trigger detection when using local provider (single-concurrent)
        # to avoid 60+s latency per message (character response + trigger + trap = 3 serial LLM calls)
        _skip_llm_detection = settings.local_llm_enabled and not llm_result.is_fallback

        trigger_result = await detect_triggers(
            manager_message=manager_message,
            client_message=llm_result.content,
            archetype_code=archetype_code or "skeptic",
            emotion_state=current_emotion,
            response_time_ms=llm_result.latency_ms,
            client_name=state.get("client_name"),
            skip_llm=_skip_llm_detection,
        )

        # ── Merge trap-originated emotion triggers (fell/dodged) ──
        trap_emotion_triggers = state.pop("_trap_emotion_triggers", [])
        all_triggers = list(trigger_result.triggers) if (trigger_result and trigger_result.triggers) else []
        if trap_emotion_triggers:
            all_triggers.extend(trap_emotion_triggers)
            logger.debug("Merged trap emotion triggers into V3 engine: %s", trap_emotion_triggers)

        # 2026-04-20: surface trigger detection at INFO level so a flat
        # emotion chart is immediately diagnosable from logs. Previously
        # the only signal was a DEBUG line inside the detector itself,
        # which made "why did my session graph stay cold?" invisible.
        logger.info(
            "emotion_pipeline session=%s method=%s confidence=%.2f triggers=%s trap=%s skip_llm=%s",
            session_id,
            getattr(trigger_result, "detection_method", "n/a") if trigger_result else "none",
            getattr(trigger_result, "confidence", 0.0) if trigger_result else 0.0,
            all_triggers,
            trap_emotion_triggers,
            _skip_llm_detection,
        )

        # Phase F1 (2026-04-20): capture rudeness detection BEFORE the
        # emotion engine — even if the client doesn't hang up on THIS
        # turn, we need to remember the manager was rude so the final
        # session report + judge can factor that in. Previously the flag
        # was only set inside the hangup branch, which meant "rude but
        # didn't escalate to hangup" was invisible.
        if "insult" in all_triggers or "counter_aggression" in all_triggers:
            state["rudeness_detected"] = True
            logger.info(
                "Rudeness detected: session=%s, triggers=%s",
                session_id, [t for t in all_triggers if t in ("insult", "counter_aggression")],
            )

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
    #
    # 2026-04-22 DEMO GRACE PERIOD: on the first 4 user messages we never
    # let the client hang up — downgrade to hostile + warning instead. This
    # gives the manager room to recover from a single rough opening turn
    # during a product showcase. Adjust _HANGUP_GRACE_MIN_MESSAGES to tune.
    _HANGUP_GRACE_MIN_MESSAGES = 4
    if new_emotion == "hangup" and state.get("message_count", 0) < _HANGUP_GRACE_MIN_MESSAGES:
        logger.info(
            "hangup suppressed by demo grace period: session=%s msg_count=%d",
            session_id, state.get("message_count", 0),
        )
        # Keep the client in hostile state with a visible warning so the
        # manager sees that escalation happened — just doesn't end the call.
        new_emotion = "hostile"
        try:
            await _send(ws, "client.hangup_warning", {
                "message": "Я начинаю терять терпение. Будьте осторожнее.",
                "emotion": "hostile",
                "severity": 0.75,
            })
        except Exception:
            logger.debug("hangup_warning send failed (non-fatal)", exc_info=True)
        # Fall through — new_emotion is now "hostile", so the `if new_emotion
        # == "hangup"` block below simply doesn't execute.

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
                task_type="simple",
                prefer_provider="local",
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
            # Phase F1 (2026-04-20): CRITICAL fix — the `rudeness_detected`
            # flag was initialised in SessionResult and read at session-end
            # but NEVER written. This meant post-match analysis couldn't
            # see that the manager had been rude. Now we flip it here so
            # judge + results page can show "you were rude → client hung
            # up" feedback instead of a generic "client decided to end".
            state["rudeness_detected"] = True
        elif "counter_aggression" in _triggers:
            hangup_reason = "Клиент ответил на вашу агрессию"
            state["rudeness_detected"] = True
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
        if is_tts_available() and _user_tts_pref:
            try:
                _tts_res = await get_tts_audio_b64(
                    hangup_phrase, str(session_id),
                    emotion="hangup",
                    active_factors=_call_tts_factors(state),
                )
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
            # Single call: end session and signal main loop to stop
            logger.info("HANGUP single | session=%s | reason=%s", session_id, hangup_reason)
            await _handle_session_end(ws, {}, state)
            state["_should_stop"] = True  # Signal main loop to break (C3 fix)

        return  # Stop — do not continue with normal flow
    # ─── END HANGUP DETECTION ───

    # 2026-04-22: AI-content-based farewell detection. The emotion FSM may not
    # transition to "hangup" (e.g. weights softened, grace period), but the
    # LLM can still generate a farewell phrase on its own ("Всё, кладу
    # трубку", "До свидания"). Without this, the AI says goodbye in text but
    # the session stays open.
    #
    # 2026-04-22 (v2): Tightened to avoid false positives — the v1 detector
    # fired on the SECOND turn whenever the LLM generated an aggressive
    # response containing "до свидания" as part of an ultimatum ("иначе я
    # кладу трубку"). Now we require:
    #   1) message_count >= 4 (4+ user replies — gives real conversation room)
    #   2) farewell phrase appears in the LAST sentence of the reply
    #      (not buried inside an aggressive mid-reply ultimatum)
    #   3) reply isn't a question (questions imply continuation)
    _AI_FAREWELL_PATTERNS = (
        "до свидания", "всего доброго", "всего хорошего", "всех благ",
        "кладу трубку", "вешаю трубку", "повешу трубку", "положу трубку",
        "всё, я заканчиваю", "разговор окончен", "разговор закончен",
        "больше не звоните", "не перезванивайте", "до встречи",
        "удачи вам", "бывайте", "прощайте",
    )
    _ai_reply_text = (llm_result.content or "").strip()
    _ai_reply_lower = _ai_reply_text.lower()
    # ── P1 (2026-04-29) Coaching mistake detector — record AI turn ──
    # Feed assistant char volume into the talk-ratio rolling window so
    # ``talk_ratio_high`` mistake fires when manager dominates the call.
    if settings.coaching_mistake_detector_v1 and _ai_reply_text:
        try:
            from app.services.mistake_detector import record_assistant_turn as _coach_rec_a
            from app.core.redis_pool import get_redis as _get_redis_coach_rec
            await _coach_rec_a(_get_redis_coach_rec(), str(session_id), _ai_reply_text)
        except Exception:
            logger.debug("Coaching record_assistant_turn failed for %s", session_id, exc_info=True)
    # Split into sentences and only look at the LAST one.
    _last_sentence = _ai_reply_lower
    for _delim in (".", "!", "?", "…"):
        _parts = [p.strip() for p in _last_sentence.split(_delim) if p.strip()]
        if _parts:
            _last_sentence = _parts[-1]
    _ai_farewell_hit = any(p in _last_sentence for p in _AI_FAREWELL_PATTERNS)
    _is_question = _ai_reply_text.rstrip().endswith("?")
    _msg_count_for_ai_farewell = state.get("message_count", 0)
    # 2026-04-22 (v3): tightened further after demo-session regression.
    # Ghost-client / skeptic archetypes naturally generate aggressive
    # "Всё, до свидания!" ultimatums in the first 1-2 turns. v2's
    # message_count >= 4 was still firing early because sequence_number
    # accounting differed from what we expected. Now:
    #   - message_count >= 8 (roughly 4 real exchanges)
    #   - AND emotion must already be "hostile" (real escalation, not
    #     LLM theatrics)
    # Net effect: AI-farewell auto-end only fires when the client has
    # genuinely been pushed to hostile over many turns — the common
    # "LLM improvises a dramatic exit" case is now IGNORED and the
    # session continues. For rare cases the emotion FSM can still
    # transition to hangup directly (that handler runs above and is
    # unaffected by this check).
    _AI_FAREWELL_MIN_MESSAGES = 8
    _can_ai_end = (
        _ai_farewell_hit
        and not _is_question
        and _msg_count_for_ai_farewell >= _AI_FAREWELL_MIN_MESSAGES
        and (current_emotion == "hostile")
        and not state.get("user_initiated_farewell")
        and not state.get("ai_initiated_farewell")
    )
    logger.debug(
        "ai_farewell check session=%s hit=%s qtn=%s msgs=%d emo=%s → %s",
        session_id, _ai_farewell_hit, _is_question,
        _msg_count_for_ai_farewell, current_emotion, _can_ai_end,
    )
    if _can_ai_end:
        state["ai_initiated_farewell"] = True
        # Phase 1 (Roadmap §6.3 path 4): previously this branch didn't stamp
        # ``call_outcome`` before delegating to ``_handle_session_end``, so
        # the downstream outcome fell back to whatever was in ``state``
        # (often ``last_call_outcome`` from a prior call in the story).
        # Force the explicit "hangup" fact so follow-up + finalize see the
        # right outcome.
        state["call_outcome"] = "hangup"
        logger.info(
            "AI-initiated farewell detected (session=%s, content snippet=%r) — "
            "auto-firing session.end after current TTS plays.",
            session_id, llm_result.content[:80],
        )
        # Send a hangup notification so the frontend shows the modal/redirect
        # consistently with FSM-driven hangups.
        try:
            await _send(ws, "client.hangup", {
                "reason": "Клиент сам завершил разговор",
                "emotion": current_emotion,
                "hangup_phrase": llm_result.content,
                "call_can_continue": False,
                "triggers": [],
            })
        except Exception:
            logger.debug("client.hangup send failed (non-fatal)", exc_info=True)
        # Schedule auto-end after TTS finishes — same pattern as user farewell.
        async def _auto_end_after_ai_farewell():
            try:
                await asyncio.sleep(3.5)  # let TTS of farewell finish playing
                await _handle_session_end(ws, {}, state)
                state["_should_stop"] = True
            except Exception:
                logger.exception("auto session.end after AI farewell failed (session=%s)", session_id)
        asyncio.create_task(_auto_end_after_ai_farewell())

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

    # 2026-04-20 defense-in-depth: decode any HTML entities the LLM may have
    # emitted (e.g. `&quot;`, `&amp;`, `&#39;`). Keeps DB / Redis / WS payload
    # in clean Unicode so downstream consumers (frontend, TTS, analytics)
    # never see literal `&quot;` in text. See XHUNTER_HTML_ENTITIES_FIX_TZ §3.5.
    clean_content = html.unescape(clean_content)

    await _send(ws, "character.response", {
        "content": clean_content,
        "emotion": new_emotion,
        # 2026-04-20: include sequence_number so the frontend can sort the
        # bubble into the correct slot. Without this, the assistant bubble
        # fell back to `?? 0` in the store's sort and could appear before
        # the user turn that triggered it.
        "sequence_number": state.get("message_count"),
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
    # Phase 2: Sentence-level TTS pipelining — synthesize and send per-sentence
    # for faster first-audio (~1.5s instead of 5-13s)
    user_tts_pref = state.get("user_prefs", {}).get("tts_enabled", True)
    tts_available = is_tts_available()
    # tts_enabled = user has TTS turned on AND backend has at least one
    # provider configured (ElevenLabs or navy). Don't require elevenlabs_enabled
    # explicitly — navy-only setups would be blocked otherwise.
    tts_enabled = tts_available and user_tts_pref
    logger.info(
        "TTS_CHECK | session=%s | is_tts_available=%s | tts_enabled=%s",
        session_id, tts_available, tts_enabled,
    )
    # If streaming TTS already dispatched all sentences during LLM stream,
    # skip the post-LLM sentence pipeline to avoid double-synthesis.
    if tts_available and tts_enabled and not _stream_tts_used:
        try:
            # Split into sentences for pipelined TTS
            import re as _re
            _sentences = _re.split(r'(?<=[.!?…])\s+', clean_content)
            # Merge very short sentences with next (avoid tiny TTS calls)
            _merged: list[str] = []
            for _s in _sentences:
                if _merged and len(_merged[-1]) < 30:
                    _merged[-1] = _merged[-1] + " " + _s
                else:
                    _merged.append(_s)
            if not _merged:
                _merged = [clean_content]

            if len(_merged) <= 1:
                # Single sentence — no pipelining benefit, use original path.
                # Sprint 0 §5: AI-tell gate (parity with streaming path).
                _gated_single = await _apply_call_scrub_gate(
                    clean_content, ws=ws, session_id=session_id,
                )
                tts_result = None
                if _gated_single is not None:
                    tts_result = await get_tts_audio_b64(
                        _gated_single, str(session_id),
                        emotion=new_emotion,
                        active_factors=_call_tts_factors(state),
                    )
                if tts_result and tts_result.get("audio"):
                    await _send(ws, "tts.audio", {
                        "audio_b64": tts_result["audio"],
                        "format": tts_result.get("format", "mp3"),
                        "emotion": tts_result.get("emotion"),
                        "voice_params": tts_result.get("voice_params"),
                        "duration_ms": tts_result.get("duration_ms"),
                        "text": clean_content,
                    })
                else:
                    # Journal #C: was silent — user heard nothing and wondered why.
                    logger.warning(
                        "TTS_RESULT_EMPTY session=%s path=single result=%s text_preview=%r",
                        session_id,
                        "None" if tts_result is None else f"dict(keys={list(tts_result.keys())})",
                        clean_content[:60],
                    )
            else:
                # Multiple sentences — synthesize in parallel, send sequentially
                async def _synth_sentence(_text: str, _idx: int) -> tuple[int, dict | None]:
                    try:
                        # Sprint 0 §5: gate each parallel sentence too.
                        _gated_text = await _apply_call_scrub_gate(
                            _text, ws=ws, session_id=session_id,
                        )
                        if _gated_text is None:
                            return (_idx, None)
                        result = await get_tts_audio_b64(
                            _gated_text, str(session_id),
                            emotion=new_emotion,
                            active_factors=_call_tts_factors(state),
                        )
                        return (_idx, result)
                    except Exception as _e:
                        # Journal #C: was `return (_idx, None)` without logging.
                        # If every sentence fails, the whole reply was silent
                        # and we had no idea why. Now at least one log per fail.
                        logger.warning(
                            "TTS_SYNTH_FAIL session=%s idx=%d err=%s",
                            session_id, _idx, _e,
                            exc_info=True,
                        )
                        return (_idx, None)

                _tasks = [
                    asyncio.create_task(_synth_sentence(s, i))
                    for i, s in enumerate(_merged)
                ]
                # Send audio chunks as they complete, but IN ORDER
                _results: dict[int, dict | None] = {}
                _next_to_send = 0
                _sent_any = False
                for coro in asyncio.as_completed(_tasks):
                    idx, result = await coro
                    _results[idx] = result
                    # Send any consecutive ready chunks
                    while _next_to_send in _results:
                        _r = _results[_next_to_send]
                        if _r and _r.get("audio"):
                            await _send(ws, "tts.audio_chunk", {
                                "audio_b64": _r["audio"],
                                "format": _r.get("format", "mp3"),
                                "sentence_index": _next_to_send,
                                "is_last": _next_to_send == len(_merged) - 1,
                                "text": _merged[_next_to_send],
                            })
                            _sent_any = True
                        _next_to_send += 1
                if not _sent_any:
                    # None of the N sentences produced audio — nothing reached UI.
                    logger.warning(
                        "TTS_ALL_EMPTY session=%s sentences=%d (user heard silence)",
                        session_id, len(_merged),
                    )

        except TTSQuotaExhausted:
            logger.warning("TTS quota exhausted for session %s, frontend fallback", session_id)
            await _send(ws, "tts.fallback", {"reason": "quota_exhausted"})
        except TTSError as e:
            logger.error("TTS error for session %s: %s", session_id, e)
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
        # v6 extensions: intensity + compound + micro-expressions
        try:
            _energy_val = emotion_meta.get("energy_after", 0.0)
            _thresh_pos = emotion_meta.get("threshold_pos", 1.0)
            _thresh_neg = emotion_meta.get("threshold_neg", -1.0)
            _intensity_level, _intensity_norm = compute_intensity(
                _energy_val, _thresh_pos, _thresh_neg,
            )
            _em_msg["intensity"] = _intensity_level.value  # "low"/"medium"/"high"
            _em_msg["intensity_value"] = round(_intensity_norm, 3)

            # Fix: use full recent states history (not just [prev, new])
            _recent_history = state.get("_emotion_history", [])
            _recent_history.append(new_emotion)
            if len(_recent_history) > 10:
                _recent_history = _recent_history[-10:]
            state["_emotion_history"] = _recent_history

            _compound = detect_compound_emotion(
                current_state=new_emotion,
                intensity=_intensity_level,
                intensity_value=_intensity_norm,
                recent_states=_recent_history,
                fake_active=emotion_meta.get("is_fake", False),
                ocean_profile=state.get("ocean_profile"),
                recent_triggers=[t for t in (trigger_result.triggers if trigger_result else [])],
            )
            _em_msg["compound"] = _compound.code if _compound else None

            # v6: MicroExpression queue
            try:
                from app.services.emotion_v6 import MicroExpressionQueue, MICRO_EXPRESSIONS
                _micro_q = state.get("_micro_queue")
                if _micro_q is None:
                    _micro_q = MicroExpressionQueue()
                elif isinstance(_micro_q, dict):
                    _micro_q = MicroExpressionQueue.from_dict(_micro_q)

                _msg_idx = emotion_meta.get("message_index", 0)
                _active_triggers = emotion_meta.get("triggers_applied", [])
                # Try triggering new micro-expressions
                for _me_code, _me in MICRO_EXPRESSIONS.items():
                    _micro_q.try_trigger(_me_code, _me, _active_triggers, _msg_idx)
                # Tick existing ones
                active_micros = _micro_q.tick()
                state["_micro_queue"] = _micro_q.to_dict()

                if active_micros:
                    _em_msg["micro_expressions"] = [
                        {"code": m.expression, "remaining": m.remaining_messages}
                        for m in active_micros
                    ]
            except Exception:
                pass  # micro-expressions are non-critical

            # v6: Store intensity for TRAP_INTENSITY_MULTIPLIER
            state["_current_intensity"] = _intensity_level.value

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
            # 2026-04-23 Sprint 3 (plan §3.1.5) — pass stage-scoped message
            # count so _check_script_stuck can detect «завис на этапе».
            # stage_tracker stores start msg index per stage — compute
            # messages on current stage = total - stage_started_at.
            _sm_by_stage = state.get("stage_message_counts") or {}  # may be empty
            _cur_stage_num = state.get("current_stage")  # 1-based
            _cur_stage_msg = None
            if _cur_stage_num is not None:
                # Prefer live state from stage_tracker; fallback to total.
                _started_at = (state.get("stage_started_at_msg") or {}).get(
                    str(_cur_stage_num), (state.get("stage_started_at_msg") or {}).get(_cur_stage_num)
                )
                if isinstance(_started_at, int):
                    _cur_stage_msg = max(0, msg_count - _started_at)
            _whisper = await _whisper_engine.generate_whisper(
                session_id=str(session_id),
                current_stage=state.get("current_stage_name", "greeting"),
                client_emotion=new_emotion,
                last_client_message=clean_content,  # AI client's response
                last_manager_message=messages[-1]["content"] if messages else "",
                manager_message_count=msg_count,
                difficulty=state.get("base_difficulty", 5),
                whispers_enabled=state.get("whispers_enabled", True),
                stage_message_count=_cur_stage_msg,
                stage_number=_cur_stage_num if isinstance(_cur_stage_num, int) else None,
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
            logger.warning(
                "Adaptive difficulty triggered hangup | session=%s | bad_streak=%d",
                session_id, ad_state.bad_streak,
            )
            # Set Redis flag — next reply will force emotion to "hangup"
            # and trigger the full hangup flow (character.response + client.hangup + session_end).
            try:
                await _r_ad.setex(f"session:{session_id}:force_hangup", 600, "adaptive")
                # Send early warning so the manager sees "client is about to hang up"
                await _send(ws, "client.hangup_warning", {
                    "reason": "adaptive_difficulty",
                    "bad_streak": ad_state.bad_streak,
                })
            except Exception:
                # FIND-008 fix (2026-04-18): Redis/WS send failures here are non-fatal —
                # session continues without adaptive hangup. Log so we can track frequency.
                logger.warning("training.adaptive_difficulty: hangup warning dispatch failed for session %s", session_id, exc_info=True)
    except Exception:
        logger.warning("Adaptive difficulty failed for session %s", session_id, exc_info=True)


async def _silence_watchdog(
    ws: WebSocket,
    session_id: uuid.UUID,
    state: dict,
    stop_event: asyncio.Event,
    state_lock: asyncio.Lock | None = None,
) -> None:
    """Background task: detect prolonged silence.

    - 30s silence → avatar says "Алло?" (character.response)
    - 60s silence → send silence.timeout modal ("Continue?")
    - Grace period after modal: SILENCE_GRACE_SEC to wait for user response
    - If still silent → end session AND send session.ended so the UI unsticks
    """
    warned = False
    timeout_modal_sent_at: float | None = None  # when the modal was shown
    SILENCE_GRACE_SEC = 20  # user has this many seconds to click "continue"

    while not stop_event.is_set():
        await asyncio.sleep(5)
        if stop_event.is_set():
            break

        # Skip silence counting while LLM is mid-response. Slow local models
        # (Gemma on CPU) can take 20-40s to answer — that's not user silence.
        if state.get("llm_busy"):
            timeout_modal_sent_at = None  # reset grace if we re-entered busy
            continue

        from app.services.session_manager import get_last_activity_time

        last_activity = await get_last_activity_time(session_id)
        if last_activity is None:
            continue

        elapsed = time.time() - last_activity

        # User responded after the modal — cancel the grace countdown
        if timeout_modal_sent_at is not None and last_activity > timeout_modal_sent_at:
            timeout_modal_sent_at = None
            warned = False

        if elapsed >= SILENCE_TIMEOUT_SEC and not stop_event.is_set():
            if timeout_modal_sent_at is None:
                # First time crossing the threshold — show the modal and start grace.
                timeout_modal_sent_at = time.time()
                await _send(ws, "silence.timeout", {
                    "message": "Вы давно молчите. Хотите продолжить тренировку?",
                    "timeout_seconds": SILENCE_GRACE_SEC,
                })
                continue

            # Grace period expired — user didn't respond to the modal.
            if time.time() - timeout_modal_sent_at < SILENCE_GRACE_SEC:
                continue

            async with async_session() as db:
                await end_session(session_id, db, status=SessionStatus.abandoned)
                # Phase 1 (Roadmap §6.3 path 5): silence watchdog used to
                # skip the completion tail entirely — no follow-up reminder,
                # no CRM row, no ``EVENT_TRAINING_COMPLETED``. Managers
                # literally couldn't tell a silent-timeout session happened.
                # Load the row fresh and run the policy so terminal columns +
                # canonical DomainEvent land. Wrapped in try/except because
                # the legacy timeout behaviour must survive even if policy
                # raises.
                try:
                    from app.models.training import TrainingSession
                    from app.services.completion_policy import (
                        CompletedVia,
                        TerminalOutcome,
                        TerminalReason,
                        finalize_training_session,
                    )

                    _sess = await db.get(TrainingSession, session_id)
                    if _sess is not None:
                        await finalize_training_session(
                            db,
                            session=_sess,
                            outcome=TerminalOutcome.timeout,
                            reason=TerminalReason.silence_timeout,
                            completed_via=CompletedVia.timeout,
                            manager_id=_sess.user_id,
                        )
                except Exception:
                    logger.warning(
                        "completion_policy stamp failed (silence) for %s",
                        session_id, exc_info=True,
                    )
                await db.commit()
            # CRITICAL: notify the client so the "loading" modal can clear and
            # the page can redirect. Without this the UI hangs forever.
            await _send(ws, "session.ended", {
                "reason": "silence_timeout",
                "status": "abandoned",
                "message": "Сессия завершена из-за длительного бездействия.",
            })
            if state_lock:
                async with state_lock:
                    state["active"] = False
            else:
                state["active"] = False
            stop_event.set()
            break

        elif elapsed >= SILENCE_WARNING_SEC and not warned and not state.get("text_mode", False):
            # 30s — avatar says emotion-aware silence prompt (voice mode only)
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
            if is_tts_available():
                try:
                    tts_result = await get_tts_audio_b64(
                        phrase, str(session_id),
                        active_factors=_call_tts_factors(state),
                    )
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


def _build_client_profile_prompt(profile, ambient_ctx: dict | None = None) -> str:
    """Build extra system prompt context from generated client profile.

    This text gets appended to the character prompt + guardrails,
    giving the LLM specific details about WHO the client is.
    The manager doesn't see this — only the LLM does.

    2026-04-21: ``ambient_ctx`` carries the 5 atmospheric parameters from
    the character builder that do NOT live on ClientProfile (emotion_preset,
    bg_noise, time_of_day, client_fatigue, debt_stage). They are injected
    as a separate "Атмосфера" block so the LLM adapts the *moment* of the
    call, not the client's permanent identity.
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

    # FIX P1: inject hidden_objections — AI-client should reveal them gradually, not ignore
    if hasattr(profile, "hidden_objections") and profile.hidden_objections:
        objections_text = "; ".join(profile.hidden_objections[:5])
        parts.append(
            f"\nСкрытые возражения (НЕ озвучивай их сразу, раскрывай постепенно по ходу диалога): {objections_text}."
        )

    # ── Атмосфера: текущее состояние клиента и среды ─────────────────
    # Constructor v2 parameters (2026-04-21). These shape the *moment*
    # of the call, not the client's identity — mood, tiredness, background
    # noise, time of day, stage of the debt process. None of them live on
    # ClientProfile; they ride on TrainingSession.custom_params and are
    # resolved into human-readable Russian labels here.
    if ambient_ctx:
        _EMOTION_LABEL = {
            "neutral": "нейтральное", "anxious": "тревожное", "angry": "злое",
            "hopeful": "надеющееся", "tired": "уставшее", "rushed": "спешит",
            "trusting": "доверчивое",
        }
        _NOISE_LABEL = {
            "none": "тишина", "office": "офисный шум (коллеги, клавиатура)",
            "street": "шум улицы (машины, люди)", "children": "дети играют/плачут рядом",
            "tv": "работает телевизор",
        }
        _TIME_LABEL = {
            "morning": "утро, 7–11 ч.", "afternoon": "день, 12–17 ч.",
            "evening": "вечер, 18–21 ч.", "night": "ночь, позже 22 ч. — клиент удивлён звонку",
        }
        _FATIGUE_LABEL = {
            "fresh": "бодр, полон сил", "normal": "в обычном тонусе",
            "tired": "уставший, реакции замедлены", "exhausted": "вымотан, раздражается от мелочей",
        }
        _DEBT_STAGE_LABEL = {
            "pre_court": "долг пока не дошёл до суда",
            "court_started": "по долгу идёт судебный процесс",
            "execution": "исполнительное производство: приставы уже работают",
            "arrest": "наложен арест на имущество и счета",
        }

        ambient_parts = []
        e = ambient_ctx.get("emotion_preset")
        if e and e in _EMOTION_LABEL:
            ambient_parts.append(f"- Настроение на момент звонка: {_EMOTION_LABEL[e]}.")
        n = ambient_ctx.get("bg_noise")
        if n and n in _NOISE_LABEL and n != "none":
            ambient_parts.append(f"- Фоновый шум: {_NOISE_LABEL[n]}. Иногда это отвлекает клиента.")
        t = ambient_ctx.get("time_of_day")
        if t and t in _TIME_LABEL:
            ambient_parts.append(f"- Время суток: {_TIME_LABEL[t]}.")
        f = ambient_ctx.get("client_fatigue")
        if f and f in _FATIGUE_LABEL and f != "normal":
            ambient_parts.append(f"- Физическое состояние: {_FATIGUE_LABEL[f]}.")
        ds = ambient_ctx.get("debt_stage")
        if ds and ds in _DEBT_STAGE_LABEL:
            ambient_parts.append(f"- Стадия долга: {_DEBT_STAGE_LABEL[ds]}.")

        if ambient_parts:
            parts.append("\n## Атмосфера (состояние клиента и среды)")
            parts.extend(ambient_parts)
            parts.append(
                "Эти условия должны читаться в поведении клиента: длина реплик, "
                "паузы, готовность слушать, отвлечения, общий тон — всё подстраивается "
                "под текущий момент. НЕ проговаривай их напрямую ('я устал', 'у меня дети кричат') "
                "— это должно чувствоваться в манере речи."
            )

    parts.append(
        "\nИспользуй эти данные для реалистичных ответов. "
        "НЕ раскрывай менеджеру свои страхи и мягкую точку напрямую — "
        "дай ему возможность выяснить это через диалог."
    )

    return "\n".join(parts)


async def _clone_source_session_profile(
    source_session_id: uuid.UUID,
    new_session_id: uuid.UUID,
    db: AsyncSession,
):
    """Clone the ClientProfile of a previous session onto a fresh retrain session.

    Bug fix (2026-04-29): clicking «Повторить звонок» on /results created a
    new session that copied scenario/archetype/profession from the source
    but RAN THE PROFILE GENERATOR FRESH — so the manager saw the old
    client's name on the results card but a different name (and debt
    amounts, fears, soft_spot, etc.) inside the actual call. The fix:
    when the new session's ``source_session_id`` is set, clone the source's
    ClientProfile row identity-for-identity — same approach used by
    ``_clone_story_profile_for_session`` for multi-call story mode.

    The clone is full-fidelity: name, age, debt, creditors, fears, traps,
    objection chain — everything that defines "who is this client" carries
    over. The retrain therefore behaves like "another call with the SAME
    person", not "a new random person from the same scenario".

    Returns:
        ClientProfile ORM instance (added + flushed) on success, ``None``
        if the source session has no profile (legacy/unfinished session).
    """
    from app.models.roleplay import ClientProfile

    src_result = await db.execute(
        select(ClientProfile).where(ClientProfile.session_id == source_session_id)
    )
    src = src_result.scalar_one_or_none()
    if src is None:
        return None

    cloned = ClientProfile(
        session_id=new_session_id,
        full_name=src.full_name,
        age=src.age,
        gender=src.gender,
        city=src.city,
        archetype_code=src.archetype_code,
        profession_id=src.profession_id,
        education_level=src.education_level,
        legal_literacy=src.legal_literacy,
        total_debt=src.total_debt,
        creditors=src.creditors,
        income=src.income,
        income_type=src.income_type,
        property_list=src.property_list,
        fears=src.fears,
        soft_spot=src.soft_spot,
        trust_level=src.trust_level,
        resistance_level=src.resistance_level,
        lead_source=src.lead_source,
        call_history=src.call_history,
        crm_notes=src.crm_notes,
        hidden_objections=src.hidden_objections,
        trap_ids=src.trap_ids,
        chain_id=src.chain_id,
        cascade_ids=src.cascade_ids,
        breaking_point=src.breaking_point,
    )
    db.add(cloned)
    await db.flush()
    return cloned


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
    ws_id: str,
) -> None:
    """Handle session.start: resume existing or create new session.

    2026-04-21 CRITICAL FIX (journal #B/#G): ws_id parameter was missing,
    so the WS lock was NEVER acquired on a fresh session.start. Only
    _handle_session_resume called _acquire_session_lock. Consequence:
      1. Client connects WS, sends session.start, backend creates session
         without setting Redis keys ws:lock:{id} / ws:lock:{id}:owner.
      2. 30s later the first heartbeat fires _refresh_session_lock.
      3. Lua CAS checks get(key)==ws_id — key is missing → returns 0.
      4. Backend reads owner_key → None → `None == user_id` → False
         → falls into the ELSE branch → sends error {code: session_hijacked}
         → closes WS with 4002.
    That is EVERY call, like clockwork, ~30s in. Acquiring the lock at
    the right spot after session creation resolves it.
    """
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

            # 2026-04-22: seed light baseline human factors so every client
            # sounds slightly natural (subtle hesitation, mild breathing in
            # voice). Without this, single-call sessions had active_factors=[]
            # → TTS rendered "polished" robotic speech. Story-mode picks its
            # own factors from ClientStory and overwrites these on resume.
            if not state.get("active_factors"):
                state["active_factors"] = [
                    {"factor": "anxiety", "intensity": 0.22, "since_call": 1},
                    {"factor": "fatigue", "intensity": 0.12, "since_call": 1},
                ]

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

            # 2026-04-21: story-mode difficulty ramp override. If
            # _handle_story_next_call computed a per-call difficulty for
            # this story step, it dominates both custom_params.difficulty
            # and scenario.difficulty — the whole point of the ramp is to
            # vary difficulty across calls of the same story.
            _ramp_diff = state.get("current_call_difficulty")
            if _ramp_diff:
                custom_difficulty = _ramp_diff

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
                from sqlalchemy.orm import selectinload
                cp_result = await db.execute(
                    select(ClientProfile)
                    .options(selectinload(ClientProfile.profession))
                    .where(ClientProfile.session_id == session.id)
                )
                existing_profile = cp_result.scalar_one_or_none()

                if existing_profile:
                    # Resume — profile already exists.
                    # 2026-04-22: pass ambient_ctx so the "## Атмосфера"
                    # block (emotion_preset, bg_noise, time_of_day,
                    # client_fatigue, debt_stage labels) is preserved
                    # across WS reconnects. Previously a dropped/restored
                    # connection stripped those cues from the LLM prompt.
                    state["client_profile_prompt"] = _build_client_profile_prompt(
                        existing_profile, ambient_ctx=custom_params,
                    )
                    from app.services.client_generator import get_crm_card
                    client_card = get_crm_card(existing_profile)
                    client_gender = getattr(existing_profile, "gender", "") or ""
                else:
                    # First connection — build client profile.
                    # 2026-04-23 Zone 1: Priority ladder for profile source:
                    #   1. session.real_client_id → build_profile_from_real_client
                    #      (CRM-card "Написать"/"Позвонить" flow). Uses the
                    #      actual customer's name/debt/creditors from the
                    #      manager's CRM. Previously ignored — user saw random
                    #      client on call-mode even though card said Иванов.
                    #   2. session.custom_character_id implicitly handled by
                    #      generate_client_profile below (archetype/profession
                    #      come from custom_params which were sourced from the
                    #      CustomCharacter at session-start).
                    #   3. Fallback → generate_client_profile from scratch
                    #      (catalog scenarios / legacy sessions).
                    from app.services.client_generator import (
                        build_profile_from_real_client,
                        generate_client_profile,
                        get_crm_card,
                    )
                    profile = None
                    if session.real_client_id:
                        from app.models.client import RealClient
                        _rc = await db.get(RealClient, session.real_client_id)
                        if _rc is not None:
                            try:
                                profile = await build_profile_from_real_client(
                                    real_client=_rc,
                                    session_id=session.id,
                                    db=db,
                                    custom_archetype=custom_archetype,
                                    custom_profession=custom_params.get("profession"),
                                    custom_lead_source=custom_params.get("lead_source"),
                                    custom_family_preset=custom_params.get("family_preset"),
                                    custom_creditors_preset=custom_params.get("creditors_preset"),
                                    custom_debt_range=custom_params.get("debt_range"),
                                    custom_tone=custom_params.get("tone"),
                                    difficulty=custom_difficulty or (scenario.difficulty if scenario else 5),
                                )
                                logger.info(
                                    "ClientProfile built from RealClient | session=%s | real_client=%s | name=%s",
                                    session.id, _rc.id, _rc.full_name,
                                )
                            except Exception:
                                logger.warning(
                                    "build_profile_from_real_client failed for session=%s, falling back to generator",
                                    session.id, exc_info=True,
                                )
                                profile = None

                    # Retrain (clone_from_session_id) — clone source profile
                    # so the manager sees the same person across retrains.
                    # Bug fix 2026-04-29 (mirror of the call-mode path).
                    if profile is None and getattr(session, "source_session_id", None):
                        try:
                            profile = await _clone_source_session_profile(
                                session.source_session_id, session.id, db,
                            )
                            if profile is not None:
                                logger.info(
                                    "ClientProfile cloned from retrain source | "
                                    "session=%s | source=%s | name=%s",
                                    session.id, session.source_session_id, profile.full_name,
                                )
                        except Exception:
                            logger.warning(
                                "_clone_source_session_profile failed for session=%s, "
                                "falling back to generator",
                                session.id, exc_info=True,
                            )
                            profile = None

                    if profile is None:
                        profile = await generate_client_profile(
                            session_id=session.id,
                            scenario=scenario,
                            character=character,
                            difficulty=custom_difficulty or (scenario.difficulty if scenario else 5),
                            db=db,
                            custom_archetype=custom_archetype,
                            custom_profession=custom_params.get("profession"),
                            custom_lead_source=custom_params.get("lead_source"),
                            custom_family_preset=custom_params.get("family_preset"),
                            custom_creditors_preset=custom_params.get("creditors_preset"),
                            custom_debt_range=custom_params.get("debt_range"),
                            custom_tone=custom_params.get("tone"),
                        )
                    client_card = get_crm_card(profile)
                    client_gender = getattr(profile, "gender", "") or ""
                    state["client_profile_prompt"] = _build_client_profile_prompt(profile, ambient_ctx=custom_params)
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

        # Use client profile name when available (matches the briefing card)
        display_name = (client_card.get("full_name") if client_card else None) or (character.name if character else "Клиент")
        response_data = {
            "session_id": str(session.id),
            "character_name": display_name,
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

    # ── Concurrent active session guard (prevent XP farming via multiple tabs) ──
    # 2026-04-17 fix: auto-abandon sessions with no activity in 30 min before
    # rejecting a new one. Previous bug: if the WS dropped (closed tab, network
    # blip, server restart) without session.end being sent, the DB row stayed
    # `status=active` forever and permanently blocked the user from starting
    # fresh. Example: admin@trainer.local had 9 stale active sessions from
    # previous days before this fix landed.
    from datetime import datetime, timedelta, timezone as _tz
    _STALE_SESSION_GRACE = timedelta(minutes=30)
    async with async_session() as guard_db:
        existing_active_result = await guard_db.execute(
            select(TrainingSession)
            .where(
                TrainingSession.user_id == user_id,
                TrainingSession.status == SessionStatus.active,
            )
            .with_for_update()
        )
        existing_active_sessions = existing_active_result.scalars().all()
        _now = datetime.now(_tz.utc)

        # Separate fresh (truly concurrent) from stale (orphaned)
        stale: list = []
        fresh: list = []
        for s in existing_active_sessions:
            started = s.started_at
            # ensure tz-aware for comparison
            if started.tzinfo is None:
                started = started.replace(tzinfo=_tz.utc)
            if _now - started > _STALE_SESSION_GRACE:
                stale.append(s)
            else:
                fresh.append(s)

        # Auto-abandon stale ones so they never block again
        for s in stale:
            s.status = SessionStatus.abandoned
            if s.ended_at is None:
                s.ended_at = _now
        if stale:
            await guard_db.commit()
            logger.info(
                "Auto-abandoned %d stale active session(s) for user=%s before "
                "starting new one (grace=%s)",
                len(stale), user_id, _STALE_SESSION_GRACE,
            )

        if fresh:
            await _send_error(
                ws,
                "У вас уже есть активная сессия. Завершите её перед началом новой.",
                "concurrent_session",
            )
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

    # 2026-04-21: story-mode difficulty ramp override — takes precedence
    # over the authored base so the "easy first → hard finale" progression
    # actually lands on the LLM. Only set when inside a story flow.
    _ramp_diff = state.get("current_call_difficulty")
    if _ramp_diff:
        custom_difficulty = _ramp_diff

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
            # 2026-04-21: persist story-ramp difficulty into session.custom_params
            # so downstream consumers (scoring, script-hints, coach) see the
            # SAME effective difficulty the LLM ran under — not the authored
            # base. If no ramp (single-call or story without ramp), leaves the
            # dict untouched.
            if state.get("current_call_difficulty"):
                custom_params = dict(custom_params)
                custom_params["difficulty"] = state["current_call_difficulty"]
            session.custom_params = custom_params

        # TZ-2 §6.2/6.3: stamp canonical mode + runtime_type on the WS-created
        # session too. WS path always emits a synthetic training session so
        # there is no real_client_id at this point — runtime_type is always
        # `training_simulation`. Mode comes from custom_params.session_mode
        # (set earlier by the FE start payload), defaulting to chat.
        from app.services.runtime_catalog import (
            MODES,
            RUNTIME_TYPES,
            derive_runtime_type,
        )
        _ws_mode = ((session.custom_params or {}).get("session_mode") or "chat").lower()
        if _ws_mode not in MODES:
            _ws_mode = None
        _ws_runtime_type = derive_runtime_type(
            mode=_ws_mode,
            has_real_client=session.real_client_id is not None,
            source=session.source,
        )
        if _ws_runtime_type not in RUNTIME_TYPES:
            _ws_runtime_type = None
        session.mode = _ws_mode
        session.runtime_type = _ws_runtime_type
        await db.flush()

        # ── Generate unique client profile (Roleplay v2) ──
        try:
            from app.services.client_generator import generate_client_profile, get_crm_card
            profile = None
            if story_id:
                profile = await _clone_story_profile_for_session(story_id, session.id, db)

            # Retrain (clone_from_session_id) — clone source profile so the
            # manager sees the same person they saw on /results. Bug fix
            # 2026-04-29: previously fell through to generate_client_profile
            # which produced a fresh random name on every retrain.
            if profile is None and getattr(session, "source_session_id", None):
                profile = await _clone_source_session_profile(
                    session.source_session_id, session.id, db,
                )

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
                    custom_family_preset=custom_params.get("family_preset"),
                    custom_creditors_preset=custom_params.get("creditors_preset"),
                    custom_debt_range=custom_params.get("debt_range"),
                    custom_tone=custom_params.get("tone"),
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
            client_profile_prompt = _build_client_profile_prompt(profile, ambient_ctx=custom_params)

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
    _tts_avail = is_tts_available()
    # Journal #C diagnostics: log exact state of TTS gates at session start.
    # User reports silent call mode in prod. If tts_available=True but no
    # audio events ever reach the client, the failure is inside synth
    # path — the message below tells us which provider we expect.
    try:
        from app.config import settings as _s
        _providers = []
        if _s.navy_tts_enabled and _s.local_llm_url and _s.local_llm_api_key:
            _providers.append(f"navy:{_s.local_llm_url}")
        if _s.elevenlabs_api_key and _s.elevenlabs_enabled:
            _providers.append(f"elevenlabs({_s.elevenlabs_voice_list and 'voices_ok' or 'voices_empty'})")
        logger.warning(
            "TTS_PROVIDERS session=%s available=%s user_pref=%s providers=%s",
            session.id, _tts_avail, user_tts_pref,
            ",".join(_providers) if _providers else "NONE_CONFIGURED",
        )
    except Exception:
        logger.warning("TTS_PROVIDERS diagnostics failed", exc_info=True)

    if _tts_avail and user_tts_pref:
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

    # Save character name in state for LLM prompt injection (prevents name mismatch)
    state["character_name"] = character.name

    # Use client profile name when available (matches the briefing card shown to user)
    _display_name = (client_card.get("full_name") if client_card else None) or character.name
    started_data = {
        "session_id": str(session.id),
        "character_name": _display_name,
        "initial_emotion": initial_emotion.value,
        "scenario_title": scenario.title,
    }
    if client_card:
        started_data["client_card"] = client_card
    if tts_voice_id:
        started_data["tts_enabled"] = True

    # 2026-04-21 CRITICAL: acquire the WS lock now that we know the final
    # session.id. Previously omitted, causing every fresh call to die with
    # session_hijacked on its first heartbeat (see function docstring).
    # Same-user takeover is allowed so reconnects & StrictMode remounts
    # don't spuriously close the session.
    #
    # If acquisition returns False we MUST NOT proceed with session.started —
    # that would put two tabs of a different user into the same session
    # (invariant violation). Send a clear error and bail. On exception
    # (Redis hiccup) we also bail, but log full trace so ops can see why.
    try:
        _lock_ok = await _acquire_session_lock(
            session.id, ws_id, state.get("user_id")
        )
    except Exception:
        logger.warning(
            "WS lock acquisition raised on session.start | session=%s",
            session.id, exc_info=True,
        )
        _lock_ok = False

    if not _lock_ok:
        logger.warning(
            "session.start refused: lock busy | session=%s user=%s ws=%s",
            session.id, state.get("user_id"), ws_id,
        )
        await _send_error(
            ws,
            "Сессия уже открыта в другой вкладке. Закрой её и попробуй снова.",
            "session_lock_busy",
        )
        return

    await _send(ws, "session.started", started_data)

    # ── (2026-05-01) Realism telemetry — feature-set snapshot ──
    # Without this snapshot none of the call-realism features show up in
    # CRM / scoring / analytics — they're effectively invisible to product.
    # Two things happen here:
    #   (1) Snapshot is stamped into ``state["__realism_snapshot"]`` so
    #       the session.end finalizer can persist it into
    #       ``scoring_details["_realism"]`` (visible on /results page).
    #   (2) ``call.realism_snapshot`` DomainEvent is emitted via the
    #       canonical helper so the unified TZ-1 timeline picks it up
    #       (queryable from admin dashboard, correlatable with
    #       lead_client / session.completed events).
    try:
        from app.services.realism_telemetry import (
            count_active_realism_features,
            snapshot_realism_features,
        )
        _cp_realism = (session.custom_params or {})
        _mode_realism = (
            _cp_realism.get("session_mode")
            or getattr(session, "mode", None)
            or "chat"
        ).lower()
        _realism_snap = snapshot_realism_features(settings, session_mode=_mode_realism)
        _realism_snap["active_count"] = count_active_realism_features(_realism_snap)
        state["__realism_snapshot"] = _realism_snap
        # DomainEvent — wrap in a try since emit can fail in dual-write
        # mode if outbox flag is mid-flip; never let telemetry break the
        # session start (TZ-1 §4.4 — observability is opt-in, not gating).
        try:
            from app.services.client_domain import emit_domain_event
            await emit_domain_event(
                db=db,
                event_type="call.realism_snapshot",
                aggregate_id=session.id,
                aggregate_type="training_session",
                lead_client_id=getattr(session, "lead_client_id", None),
                payload=_realism_snap,
                correlation_id=str(session.id),
                source="ws_training",
            )
        except Exception:
            logger.debug(
                "call.realism_snapshot DomainEvent emit failed for %s",
                session.id, exc_info=True,
            )
        logger.info(
            "realism_snapshot | session=%s | active_count=%d | flags=%s",
            session.id, _realism_snap["active_count"],
            ",".join(k for k, v in _realism_snap.items()
                     if isinstance(v, bool) and v),
        )
    except Exception:
        logger.debug(
            "Realism telemetry snapshot failed for session %s",
            session.id, exc_info=True,
        )

    # ── Init stage tracker ──
    try:
        from app.core.redis_pool import get_redis as _get_redis_stage
        r_stage = _get_redis_stage()
        stage_tracker = StageTracker(str(session.id), r_stage)
        init_stage = await stage_tracker.init_state()
        await _send(ws, "stage.update", stage_tracker.build_ws_payload(init_stage))
    except Exception:
        logger.debug("Stage tracker init failed for session %s", session.id)

    # ── Sprint 0 §6 (Bug B fix) — auto-opener for call mode ──
    # Pre-Sprint-0 a fresh call session sat silently waiting for the
    # manager to speak first. Real debtors who pick up the phone always
    # say SOMETHING ("Алло?" / "Да?" / "Слушаю"). Without this the
    # session sounded like a standby AI assistant.
    #
    # Gated by THREE flags so any of them flipping off rolls back cleanly:
    #   - settings.call_humanized_v2          — master Sprint 0 flag
    #   - settings.call_humanized_v2_auto_opener — feature-specific flag
    #   - state.session_mode in {call,center}    — chat sessions are silent
    #     by design (manager types first), don't touch them
    try:
        _cp_open = state.get("custom_params") or {}
        _mode_open = _cp_open.get("session_mode") or "chat"
        _opener_eligible = (
            settings.call_humanized_v2
            and settings.call_humanized_v2_auto_opener
            and _mode_open in ("call", "center")
        )
        # Sprint 0 §6: log the gate decision unconditionally — without
        # this, "opener didn't fire" is indistinguishable from "fired
        # but the WS dropped the message" in prod logs. Plain INFO
        # because it's once per session.start and useful for the pilot.
        logger.info(
            "auto-opener gate session=%s eligible=%s "
            "v2=%s opener_flag=%s mode=%r",
            session.id, _opener_eligible,
            settings.call_humanized_v2,
            settings.call_humanized_v2_auto_opener,
            _mode_open,
        )
        if _opener_eligible:
            await _send_call_auto_opener(ws, session.id, state)
    except Exception:
        # Never let opener failure abort session.start. The manager can
        # always start the call manually — the opener is a UX nicety.
        logger.warning(
            "auto-opener failed for session=%s — session continues silently",
            session.id, exc_info=True,
        )


async def _send_call_auto_opener(ws, session_id, state: dict) -> None:
    """Emit a short opener phrase (text + TTS audio) and persist it.

    Behaves like the silence-prompt path: assistant message saved to DB so
    history replay reconstructs UI exactly, TTS uses active_factors so the
    voice carries the same humanisation factors as the rest of the call.

    Persona-aware (2026-05-01) — when ``call_opener_persona_aware`` flag is
    on, the phrase is picked from a (mood, age_bucket) bank: hostile says
    "Что?", senior cold says "Слушаю", young cold says "Да?". This is the
    biggest single "feels real" tell on first turn — a flat "Алло?" on
    every call is the strongest "this is AI" signal. See call_opener.py
    for the full register bank and the cluster 1.4 research that drove it.

    Pickup-delay (2026-05-01) — also under the same flag: instead of
    firing the opener TTS instantly, sample a triangular delay (300-1800ms
    typical, longer for "busy" moods) and silently wait before emitting.
    Real humans don't pick up at zero ms — the variation is what makes
    the call sound human.
    """
    _opener_persona_aware = bool(getattr(settings, "call_opener_persona_aware", False))
    if _opener_persona_aware:
        try:
            from app.services.call_opener import pick_opener
            _client_card = state.get("client_card") or {}
            _persona_age = _client_card.get("age") if isinstance(_client_card, dict) else None
            _persona_emotion = state.get("emotion") or "cold"
            _opener_choice = pick_opener(_persona_emotion, _persona_age)
            phrase = _opener_choice.text
            # Apply human-like pickup delay before emitting any audio. Skip if
            # the choice returned 0 (e.g. hangup mood — opener shouldn't fire
            # at all, but the upstream gate should already prevent us from
            # being here for hangup).
            if _opener_choice.pickup_delay_ms > 0:
                await asyncio.sleep(_opener_choice.pickup_delay_ms / 1000.0)
            logger.info(
                "auto_opener (persona-aware) | session=%s | emotion=%s | age_bucket=%s | "
                "phrase=%r | pickup_delay_ms=%d",
                session_id, _persona_emotion, _opener_choice.age_bucket,
                phrase, _opener_choice.pickup_delay_ms,
            )
        except Exception:
            logger.debug(
                "Persona-aware opener failed for %s — falling back to flat pool",
                session_id, exc_info=True,
            )
            phrase = _pick_call_auto_opener()
    else:
        phrase = _pick_call_auto_opener()
    # 1) Notify the UI immediately so the message bubble appears.
    await _send(ws, "character.message", {
        "content": phrase,
        "emotion": "cold",
        "is_auto_opener": True,
    })
    # 2) Best-effort TTS. If it fails the text bubble still rendered.
    if is_tts_available() and (state.get("user_prefs") or {}).get("tts_enabled", True):
        try:
            tts_result = await get_tts_audio_b64(
                phrase, str(session_id),
                emotion="cold",
                active_factors=_call_tts_factors(state),
            )
            if tts_result and tts_result.get("audio"):
                await _send(ws, "tts.audio", {
                    "audio_b64": tts_result["audio"],
                    "format": tts_result.get("format", "mp3"),
                    "emotion": "cold",
                    "voice_params": tts_result.get("voice_params"),
                    "duration_ms": tts_result.get("duration_ms"),
                    "text": phrase,
                })
        except TTSError as exc:
            logger.debug(
                "auto-opener TTS failed session=%s: %s", session_id, exc,
            )
    # 3) Persist as assistant message so /resume rebuilds the UI cleanly.
    try:
        async with async_session() as db:
            await add_message(
                session_id=session_id,
                role=MessageRole.assistant,
                content=phrase,
                db=db,
                emotion_state="cold",
            )
            await db.commit()
    except Exception:
        # Persistence is the least critical — UI already saw the bubble.
        logger.warning(
            "auto-opener persist failed session=%s", session_id, exc_info=True,
        )


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

    # Transcribe-only mode: return transcription without processing
    # Frontend shows preview → user confirms → sends text.message
    if data.get("transcribe_only"):
        return

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
    _coach_audio_stage = None
    try:
        from app.core.redis_pool import get_redis as _get_redis_sta
        r_sta = _get_redis_sta()
        st = StageTracker(str(session_id), r_sta)
        msg_count = state.get("message_count", 0)
        stage_state, stage_changed, skipped = await st.process_message(stt_result.text, msg_count, "user")
        _coach_audio_stage = stage_state.current_stage
        # 2026-04-23 Sprint 7 — mirror stage state into WS dict so the
        # whisper_engine (and anyone reading state["current_stage_name"])
        # gets fresh values. Previously nobody wrote these back, so
        # whispers always saw «greeting».
        state["current_stage"] = stage_state.current_stage
        state["current_stage_name"] = stage_state.current_stage_name
        state["stage_started_at_msg"] = dict(stage_state.stage_started_at_msg)
        state["stage_message_counts"] = dict(stage_state.stage_message_counts)
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

    # ── P1 (2026-04-29) Coaching mistake detector — audio path ──
    # Rule-based, no LLM, <1ms. Side effect: emits coaching.mistake WS
    # events. Flag-gated; OFF by default = exact no-op.
    if settings.coaching_mistake_detector_v1:
        try:
            from app.services.mistake_detector import evaluate_user_turn as _coach_eval_a
            from app.core.redis_pool import get_redis as _get_redis_coach_a
            _r_coach_a = _get_redis_coach_a()
            _stage_for_coach = _coach_audio_stage if _coach_audio_stage is not None else state.get("current_stage", 1)
            _fired_a = await _coach_eval_a(
                _r_coach_a, str(session_id), stt_result.text, int(_stage_for_coach or 1),
            )
            for _m_a in _fired_a:
                await _send(ws, "coaching.mistake", _m_a.to_payload())
        except Exception:
            logger.debug("Coaching mistake detector failed (audio) for %s", session_id, exc_info=True)

    # Generate character response (with fail-safe: ensure UI isn't stuck
    # on "avatar typing" if the LLM path raises something other than the
    # explicit LLMError it already handles).
    try:
        await _generate_character_reply(ws, session_id, state)
    except Exception as _reply_err:
        logger.exception(
            "character_reply failed unexpectedly for session=%s: %s",
            session_id, _reply_err,
        )
        state["llm_busy"] = False
        try:
            await _send(ws, "avatar.typing", {"is_typing": False})
        except Exception:
            pass  # WS may be closed; don't cascade


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
            # Primary path: script with DB checkpoints.
            # Phase 3.2 (2026-04-19): threshold is picked from
            # DIFFICULTY_PARAMS instead of the hardcoded 0.58 so that easy
            # scenarios actually *feel* easier (the matcher forgives
            # paraphrases earlier).
            from app.services.script_checker import check_checkpoints_with_accumulation
            from app.services.adaptive_difficulty import resolve_params as _resolve_diff

            _diff_params = _resolve_diff(state.get("scenario_difficulty"))

            all_results, new_matches = await check_checkpoints_with_accumulation(
                user_text=user_text,
                script_id=script_id,
                already_matched=matched_ids,
                threshold=_diff_params.script_similarity_threshold,
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

        # v6: Apply TRAP_INTENSITY_MULTIPLIER based on current emotion intensity
        _trap_multiplier = 1.0
        try:
            from app.services.emotion_v6 import TRAP_INTENSITY_MULTIPLIER, IntensityLevel
            _cur_intensity = state.get("_current_intensity", "MEDIUM")
            _int_level = IntensityLevel[_cur_intensity.upper()] if isinstance(_cur_intensity, str) else IntensityLevel.MEDIUM
            _trap_multiplier = TRAP_INTENSITY_MULTIPLIER.get(_int_level, 1.0)
        except Exception:
            # FIND-008: emotion_v6 optional module — fall back to 1.0 multiplier, debug-log.
            logger.debug("training.trap_intensity: emotion_v6 lookup failed, using 1.0", exc_info=True)

        for result in results:
            if result.status == "not_activated":
                continue

            _scaled_delta = round(result.score_delta * _trap_multiplier, 1)
            await _send(ws, "trap.triggered", {
                "trap_name": result.trap_name,
                "category": result.category,
                "status": result.status,  # fell | dodged | partial
                "score_delta": _scaled_delta,
                "intensity_multiplier": _trap_multiplier,
                "wrong_keywords": result.wrong_keywords_found,
                "correct_keywords": result.correct_keywords_found,
                # Post-session review data
                "client_phrase": result.client_phrase,
                "correct_example": result.correct_example,
            })

        # ── Personal Challenge: track trap fails per user, send challenge on 2+ ──
        _user_id = state.get("user_id")
        if _user_id:
            for result in results:
                if result.status != "fell":
                    continue
                try:
                    _trap_code = result.trap_name or result.category
                    async with async_session() as _tc_db:
                        # Increment trap fail counter
                        from app.models.traps import TrapSessionLog
                        _fail_count_r = await _tc_db.execute(
                            select(func.count(TrapSessionLog.id)).where(
                                TrapSessionLog.session_id.in_(
                                    select(TrainingSession.id).where(
                                        TrainingSession.user_id == _user_id,
                                        TrainingSession.status == SessionStatus.completed,
                                    )
                                ),
                                TrapSessionLog.trap_code == _trap_code,
                                TrapSessionLog.outcome == "fell",
                            )
                        )
                        _fail_count = (_fail_count_r.scalar() or 0) + 1  # +1 for current (not yet committed)

                        if _fail_count >= 2:
                            await _send(ws, "trap.personal_challenge", {
                                "trap_name": _trap_code,
                                "fail_count": _fail_count,
                                "message": f"Ловушка «{_trap_code}» победила тебя {_fail_count} раз. Попробуешь ещё?",
                            })
                except Exception:
                    pass  # personal challenge is non-critical

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

    # ── Narrative traps: memory/promise/consistency checks (story mode, call 2+) ──
    story_id = state.get("story_id")
    if story_id:
        try:
            from app.services.narrative_trap_detector import (
                detect_narrative_traps,
                build_consequences as build_narrative_consequences,
            )
            # Reuse cached ClientStory from prompt injection (avoids extra DB session)
            _narr_story = state.get("_cached_client_story")
            if _narr_story is None:
                from app.models.roleplay import ClientStory as _CSNarr
                async with async_session() as _narr_db:
                    _narr_res = await _narr_db.execute(
                        select(_CSNarr).where(_CSNarr.id == uuid.UUID(str(story_id)))
                    )
                    _narr_story = _narr_res.scalar_one_or_none()
                    state["_cached_client_story"] = _narr_story
            if _narr_story:
                    narrative_results = await detect_narrative_traps(
                        session_id=session_id,
                        client_message=last_character_msg,
                        manager_message=manager_message,
                        story=_narr_story,
                    )
                    for nr in narrative_results:
                        if nr.status == "not_activated":
                            continue
                        await _send(ws, "trap.triggered", {
                            "trap_name": nr.trap_type,
                            "category": "narrative",
                            "status": nr.status,
                            "score_delta": nr.score_delta,
                            "description": nr.description,
                            "evidence": nr.evidence,
                        })
                    # Feed consequences to Game Director state
                    narr_consequences = build_narrative_consequences(session_id, narrative_results)
                    if narr_consequences:
                        acc = state.get("accumulated_consequences", [])
                        acc.extend([
                            {"type": c.consequence_type, "severity": c.severity, "detail": str(c.payload)}
                            for c in narr_consequences
                        ])
                        state["accumulated_consequences"] = acc
        except Exception:
            logger.debug("Narrative trap detection failed for session %s", session_id, exc_info=True)

    # ── Human Factor traps: combinatorial patience/empathy/flattery/urgency (no LLM) ──
    if state.get("active_factors"):
        try:
            from app.services.human_factor_traps import (
                detect_human_factor_traps,
                build_consequences as build_hf_consequences,
            )
            from app.services.trigger_detector import detect_triggers
            trigger_result = await detect_triggers(
                manager_message=manager_message,
                client_message=last_character_msg,
                archetype_code=state.get("archetype_code", "neutral"),
                emotion_state=state.get("emotion_state", "cold"),
                skip_llm=True,  # fast keyword-only for real-time
            )
            hf_results = detect_human_factor_traps(
                trigger_result=trigger_result,
                client_message=last_character_msg,
                active_factors=state.get("active_factors", []),
                session_id=str(session_id),
            )
            state["_last_hf_results"] = hf_results  # for prompt injection
            for hfr in hf_results:
                if hfr.status == "not_activated":
                    continue
                await _send(ws, "trap.triggered", {
                    "trap_name": hfr.trap_type,
                    "category": "human_factor",
                    "status": hfr.status,
                    "score_delta": hfr.score_delta,
                    "description": hfr.description,
                    "matched_triggers": hfr.matched_triggers,
                })
            # Feed consequences to accumulated state
            hf_consequences = build_hf_consequences(hf_results, str(session_id))
            if hf_consequences:
                acc = state.get("accumulated_consequences", [])
                acc.extend([
                    {"type": c.consequence_type, "severity": c.severity, "detail": str(c.payload)}
                    for c in hf_consequences
                ])
                state["accumulated_consequences"] = acc
        except Exception:
            logger.debug("Human factor trap detection failed for session %s", session_id, exc_info=True)

    # Clear cached story after trap processing (refresh on next message)
    state.pop("_cached_client_story", None)


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

    # T2 fix: bound WS text input at 10KB to prevent DoS via oversized LLM
    # prompt (audio path already has MAX_AUDIO_B64_SIZE, text path had no limit).
    _WS_MAX_TEXT_CHARS = 10_000
    raw_content = data.get("content", "").strip()
    if not raw_content:
        await _send_error(ws, "content field is required", "missing_field")
        return
    if len(raw_content) > _WS_MAX_TEXT_CHARS:
        logger.warning(
            "WS text.message truncated from %d to %d chars (session=%s)",
            len(raw_content), _WS_MAX_TEXT_CHARS, session_id,
        )
    content = raw_content[:_WS_MAX_TEXT_CHARS]

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

    # 2026-04-22: Manager-initiated farewell intent. When the manager says
    # goodbye / wraps up the call, we want the AI client to respond
    # naturally (one short closing reply) and then session.end auto-fires
    # — instead of sitting there waiting for more input. Two-phase: (1)
    # mark intent on this turn, (2) on next manager turn (or after the
    # AI's farewell reply) trigger session.end. See _generate_character_reply
    # for the prompt-injection side and the auto-end logic below.
    _FAREWELL_PATTERNS = (
        "до свидания", "до встречи", "до связи", "всего доброго",
        "всего хорошего", "всех благ", "удачи вам", "всего наилучшего",
        "хорошего дня", "хорошего вечера", "спасибо за уделённое время",
        "спасибо за уделенное время", "спасибо за разговор",
        "до завтра", "до понедельника", "созвонимся", "перезвоню вам",
        "приятно было пообщаться",
        # Direct call-end phrases
        "я заканчиваю звонок", "буду закругляться", "буду заканчивать",
        "пора заканчивать", "нам пора прощаться",
    )
    _content_lower_for_intent = content.lower()
    _farewell_hit = any(p in _content_lower_for_intent for p in _FAREWELL_PATTERNS)
    # Two-stage farewell: first hit → mark + tell LLM to respond closing-style.
    # On subsequent reply we auto-end.
    if _farewell_hit and not state.get("user_initiated_farewell"):
        state["user_initiated_farewell"] = True
        state["user_farewell_msg_idx"] = state.get("message_count", 0)
        logger.info(
            "Manager farewell detected (session=%s) — AI will close politely, "
            "then session.end auto-fires.",
            session_id,
        )

    # Phase 2.5 (2026-04-18): optional quoted_message_id from frontend when
    # the manager clicks "Ответить" on an older bubble. Validated when the
    # prompt is built (see _generate_character_reply); here we only stash it.
    _quoted_id = data.get("quoted_message_id")
    if _quoted_id:
        # Cheap pre-validation so we don't pass garbage along.
        try:
            uuid.UUID(str(_quoted_id))
            state["pending_quoted_message_id"] = str(_quoted_id)
        except (ValueError, TypeError):
            logger.debug("text.message: invalid quoted_message_id=%r", _quoted_id)

    async with async_session() as db:
        _saved_msg = await add_message(
            session_id=session_id,
            role=MessageRole.user,
            content=content,
            db=db,
            emotion_state=current_emotion,
        )
        # Persist the quote link on the message row itself so historical
        # replay can reconstruct the UI state. The add_message helper
        # doesn't yet take quoted_message_id — set it directly before commit.
        if state.get("pending_quoted_message_id"):
            try:
                _saved_msg.quoted_message_id = uuid.UUID(
                    state["pending_quoted_message_id"]
                )
            except (ValueError, TypeError):
                pass
        state["message_count"] = _saved_msg.sequence_number

        # Phase 2.4 (2026-04-18): extract manager name/company from this turn.
        # Non-blocking on failure — extraction is best-effort.
        try:
            from app.services.manager_profile import (
                extract_manager_identity,
                persist_manager_identity,
            )

            ident = extract_manager_identity(content)
            if ident is not None and ident.confidence >= 0.7 and state.get("story_id"):
                await persist_manager_identity(
                    story_id=state["story_id"],
                    session_id=session_id,
                    call_number=int(state.get("call_number", 1)),
                    identity=ident,
                    db=db,
                )
        except Exception:
            logger.debug("manager_profile extraction failed", exc_info=True)

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
        # 2026-04-23 Sprint 7 — mirror stage state into WS dict so the
        # whisper_engine (and anyone reading state["current_stage_name"])
        # gets fresh values. Matches the audio-path writer above.
        state["current_stage"] = stage_state.current_stage
        state["current_stage_name"] = stage_state.current_stage_name
        state["stage_started_at_msg"] = dict(stage_state.stage_started_at_msg)
        state["stage_message_counts"] = dict(stage_state.stage_message_counts)
        if stage_changed:
            await _send(ws, "stage.update", st.build_ws_payload(stage_state))
        if skipped:
            state["cumulative_skips"] = state.get("cumulative_skips", 0) + len(skipped)
            reactions = st.get_skip_reactions(stage_state, skipped)
            if reactions:
                state["_pending_skip_reactions"] = reactions
            # 2026-04-23 Sprint 2: emit stage.skipped so frontend ScriptPanel
            # can flash a yellow border + show a hint ("вернитесь и
            # установите раппорт"). Previously skip was silent — AI voiced
            # a reaction phrase but user didn't see WHY.
            for _sk_num in skipped:
                if _sk_num < 1 or _sk_num > len(STAGE_ORDER):
                    continue
                _sk_name = STAGE_ORDER[_sk_num - 1]
                _sk_label = STAGE_LABELS.get(_sk_name, _sk_name)
                _sk_behavior = STAGE_BEHAVIOR.get(_sk_name, {})
                await _send(ws, "stage.skipped", {
                    "missed_stage_number": _sk_num,
                    "missed_stage_name": _sk_name,
                    "missed_stage_label": _sk_label,
                    "current_stage_number": stage_state.current_stage,
                    "current_stage_label": STAGE_LABELS.get(
                        stage_state.current_stage_name, stage_state.current_stage_name,
                    ),
                    "hint": _sk_behavior.get("skip_reaction") or (
                        f"Вы пропустили «{_sk_label}». Советуем вернуться."
                    ),
                })
    except Exception:
        logger.debug("Stage tracking failed for session %s", session_id, exc_info=True)

    # ── P1 (2026-04-29) Coaching mistake detector — text path ──
    # Same contract as the audio-path hook above. See mistake_detector.py.
    if settings.coaching_mistake_detector_v1:
        try:
            from app.services.mistake_detector import evaluate_user_turn as _coach_eval_t
            from app.core.redis_pool import get_redis as _get_redis_coach_t
            _r_coach_t = _get_redis_coach_t()
            _stage_for_coach_t = state.get("current_stage", 1) or 1
            _fired_t = await _coach_eval_t(
                _r_coach_t, str(session_id), content, int(_stage_for_coach_t),
            )
            for _m_t in _fired_t:
                await _send(ws, "coaching.mistake", _m_t.to_payload())
        except Exception:
            logger.debug("Coaching mistake detector failed (text) for %s", session_id, exc_info=True)

    try:
        await _generate_character_reply(ws, session_id, state)
        # 2026-04-22: Auto-fire session.end after AI replied to a manager
        # farewell. Two-phase done — manager said goodbye, AI politely closed,
        # now wrap the session and send results. Small await so the TTS chunk
        # of the closing reply finishes playing client-side before redirect.
        if state.get("user_initiated_farewell") and not state.get("user_farewell_replied"):
            state["user_farewell_replied"] = True
            logger.info(
                "Auto-firing session.end after manager farewell (session=%s).",
                session_id,
            )
            # Brief pause so closing TTS reaches the client cleanly.
            await asyncio.sleep(2.5)
            try:
                await _handle_session_end(ws, {}, state)
                state["_should_stop"] = True
            except Exception:
                logger.exception("Auto session.end on farewell failed (session=%s)", session_id)
    except Exception as _reply_err:
        # Same fail-safe as in _handle_audio_chunk: don't let
        # unhandled exceptions leave avatar.typing=True forever.
        logger.exception(
            "character_reply failed unexpectedly for session=%s: %s",
            session_id, _reply_err,
        )
        state["llm_busy"] = False
        try:
            await _send(ws, "avatar.typing", {"is_typing": False})
        except Exception:
            pass


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

    explicit_outcome = normalize_session_outcome(data.get("outcome") or data.get("result"))
    if explicit_outcome:
        state["call_outcome"] = explicit_outcome

    state_mode = (
        state.get("session_mode")
        or (state.get("custom_params") or {}).get("session_mode")
        or state.get("mode")
        or "chat"
    )

    # TZ-2 Phase 3B — end guards routed through runtime_guard_engine.
    # Engine delegates to validate_terminal_outcome internally so the WS
    # `terminal_outcome_required` error code (used by the call-page modal
    # to highlight the missing outcome) stays unchanged.
    from app.services.runtime_guard_engine import evaluate_end_guards
    _end_violations = evaluate_end_guards(
        mode=state_mode, raw_outcome=state.get("call_outcome"),
    )
    if _end_violations:
        v = _end_violations[0]
        from app.services.runtime_metrics import record_blocked_start
        record_blocked_start(
            guard_code=v.code,
            mode=state_mode,
            runtime_type=(state.get("runtime_type") if isinstance(state, dict) else None),
            phase="end",
        )
        await _send_error(ws, v.message, v.code)
        return

    # Phase 4 end-guards (deferred). Each behind a feature flag (default
    # OFF); when enabled, refuse the WS finalize on the same conditions
    # the REST end handler refuses (status not active, projection target
    # missing/archived). Same record_blocked_start call so the SRE
    # dashboard counts both transports under one bucket per guard.
    from app.config import settings as _ws_settings
    if (
        _ws_settings.tz2_guard_runtime_status_enabled
        or _ws_settings.tz2_guard_projection_safe_commit_enabled
    ):
        from app.services.runtime_metrics import record_blocked_start
        async with async_session() as guard_db:
            guard_session = await guard_db.get(TrainingSession, session_id)
            if guard_session is not None:
                if _ws_settings.tz2_guard_runtime_status_enabled:
                    from app.services.runtime_guard_engine import evaluate_runtime_status_guard
                    rs_v = evaluate_runtime_status_guard(session=guard_session)
                    if rs_v is not None:
                        record_blocked_start(
                            guard_code=rs_v.code,
                            mode=state_mode,
                            runtime_type=(
                                state.get("runtime_type")
                                if isinstance(state, dict) else None
                            ),
                            phase="end",
                        )
                        await _send_error(ws, rs_v.message, rs_v.code)
                        return
                if _ws_settings.tz2_guard_projection_safe_commit_enabled:
                    from app.services.runtime_guard_engine import (
                        evaluate_projection_safe_commit_guard,
                    )
                    proj_v = await evaluate_projection_safe_commit_guard(
                        guard_db, session=guard_session,
                    )
                    if proj_v is not None:
                        record_blocked_start(
                            guard_code=proj_v.code,
                            mode=state_mode,
                            runtime_type=(
                                state.get("runtime_type")
                                if isinstance(state, dict) else None
                            ),
                            phase="end",
                        )
                        await _send_error(ws, proj_v.message, proj_v.code)
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
        import asyncio as _aio
        async with async_session() as db:
            scores = await _aio.wait_for(
                calculate_scores(session_id, db),
                timeout=45.0,  # C4 fix: 45s timeout prevents infinite hang
            )
    except _aio.TimeoutError:
        logger.error("Scoring timed out after 45s for session %s", session_id)
    except Exception:
        logger.exception("Failed to calculate scores for session %s", session_id)

    # ── Save emotion journey snapshot BEFORE cleanup (end_session deletes Redis) ──
    _emotion_journey: dict = {}
    try:
        _emotion_journey = await save_journey_snapshot(session_id)
    except Exception:
        logger.debug("Failed to save emotion journey snapshot for %s", session_id)

    mp_result: dict | None = None
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

            # BUG-FIX: Persist score to state so story mode's Game Director
            # receives actual scores (was always 0.0 before this fix)
            state["last_score_total"] = scores.total
            state["last_score_breakdown"] = {
                "script_adherence": scores.script_adherence,
                "objection_handling": scores.objection_handling,
                "communication": scores.communication,
                "anti_patterns": scores.anti_patterns,
                "result": scores.result,
                "chain_traversal": scores.chain_traversal,
                "trap_handling": scores.trap_handling,
                "total": scores.total,
            }

            # Inject v5 metadata into scoring_details for results page
            enriched_details = dict(scores.details) if scores.details else {}
            if state.get("call_outcome"):
                enriched_details["call_outcome"] = state["call_outcome"]
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

            # ── (2026-05-01) Realism telemetry → scoring_details ──
            # Stamp the session-start snapshot of active realism features
            # into ``scoring_details["_realism"]`` so /results page and any
            # SQL analytics can correlate feature-set with score / outcome.
            _realism_snap = state.get("__realism_snapshot")
            if _realism_snap:
                enriched_details["_realism"] = _realism_snap

            # ── P1 (2026-04-29) Coaching state cleanup ──
            if settings.coaching_mistake_detector_v1:
                try:
                    from app.services.mistake_detector import reset as _coach_reset
                    from app.core.redis_pool import get_redis as _get_redis_coach_end
                    await _coach_reset(_get_redis_coach_end(), str(session_id))
                except Exception:
                    logger.debug("Coaching cleanup failed for session %s", session_id, exc_info=True)

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

        # ── TZ-2 Phase 1B: post-finalize enrichment via shared helper ──
        # Replaces three formerly-inline blocks (RAG feedback capture,
        # SessionHistory creation, ManagerProgress XP award) with a single
        # call. Helper is also called from the REST end-handler — both
        # paths converge on the same logic with SessionHistory.session_id
        # UNIQUE acting as the idempotency lock so XP is awarded once even
        # when both paths fire (multi-tab race, REST after WS, etc).
        #
        # The AI-coach generation block above (4674-4740) is intentionally
        # kept inline because it builds richer enriched_details fields
        # (_cited_moments, _stage_analysis, _historical_patterns) that the
        # helper does not produce. By the time the helper runs Step 3, it
        # sees session.feedback_text already populated and short-circuits.
        mp_result = None
        if scores is not None and session is not None:
            try:
                from app.services.runtime_finalizer import apply_post_finalize_enrichment
                _enrich_result = await apply_post_finalize_enrichment(
                    db, session=session, scores=scores, state=state,
                )
                mp_result = _enrich_result.get("mp_result")
            except Exception as e:
                logger.warning("apply_post_finalize_enrichment failed: %s", e, exc_info=True)

            # Emit EVENT_TRAINING_COMPLETED here (NOT in the helper) so the
            # outbox idempotency_key collapses with the parallel REST emit
            # if both paths fire for the same session. Helper is intentionally
            # event-bus-agnostic (single responsibility: write SessionHistory
            # + award XP); event emission is the WS/REST handler's job.
            _uid = state.get("user_id")
            if _uid:
                try:
                    from app.services.event_bus import event_bus, GameEvent, EVENT_TRAINING_COMPLETED
                    await event_bus.emit(
                        GameEvent(
                            kind=EVENT_TRAINING_COMPLETED,
                            user_id=_uid,
                            db=db,
                            payload={
                                "session_id": str(session_id),
                                "score": scores.total,
                                "scenario_id": str(state.get("scenario_id", "")),
                                "xp_earned": _enrich_result.get("xp_earned") if mp_result else 0,
                                "weak_legal_categories": (scores.details or {}).get("legal_accuracy", {}).get("weak_categories", []),
                            },
                        ),
                        aggregate_id=session_id,
                        idempotency_key=f"training_completed:{session_id}",
                    )
                except Exception as emit_exc:
                    logger.warning("Failed to emit training_completed event: %s", emit_exc)

        # 2026-04-21: reconcile CustomCharacter stats for constructor-born
        # sessions before we commit. update_custom_character_stats is a
        # no-op on sessions without a custom_character_id link, so safe to
        # call unconditionally. Its flush joins the same transaction as
        # the session-end writes above, so either both land or neither.
        if session is not None:
            try:
                from app.services.custom_character_stats import update_custom_character_stats
                await update_custom_character_stats(session, db)
            except Exception:
                logger.warning(
                    "custom_character_stats update failed (WS end) for %s",
                    session_id, exc_info=True,
                )

        if session is not None and session.real_client_id:
            try:
                await log_training_real_case_summary(
                    db,
                    session=session,
                    source="ws.training.end",
                    manager_id=session.user_id,
                )
            except Exception:
                logger.warning(
                    "ClientInteraction auto-create failed (WS end) for session=%s real_client=%s",
                    session_id, session.real_client_id, exc_info=True,
                )

            try:
                await ensure_followup_for_session(
                    db,
                    session,
                    outcome=state.get("call_outcome") or state.get("last_call_outcome"),
                )
            except Exception:
                logger.warning(
                    "CRM follow-up auto-create failed (WS end) for session=%s real_client=%s",
                    session_id, session.real_client_id, exc_info=True,
                )

        # Phase 1 (Roadmap §6.3) — stamp canonical terminal contract
        # regardless of whether the session had a real_client. Producer
        # legacy blocks above still own follow-up/CRM/gamification in
        # shadow mode; policy will take over when
        # ``completion_policy_strict`` flips.
        if session is not None:
            try:
                from app.services.completion_policy import (
                    CompletedVia,
                    TerminalReason,
                    finalize_training_session,
                    outcome_from_raw,
                )

                _raw_outcome = (
                    state.get("call_outcome")
                    or state.get("last_call_outcome")
                    or (session.scoring_details or {}).get("call_outcome")
                )
                _reason = (
                    TerminalReason.client_farewell_detected
                    if state.get("ai_initiated_farewell") or _raw_outcome == "hangup"
                    else TerminalReason.user_ended
                )
                await finalize_training_session(
                    db,
                    session=session,
                    outcome=outcome_from_raw(_raw_outcome),
                    reason=_reason,
                    completed_via=CompletedVia.ws,
                    manager_id=session.user_id,
                    emit_followup=False,
                    emit_crm=False,
                    emit_gamification=False,
                )
            except Exception:
                logger.warning(
                    "completion_policy stamp failed (ws) for %s", session_id, exc_info=True,
                )

        await db.commit()

    # ── C4 fix: Send results to client NOW (critical path done) ──
    # Everything below is background work — user should not wait for it.
    state["last_ended_session_id"] = session_id
    state["active"] = False
    state["session_id"] = None

    _early_result = {"message": err.WS_SESSION_ENDED}
    if session:
        _early_result.update({
            "session_id": str(session.id),
            "duration_seconds": session.duration_seconds,
            "status": session.status.value,
        })
        if scores:
            _early_result["scores"] = {
                "script_adherence": scores.script_adherence,
                "objection_handling": scores.objection_handling,
                "communication": scores.communication,
                "anti_patterns": scores.anti_patterns,
                "result": scores.result,
                "total": scores.total,
            }
    await _send(ws, "session.ended", _early_result)
    logger.info("Session ended (fast path): %s, score=%s", session_id, scores.total if scores else "N/A")

    # ═══ BACKGROUND TASKS (fire-and-forget, user already got results) ═══

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

    # NOTE: ManagerProgress (SessionHistory + XP + EVENT_TRAINING_COMPLETED
    # emission) and RAG feedback capture run in the shared
    # apply_post_finalize_enrichment helper above — same code path REST uses.

    # --- S3-01: Update team challenge progress ---
    try:
        user_id_tc = state.get("user_id")
        if user_id_tc:
            from app.services.team_challenge import on_session_complete
            async with async_session() as tc_db:
                await on_session_complete(user_id_tc, tc_db)
                await tc_db.commit()
    except Exception as tc_exc:
        logger.warning("Failed to update team challenge progress: %s", tc_exc)

    # --- Story Progression: record session + check chapter advancement ---
    try:
        user_id_sp = state.get("user_id")
        final_score_sp = state.get("final_score") or state.get("score_total") or 0
        if user_id_sp and isinstance(final_score_sp, (int, float)):
            from app.services.story_progression import record_session_completion, check_chapter_advancement
            async with async_session() as sp_db:
                await record_session_completion(user_id_sp, float(final_score_sp), sp_db)
                advancement = await check_chapter_advancement(user_id_sp, sp_db)
                await sp_db.commit()
                if advancement:
                    await _send(ws, "story.chapter_advanced", advancement.to_dict())
    except Exception as sp_exc:
        logger.warning("Failed to update story progression: %s", sp_exc)

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

    # Generate AI recommendations as a fallback feedback_text. Phase 1B
    # makes this strictly subordinate to the AI-coach summary written by
    # the inline block: if the coach already populated feedback_text, the
    # recommendations are NOT written (would overwrite richer text with
    # rule-based one). Race fix for the long-standing bug where a slow
    # AI-coach call let recommendations win silently.
    try:
        from app.services.scoring import generate_recommendations
        if scores:
            async with async_session() as rec_db:
                feedback = await generate_recommendations(session_id, rec_db, scores)
                if feedback:
                    # Persist to session record
                    async with async_session() as upd_db:
                        from app.models.training import TrainingSession as TS
                        sess_rec = await upd_db.get(TS, session_id)
                        if sess_rec and not sess_rec.feedback_text:
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

    # Send XP/level update as separate event (after background processing)
    if mp_result:
        try:
            await _send(ws, "session.xp_update", {
                "session_id": str(session_id),
                "xp_breakdown": mp_result.get("xp_breakdown", {}),
                "level_up": mp_result.get("level_up", False),
                "new_level": mp_result.get("new_level"),
                "new_level_name": mp_result.get("new_level_name"),
            })
        except Exception:
            logger.debug("Failed to send XP update for session %s", session_id)


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

        # Resolve VRM avatar model from archetype
        from app.services.avatar_assignment import resolve_model_key
        vrm_model_id = resolve_model_key(archetype_code)

        # Create ClientStory
        from app.models.roleplay import ClientStory
        story = ClientStory(
            user_id=user_id,
            story_name=f"Story: {scenario.title}",
            total_calls_planned=total_calls,
            current_call_number=0,
            personality_profile=personality_profile,
            vrm_model_id=vrm_model_id,
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

    # 2026-04-18 audit fix: idempotency lock. Prevents double-click / duplicate
    # WS messages from advancing call_number twice. Without this, a quick
    # second story.next_call skipped a call entirely (3-call chain becomes
    # 2 effective calls) and pushed the pre_call_brief out of sync.
    # NOTE: the lock is released at the end of this function (after
    # `story.call_ready` is sent) AND on every early-return path below.
    if state.get("_next_call_in_progress"):
        logger.info(
            "Ignoring duplicate story.next_call for story %s (already in progress)",
            story_id,
        )
        return
    state["_next_call_in_progress"] = True

    total_calls = state.get("total_calls", 3)
    current_call = state.get("call_number", 0) + 1

    if current_call > total_calls:
        await _send_error(ws, "Story complete — all calls done", "story_complete")
        state["_next_call_in_progress"] = False
        return

    state["call_number"] = current_call
    archetype_code = state.get("archetype_code", "skeptic")

    # 2026-04-21: story-mode difficulty ramp. Owner requested a "крутой"
    # progression — easy first contact, hard final call — so the manager
    # warms up on the easy end and the 5th call stress-tests them. Base
    # comes from custom_params.difficulty (picked in the constructor) or
    # the scenario's own difficulty as a legacy fallback. The ramp
    # shifts the per-call difficulty only for story-mode; single chat/
    # call sessions continue to use the authored value unchanged.
    try:
        from app.services.adaptive_difficulty import story_difficulty_ramp
        _story_cp = state.get("story_custom_params") or {}
        _base_diff = _story_cp.get("difficulty")
        if _base_diff is None:
            _scn = state.get("scenario")
            _base_diff = getattr(_scn, "difficulty", None) if _scn else None
        _base_diff = int(_base_diff) if _base_diff else 5
        _ramp = story_difficulty_ramp(_base_diff, total_calls)
        _call_idx = max(0, min(current_call - 1, len(_ramp) - 1))
        _call_diff = _ramp[_call_idx]
        state["current_call_difficulty"] = _call_diff
        logger.info(
            "Story ramp | story=%s | base=%d total=%d | ramp=%s | call=%d → diff=%d",
            story_id, _base_diff, total_calls, _ramp, current_call, _call_diff,
        )
    except Exception:
        # Never block a story call over a ramp glitch — fall back to base.
        logger.warning("story_difficulty_ramp failed, using base difficulty", exc_info=True)
        state.pop("current_call_difficulty", None)

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
    gd_events = []  # BUG-FIX: must be defined before if-block to avoid NameError on call 1
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

        # 2026-04-18 audit fix: only send between_calls if we actually have
        # content beyond the always-present "status indicator". Empty/noise
        # events produced an invisible overlay (`s.betweenCallsEvents.length > 0`
        # guard hides it) — but they still polluted WS traffic and flipped
        # `showBetweenCalls=true` in the store, which then raced with the
        # pre_call_brief overlay. Skip the send entirely when the only item
        # is the auto-generated status indicator.
        _meaningful_events = [
            e for e in frontend_events
            if e.get("event_type") != "status_indicator"
        ]
        if _meaningful_events:
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
            # Fetch chapter context for story-aware narration
            _ch_id, _ch_name, _ep_name = 1, "", ""
            try:
                from app.services.story_progression import get_chapter_context
                async with async_session() as _ch_db:
                    _ch_ctx = await get_chapter_context(state["user_id"], _ch_db)
                    _ch_id = _ch_ctx.chapter_id
                    _ch_name = _ch_ctx.chapter_name
                    _ep_name = _ch_ctx.epoch_name
            except Exception:
                pass  # graceful degradation
            _narrator_ctx = NarratorContext(
                lifecycle_state=state.get("lifecycle_state", "FIRST_CONTACT"),
                relationship_score=state.get("relationship_score", 50.0),
                call_number=current_call - 1,  # previous call number
                total_calls=total_calls,
                archetype_code=archetype_code,
                client_name=state.get("client_name", "Клиент"),
                # H4 (Roadmap Phase 0 §5.1): pass client gender so the
                # narrator picks grammatically agreed adjectives.
                gender=(state.get("client_gender") or "unknown"),
                last_outcome=state.get("last_call_outcome", "unknown"),
                last_emotion=state.get("last_call_emotion", "cold"),
                last_score=state.get("last_score_total", 0.0),
                key_memories=key_memories,
                active_storylets=state.get("active_storylets", []),
                active_consequences=state.get("accumulated_consequences", []),
                between_events=between_events,
                manager_weak_points=_mgr_weak_points or [],
                chapter_id=_ch_id,
                chapter_name=_ch_name,
                epoch_name=_ep_name,
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
        "total_calls": total_calls,
        "session_id": str(state.get("session_id", "")),
    })

    # 2026-04-18 audit fix: release idempotency lock after successful flow.
    state["_next_call_in_progress"] = False


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

                # Compress older calls if needed.
                # 2026-04-18 audit fix: only compress on call 3+ AND when more
                # calls remain. On the final call, compression output is never
                # read — it was wasted CPU and delayed `story.call_report`.
                if call_number >= 3 and call_number < state.get("total_calls", 3):
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
            "is_final": call_number >= state.get("total_calls", 3),
            "total_calls": state.get("total_calls", 3),
        })

    except Exception:
        logger.warning("Failed to generate report for story %s call %d", story_id, call_number)

    # NOTE: last_call_outcome and last_call_emotion are already set above
    # (lines ~3560-3561) with smarter fallback logic. Do NOT overwrite them here.
    #
    # 2026-04-18 audit: the `story.completed` emit + EVENT_STORY_COMPLETED
    # broadcast happen in the `else` branch below when call_number >=
    # total_calls. This is already handled — no separate emit needed here.

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
    _last_entitlement_check: float = time.time()
    _ENTITLEMENT_RECHECK_INTERVAL = 300  # 5 minutes
    state_lock = asyncio.Lock()

    watchdog_task: asyncio.Task | None = None
    hint_task: asyncio.Task | None = None
    soft_skills_task: asyncio.Task | None = None
    # Track fire-and-forget background tasks for cleanup on disconnect
    _bg_tasks: list[asyncio.Task] = []
    stop_event = asyncio.Event()
    _rate_limiter = training_limiter()

    # FIX P2: health-check STT provider instead of just checking config
    async def _check_stt_available() -> bool:
        if settings.deepgram_api_key:
            return True  # Deepgram streaming — always available if key set
        if not settings.whisper_url:
            return False
        try:
            _base = settings.whisper_url.rstrip("/")
            if _base.endswith("/v1"):
                _base = _base[:-3]
            _headers = {}
            if settings.whisper_api_key:
                _headers["Authorization"] = f"Bearer {settings.whisper_api_key}"
            # 2026-04-22: 3.0 → 10.0s. Whisper model cold-start takes 6-10s
            # after idle unload; 3s default reported stt_available=false
            # until the model was warmed by a failed request.
            async with httpx.AsyncClient(timeout=10.0) as _c:
                _r = await _c.get(f"{_base}/v1/models", headers=_headers)
                return _r.status_code == 200
        except Exception:
            return False

    try:
        stt_ok = await _check_stt_available()
        # H6 fix: include TTS/STT availability status so frontend can show banners
        await _send(websocket, "session.ready", {
            "message": err.WS_AUTHENTICATED,
            "tts_available": is_tts_available(),
            "stt_available": stt_ok,
            "llm_provider": "local" if settings.local_llm_enabled else "cloud",
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

            # L6c fix: per-user rate limit across ALL tabs/connections (Redis).
            # Default 300 msg/10s for training. Prevents N-tab amplification.
            from app.core.ws_rate_limiter import check_user_rate_limit
            if not await check_user_rate_limit(str(user_id), scope="training"):
                await _send_error(
                    websocket,
                    "Слишком много сообщений со всех ваших сессий. Подождите секунду.",
                    "rate_limited_user",
                )
                continue

            # Periodic entitlement re-check (every 5 min) — disconnect if plan expired
            now_t = time.time()
            if now_t - _last_entitlement_check > _ENTITLEMENT_RECHECK_INTERVAL and state.get("session_id"):
                _last_entitlement_check = now_t
                try:
                    from app.services.entitlement import get_entitlement, check_session_limit
                    async with async_session() as _ent_db:
                        ent = await get_entitlement(user_id, _ent_db)
                        if not check_session_limit(ent):
                            await _send(websocket, "entitlement.expired", {
                                "message": "Лимит сессий исчерпан. Обновите подписку.",
                                "plan": ent.plan.value,
                            })
                            logger.info("ws: entitlement expired mid-session for user %s (plan=%s)", user_id, ent.plan.value)
                except Exception as _ent_exc:
                    logger.debug("ws: entitlement re-check failed: %s", _ent_exc)

            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await _send_error(websocket, err.WS_INVALID_JSON, "parse_error")
                continue

            msg_type = message.get("type")
            msg_data = message.get("data", {})

            if msg_type == "session.start":
                await _handle_session_start(websocket, msg_data, state, ws_id)
                if state.get("session_id"):
                    # BUG-FIX: Cancel stale background tasks from previous call
                    # in story mode (calls 2-5). Without this, tasks monitor old
                    # session_id and new calls run without watchdog/hints.
                    for _old_task in (watchdog_task, hint_task, soft_skills_task):
                        if _old_task and not _old_task.done():
                            _old_task.cancel()
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
                state["text_mode"] = False  # H4 fix: re-enable silence watchdog on voice input
                await _handle_audio_chunk(websocket, msg_data, state)

            elif msg_type == "audio.end":
                await _handle_audio_end(websocket, msg_data, state)
                # C3 fix: hangup detection inside message processing sets _should_stop
                if state.get("_should_stop"):
                    stop_event.set()
                    break

            elif msg_type == "text.message":
                state["text_mode"] = True  # Disable silence watchdog for text input
                await _handle_text_message(websocket, msg_data, state)
                # C3 fix: hangup detection inside message processing sets _should_stop
                if state.get("_should_stop"):
                    stop_event.set()
                    break

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
                        # Lock lost. Distinguish same-user takeover (dev HMR /
                        # React Strict-Mode remount / user opened new tab) from
                        # a real hijack by a different user.
                        try:
                            from app.core.redis_pool import get_redis
                            r = get_redis()
                            owner_key = _WS_LOCK_OWNER_KEY.format(session_id=state["session_id"])
                            new_owner_raw = await r.get(owner_key)
                            new_owner = new_owner_raw.decode() if new_owner_raw else None
                        except Exception:
                            new_owner = None
                        if new_owner and new_owner == str(state.get("user_id", "")):
                            # Same user took over — close silently so the UI
                            # doesn't redirect to results or end the session.
                            await _send(websocket, "session.takeover_by_self", {
                                "message": "Сессия продолжается в другой вкладке/окне",
                            })
                            await websocket.close(code=4000)
                            return
                        # 2026-04-21 rev2 (journal: reconnect-loop): owner_key is
                        # None means NO ONE currently holds the lock (TTL lapsed
                        # between acquire and heartbeat, or Redis momentarily lost
                        # the key). This is NOT a hijack and must NOT close the
                        # WS — previously we closed with 4000, but client auto-
                        # reconnects on 4000, new WS re-acquires, old ws_id is
                        # stale, next heartbeat finds owner again None, loop.
                        # Symptom: session.takeover_by_self burst immediately
                        # followed by 2–3 session.start cascades.
                        # Right action: silently re-acquire the lock with OUR
                        # ws_id and carry on. No event to client, no close.
                        if not new_owner:
                            try:
                                from app.core.redis_pool import get_redis as _get_r
                                _r = _get_r()
                                _key = _WS_LOCK_KEY.format(session_id=state["session_id"])
                                await _r.set(_key, ws_id, ex=_WS_LOCK_TTL)
                                if state.get("user_id") is not None:
                                    await _r.set(
                                        _WS_LOCK_OWNER_KEY.format(session_id=state["session_id"]),
                                        str(state["user_id"]),
                                        ex=_WS_LOCK_TTL,
                                    )
                                logger.info(
                                    "WS lock was gone on heartbeat for session=%s "
                                    "ws=%s — silently re-acquired (no hijack)",
                                    state.get("session_id"), ws_id,
                                )
                            except Exception as _reacq_exc:
                                logger.warning(
                                    "Failed to re-acquire expired WS lock for session=%s: %s",
                                    state.get("session_id"), _reacq_exc,
                                )
                            # Fall through to pong so the client keeps its
                            # WS. No close, no reconnect cascade.
                            await _send(websocket, "pong", {})
                            continue
                        # DEV ONLY: HMR/StrictMode creates race where owner_key gets wiped
                        # between WS instances. Silently re-acquire lock instead of killing session.
                        if settings.app_env == "development":
                            try:
                                from app.core.redis_pool import get_redis as _get_r
                                _r = _get_r()
                                _key = _WS_LOCK_KEY.format(session_id=state["session_id"])
                                await _r.set(_key, ws_id, ex=_WS_LOCK_TTL)
                                if state.get("user_id") is not None:
                                    await _r.set(
                                        _WS_LOCK_OWNER_KEY.format(session_id=state["session_id"]),
                                        str(state["user_id"]),
                                        ex=_WS_LOCK_TTL,
                                    )
                                logger.info(
                                    "[dev] Re-acquired WS lock for session %s (ws_id=%s) — skipping hijack",
                                    state["session_id"], ws_id,
                                )
                            except Exception as e:
                                logger.warning("[dev] Failed to re-acquire lock: %s", e)
                            # Skip hijack error path in dev
                        else:
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
                    # Phase 1 (Roadmap §6.3 path 6): disconnect/error path
                    # used to only flip ``status=error``. The session
                    # effectively vanished from CRM timeline and manager
                    # analytics — terminal event never surfaced. Finalize
                    # through the policy so the row gets a proper
                    # ``technical_failed`` outcome + ``session.completed``
                    # DomainEvent for observability.
                    try:
                        from app.models.training import TrainingSession
                        from app.services.completion_policy import (
                            CompletedVia,
                            TerminalOutcome,
                            TerminalReason,
                            finalize_training_session,
                        )

                        _sess = await db.get(TrainingSession, _err_session_id)
                        if _sess is not None:
                            await finalize_training_session(
                                db,
                                session=_sess,
                                outcome=TerminalOutcome.technical_failed,
                                reason=TerminalReason.ws_disconnect,
                                completed_via=CompletedVia.disconnect,
                                manager_id=_sess.user_id,
                            )
                    except Exception:
                        logger.warning(
                            "completion_policy stamp failed (disconnect) for %s",
                            _err_session_id, exc_info=True,
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
