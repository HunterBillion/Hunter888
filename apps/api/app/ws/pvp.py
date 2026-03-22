"""WebSocket endpoint for PvP and PvE arena duels."""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import or_, select

from app.core.security import decode_token
from app.database import async_session
from app.models.pvp import DuelStatus, PvPDuel
from app.models.user import User, UserRole
from app.services import pvp_matchmaker as matchmaker
from app.services.llm import generate_response
from app.services.pvp_judge import judge_full_duel
from app.services.rag_legal import retrieve_legal_context
from app.services.anti_cheat import run_anti_cheat
from app.services.glicko2 import update_rating_after_duel
from app.ws.notifications import notification_manager

logger = logging.getLogger(__name__)

BOT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
ROUND_TIME_LIMIT = 600
ROUND_MESSAGE_LIMIT = 8

_active_connections: dict[uuid.UUID, WebSocket] = {}
_duel_messages: dict[uuid.UUID, dict[int, list[dict[str, Any]]]] = {}
_duel_sessions: dict[uuid.UUID, dict[str, Any]] = {}


async def _send(ws: WebSocket, msg_type: str, data: dict | None = None) -> None:
    try:
        await ws.send_json({"type": msg_type, "data": data or {}})
    except Exception:
        pass


async def _send_to_user(user_id: uuid.UUID, msg_type: str, data: dict | None = None) -> None:
    ws = _active_connections.get(user_id)
    if ws:
        await _send(ws, msg_type, data)


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

    await _send(ws, "auth.success", {"user_id": str(user_id), "username": username})
    return user_id, username


def _player_role_for_round(session: dict[str, Any], user_id: uuid.UUID, round_number: int) -> str:
    if round_number == 1:
        return "seller" if user_id == session["player1_id"] else "client"
    return "client" if user_id == session["player1_id"] else "seller"


async def _load_duel_context(duel_id: uuid.UUID) -> dict[str, Any] | None:
    async with async_session() as db:
        duel = (await db.execute(select(PvPDuel).where(PvPDuel.id == duel_id))).scalar_one_or_none()
        if not duel:
            return None

        player_ids = [duel.player1_id]
        if duel.player2_id != BOT_ID:
            player_ids.append(duel.player2_id)

        result = await db.execute(select(User).where(User.id.in_(player_ids)))
        users = {user.id: user for user in result.scalars().all()}
        return {
            "duel": duel,
            "player1_name": users.get(duel.player1_id).full_name if users.get(duel.player1_id) else "Player 1",
            "player2_name": users.get(duel.player2_id).full_name if users.get(duel.player2_id) else "AI Бот",
        }


def _ensure_session(duel_id: uuid.UUID, duel: PvPDuel, player1_name: str, player2_name: str) -> dict[str, Any]:
    session = _duel_sessions.get(duel_id)
    if session:
        return session

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
        "is_pve": duel.is_pve,
        "ready": set(),
        "round": 1,
        "started": False,
        "round_task": None,
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
    await _send_to_user(session["player1_id"], "duel.message", payload)


async def _generate_ai_reply(session: dict[str, Any], round_number: int, user_text: str, ai_role: str) -> str:
    async with async_session() as db:
        rag_context = await retrieve_legal_context(user_text, db, top_k=3)

    if ai_role == "client":
        system_prompt = (
            "Ты играешь клиента в PvP-арене по банкротству физлиц. "
            "Отвечай по-русски, живо, короткими репликами, с сопротивлением и эмоцией. "
            "Не раскрывай, что ты ИИ. Держи 1-3 предложения."
        )
    else:
        system_prompt = (
            "Ты играешь менеджера по банкротству физлиц в PvP-арене. "
            "Говори уверенно, предметно, коротко. Веди к следующему шагу и не ломай роль."
        )

    system_prompt += f"\nСложность: {session['difficulty'].value}."
    if rag_context.has_results:
        system_prompt += "\n" + rag_context.to_prompt_context()

    response = await generate_response(
        system_prompt=system_prompt,
        messages=session["history"][round_number][-8:],
        emotion_state="testing" if ai_role == "client" else "considering",
        user_id=str(session["player1_id"]),
    )
    return response.content.strip()


async def _start_round(duel_id: uuid.UUID, round_number: int) -> None:
    session = _duel_sessions.get(duel_id)
    if not session or session["completed"]:
        return

    session["round"] = round_number
    await _update_duel_row(
        duel_id,
        status=DuelStatus.round_1 if round_number == 1 else DuelStatus.round_2,
        round_number=round_number,
    )

    for user_id in [session["player1_id"], session["player2_id"]]:
        if user_id == BOT_ID:
            continue
        role = _player_role_for_round(session, user_id, round_number)
        await _send_to_user(user_id, "duel.brief", {
            "duel_id": str(duel_id),
            "your_role": role,
            "archetype": "skeptic" if role == "client" else None,
            "human_factors": None,
            "difficulty": session["difficulty"].value,
            "scenario_title": session["scenario_title"],
            "round_number": round_number,
            "time_limit_seconds": ROUND_TIME_LIMIT,
        })
        await _send_to_user(user_id, "round.start", {
            "round": round_number,
            "your_role": role,
            "archetype": "skeptic" if role == "client" else None,
            "time_limit": ROUND_TIME_LIMIT,
        })

    task = session.get("round_task")
    if task and not task.done():
        task.cancel()
    session["round_task"] = asyncio.create_task(_finish_round_after_timeout(duel_id, round_number))

    if session["is_pve"]:
        user_role = _player_role_for_round(session, session["player1_id"], round_number)
        if user_role == "client":
            opener = await _generate_ai_reply(session, round_number, "Начни диалог и захвати инициативу.", "seller")
            await _send_ai_message(duel_id, round_number, "seller", opener)


async def _advance_round(duel_id: uuid.UUID) -> None:
    session = _duel_sessions.get(duel_id)
    if not session or session["completed"]:
        return

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

        duel.status = DuelStatus.judging
        db.add(duel)
        await db.flush()

        judge_result = await judge_full_duel(
            round1_dialog=round1_messages,
            round2_dialog=round2_messages,
            player1_id=session["player1_id"],
            player2_id=session["player2_id"],
            player1_name=session["player_names"][session["player1_id"]],
            player2_name=session["player_names"][session["player2_id"]],
            archetype="skeptic",
            difficulty=duel.difficulty,
            db=db,
        )

        duel.player1_total = judge_result.player1_total
        duel.player2_total = judge_result.player2_total
        duel.winner_id = judge_result.winner_id
        duel.is_draw = judge_result.is_draw
        duel.round_1_data = {"messages": round1_messages}
        duel.round_2_data = {"messages": round2_messages}
        duel.completed_at = datetime.now(timezone.utc)
        duel.status = DuelStatus.completed

        p1_delta = 0.0
        p2_delta = 0.0
        if not duel.is_pve:
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
            for uid in [duel.player1_id, duel.player2_id]:
                ac_result = await run_anti_cheat(uid, duel_id, round1_messages + round2_messages, db)
                if ac_result.flagged:
                    duel.anti_cheat_flags = duel.anti_cheat_flags or []
                    duel.anti_cheat_flags.append({
                        "player_id": str(uid),
                        "check_type": ac_result.check_type.value,
                        "score": ac_result.score,
                        "details": ac_result.details,
                    })

        duel.player1_rating_delta = p1_delta
        duel.player2_rating_delta = p2_delta
        duel.rating_change_applied = not duel.is_pve
        db.add(duel)
        await db.commit()

    result_data = {
        "duel_id": str(duel_id),
        "player1_total": judge_result.player1_total,
        "player2_total": judge_result.player2_total,
        "winner_id": str(judge_result.winner_id) if judge_result.winner_id else None,
        "is_draw": judge_result.is_draw,
        "player1_rating_delta": p1_delta,
        "player2_rating_delta": p2_delta,
        "summary": judge_result.summary if not session["is_pve"] else f"{judge_result.summary} PvE-результат без рейтингового изменения.",
    }
    for user_id in [session["player1_id"], session["player2_id"]]:
        if user_id != BOT_ID:
            await _send_to_user(user_id, "duel.result", result_data)

    await matchmaker.cleanup_duel_state(duel_id)


async def _handle_duel_ready(user_id: uuid.UUID, duel_id: uuid.UUID) -> None:
    context = await _load_duel_context(duel_id)
    if not context:
        await _send_to_user(user_id, "error", {"detail": "Дуэль не найдена"})
        return
    duel = context["duel"]
    if duel.player1_id != user_id and duel.player2_id != user_id:
        await _send_to_user(user_id, "error", {"detail": "Нет доступа к дуэли"})
        return

    session = _ensure_session(duel_id, duel, context["player1_name"], context["player2_name"])
    session["ready"].add(user_id)

    ready_required = 1 if session["is_pve"] else 2
    if session["started"] or len(session["ready"]) < ready_required:
        return

    session["started"] = True
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


async def _matchmaking_loop(ws: WebSocket, user_id: uuid.UUID) -> dict | None:
    start_time = time.time()
    while True:
        elapsed = time.time() - start_time
        async with async_session() as db:
            match = await matchmaker.find_match(user_id, db)
            if match:
                await db.commit()
                return match

        if elapsed >= matchmaker.MATCH_TIMEOUT_SECONDS:
            return None

        queue_size = await matchmaker.get_queue_size()
        await _send(ws, "queue.status", {
            "position": queue_size,
            "wait_seconds": int(elapsed),
            "estimated_remaining": max(0, int(matchmaker.MATCH_TIMEOUT_SECONDS - elapsed)),
        })
        try:
            msg = await asyncio.wait_for(ws.receive_json(), timeout=3.0)
        except asyncio.TimeoutError:
            continue
        except WebSocketDisconnect:
            await matchmaker.leave_queue(user_id)
            raise

        if msg.get("type") == "queue.leave":
            await matchmaker.leave_queue(user_id)
            await _send(ws, "queue.left")
            return "cancelled"
        if msg.get("type") == "ping":
            await _send(ws, "pong")


async def pvp_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    auth = await _auth_websocket(websocket)
    if not auth:
        await websocket.close(code=1008)
        return

    user_id, username = auth
    _active_connections[user_id] = websocket

    try:
        reconnect = await matchmaker.check_reconnect(user_id)
        if reconnect:
            await _send(websocket, "duel.resumed", {
                "duel_id": str(reconnect["duel_id"]),
                "seconds_remaining": reconnect["seconds_remaining"],
            })

        while True:
            try:
                msg = await websocket.receive_json()
            except WebSocketDisconnect:
                break

            msg_type = msg.get("type")

            if msg_type == "ping":
                await _send(websocket, "pong")
                continue

            if msg_type == "duel.ready":
                duel_id_raw = msg.get("duel_id") or (msg.get("data") or {}).get("duel_id")
                if not duel_id_raw:
                    await _send(websocket, "error", {"detail": "duel_id is required"})
                    continue
                await _handle_duel_ready(user_id, uuid.UUID(str(duel_id_raw)))
                continue

            if msg_type == "duel.message":
                text = (msg.get("text") or "").strip()
                if text:
                    await _handle_duel_message(user_id, text)
                continue

            if msg_type == "queue.leave":
                await matchmaker.leave_queue(user_id)
                await _send(websocket, "queue.left")
                continue

            if msg_type == "queue.join":
                invitation_challenger_id = msg.get("invitation_challenger_id")
                if invitation_challenger_id:
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

                    await _send(websocket, "match.found", {
                        "duel_id": str(match["duel_id"]),
                        "opponent_rating": match.get("opponent_rating"),
                        "difficulty": match["difficulty"],
                        "is_pve": False,
                    })
                    await _send_to_user(cid, "match.found", {
                        "duel_id": str(match["duel_id"]),
                        "difficulty": match["difficulty"],
                        "is_pve": False,
                    })
                    continue

                async with async_session() as db:
                    queue_result = await matchmaker.join_queue(user_id, db)
                    await db.commit()
                await _send(websocket, "queue.joined", queue_result)

                async with async_session() as db:
                    result = await db.execute(
                        select(User.id).where(
                            User.is_active.is_(True),
                            or_(User.role == UserRole.manager, User.role == UserRole.rop),
                            User.id != user_id,
                        )
                    )
                    for (target_id,) in result.all():
                        await notification_manager.send_to_user(str(target_id), {
                            "type": "pvp.invitation",
                            "data": {
                                "challenger_id": str(user_id),
                                "challenger_name": username,
                            },
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }, force=True)

                try:
                    match = await _matchmaking_loop(websocket, user_id)
                except WebSocketDisconnect:
                    await matchmaker.leave_queue(user_id)
                    break

                if match == "cancelled":
                    continue

                if match is None:
                    await _send(websocket, "pve.offer", {
                        "message": "Противник не найден за 60 секунд. Предлагаем дуэль с AI-ботом по RAG.",
                    })
                    continue

                opponent_id = match["opponent_id"]
                await _send(websocket, "match.found", {
                    "duel_id": str(match["duel_id"]),
                    "opponent_rating": match.get("opponent_rating"),
                    "difficulty": match["difficulty"],
                    "is_pve": False,
                })
                await _send_to_user(opponent_id, "match.found", {
                    "duel_id": str(match["duel_id"]),
                    "difficulty": match["difficulty"],
                    "is_pve": False,
                })
                continue

            if msg_type == "pve.accept":
                async with async_session() as db:
                    duel = await matchmaker.create_pve_duel(user_id, db)
                    await db.commit()
                await _send(websocket, "match.found", {
                    "duel_id": str(duel.id),
                    "difficulty": duel.difficulty.value,
                    "is_pve": True,
                })
                continue

            await _send(websocket, "error", {"detail": f"Unknown message type: {msg_type}"})

    except Exception as exc:
        logger.error("PvP WebSocket error: user=%s error=%s", user_id, exc)
        await _send(websocket, "error", {"detail": str(exc)})
    finally:
        _active_connections.pop(user_id, None)
        for duel_id, session in list(_duel_sessions.items()):
            if user_id in (session["player1_id"], session["player2_id"]) and not session["completed"]:
                await matchmaker.set_reconnect_grace(user_id, duel_id)
        logger.info("PvP connection cleaned up: user=%s", user_id)
