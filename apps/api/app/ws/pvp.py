"""WebSocket endpoint for PvP and PvE arena duels."""

import asyncio
import logging
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.security import decode_token
from app.database import async_session
from app.models.pvp import (
    DuelDifficulty,
    DuelMode,
    DuelStatus,
    GauntletRun,
    PvPDuel,
    PvPTeam,
    RapidFireMatch,
)
from app.models.user import User
from app.services import pvp_matchmaker as matchmaker
from app.services.llm import generate_response
from app.services.pvp_judge import judge_full_duel, judge_round
from app.services.rag_legal import retrieve_legal_context
from app.services.anti_cheat import run_anti_cheat, save_anti_cheat_result
from app.services.anti_cheat_realtime import (
    init_player as ac_init_player,
    check_message as ac_check_message,
    cleanup_duel as ac_cleanup_duel,
)
from app.services.content_filter import filter_ai_output, filter_user_input
from app.services.glicko2 import get_or_create_rating, update_rating_after_duel
from app.services.pvp_matchmaker import check_tier_change
from app.services.pvp_bot_engine import (
    generate_bot_reply,
    generate_bot_opener,
    cleanup_bot_state,
)
from app.core.ws_rate_limiter import pvp_limiter

logger = logging.getLogger(__name__)

# Archetype pool for PvP duels (subset suitable for competitive play)
_PVP_ARCHETYPES = [
    "skeptic", "anxious", "passive", "pragmatic", "desperate",
    "aggressive", "sarcastic", "know_it_all", "paranoid", "manipulator",
]

# Character briefs for role swap — help the client-role player get into character
_ARCHETYPE_BRIEFS: dict[str, dict[str, str]] = {
    "skeptic": {
        "name": "Скептик",
        "brief": "Не верит в эффективность банкротства. Требует фактов и доказательств. Задаёт много уточняющих вопросов. Не поддаётся на эмоции.",
        "behavior": "Сомневайтесь в каждом утверждении. Просите конкретные статьи закона и реальные кейсы.",
    },
    "anxious": {
        "name": "Тревожный",
        "brief": "Боится последствий банкротства: потери имущества, публичности, влияния на семью. Эмоционален и нерешителен.",
        "behavior": "Выражайте страхи: 'А что будет с квартирой?', 'А если узнают на работе?'. Меняйте мнение.",
    },
    "passive": {
        "name": "Пассивный",
        "brief": "Избегает принятия решений. Отвечает коротко и уклончиво. Говорит 'я подумаю', 'перезвоните позже'.",
        "behavior": "Отвечайте односложно. Не проявляйте инициативу. Уходите от прямых вопросов.",
    },
    "pragmatic": {
        "name": "Прагматик",
        "brief": "Интересуют только цифры и сроки. Не терпит общих фраз. Хочет конкретный план с датами.",
        "behavior": "Требуйте конкретику: 'Сколько это стоит?', 'Какие сроки?', 'Что именно я получу?'.",
    },
    "desperate": {
        "name": "Отчаявшийся",
        "brief": "Загнан в угол долгами. Готов на всё, но не верит что ему помогут. Эмоционально нестабилен.",
        "behavior": "Рассказывайте о безвыходности. Быстро соглашайтесь, но потом снова сомневайтесь.",
    },
    "aggressive": {
        "name": "Агрессивный",
        "brief": "Раздражён ситуацией. Грубит, перебивает, угрожает жалобой. Воспринимает звонок как вторжение.",
        "behavior": "Будьте резки: 'Зачем вы звоните?', 'Меня это не интересует!'. Повышайте голос.",
    },
    "sarcastic": {
        "name": "Саркастичный",
        "brief": "Использует иронию как защиту. Обесценивает предложения шутками. На самом деле заинтересован.",
        "behavior": "Отвечайте с сарказмом: 'Да-да, спасите меня', 'Очередные чудо-юристы'. Но слушайте.",
    },
    "know_it_all": {
        "name": "Всезнайка",
        "brief": "Считает что знает закон лучше менеджера. Цитирует (часто неверно) статьи. Проверяет компетентность.",
        "behavior": "Указывайте на ошибки (реальные и мнимые). Цитируйте статьи 127-ФЗ. Задавайте каверзные вопросы.",
    },
    "paranoid": {
        "name": "Параноик",
        "brief": "Подозревает мошенничество. Боится утечки данных. Не доверяет никому.",
        "behavior": "Спрашивайте про гарантии. Подозревайте подвох: 'Откуда у вас мои данные?', 'Это развод?'.",
    },
    "manipulator": {
        "name": "Манипулятор",
        "brief": "Пытается получить бесплатную консультацию. Давит на жалость, потом резко меняет тему.",
        "behavior": "Выуживайте информацию. Давите на жалость. Пытайтесь получить максимум бесплатно.",
    },
}

BOT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
ROUND_TIME_LIMIT = 600
ROUND_MESSAGE_LIMIT = 8

# ── New PvP Mode Constants ──────────────────────────────────────────────────
RAPID_FIRE_ROUNDS = 5
RAPID_FIRE_TIME_LIMIT = 120          # 2 min per mini-round
RAPID_FIRE_MSG_LIMIT = 5             # 5 messages per mini-round
RAPID_FIRE_MAX_SCORE = 20            # per mini-round (selling 0-15, legal 0-5)
RAPID_FIRE_RATING_MULTIPLIER = 0.8

GAUNTLET_MAX_DUELS = 5
GAUNTLET_MIN_DUELS = 3
GAUNTLET_TIME_LIMIT = 600            # 10 min per duel stage
GAUNTLET_MSG_LIMIT = 8
GAUNTLET_LOSS_THRESHOLD = 50.0       # Score below this = loss
GAUNTLET_MAX_LOSSES = 2
GAUNTLET_COOLDOWN_HOURS = 6

TEAM_TIME_LIMIT = 600
TEAM_MSG_LIMIT = 8

# (websocket, conn_id) — conn_id prevents race condition on connection swap
_active_connections: dict[uuid.UUID, tuple[WebSocket, str]] = {}
_duel_messages: dict[uuid.UUID, dict[int, list[dict[str, Any]]]] = {}
_duel_sessions: dict[uuid.UUID, dict[str, Any]] = {}
_disconnect_tasks: dict[tuple[uuid.UUID, uuid.UUID], asyncio.Task] = {}
# Lock to protect concurrent access to _duel_sessions (race condition prevention)
_duel_sessions_lock = asyncio.Lock()

# ── New mode session storage ────────────────────────────────────────────────
_rapid_fire_sessions: dict[uuid.UUID, dict[str, Any]] = {}
_gauntlet_sessions: dict[uuid.UUID, dict[str, Any]] = {}
_team_sessions: dict[uuid.UUID, dict[str, Any]] = {}
# Team 2v2: waiting room for partner to connect
_team_waiting: dict[uuid.UUID, dict[str, Any]] = {}  # team_id -> {players, ws_map, ...}


async def _send(ws: WebSocket, msg_type: str, data: dict | None = None) -> None:
    try:
        await ws.send_json({"type": msg_type, "data": data or {}})
    except Exception:
        pass


async def _send_to_user(user_id: uuid.UUID, msg_type: str, data: dict | None = None) -> None:
    """Send message to a connected user. Logs warning if user not connected."""
    entry = _active_connections.get(user_id)
    if entry:
        ws, _ = entry
        await _send(ws, msg_type, data)
    else:
        logger.warning(
            "PvP message lost: user %s not connected, type=%s", user_id, msg_type
        )


async def _auth_websocket(ws: WebSocket) -> tuple[uuid.UUID, str] | None:
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
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if not user:
            await _send(ws, "auth.error", {"detail": "User not found"})
            return None
        username = user.full_name or user.email or str(user_id)[:8]

    # Check if user was logged out (token blacklisted)
    from app.core.deps import _is_user_blacklisted
    if await _is_user_blacklisted(str(user_id)):
        await _send(ws, "auth.error", {"detail": "Token has been revoked"})
        return None

    await _send(ws, "auth.success", {"user_id": str(user_id), "username": username})
    return user_id, username


def _player_role_for_round(session: dict[str, Any], user_id: uuid.UUID, round_number: int) -> str:
    if round_number == 1:
        return "seller" if user_id == session["player1_id"] else "client"
    return "client" if user_id == session["player1_id"] else "seller"


def _remaining_round_time(session: dict[str, Any]) -> int:
    started_at = session.get("round_started_at")
    if not started_at:
        return ROUND_TIME_LIMIT
    elapsed = max(0, int(time.time() - started_at))
    return max(0, ROUND_TIME_LIMIT - elapsed)


def _serialize_round_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for item in messages:
        serialized.append({
            "sender_role": item.get("role"),
            "text": item.get("text"),
            "round": item.get("round"),
            "timestamp": item.get("timestamp"),
        })
    return serialized


def _flatten_duel_messages(duel_id: uuid.UUID) -> list[dict[str, Any]]:
    all_messages: list[dict[str, Any]] = []
    rounds = _duel_messages.get(duel_id, {})
    for round_number in (1, 2):
        all_messages.extend(_serialize_round_messages(rounds.get(round_number, [])))
    return all_messages


def _collect_anti_cheat_flag(user_id: uuid.UUID, result: Any) -> dict[str, Any]:
    return {
        "player_id": str(user_id),
        "score": result.max_score,
        "action": result.recommended_action.value,
        "signals": [
            {
                "check_type": signal.check_type.value,
                "score": signal.score,
                "details": signal.details,
            }
            for signal in result.flagged_signals
        ],
    }


def _match_found_payload(match: dict[str, Any], viewer_id: uuid.UUID) -> dict[str, Any]:
    player1_id = match.get("player1_id")
    player2_id = match.get("player2_id")
    player1_rating = match.get("player1_rating")
    player2_rating = match.get("player2_rating")

    if viewer_id == player1_id:
        opponent_rating = player2_rating
    elif viewer_id == player2_id:
        opponent_rating = player1_rating
    else:
        opponent_rating = None

    return {
        "duel_id": str(match["duel_id"]),
        "opponent_rating": opponent_rating,
        "difficulty": match["difficulty"],
        "is_pve": False,
    }


async def _load_duel_context(duel_id: uuid.UUID) -> dict[str, Any] | None:
    from app.models.scenario import Scenario
    import random as _rand

    async with async_session() as db:
        duel = (await db.execute(select(PvPDuel).where(PvPDuel.id == duel_id))).scalar_one_or_none()
        if not duel:
            return None

        player_ids = [duel.player1_id]
        if duel.player2_id != BOT_ID:
            player_ids.append(duel.player2_id)

        result = await db.execute(select(User).where(User.id.in_(player_ids)))
        users = {user.id: user for user in result.scalars().all()}

        # Load scenario — use duel's scenario_id or pick random active one
        scenario_title = None
        if duel.scenario_id:
            sc = (await db.execute(
                select(Scenario).where(Scenario.id == duel.scenario_id)
            )).scalar_one_or_none()
            scenario_title = sc.title if sc else None
        else:
            sc_result = await db.execute(
                select(Scenario).where(Scenario.is_active == True)
            )
            scenarios = sc_result.scalars().all()
            if scenarios:
                picked = _rand.choice(scenarios)
                scenario_title = picked.title
                duel.scenario_id = picked.id
                db.add(duel)
                await db.commit()

        return {
            "duel": duel,
            "player1_name": users.get(duel.player1_id).full_name if users.get(duel.player1_id) else "Player 1",
            "player2_name": users.get(duel.player2_id).full_name if users.get(duel.player2_id) else "AI Бот",
            "scenario_title": scenario_title,
        }


async def _ensure_session(duel_id: uuid.UUID, duel: PvPDuel, player1_name: str, player2_name: str) -> dict[str, Any]:
    async with _duel_sessions_lock:
        session = _duel_sessions.get(duel_id)
        if session:
            return session

        import random as _rand

        # Determine archetype — use PvE metadata if available, else random
        pve_meta = duel.pve_metadata or {}
        archetype = pve_meta.get("archetype") or _rand.choice(_PVP_ARCHETYPES)

        # PvE mode-specific configuration
        pve_mode = duel.pve_mode  # ladder / boss / mirror / standard / None
        boss_mechanic = pve_meta.get("mechanic")  # legal_penalty / composure_drain / archetype_shift
        mirror_style = pve_meta.get("mirror_style")  # player's extracted style
        boss_message_count = 0  # for chameleon archetype shifting

        session = {
            "duel_id": duel_id,
            "player1_id": duel.player1_id,
            "player2_id": duel.player2_id,
            "player_names": {
                duel.player1_id: player1_name,
                duel.player2_id: player2_name,
            },
            "difficulty": duel.difficulty,
            "scenario_title": None,
            "archetype": archetype,
            "is_pve": duel.is_pve,
            "pve_mode": pve_mode,
            "pve_metadata": pve_meta,
            "boss_mechanic": boss_mechanic,
            "boss_message_count": boss_message_count,
            "mirror_style": mirror_style,
            "boss_penalty_total": 0.0,
            "ready": set(),
            "round": 1,
            "started": False,
            "round_task": None,
            "round_started_at": None,
            "completed": False,
            "last_ai_message": "",
            "history": {
                1: [],
                2: [],
            },
        }
        _duel_sessions[duel_id] = session
        _duel_messages.setdefault(duel_id, {1: [], 2: []})
        return session


async def _update_duel_row(duel_id: uuid.UUID, **updates: Any) -> None:
    async with async_session() as db:
        duel = (await db.execute(select(PvPDuel).where(PvPDuel.id == duel_id))).scalar_one_or_none()
        if not duel:
            return
        for key, value in updates.items():
            setattr(duel, key, value)
        db.add(duel)
        await db.commit()


async def _send_duel_state(user_id: uuid.UUID, session: dict[str, Any]) -> None:
    round_number = session["round"]
    role = _player_role_for_round(session, user_id, round_number)
    await _send_to_user(user_id, "duel.brief", {
        "duel_id": str(session["duel_id"]),
        "your_role": role,
        "archetype": session["archetype"] if role == "client" else None,
        "character_brief": _ARCHETYPE_BRIEFS.get(session["archetype"]) if role == "client" else None,
        "human_factors": None,
        "difficulty": session["difficulty"].value,
        "scenario_title": session["scenario_title"],
        "round_number": round_number,
        "time_limit_seconds": ROUND_TIME_LIMIT,
    })
    await _send_to_user(user_id, "duel.state", {
        "duel_id": str(session["duel_id"]),
        "your_role": role,
        "round_number": round_number,
        "time_limit": ROUND_TIME_LIMIT,
        "time_remaining": _remaining_round_time(session),
        "messages": _flatten_duel_messages(session["duel_id"]),
    })


def _cancel_disconnect_task(user_id: uuid.UUID, duel_id: uuid.UUID) -> None:
    task = _disconnect_tasks.pop((duel_id, user_id), None)
    if task and not task.done():
        task.cancel()


async def _cleanup_duel_runtime(duel_id: uuid.UUID) -> None:
    async with _duel_sessions_lock:
        session = _duel_sessions.pop(duel_id, None)
    if session:
        round_task = session.get("round_task")
        if round_task and not round_task.done():
            round_task.cancel()
            try:
                await round_task
            except asyncio.CancelledError:
                pass
        for participant_id in [session["player1_id"], session["player2_id"]]:
            _cancel_disconnect_task(participant_id, duel_id)
    _duel_messages.pop(duel_id, None)
    # Clean up bot emotion/state memory for this duel
    cleanup_bot_state(str(duel_id))


async def _cancel_duel_after_disconnect(user_id: uuid.UUID, duel_id: uuid.UUID) -> None:
    try:
        await asyncio.sleep(matchmaker.RECONNECT_GRACE_SECONDS + 1)
        if user_id in _active_connections:
            return

        session = _duel_sessions.get(duel_id)
        if not session or session["completed"]:
            return

        async with async_session() as db:
            duel = (await db.execute(select(PvPDuel).where(PvPDuel.id == duel_id))).scalar_one_or_none()
            if not duel or duel.status in (DuelStatus.completed, DuelStatus.cancelled):
                return
            duel.status = DuelStatus.cancelled
            duel.completed_at = datetime.now(timezone.utc)
            if duel.created_at:
                duel.duration_seconds = max(
                    0,
                    int((duel.completed_at - duel.created_at).total_seconds()),
                )
            db.add(duel)
            await db.commit()

        for participant_id in [session["player1_id"], session["player2_id"]]:
            if participant_id in (user_id, BOT_ID):
                continue
            await _send_to_user(participant_id, "duel.cancelled", {
                "duel_id": str(duel_id),
                "reason": "opponent_disconnected",
            })

        await matchmaker.cleanup_duel_state(duel_id)
        await _cleanup_duel_runtime(duel_id)
    finally:
        _disconnect_tasks.pop((duel_id, user_id), None)


async def _finish_round_after_timeout(duel_id: uuid.UUID, round_number: int) -> None:
    await asyncio.sleep(ROUND_TIME_LIMIT)
    session = _duel_sessions.get(duel_id)
    if not session or session["completed"] or session["round"] != round_number:
        return
    for user_id in [session["player1_id"], session["player2_id"]]:
        if user_id != BOT_ID:
            await _send_to_user(user_id, "round.time_up", {"round": round_number})
    await _advance_round(duel_id)


async def _send_ai_message(duel_id: uuid.UUID, round_number: int, ai_role: str, text: str) -> None:
    session = _duel_sessions.get(duel_id)
    if not session or session["completed"]:
        return

    session["last_ai_message"] = text
    payload = {
        "sender_role": ai_role,
        "text": text,
        "round": round_number,
    }
    _duel_messages[duel_id][round_number].append({
        "sender_id": str(BOT_ID),
        "role": ai_role,
        "text": text,
        "timestamp": time.time(),
    })
    session["history"][round_number].append({"role": "assistant", "content": text})
    # PvP-1 fix: send AI message to BOTH players, not just player1
    for pid in [session["player1_id"], session["player2_id"]]:
        if pid != BOT_ID:
            await _send_to_user(pid, "duel.message", payload)


async def _generate_ai_reply(session: dict[str, Any], round_number: int, user_text: str, ai_role: str) -> str:
    """Delegate to pvp_bot_engine for intelligent archetype-aware responses.

    Enhanced for PvE modes:
    - Boss Rush: chameleon shifts archetype every 2 messages
    - Mirror Match: adds player style context to the prompt
    """
    archetype = session["archetype"]
    pve_mode = session.get("pve_mode")

    # Boss Rush — Chameleon: shift archetype every 2 messages
    if pve_mode == "boss" and session.get("boss_mechanic") == "archetype_shift":
        session["boss_message_count"] = session.get("boss_message_count", 0) + 1
        if session["boss_message_count"] % 2 == 0:
            import random as _r
            new_arch = _r.choice([a for a in _PVP_ARCHETYPES if a != archetype])
            session["archetype"] = new_arch
            archetype = new_arch
            # Notify player about the shift
            await _send_to_user(session["player1_id"], "boss.mechanic", {
                "event": "archetype_shift",
                "new_archetype": archetype,
                "message": f"Хамелеон меняет стиль! Теперь он — {_ARCHETYPE_BRIEFS.get(archetype, {}).get('name', archetype)}",
            })

    # Mirror Match: inject player style into scenario_title for prompt context
    scenario_title = session.get("scenario_title")
    if pve_mode == "mirror" and session.get("mirror_style"):
        mirror = session["mirror_style"]
        samples = mirror.get("sample_messages", [])
        sample_text = "\n".join(f"- {s}" for s in samples[:3]) if samples else ""
        scenario_title = (
            f"{scenario_title or 'Mirror Match'}\n\n"
            f"[MIRROR MODE] Имитируй стиль игрока. "
            f"Средняя длина сообщений: {mirror.get('avg_messages', 5)} за сессию. "
            f"Примеры сообщений игрока:\n{sample_text}"
        )

    reply = await generate_bot_reply(
        duel_id=str(session["duel_id"]),
        round_number=round_number,
        archetype=archetype,
        difficulty=session["difficulty"],
        ai_role=ai_role,
        user_text=user_text,
        history=session["history"][round_number],
        player_id=str(session["player1_id"]),
        scenario_title=scenario_title,
    )

    # Boss Rush — Emotional Vampire: apply composure drain penalty notification
    if pve_mode == "boss" and session.get("boss_mechanic") == "composure_drain":
        msg_count = len(session["history"][round_number])
        penalty = msg_count * 1.5  # growing penalty per message
        session["boss_penalty_total"] = session.get("boss_penalty_total", 0) + penalty
        await _send_to_user(session["player1_id"], "boss.mechanic", {
            "event": "composure_drain",
            "penalty": penalty,
            "total_penalty": session["boss_penalty_total"],
            "message": f"Эмоциональное давление: -{penalty:.1f} баллов (всего: -{session['boss_penalty_total']:.1f})",
        })

    # Boss Rush — Lawyer Perfectionist: check for legal errors (heuristic)
    if pve_mode == "boss" and session.get("boss_mechanic") == "legal_penalty":
        # Simple heuristic: check if player mentions legal articles incorrectly
        legal_error_markers = ["127-фз", "статья", "ст."]
        has_legal_ref = any(m in user_text.lower() for m in legal_error_markers)
        if not has_legal_ref and len(session["history"][round_number]) > 2:
            # Player not citing law — potential penalty
            session["boss_penalty_total"] = session.get("boss_penalty_total", 0) + 10
            await _send_to_user(session["player1_id"], "boss.mechanic", {
                "event": "legal_penalty",
                "penalty": 10,
                "total_penalty": session["boss_penalty_total"],
                "message": "Юрист-перфекционист: нет ссылки на закон! -10 баллов",
            })

    return reply


async def _start_round(duel_id: uuid.UUID, round_number: int) -> None:
    session = _duel_sessions.get(duel_id)
    if not session or session["completed"]:
        return

    session["round"] = round_number
    session["round_started_at"] = time.time()
    await _update_duel_row(
        duel_id,
        status=DuelStatus.round_1 if round_number == 1 else DuelStatus.round_2,
        round_number=round_number,
    )

    for user_id in [session["player1_id"], session["player2_id"]]:
        if user_id == BOT_ID:
            continue
        role = _player_role_for_round(session, user_id, round_number)
        archetype = session["archetype"]
        await _send_to_user(user_id, "duel.brief", {
            "duel_id": str(duel_id),
            "your_role": role,
            "archetype": archetype if role == "client" else None,
            "character_brief": _ARCHETYPE_BRIEFS.get(archetype) if role == "client" else None,
            "human_factors": None,
            "difficulty": session["difficulty"].value,
            "scenario_title": session["scenario_title"],
            "round_number": round_number,
            "time_limit_seconds": ROUND_TIME_LIMIT,
        })
        await _send_to_user(user_id, "round.start", {
            "round": round_number,
            "your_role": role,
            "archetype": archetype if role == "client" else None,
            "time_limit": ROUND_TIME_LIMIT,
        })

    task = session.get("round_task")
    if task and not task.done():
        task.cancel()
    session["round_task"] = asyncio.create_task(_finish_round_after_timeout(duel_id, round_number))

    if session["is_pve"]:
        user_role = _player_role_for_round(session, session["player1_id"], round_number)
        if user_role == "client":
            opener = await generate_bot_opener(
                duel_id=str(duel_id),
                round_number=round_number,
                archetype=session["archetype"],
                difficulty=session["difficulty"],
                ai_role="seller",
                player_id=str(session["player1_id"]),
                scenario_title=session.get("scenario_title"),
            )
            await _send_ai_message(duel_id, round_number, "seller", opener)


async def _advance_round(duel_id: uuid.UUID) -> None:
    session = _duel_sessions.get(duel_id)
    if not session or session["completed"]:
        return

    round_number = session["round"]
    round_messages = _duel_messages.get(duel_id, {}).get(round_number, [])
    seller_id = session["player1_id"] if round_number == 1 else session["player2_id"]
    client_id = session["player2_id"] if round_number == 1 else session["player1_id"]
    seller_name = session["player_names"].get(seller_id, "Seller")
    client_name = session["player_names"].get(client_id, "Client")

    try:
        async with async_session() as db:
            seller_score, client_score = await judge_round(
                dialog=round_messages,
                seller_id=seller_id,
                client_id=client_id,
                seller_name=seller_name,
                client_name=client_name,
                archetype=session["archetype"],
                difficulty=session["difficulty"],
                round_number=round_number,
                db=db,
            )
        round_score_payload = {
            "round": round_number,
            "selling_score": seller_score.selling_score,
            "acting_score": client_score.acting_score,
            "legal_accuracy": seller_score.legal_accuracy,
            "summary": {
                "seller_flags": seller_score.flags,
                "legal_details": seller_score.legal_details,
            },
        }
        for participant_id in [session["player1_id"], session["player2_id"]]:
            if participant_id != BOT_ID:
                await _send_to_user(participant_id, "judge.score", round_score_payload)
    except Exception as exc:
        logger.error("Round judge failed: duel=%s round=%s error=%s", duel_id, round_number, exc, exc_info=True)
        # Notify players about partial scoring failure
        for pid in [session["player1_id"], session["player2_id"]]:
            if pid != BOT_ID:
                await _send_to_user(pid, "round.judge_error", {
                    "duel_id": str(duel_id), "round": round_number,
                    "detail": "Ошибка оценки раунда — результат будет рассчитан при финализации",
                })

    if session["round"] == 1:
        await _update_duel_row(duel_id, status=DuelStatus.swap)
        for user_id in [session["player1_id"], session["player2_id"]]:
            if user_id != BOT_ID:
                await _send_to_user(user_id, "round.swap", {"next_round": 2})
        await asyncio.sleep(1.0)
        await _start_round(duel_id, 2)
        return

    await _finalize_duel(duel_id)


async def _maybe_finish_round(duel_id: uuid.UUID) -> None:
    session = _duel_sessions.get(duel_id)
    if not session or session["completed"]:
        return
    current_round = session["round"]
    if len(_duel_messages[duel_id][current_round]) >= ROUND_MESSAGE_LIMIT:
        await _advance_round(duel_id)


async def _finalize_duel(duel_id: uuid.UUID) -> None:
    session = _duel_sessions.get(duel_id)
    if not session or session["completed"]:
        return
    session["completed"] = True

    round_task = session.get("round_task")
    if round_task and not round_task.done():
        round_task.cancel()

    round1_messages = _duel_messages.get(duel_id, {}).get(1, [])
    round2_messages = _duel_messages.get(duel_id, {}).get(2, [])

    async with async_session() as db:
        duel = (await db.execute(select(PvPDuel).where(PvPDuel.id == duel_id))).scalar_one_or_none()
        if not duel:
            return

        # Idempotency guard with SELECT FOR UPDATE to prevent race condition:
        # Two concurrent _finish_duel calls could both pass the check without locking.
        duel = (await db.execute(
            select(PvPDuel).where(PvPDuel.id == duel_id).with_for_update()
        )).scalar_one_or_none()
        if not duel:
            return
        if duel.status in (DuelStatus.completed, DuelStatus.judging):
            logger.warning("Duel %s already finalized (status=%s), skipping", duel_id, duel.status.value)
            return

        duel.status = DuelStatus.judging
        db.add(duel)
        await db.flush()

        try:
            judge_result = await judge_full_duel(
                round1_dialog=round1_messages,
                round2_dialog=round2_messages,
                player1_id=session["player1_id"],
                player2_id=session["player2_id"],
                player1_name=session["player_names"][session["player1_id"]],
                player2_name=session["player_names"][session["player2_id"]],
                archetype=session["archetype"],
                difficulty=duel.difficulty,
                db=db,
            )
        except Exception as exc:
            # Judge failed — mark duel as error state, don't lose messages
            logger.error("Judge failed for duel %s: %s", duel_id, exc, exc_info=True)
            duel.status = DuelStatus.completed
            duel.round_1_data = {"messages": round1_messages}
            duel.round_2_data = {"messages": round2_messages}
            duel.completed_at = datetime.now(timezone.utc)
            db.add(duel)
            await db.commit()
            for uid in [session["player1_id"], session["player2_id"]]:
                if uid != BOT_ID:
                    await _send_to_user(uid, "duel.error", {"duel_id": str(duel_id), "detail": "Ошибка судейства"})
            await matchmaker.cleanup_duel_state(duel_id)
            await _cleanup_duel_runtime(duel_id)
            return

        duel.player1_total = judge_result.player1_total
        duel.player2_total = judge_result.player2_total
        duel.winner_id = judge_result.winner_id
        duel.is_draw = judge_result.is_draw
        duel.round_1_data = {"messages": round1_messages}
        duel.round_2_data = {"messages": round2_messages}
        duel.completed_at = datetime.now(timezone.utc)
        if duel.created_at:
            duel.duration_seconds = max(
                0,
                int((duel.completed_at - duel.created_at).total_seconds()),
            )
        duel.status = DuelStatus.completed

        p1_delta = 0.0
        p2_delta = 0.0
        if not duel.is_pve:
            try:
                _, p1_delta = await update_rating_after_duel(
                    duel.player1_id,
                    duel.player2_id,
                    0.5 if judge_result.is_draw else 1.0 if judge_result.winner_id == duel.player1_id else 0.0,
                    False,
                    db,
                )
                _, p2_delta = await update_rating_after_duel(
                    duel.player2_id,
                    duel.player1_id,
                    0.5 if judge_result.is_draw else 1.0 if judge_result.winner_id == duel.player2_id else 0.0,
                    False,
                    db,
                )
            except Exception as exc:
                logger.error("Rating update failed for duel %s: %s", duel_id, exc, exc_info=True)
                # Continue — duel result is still valid even if rating update fails

            # --- Promotion / Demotion check (DOC_13) ---
            for uid, old_r, delta in [
                (duel.player1_id, judge_result.player1_total, p1_delta),
                (duel.player2_id, judge_result.player2_total, p2_delta),
            ]:
                if uid == BOT_ID or delta == 0.0:
                    continue
                try:
                    # Approximate old_rating from current - delta
                    r_obj = await get_or_create_rating(uid, db)
                    old_rating = r_obj.rating - delta
                    tier_result = await check_tier_change(
                        uid, old_rating, r_obj.rating, duel_id, db,
                    )
                    if tier_result:
                        await _send_to_user(uid, "tier.change", tier_result)
                except Exception as tc_exc:
                    logger.warning(
                        "Tier change check failed for user %s: %s", uid, tc_exc,
                    )

            # Collect real-time signals before cleanup
            rt_signals = ac_cleanup_duel(duel_id)

            for uid in [duel.player1_id, duel.player2_id]:
                try:
                    ac_result = await run_anti_cheat(uid, duel_id, round1_messages + round2_messages, db)
                    # Merge real-time signals into post-match result
                    player_rt = rt_signals.get(uid)
                    if player_rt and player_rt.get("flagged"):
                        ac_result.overall_flagged = True
                        from app.services.anti_cheat import AntiCheatSignal, AntiCheatCheckType
                        ac_result.signals.append(AntiCheatSignal(
                            check_type=AntiCheatCheckType.behavioral,
                            score=min(1.0, player_rt["realtime_warning_score"] / 5.0),
                            flagged=True,
                            details={"source": "realtime", **player_rt},
                        ))
                    await save_anti_cheat_result(ac_result, db)
                    if ac_result.overall_flagged:
                        flags = list(duel.anti_cheat_flags or [])
                        flags.append(_collect_anti_cheat_flag(uid, ac_result))
                        duel.anti_cheat_flags = flags
                except Exception as exc:
                    logger.warning("Anti-cheat failed for user %s in duel %s: %s", uid, duel_id, exc)

        duel.player1_rating_delta = p1_delta
        duel.player2_rating_delta = p2_delta
        duel.rating_change_applied = not duel.is_pve
        db.add(duel)
        await db.commit()

    # Auto-complete bracket match if this duel belongs to one
    try:
        from app.models.tournament import BracketMatch
        from app.services.bracket import complete_bracket_match
        async with async_session() as bracket_db:
            bm_result = await bracket_db.execute(
                select(BracketMatch).where(BracketMatch.duel_id == duel_id)
            )
            bm = bm_result.scalar_one_or_none()
            if bm and judge_result.winner_id:
                await complete_bracket_match(
                    match_id=bm.id,
                    winner_id=judge_result.winner_id,
                    player1_score=judge_result.player1_total,
                    player2_score=judge_result.player2_total,
                    duel_id=duel_id,
                    db=bracket_db,
                )
                await bracket_db.commit()
                logger.info("Bracket match %s auto-completed from duel %s", bm.id, duel_id)
    except Exception:
        logger.debug("Bracket match update skipped for duel %s", duel_id, exc_info=True)

    # Build detailed breakdown dicts for frontend
    def _breakdown_to_dict(bd):
        if bd is None:
            return None
        from dataclasses import asdict
        return asdict(bd)

    result_data = {
        "duel_id": str(duel_id),
        "player1_total": judge_result.player1_total,
        "player2_total": judge_result.player2_total,
        "winner_id": str(judge_result.winner_id) if judge_result.winner_id else None,
        "is_draw": judge_result.is_draw,
        "is_pve": session["is_pve"],
        "rating_change_applied": not session["is_pve"],
        "player1_rating_delta": p1_delta,
        "player2_rating_delta": p2_delta,
        "summary": judge_result.summary if not session["is_pve"] else f"{judge_result.summary} PvE-результат без рейтингового изменения.",
        # Post-duel breakdown (Task 2.5)
        "player1_breakdown": _breakdown_to_dict(judge_result.player1_breakdown),
        "player2_breakdown": _breakdown_to_dict(judge_result.player2_breakdown),
        "turning_point": judge_result.turning_point,
    }
    for user_id in [session["player1_id"], session["player2_id"]]:
        if user_id != BOT_ID:
            await _send_to_user(user_id, "duel.result", result_data)

    # ── 3.4: EventBus → PvP achievements + gamification ──
    try:
        from app.services.event_bus import event_bus, GameEvent, EVENT_PVP_COMPLETED
        async with async_session() as ev_db:
            for uid in [session["player1_id"], session["player2_id"]]:
                if uid == BOT_ID:
                    continue
                is_winner = (winner_id is not None and uid == winner_id)
                await event_bus.emit(GameEvent(
                    kind=EVENT_PVP_COMPLETED,
                    user_id=uid,
                    db=ev_db,
                    payload={
                        "duel_id": str(duel_id),
                        "is_win": is_winner,
                        "is_pve": session.get("is_pve", False),
                    },
                ))
            await ev_db.commit()
    except Exception:
        logger.debug("PvP EventBus emit failed for duel %s", duel_id)

    # ── 3.4b: Arena Points + Season Pass progression ──
    try:
        from app.services.arena_points import award_arena_points, AP_RATES
        from app.services.season_pass import advance_season
        async with async_session() as ap_db:
            for uid in [session["player1_id"], session["player2_id"]]:
                if uid == BOT_ID:
                    continue
                is_winner = (winner_id is not None and uid == winner_id)
                is_draw = judge_result.is_draw
                if is_draw:
                    ap_source = "pvp_draw"
                elif is_winner:
                    ap_source = "pvp_win"
                else:
                    ap_source = "pvp_loss"
                ap_balance = await award_arena_points(ap_db, uid, ap_source)
                season_result = await advance_season(uid, AP_RATES[ap_source], ap_db)
                await _send_to_user(uid, "ap.earned", {
                    "amount": AP_RATES[ap_source],
                    "source": ap_source,
                    "balance": ap_balance,
                    "season": season_result,
                })
            await ap_db.commit()
    except Exception:
        logger.debug("AP/Season award failed for duel %s", duel_id, exc_info=True)

    # ── 3.5: Cross-module PvP notifications ──
    try:
        from app.ws.notifications import send_typed_notification, NotificationType
        for uid, delta in [
            (session["player1_id"], p1_delta),
            (session["player2_id"], p2_delta),
        ]:
            if uid == BOT_ID:
                continue
            uid_str = str(uid)
            # Significant rating gain → rank up notification
            if delta and delta > 30:
                await send_typed_notification(
                    uid_str,
                    NotificationType.PVP_RANK_UP,
                    f"Рейтинг +{int(delta)} ELO!",
                    "Отличная победа! Ваш рейтинг значительно вырос.",
                    action_url="/pvp",
                )
            # Winner scored high
            if str(uid) == str(winner_id) and max(p1_total, p2_total) >= 80:
                await send_typed_notification(
                    uid_str,
                    NotificationType.GAMIFICATION_ACHIEVEMENT,
                    "Доминирующая победа!",
                    f"Вы набрали {int(max(p1_total, p2_total))} в PvP дуэли.",
                    action_url=f"/pvp/duel/{duel_id}",
                )
    except Exception:
        logger.debug("PvP cross-module notification failed for duel %s", duel_id)

    await matchmaker.cleanup_duel_state(duel_id)
    await _cleanup_duel_runtime(duel_id)


async def _handle_duel_ready(user_id: uuid.UUID, duel_id: uuid.UUID) -> None:
    context = await _load_duel_context(duel_id)
    if not context:
        await _send_to_user(user_id, "error", {"detail": "Дуэль не найдена"})
        return
    duel = context["duel"]
    if duel.status == DuelStatus.cancelled:
        await _send_to_user(user_id, "duel.cancelled", {
            "duel_id": str(duel_id),
            "reason": "cancelled",
        })
        return
    if duel.status == DuelStatus.completed:
        await _send_to_user(user_id, "error", {"detail": "Дуэль уже завершена"})
        return
    if duel.player1_id != user_id and duel.player2_id != user_id:
        await _send_to_user(user_id, "error", {"detail": "Нет доступа к дуэли"})
        return

    session = await _ensure_session(duel_id, duel, context["player1_name"], context["player2_name"])
    # Apply scenario title from loaded context
    if context.get("scenario_title") and not session.get("scenario_title"):
        session["scenario_title"] = context["scenario_title"]
    session["ready"].add(user_id)
    _cancel_disconnect_task(user_id, duel_id)

    ready_required = 1 if session["is_pve"] else 2
    if session["started"]:
        await _send_duel_state(user_id, session)
        return

    if len(session["ready"]) < ready_required:
        return

    session["started"] = True
    # Initialize real-time anti-cheat tracking for both players
    ac_init_player(session["player1_id"], duel_id)
    ac_init_player(session["player2_id"], duel_id)
    await _start_round(duel_id, 1)


async def _handle_duel_message(user_id: uuid.UUID, text: str) -> None:
    session = next(
        (
            duel_session for duel_session in _duel_sessions.values()
            if user_id in (duel_session["player1_id"], duel_session["player2_id"])
            and duel_session["started"] and not duel_session["completed"]
        ),
        None,
    )
    if not session:
        await _send_to_user(user_id, "error", {"detail": "Активная дуэль не найдена"})
        return

    if session["completed"] or _remaining_round_time(session) <= 0:
        await _send_to_user(user_id, "error", {"detail": "Раунд уже завершён"})
        return

    # Security: filter user input (jailbreak detection + profanity)
    text, input_violations = filter_user_input(text)
    if input_violations:
        logger.warning("PvP user input violations [user=%s]: %s", user_id, input_violations)

    # Real-time anti-cheat: lightweight per-message checks (no IO)
    ac_result = ac_check_message(user_id, session["duel_id"], text)
    if ac_result.should_warn:
        await _send_to_user(user_id, "anti_cheat.warning", {
            "message": "Система обнаружила подозрительную активность. "
                       "Пожалуйста, формулируйте ответы самостоятельно.",
        })
    if ac_result.flags:
        logger.info("AC realtime [user=%s]: %s", user_id, ac_result.flags)

    round_number = session["round"]
    role = _player_role_for_round(session, user_id, round_number)
    payload = {
        "sender_role": role,
        "text": text,
        "round": round_number,
    }
    msg = {
        "sender_id": str(user_id),
        "role": role,
        "text": text,
        "timestamp": time.time(),
    }
    msg["round"] = round_number
    _duel_messages[session["duel_id"]][round_number].append(msg)
    session["history"][round_number].append({"role": "user", "content": text})

    if session["is_pve"]:
        await _send_to_user(user_id, "duel.message", payload)
        ai_role = "client" if role == "seller" else "seller"
        ai_reply = await _generate_ai_reply(session, round_number, text, ai_role)
        await _send_ai_message(session["duel_id"], round_number, ai_role, ai_reply)
        await _maybe_finish_round(session["duel_id"])
        return

    opponent_id = session["player2_id"] if user_id == session["player1_id"] else session["player1_id"]
    await _send_to_user(user_id, "duel.message", payload)
    await _send_to_user(opponent_id, "duel.message", payload)
    await _maybe_finish_round(session["duel_id"])


# ── Non-blocking background matchmaking (replaces _matchmaking_loop) ──
_matchmaking_tasks: dict[uuid.UUID, asyncio.Task] = {}


async def _background_matchmaking(user_id: uuid.UUID) -> None:
    """Background task: polls find_match() every 3s, sends results via _send_to_user.

    This runs as an asyncio.Task, NOT inside the main WS receive loop,
    so the main handler stays free to process duel.ready, duel.message, etc.
    """
    start_time = time.time()
    try:
        while True:
            elapsed = time.time() - start_time

            # Check if user left queue (via REST accept-pve or queue.leave)
            if not await matchmaker.is_in_queue(user_id):
                return

            async with async_session() as db:
                match = await matchmaker.find_match(user_id, db)
                # PvP-2 fix: always commit — find_match may flush queue metadata
                await db.commit()
                if match:
                    opponent_id = match["opponent_id"]
                    await _send_to_user(
                        user_id, "match.found",
                        _match_found_payload(match, user_id),
                    )
                    await _send_to_user(
                        opponent_id, "match.found",
                        _match_found_payload(match, opponent_id),
                    )
                    return

            if elapsed >= matchmaker.MATCH_TIMEOUT_SECONDS:
                # Timeout → auto-create PvE duel
                async with async_session() as db:
                    duel = await matchmaker.create_pve_duel(user_id, db)
                    await db.commit()
                await _send_to_user(user_id, "match.found", {
                    "duel_id": str(duel.id),
                    "difficulty": duel.difficulty.value,
                    "is_pve": True,
                })
                return

            # Send status update
            queue_size = await matchmaker.get_queue_size()
            await _send_to_user(user_id, "queue.status", {
                "position": queue_size,
                "queue_size": queue_size,
                "wait_seconds": int(elapsed),
                "estimated_remaining": max(
                    0, int(matchmaker.MATCH_TIMEOUT_SECONDS - elapsed)
                ),
            })

            await asyncio.sleep(3.0)
    except asyncio.CancelledError:
        # Cleanup: leave queue if task was cancelled (user disconnected / left)
        await matchmaker.leave_queue(user_id)
    except Exception as exc:
        logger.error(
            "Background matchmaking error for %s: %s", user_id, exc, exc_info=True,
        )
        await matchmaker.leave_queue(user_id)
        await _send_to_user(
            user_id, "error",
            {"detail": "Ошибка подбора соперника. Попробуйте снова."},
        )
    finally:
        _matchmaking_tasks.pop(user_id, None)


def _cancel_matchmaking_task(user_id: uuid.UUID) -> None:
    """Cancel a running background matchmaking task for the user."""
    task = _matchmaking_tasks.pop(user_id, None)
    if task and not task.done():
        task.cancel()


# ═══════════════════════════════════════════════════════════════════════════
# NEW PVP MODES: Rapid Fire, Gauntlet, Team 2v2
# ═══════════════════════════════════════════════════════════════════════════


def _difficulty_for_rating(rating: float) -> DuelDifficulty:
    """Determine difficulty tier from a single player's rating."""
    if rating < 1600:
        return DuelDifficulty.easy
    elif rating < 2200:
        return DuelDifficulty.medium
    return DuelDifficulty.hard


def _escalate_difficulty(base: DuelDifficulty, steps: int) -> DuelDifficulty:
    """Increase difficulty by N steps (easy -> medium -> hard)."""
    order = [DuelDifficulty.easy, DuelDifficulty.medium, DuelDifficulty.hard]
    idx = order.index(base) if base in order else 0
    return order[min(idx + steps, len(order) - 1)]


async def _score_rapid_mini_round(
    messages: list[dict[str, Any]],
    archetype: str,
    difficulty: DuelDifficulty,
    db,
) -> dict:
    """Score a single Rapid Fire mini-round. Returns {selling: 0-15, legal: 0-5, total: 0-20}."""
    try:
        seller_score, _ = await judge_round(
            dialog=messages,
            seller_id=uuid.UUID(int=0),
            client_id=BOT_ID,
            seller_name="Player",
            client_name="AI Client",
            archetype=archetype,
            difficulty=difficulty,
            round_number=1,
            db=db,
        )
        # Normalize to mini-round scale: selling 0-15 (from 0-50), legal 0-5 (from 0-20)
        selling = min(15.0, seller_score.selling_score * 15.0 / 50.0)
        legal = min(5.0, seller_score.legal_accuracy * 5.0 / 20.0)
        return {"selling": round(selling, 1), "legal": round(legal, 1), "total": round(selling + legal, 1)}
    except Exception as exc:
        logger.error("Rapid mini-round scoring failed: %s", exc, exc_info=True)
        return {"selling": 7.5, "legal": 2.5, "total": 10.0}


async def _handle_rapid_fire(ws: WebSocket, user_id: uuid.UUID, match_id: uuid.UUID) -> None:
    """Handle a full Rapid Fire match: 5 mini-rounds, seller-only, AI client.

    The player sends duel.message messages; after each mini-round (5 msgs or 120s),
    scores are sent and the next round starts with a new archetype.
    """
    try:
        async with async_session() as db:
            match = (await db.execute(
                select(RapidFireMatch).where(RapidFireMatch.id == match_id)
            )).scalar_one_or_none()
            if not match:
                await _send(ws, "error", {"detail": "Rapid Fire match not found"})
                return

            rating = await get_or_create_rating(user_id, db, rating_type="rapid_fire")
            base_difficulty = _difficulty_for_rating(rating.rating)

            # Pick 5 different archetypes
            archetypes = random.sample(
                _PVP_ARCHETYPES, min(RAPID_FIRE_ROUNDS, len(_PVP_ARCHETYPES))
            )
            match.archetypes = archetypes
            db.add(match)
            await db.flush()

        mini_scores: list[dict] = []
        session_key = f"rapid:{match_id}"

        await _send(ws, "rapid.started", {
            "match_id": str(match_id),
            "total_rounds": RAPID_FIRE_ROUNDS,
            "time_per_round": RAPID_FIRE_TIME_LIMIT,
            "messages_per_round": RAPID_FIRE_MSG_LIMIT,
        })

        for round_num in range(RAPID_FIRE_ROUNDS):
            archetype = archetypes[round_num]
            difficulty = _escalate_difficulty(base_difficulty, round_num // 2)

            await _send(ws, "rapid.round_start", {
                "round": round_num + 1,
                "archetype": archetype,
                "archetype_name": _ARCHETYPE_BRIEFS.get(archetype, {}).get("name", archetype),
                "difficulty": difficulty.value,
                "time_limit": RAPID_FIRE_TIME_LIMIT,
                "message_limit": RAPID_FIRE_MSG_LIMIT,
            })

            round_messages: list[dict[str, Any]] = []
            history: list[dict[str, str]] = []
            round_start = time.time()
            msg_count = 0

            while msg_count < RAPID_FIRE_MSG_LIMIT:
                remaining = RAPID_FIRE_TIME_LIMIT - (time.time() - round_start)
                if remaining <= 0:
                    await _send(ws, "rapid.round_time_up", {"round": round_num + 1})
                    break

                try:
                    raw = await asyncio.wait_for(ws.receive_json(), timeout=remaining)
                except (asyncio.TimeoutError, WebSocketDisconnect):
                    break

                msg_type = raw.get("type")
                if msg_type == "ping":
                    await _send(ws, "pong")
                    continue
                if msg_type != "duel.message":
                    continue

                text = (raw.get("text") or "").strip()[:2000]
                if not text:
                    continue

                text, _ = filter_user_input(text)
                msg_count += 1

                msg_record = {
                    "sender_id": str(user_id),
                    "role": "seller",
                    "text": text,
                    "timestamp": time.time(),
                }
                round_messages.append(msg_record)
                history.append({"role": "user", "content": text})

                await _send(ws, "duel.message", {
                    "sender_role": "seller",
                    "text": text,
                    "round": round_num + 1,
                })

                # Generate bot client reply
                try:
                    bot_reply = await generate_bot_reply(
                        duel_id=f"rapid-{match_id}-r{round_num}",
                        round_number=1,
                        archetype=archetype,
                        difficulty=difficulty,
                        ai_role="client",
                        user_text=text,
                        history=history,
                        player_id=str(user_id),
                        scenario_title=None,
                    )
                    bot_msg = {
                        "sender_id": str(BOT_ID),
                        "role": "client",
                        "text": bot_reply,
                        "timestamp": time.time(),
                    }
                    round_messages.append(bot_msg)
                    history.append({"role": "assistant", "content": bot_reply})

                    await _send(ws, "duel.message", {
                        "sender_role": "client",
                        "text": bot_reply,
                        "round": round_num + 1,
                    })
                except Exception as exc:
                    logger.warning("Rapid Fire bot reply failed: %s", exc)

            # Score this mini-round
            async with async_session() as db:
                score = await _score_rapid_mini_round(round_messages, archetype, difficulty, db)

            mini_scores.append(score)
            await _send(ws, "rapid.round_result", {
                "round": round_num + 1,
                "score": score,
                "archetype": archetype,
            })

            # Clean up bot state for this mini-round
            cleanup_bot_state(f"rapid-{match_id}-r{round_num}")

        # ── Final scoring ──
        total = sum(s["total"] for s in mini_scores)
        normalized = round(total * 100.0 / (RAPID_FIRE_MAX_SCORE * RAPID_FIRE_ROUNDS), 1) if mini_scores else 0.0

        # Apply rating change
        rating_delta = 0.0
        async with async_session() as db:
            match = (await db.execute(
                select(RapidFireMatch).where(RapidFireMatch.id == match_id)
            )).scalar_one_or_none()
            if match:
                match.mini_scores = mini_scores
                match.total_score = total
                match.normalized_score = normalized
                match.completed_at = datetime.now(timezone.utc)
                db.add(match)

                # Rating: treat as PvE with multiplier
                try:
                    pve_score = 1.0 if normalized >= 70 else (0.5 if normalized >= 40 else 0.0)
                    _, delta = await update_rating_after_duel(
                        user_id, BOT_ID, pve_score, True, db,
                    )
                    rating_delta = round(delta * RAPID_FIRE_RATING_MULTIPLIER, 1)
                    match.rating_delta = rating_delta
                except Exception as exc:
                    logger.warning("Rapid Fire rating update failed: %s", exc)

                await db.commit()

        # ── Arena Points + Season Pass for Rapid Fire ──
        ap_data = {}
        try:
            from app.services.arena_points import award_arena_points, AP_RATES
            from app.services.season_pass import advance_season
            async with async_session() as ap_db:
                ap_source = "pve_match"
                ap_balance = await award_arena_points(ap_db, user_id, ap_source)
                season_result = await advance_season(user_id, AP_RATES[ap_source], ap_db)
                await ap_db.commit()
                ap_data = {
                    "ap_earned": AP_RATES[ap_source],
                    "ap_source": ap_source,
                    "ap_balance": ap_balance,
                    "season": season_result,
                }
        except Exception as exc:
            logger.debug("Rapid Fire AP award failed: %s", exc)

        await _send(ws, "rapid.completed", {
            "match_id": str(match_id),
            "total": total,
            "normalized": normalized,
            "mini_scores": mini_scores,
            "rating_delta": rating_delta,
            **ap_data,
        })

    except WebSocketDisconnect:
        logger.info("Rapid Fire disconnected: user=%s match=%s", user_id, match_id)
    except Exception as exc:
        logger.error("Rapid Fire error: user=%s match=%s error=%s", user_id, match_id, exc, exc_info=True)
        try:
            await _send(ws, "error", {"detail": "Ошибка Rapid Fire режима"})
        except Exception:
            pass


async def _handle_gauntlet(ws: WebSocket, user_id: uuid.UUID, run_id: uuid.UUID) -> None:
    """Handle a Gauntlet run: 3-5 consecutive PvE duels with escalating difficulty.

    Player is always seller. 2 losses = elimination. Each duel is a single round.
    """
    try:
        async with async_session() as db:
            run = (await db.execute(
                select(GauntletRun).where(GauntletRun.id == run_id)
            )).scalar_one_or_none()
            if not run:
                await _send(ws, "error", {"detail": "Gauntlet run not found"})
                return

            rating = await get_or_create_rating(user_id, db)
            base_difficulty = _difficulty_for_rating(rating.rating)

        await _send(ws, "gauntlet.started", {
            "run_id": str(run_id),
            "total_duels": run.total_duels,
            "base_difficulty": base_difficulty.value,
        })

        duel_scores: list[float] = []
        duel_ids: list[str] = []
        difficulties: list[str] = []
        losses = 0

        for duel_num in range(run.total_duels):
            difficulty = _escalate_difficulty(base_difficulty, duel_num)
            archetype = random.choice(_PVP_ARCHETYPES)

            await _send(ws, "gauntlet.duel_start", {
                "duel_number": duel_num + 1,
                "total_duels": run.total_duels,
                "archetype": archetype,
                "archetype_name": _ARCHETYPE_BRIEFS.get(archetype, {}).get("name", archetype),
                "difficulty": difficulty.value,
                "losses": losses,
                "max_losses": GAUNTLET_MAX_LOSSES,
                "time_limit": GAUNTLET_TIME_LIMIT,
                "message_limit": GAUNTLET_MSG_LIMIT,
            })

            # Run a single-round duel (seller only)
            round_messages: list[dict[str, Any]] = []
            history: list[dict[str, str]] = []
            duel_start = time.time()
            msg_count = 0
            duel_session_key = f"gauntlet-{run_id}-d{duel_num}"

            # Generate bot opener (bot is client, player is seller)
            try:
                # No opener needed -- player (seller) speaks first in gauntlet
                pass
            except Exception:
                pass

            while msg_count < GAUNTLET_MSG_LIMIT:
                remaining = GAUNTLET_TIME_LIMIT - (time.time() - duel_start)
                if remaining <= 0:
                    await _send(ws, "gauntlet.duel_time_up", {"duel_number": duel_num + 1})
                    break

                try:
                    raw = await asyncio.wait_for(ws.receive_json(), timeout=remaining)
                except (asyncio.TimeoutError, WebSocketDisconnect):
                    break

                msg_type = raw.get("type")
                if msg_type == "ping":
                    await _send(ws, "pong")
                    continue
                if msg_type != "duel.message":
                    continue

                text = (raw.get("text") or "").strip()[:2000]
                if not text:
                    continue

                text, _ = filter_user_input(text)
                msg_count += 1

                msg_record = {
                    "sender_id": str(user_id),
                    "role": "seller",
                    "text": text,
                    "timestamp": time.time(),
                }
                round_messages.append(msg_record)
                history.append({"role": "user", "content": text})

                await _send(ws, "duel.message", {
                    "sender_role": "seller",
                    "text": text,
                    "round": duel_num + 1,
                })

                # Bot client reply
                try:
                    bot_reply = await generate_bot_reply(
                        duel_id=duel_session_key,
                        round_number=1,
                        archetype=archetype,
                        difficulty=difficulty,
                        ai_role="client",
                        user_text=text,
                        history=history,
                        player_id=str(user_id),
                        scenario_title=None,
                    )
                    bot_msg = {
                        "sender_id": str(BOT_ID),
                        "role": "client",
                        "text": bot_reply,
                        "timestamp": time.time(),
                    }
                    round_messages.append(bot_msg)
                    history.append({"role": "assistant", "content": bot_reply})

                    await _send(ws, "duel.message", {
                        "sender_role": "client",
                        "text": bot_reply,
                        "round": duel_num + 1,
                    })
                except Exception as exc:
                    logger.warning("Gauntlet bot reply failed: %s", exc)

            # Score this duel stage
            duel_score = 0.0
            async with async_session() as db:
                try:
                    seller_score, _ = await judge_round(
                        dialog=round_messages,
                        seller_id=user_id,
                        client_id=BOT_ID,
                        seller_name="Player",
                        client_name="AI Client",
                        archetype=archetype,
                        difficulty=difficulty,
                        round_number=1,
                        db=db,
                    )
                    duel_score = seller_score.total  # selling + legal (0-70 range)
                except Exception as exc:
                    logger.error("Gauntlet duel scoring failed: %s", exc, exc_info=True)
                    duel_score = 35.0  # neutral fallback

            duel_scores.append(duel_score)
            difficulties.append(difficulty.value)
            cleanup_bot_state(duel_session_key)

            is_loss = duel_score < GAUNTLET_LOSS_THRESHOLD
            if is_loss:
                losses += 1

            await _send(ws, "gauntlet.duel_result", {
                "duel_number": duel_num + 1,
                "score": round(duel_score, 1),
                "is_loss": is_loss,
                "losses": losses,
                "max_losses": GAUNTLET_MAX_LOSSES,
            })

            if losses >= GAUNTLET_MAX_LOSSES:
                await _send(ws, "gauntlet.eliminated", {
                    "duel_number": duel_num + 1,
                    "total_score": round(sum(duel_scores), 1),
                    "losses": losses,
                })
                break

        # ── Final result ──
        total_score = sum(duel_scores)
        completed_duels = len(duel_scores)
        is_eliminated = losses >= GAUNTLET_MAX_LOSSES

        async with async_session() as db:
            run = (await db.execute(
                select(GauntletRun).where(GauntletRun.id == run_id)
            )).scalar_one_or_none()
            if run:
                run.completed_duels = completed_duels
                run.losses = losses
                run.scores = duel_scores
                run.difficulties = difficulties
                run.final_score = total_score
                run.is_completed = True
                run.is_eliminated = is_eliminated
                run.completed_at = datetime.now(timezone.utc)

                # Rating bonus for gauntlet completion (proportional to duels survived)
                try:
                    pve_score = 1.0 if not is_eliminated else (0.5 if completed_duels >= 3 else 0.0)
                    _, delta = await update_rating_after_duel(
                        user_id, BOT_ID, pve_score, True, db,
                    )
                    run.rating_bonus = delta
                except Exception as exc:
                    logger.warning("Gauntlet rating update failed: %s", exc)

                db.add(run)
                await db.commit()

        # ── Arena Points + Season Pass for Gauntlet ──
        gauntlet_ap_data = {}
        try:
            from app.services.arena_points import award_arena_points, AP_RATES
            from app.services.season_pass import advance_season
            # Award AP per duel completed in gauntlet
            total_ap = AP_RATES["pve_match"] * completed_duels
            async with async_session() as ap_db:
                ap_balance = await award_arena_points(ap_db, user_id, "pve_match", amount=total_ap)
                season_result = await advance_season(user_id, total_ap, ap_db)
                await ap_db.commit()
                gauntlet_ap_data = {
                    "ap_earned": total_ap,
                    "ap_source": "gauntlet",
                    "ap_balance": ap_balance,
                    "season": season_result,
                }
        except Exception as exc:
            logger.debug("Gauntlet AP award failed: %s", exc)

        await _send(ws, "gauntlet.completed", {
            "run_id": str(run_id),
            "total_score": round(total_score, 1),
            "completed_duels": completed_duels,
            "total_duels": run.total_duels if run else GAUNTLET_MIN_DUELS,
            "losses": losses,
            "is_eliminated": is_eliminated,
            "duel_scores": [round(s, 1) for s in duel_scores],
            "difficulties": difficulties,
            "rating_bonus": run.rating_bonus if run else 0.0,
            **gauntlet_ap_data,
        })

    except WebSocketDisconnect:
        logger.info("Gauntlet disconnected: user=%s run=%s", user_id, run_id)
    except Exception as exc:
        logger.error("Gauntlet error: user=%s run=%s error=%s", user_id, run_id, exc, exc_info=True)
        try:
            await _send(ws, "error", {"detail": "Ошибка режима Испытание"})
        except Exception:
            pass


async def _handle_team_battle(ws: WebSocket, user_id: uuid.UUID, team_id: uuid.UUID) -> None:
    """Handle Team 2v2 mode (simplified: sequential, not truly parallel).

    Both team members are sellers. Each talks to their own AI client (different archetype).
    Team score = average of both sellers' scores.
    This simplified version has players take turns rather than true parallel WS.
    """
    try:
        async with async_session() as db:
            team = (await db.execute(
                select(PvPTeam).where(PvPTeam.id == team_id)
            )).scalar_one_or_none()
            if not team:
                await _send(ws, "error", {"detail": "Team not found"})
                return

            is_player1 = user_id == team.player1_id
            partner_id = team.player2_id if is_player1 else team.player1_id

        # Register this player in waiting room
        if team_id not in _team_waiting:
            _team_waiting[team_id] = {
                "team": team,
                "connected": set(),
                "ready": set(),
                "scores": {},
                "completed": False,
            }

        tw = _team_waiting[team_id]
        tw["connected"].add(user_id)

        # Choose 2 different archetypes for the two AI clients
        if "archetypes" not in tw:
            tw["archetypes"] = random.sample(_PVP_ARCHETYPES, 2)

        my_archetype = tw["archetypes"][0] if is_player1 else tw["archetypes"][1]

        await _send(ws, "team.waiting", {
            "team_id": str(team_id),
            "your_archetype": my_archetype,
            "archetype_name": _ARCHETYPE_BRIEFS.get(my_archetype, {}).get("name", my_archetype),
            "partner_connected": partner_id in tw["connected"],
        })

        # Wait for partner (up to 120 seconds)
        wait_start = time.time()
        while partner_id not in tw["connected"]:
            remaining = 120 - (time.time() - wait_start)
            if remaining <= 0:
                await _send(ws, "team.timeout", {"detail": "Партнёр не подключился"})
                _team_waiting.pop(team_id, None)
                return
            try:
                raw = await asyncio.wait_for(ws.receive_json(), timeout=min(5.0, remaining))
                if raw.get("type") == "ping":
                    await _send(ws, "pong")
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                tw["connected"].discard(user_id)
                return

        # Both connected — notify
        await _send(ws, "team.ready", {
            "team_id": str(team_id),
            "your_archetype": my_archetype,
            "archetype_name": _ARCHETYPE_BRIEFS.get(my_archetype, {}).get("name", my_archetype),
            "time_limit": TEAM_TIME_LIMIT,
            "message_limit": TEAM_MSG_LIMIT,
        })

        # Signal ready
        tw["ready"].add(user_id)
        while len(tw["ready"]) < 2:
            try:
                raw = await asyncio.wait_for(ws.receive_json(), timeout=10.0)
                if raw.get("type") == "ping":
                    await _send(ws, "pong")
                elif raw.get("type") == "team.ready_ack":
                    break
            except asyncio.TimeoutError:
                if len(tw["ready"]) >= 2:
                    break
                continue
            except WebSocketDisconnect:
                tw["connected"].discard(user_id)
                return

        # ── Run this player's individual selling conversation ──
        async with async_session() as db:
            rating = await get_or_create_rating(user_id, db, rating_type="team_battle")
            difficulty = _difficulty_for_rating(rating.rating)

        await _send(ws, "team.round_start", {
            "archetype": my_archetype,
            "difficulty": difficulty.value,
            "time_limit": TEAM_TIME_LIMIT,
            "message_limit": TEAM_MSG_LIMIT,
        })

        round_messages: list[dict[str, Any]] = []
        history: list[dict[str, str]] = []
        round_start = time.time()
        msg_count = 0
        team_duel_key = f"team-{team_id}-{user_id}"

        while msg_count < TEAM_MSG_LIMIT:
            remaining = TEAM_TIME_LIMIT - (time.time() - round_start)
            if remaining <= 0:
                await _send(ws, "team.time_up", {})
                break

            try:
                raw = await asyncio.wait_for(ws.receive_json(), timeout=remaining)
            except (asyncio.TimeoutError, WebSocketDisconnect):
                break

            msg_type = raw.get("type")
            if msg_type == "ping":
                await _send(ws, "pong")
                continue
            if msg_type != "duel.message":
                continue

            text = (raw.get("text") or "").strip()[:2000]
            if not text:
                continue

            text, _ = filter_user_input(text)
            msg_count += 1

            msg_record = {
                "sender_id": str(user_id),
                "role": "seller",
                "text": text,
                "timestamp": time.time(),
            }
            round_messages.append(msg_record)
            history.append({"role": "user", "content": text})

            await _send(ws, "duel.message", {
                "sender_role": "seller",
                "text": text,
                "round": 1,
            })

            try:
                bot_reply = await generate_bot_reply(
                    duel_id=team_duel_key,
                    round_number=1,
                    archetype=my_archetype,
                    difficulty=difficulty,
                    ai_role="client",
                    user_text=text,
                    history=history,
                    player_id=str(user_id),
                    scenario_title=None,
                )
                bot_msg = {
                    "sender_id": str(BOT_ID),
                    "role": "client",
                    "text": bot_reply,
                    "timestamp": time.time(),
                }
                round_messages.append(bot_msg)
                history.append({"role": "assistant", "content": bot_reply})

                await _send(ws, "duel.message", {
                    "sender_role": "client",
                    "text": bot_reply,
                    "round": 1,
                })
            except Exception as exc:
                logger.warning("Team 2v2 bot reply failed: %s", exc)

        # Score this player's conversation
        my_score = 0.0
        async with async_session() as db:
            try:
                seller_score, _ = await judge_round(
                    dialog=round_messages,
                    seller_id=user_id,
                    client_id=BOT_ID,
                    seller_name="Player",
                    client_name="AI Client",
                    archetype=my_archetype,
                    difficulty=difficulty,
                    round_number=1,
                    db=db,
                )
                my_score = seller_score.total
            except Exception as exc:
                logger.error("Team 2v2 scoring failed: %s", exc, exc_info=True)
                my_score = 35.0

        cleanup_bot_state(team_duel_key)

        # Store score and wait for partner
        tw["scores"][user_id] = my_score
        await _send(ws, "team.your_score", {
            "score": round(my_score, 1),
            "waiting_for_partner": partner_id not in tw["scores"],
        })

        # Wait for partner to finish (up to TEAM_TIME_LIMIT + 30s buffer)
        wait_start = time.time()
        while partner_id not in tw["scores"]:
            remaining = TEAM_TIME_LIMIT + 30 - (time.time() - wait_start)
            if remaining <= 0:
                tw["scores"].setdefault(partner_id, 0.0)
                break
            try:
                raw = await asyncio.wait_for(ws.receive_json(), timeout=min(5.0, remaining))
                if raw.get("type") == "ping":
                    await _send(ws, "pong")
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                return

        # ── Team result ──
        p1_score = tw["scores"].get(team.player1_id, 0.0)
        p2_score = tw["scores"].get(team.player2_id, 0.0)
        team_score = (p1_score + p2_score) / 2.0

        await _send(ws, "team.completed", {
            "team_id": str(team_id),
            "team_score": round(team_score, 1),
            "your_score": round(my_score, 1),
            "partner_score": round(tw["scores"].get(partner_id, 0.0), 1),
            "archetypes": tw["archetypes"],
        })

        # Update rating for this player
        async with async_session() as db:
            try:
                pve_score = 1.0 if team_score >= 50 else (0.5 if team_score >= 30 else 0.0)
                await update_rating_after_duel(
                    user_id, BOT_ID, pve_score, True, db,
                )
                await db.commit()
            except Exception as exc:
                logger.warning("Team 2v2 rating update failed: %s", exc)

        # ── Arena Points + Season Pass for Team 2v2 ──
        try:
            from app.services.arena_points import award_arena_points, AP_RATES
            from app.services.season_pass import advance_season
            async with async_session() as ap_db:
                ap_source = "pve_match"
                ap_balance = await award_arena_points(ap_db, user_id, ap_source)
                season_result = await advance_season(user_id, AP_RATES[ap_source], ap_db)
                await ap_db.commit()
                await _send(ws, "ap.earned", {
                    "amount": AP_RATES[ap_source],
                    "source": ap_source,
                    "balance": ap_balance,
                    "season": season_result,
                })
        except Exception as exc:
            logger.debug("Team 2v2 AP award failed: %s", exc)

        # Cleanup if both players done
        if len(tw["scores"]) >= 2:
            _team_waiting.pop(team_id, None)

    except WebSocketDisconnect:
        logger.info("Team 2v2 disconnected: user=%s team=%s", user_id, team_id)
        tw = _team_waiting.get(team_id)
        if tw:
            tw["connected"].discard(user_id)
    except Exception as exc:
        logger.error("Team 2v2 error: user=%s team=%s error=%s", user_id, team_id, exc, exc_info=True)
        try:
            await _send(ws, "error", {"detail": "Ошибка режима Командная битва"})
        except Exception:
            pass


async def pvp_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    auth = await _auth_websocket(websocket)
    if not auth:
        try:
            await websocket.close(code=1008)
        except RuntimeError:
            pass  # Already closed by client
        return

    user_id, _ = auth

    # ── B.2: Connection race guard ──────────────────────────────────────
    # Each connection gets a unique ID so the finally block only removes
    # its own entry (prevents new connection being popped by old one).
    conn_id = str(uuid.uuid4())
    old_entry = _active_connections.get(user_id)
    if old_entry:
        old_ws, _ = old_entry
        try:
            await old_ws.close(code=4001)  # "superseded by new connection"
        except Exception:
            pass
    _active_connections[user_id] = (websocket, conn_id)

    # Record fingerprint for multi-account detection
    try:
        from app.services.anti_cheat import record_fingerprint
        _ip = websocket.client.host if websocket.client else None
        _ua = dict(websocket.headers).get("user-agent")
        async with async_session() as _fp_db:
            await record_fingerprint(
                user_id=user_id,
                ip_address=_ip,
                user_agent=_ua,
                event_type="pvp_connect",
                db=_fp_db,
            )
            await _fp_db.commit()
    except Exception:
        logger.debug("Failed to record fingerprint for %s", user_id)

    try:
        reconnect = await matchmaker.check_reconnect(user_id)
        if reconnect:
            await matchmaker.clear_reconnect_grace(user_id)
            await _send(websocket, "duel.resumed", {
                "duel_id": str(reconnect["duel_id"]),
                "seconds_remaining": reconnect["seconds_remaining"],
            })

        _rate_limiter = pvp_limiter()
        while True:
            try:
                msg = await websocket.receive_json()
            except WebSocketDisconnect:
                break

            if not _rate_limiter.is_allowed():
                await _send(websocket, "error", {"code": "rate_limited", "detail": "Too many messages"})
                continue

            msg_type = msg.get("type")

            if msg_type == "ping":
                await _send(websocket, "pong")
                continue

            if msg_type == "duel.ready":
                duel_id_raw = msg.get("duel_id") or (msg.get("data") or {}).get("duel_id")
                if not duel_id_raw:
                    await _send(websocket, "error", {"detail": "duel_id is required"})
                    continue
                try:
                    duel_id_parsed = uuid.UUID(str(duel_id_raw))
                except (TypeError, ValueError):
                    await _send(websocket, "error", {"detail": "Invalid duel_id format"})
                    continue
                await _handle_duel_ready(user_id, duel_id_parsed)
                continue

            if msg_type == "duel.message":
                text = (msg.get("text") or "").strip()
                # B.3: Defense-in-depth — truncate before any processing
                text = text[:2000]
                if text:
                    await _handle_duel_message(user_id, text)
                continue

            if msg_type == "queue.leave":
                _cancel_matchmaking_task(user_id)
                await matchmaker.leave_queue(user_id)
                await _send(websocket, "queue.left")
                continue

            # ── B.1: Non-blocking queue.join ─────────────────────────────
            if msg_type == "queue.join":
                # Cancel any existing matchmaking task first
                _cancel_matchmaking_task(user_id)

                invitation_challenger_id = msg.get("invitation_challenger_id")
                if invitation_challenger_id:
                    # Invitation flow — synchronous, fast
                    try:
                        cid = uuid.UUID(invitation_challenger_id)
                    except (TypeError, ValueError):
                        await _send(websocket, "error", {"detail": "Invalid invitation"})
                        continue

                    async with async_session() as db:
                        match = await matchmaker.accept_invitation(cid, user_id, db)
                        await db.commit()
                    if not match:
                        await _send(websocket, "error", {"detail": "Приглашение истекло или недоступно"})
                        continue

                    await _send(websocket, "match.found", _match_found_payload(match, user_id))
                    await _send_to_user(cid, "match.found", _match_found_payload(match, cid))
                    continue

                # Regular queue join → background task (NON-BLOCKING)
                async with async_session() as db:
                    queue_result = await matchmaker.join_queue(user_id, db)
                    await db.commit()
                await _send(websocket, "queue.joined", queue_result)

                # Launch background matchmaking — main loop stays free!
                task = asyncio.create_task(_background_matchmaking(user_id))
                _matchmaking_tasks[user_id] = task
                continue

            # queue.watch: same as queue.join (backwards compat for FriendsPanel)
            if msg_type == "queue.watch":
                _cancel_matchmaking_task(user_id)
                async with async_session() as db:
                    queue_result = await matchmaker.join_queue(user_id, db)
                    await db.commit()
                await _send(websocket, "queue.joined", queue_result)
                task = asyncio.create_task(_background_matchmaking(user_id))
                _matchmaking_tasks[user_id] = task
                continue

            if msg_type == "pve.accept":
                _cancel_matchmaking_task(user_id)
                async with async_session() as db:
                    duel = await matchmaker.create_pve_duel(user_id, db)
                    await db.commit()
                await _send(websocket, "match.found", {
                    "duel_id": str(duel.id),
                    "difficulty": duel.difficulty.value,
                    "is_pve": True,
                })
                continue

            # ── New PvP Modes ───────────────────────────────────────────
            if msg_type == "rapid_fire.start":
                match_id_raw = msg.get("match_id") or (msg.get("data") or {}).get("match_id")
                if not match_id_raw:
                    await _send(websocket, "error", {"detail": "match_id is required"})
                    continue
                try:
                    rf_match_id = uuid.UUID(str(match_id_raw))
                except (TypeError, ValueError):
                    await _send(websocket, "error", {"detail": "Invalid match_id"})
                    continue
                # Rapid Fire takes over the WS loop
                await _handle_rapid_fire(websocket, user_id, rf_match_id)
                break  # After rapid fire completes, close WS

            if msg_type == "gauntlet.start":
                run_id_raw = msg.get("run_id") or (msg.get("data") or {}).get("run_id")
                if not run_id_raw:
                    await _send(websocket, "error", {"detail": "run_id is required"})
                    continue
                try:
                    g_run_id = uuid.UUID(str(run_id_raw))
                except (TypeError, ValueError):
                    await _send(websocket, "error", {"detail": "Invalid run_id"})
                    continue
                await _handle_gauntlet(websocket, user_id, g_run_id)
                break

            if msg_type == "team.start":
                team_id_raw = msg.get("team_id") or (msg.get("data") or {}).get("team_id")
                if not team_id_raw:
                    await _send(websocket, "error", {"detail": "team_id is required"})
                    continue
                try:
                    t_team_id = uuid.UUID(str(team_id_raw))
                except (TypeError, ValueError):
                    await _send(websocket, "error", {"detail": "Invalid team_id"})
                    continue
                await _handle_team_battle(websocket, user_id, t_team_id)
                break

            await _send(websocket, "error", {"detail": f"Unknown message type: {msg_type}"})

    except WebSocketDisconnect:
        logger.info("PvP WebSocket disconnected: user=%s", user_id)
    except Exception as exc:
        logger.error("PvP WebSocket error: user=%s error=%s", user_id, exc, exc_info=True)
        try:
            await _send(websocket, "error", {"detail": "Внутренняя ошибка сервера"})
        except Exception:
            pass  # Connection already closed
    finally:
        # ── B.2: Only remove OUR connection (not a newer one) ───────────
        entry = _active_connections.get(user_id)
        if entry and entry[1] == conn_id:
            _active_connections.pop(user_id, None)

        # Cancel matchmaking task
        _cancel_matchmaking_task(user_id)

        # Handle active duel disconnection
        for duel_id, session in list(_duel_sessions.items()):
            if user_id in (session["player1_id"], session["player2_id"]) and not session["completed"]:
                await matchmaker.set_reconnect_grace(user_id, duel_id)
                _cancel_disconnect_task(user_id, duel_id)
                _disconnect_tasks[(duel_id, user_id)] = asyncio.create_task(
                    _cancel_duel_after_disconnect(user_id, duel_id)
                )
                opponent_id = session["player2_id"] if user_id == session["player1_id"] else session["player1_id"]
                if opponent_id != BOT_ID:
                    await _send_to_user(opponent_id, "opponent.disconnected", {
                        "duel_id": str(duel_id),
                        "seconds_remaining": matchmaker.RECONNECT_GRACE_SECONDS,
                    })
        logger.info("PvP connection cleaned up: user=%s", user_id)
