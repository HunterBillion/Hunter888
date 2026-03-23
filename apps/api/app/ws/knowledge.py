"""WebSocket handler for Knowledge Quiz (127-FZ knowledge testing).

Supports:
- AI Examiner mode (solo, text-based Q&A)
- PvP Arena mode (2-4 players, real-time competition)

Protocol:
  Client -> Server:
    auth                  - JWT token (first message, same as training WS)
    quiz.start            - {mode, category?, difficulty?, max_players?}
    text.message          - {text: string} (user's answer)
    quiz.skip             - {} (skip current question)
    quiz.hint             - {} (request hint, -2 points penalty)
    quiz.end              - {} (end quiz early)

    # PvP specific:
    pvp.find_opponent     - {max_players: 2|4, category?}
    pvp.accept_challenge  - {challenge_id: string}
    pvp.decline_challenge - {challenge_id: string}

    ping                  - keepalive

  Server -> Client:
    auth.success / auth.error
    quiz.ready            - {session_id, mode, total_questions, time_limit_per_question}
    quiz.question         - {text, category, difficulty, question_number, total_questions}
    quiz.feedback         - {is_correct, explanation, article_reference, score_delta, correct_answer?}
    quiz.hint             - {text, penalty}
    quiz.progress         - {current, total, correct, incorrect, skipped, score}
    quiz.completed        - {results: QuizResults}
    quiz.timeout          - {question_number}

    # PvP specific:
    pvp.searching         - {challenge_id, max_players, expires_in_seconds}
    pvp.opponent_found    - {opponent_name, opponent_id}
    pvp.challenge         - {challenge_id, challenger_name, category, max_players}
    pvp.match_ready       - {session_id, players, total_rounds}
    pvp.waiting_answers   - {question_number, time_limit_seconds}
    pvp.round_result      - {question, players, correct_answer, explanation}
    pvp.final_results     - {rankings, total_rounds}

    error                 - {message, code}
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import decode_token
from app.database import async_session
from app.models.user import User
from app.models.knowledge import (
    KnowledgeQuizSession,
    KnowledgeAnswer,
    QuizChallenge,
    QuizMode,
    QuizParticipant,
    QuizSessionStatus,
)
from app.services.knowledge_quiz import (
    QuizQuestion,
    evaluate_answer,
    evaluate_pvp_round,
    generate_question,
    get_total_questions,
    get_time_limit_seconds,
    get_user_weak_areas,
    calculate_quiz_results,
)

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

AUTH_TIMEOUT_SEC = 10.0
BLITZ_TIME_LIMIT_SEC = 60
PVP_ROUND_TIME_LIMIT_SEC = 90
PVP_CHALLENGE_EXPIRY_SEC = 60
PVP_ANSWER_TIMEOUT_SEC = 60

# ── Module-level state for PvP cross-connection tracking ─────────────────────

# session_id -> [(ws, user_id, username)]
_pvp_connections: dict[str, list[tuple[WebSocket, uuid.UUID, str]]] = {}

# challenge_id -> challenge metadata dict
_pvp_challenges: dict[str, dict] = {}

# user_id -> WebSocket (for sending PvP challenge notifications)
_knowledge_connections: dict[uuid.UUID, WebSocket] = {}


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _send(ws: WebSocket, msg_type: str, data: dict) -> None:
    """Send a typed JSON message to the client."""
    try:
        await ws.send_json({"type": msg_type, "data": data})
    except Exception:
        logger.debug("Failed to send message type=%s", msg_type)


async def _send_error(ws: WebSocket, message: str, code: str = "error") -> None:
    await _send(ws, "error", {"message": message, "code": code})


async def _auth_websocket(ws: WebSocket) -> tuple[uuid.UUID, str] | None:
    """Authenticate via first WS message containing JWT token.

    Returns (user_id, username) or None on failure.
    """
    try:
        msg = await asyncio.wait_for(ws.receive_json(), timeout=AUTH_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        await _send(ws, "auth.error", {"message": "Auth timeout"})
        return None
    except Exception:
        await _send(ws, "auth.error", {"message": "Invalid auth message"})
        return None

    token = msg.get("token") or (msg.get("data") or {}).get("token")
    if msg.get("type") != "auth" or not token:
        await _send(ws, "auth.error", {"message": "First message must be auth"})
        return None

    try:
        payload = decode_token(token)
        if payload is None or payload.get("type") != "access":
            await _send(ws, "auth.error", {"message": "Invalid or expired token"})
            return None
        user_id = uuid.UUID(payload["sub"])
    except Exception:
        await _send(ws, "auth.error", {"message": "Invalid token"})
        return None

    # Verify user exists and is active
    async with async_session() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            await _send(ws, "auth.error", {"message": "User not found or inactive"})
            return None
        username = user.full_name or user.email or str(user_id)[:8]

    # Check if user was logged out (token blacklisted)
    from app.core.deps import _is_user_blacklisted
    if await _is_user_blacklisted(str(user_id)):
        await _send(ws, "auth.error", {"message": "Token has been revoked"})
        return None

    await _send(ws, "auth.success", {"user_id": str(user_id), "username": username})
    return user_id, username


async def _send_to_pvp_session(
    session_id: str, msg_type: str, data: dict, *, exclude_user: uuid.UUID | None = None,
) -> None:
    """Broadcast a message to all connections in a PvP session."""
    connections = _pvp_connections.get(session_id, [])
    for ws, uid, _name in connections:
        if exclude_user and uid == exclude_user:
            continue
        await _send(ws, msg_type, data)


# ══════════════════════════════════════════════════════════════════════════════
# AI EXAMINER MODE — Solo quiz session state
# ══════════════════════════════════════════════════════════════════════════════

class _SoloQuizState:
    """In-memory state for a single AI examiner quiz session."""

    def __init__(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        mode: QuizMode,
        total_questions: int,
        time_limit: int | None,
        category: str | None,
        difficulty: int,
    ):
        self.session_id = session_id
        self.user_id = user_id
        self.mode = mode
        self.total_questions = total_questions
        self.time_limit = time_limit  # seconds per question (None = unlimited)
        self.category = category
        self.difficulty = difficulty

        self.current_question: int = 0
        self.correct: int = 0
        self.incorrect: int = 0
        self.skipped: int = 0
        self.score: float = 0.0
        self.hint_used_for_current: bool = False

        self.current_q: QuizQuestion | None = None
        self.question_start_time: float = 0.0
        self.timer_task: asyncio.Task | None = None
        self.finished: bool = False


async def _start_solo_quiz(
    ws: WebSocket,
    user_id: uuid.UUID,
    data: dict,
) -> _SoloQuizState | None:
    """Create quiz session in DB, generate first question, return state."""
    mode_str = data.get("mode", "free_dialog")
    try:
        mode = QuizMode(mode_str)
    except ValueError:
        await _send_error(ws, f"Invalid mode: {mode_str}", "invalid_mode")
        return None

    if mode == QuizMode.pvp:
        await _send_error(ws, "Use pvp.find_opponent for PvP mode", "invalid_mode")
        return None

    category = data.get("category")
    difficulty = int(data.get("difficulty", 3))
    difficulty = max(1, min(5, difficulty))

    total_questions = get_total_questions(mode)
    time_limit = get_time_limit_seconds(mode)

    # Create session in DB
    session_id = uuid.uuid4()
    async with async_session() as db:
        session = KnowledgeQuizSession(
            id=session_id,
            user_id=user_id,
            mode=mode,
            category=category,
            difficulty=difficulty,
            total_questions=total_questions,
            max_players=1,
            status=QuizSessionStatus.active,
        )
        db.add(session)

        participant = QuizParticipant(
            session_id=session_id,
            user_id=user_id,
            score=0.0,
        )
        db.add(participant)
        await db.commit()

    state = _SoloQuizState(
        session_id=session_id,
        user_id=user_id,
        mode=mode,
        total_questions=total_questions,
        time_limit=time_limit,
        category=category,
        difficulty=difficulty,
    )

    # Send quiz.ready
    await _send(ws, "quiz.ready", {
        "session_id": str(session_id),
        "mode": mode.value,
        "total_questions": total_questions,
        "time_limit_per_question": time_limit,
    })

    # Generate and send first question
    await _next_question(ws, state)
    return state


async def _next_question(ws: WebSocket, state: _SoloQuizState) -> None:
    """Generate the next question and send it to the client."""
    if state.current_question >= state.total_questions:
        await _finish_solo_quiz(ws, state)
        return

    state.current_question += 1
    state.hint_used_for_current = False

    # Get user weak areas for adaptive difficulty
    weak_areas = await get_user_weak_areas(state.user_id)

    question = await generate_question(
        mode=state.mode,
        category=state.category,
        difficulty=state.difficulty,
        question_number=state.current_question,
        weak_areas=weak_areas,
    )
    state.current_q = question
    state.question_start_time = time.time()

    await _send(ws, "quiz.question", {
        "text": question.text,
        "category": question.category,
        "difficulty": question.difficulty,
        "question_number": state.current_question,
        "total_questions": state.total_questions,
    })

    # Start blitz timer if needed
    if state.timer_task and not state.timer_task.done():
        state.timer_task.cancel()
    if state.time_limit:
        state.timer_task = asyncio.create_task(
            _blitz_timer(ws, state, state.current_question)
        )


async def _blitz_timer(ws: WebSocket, state: _SoloQuizState, question_number: int) -> None:
    """Timer for blitz mode: auto-skip after time limit."""
    try:
        await asyncio.sleep(state.time_limit)
        # Only fire if still on the same question
        if state.current_question == question_number and not state.finished:
            await _send(ws, "quiz.timeout", {"question_number": question_number})
            # Treat timeout as incorrect
            state.incorrect += 1
            await _save_answer(state, "", is_correct=False, explanation="Time expired", score_delta=-1.0)
            await _send_progress(ws, state)
            await _next_question(ws, state)
    except asyncio.CancelledError:
        pass


async def _handle_answer(ws: WebSocket, state: _SoloQuizState, text: str) -> None:
    """Evaluate user's answer and send feedback."""
    if state.finished or state.current_q is None:
        await _send_error(ws, "No active question", "no_question")
        return

    # Cancel blitz timer
    if state.timer_task and not state.timer_task.done():
        state.timer_task.cancel()

    response_time_ms = int((time.time() - state.question_start_time) * 1000)

    # Evaluate via service
    result = await evaluate_answer(
        question=state.current_q,
        user_answer=text,
        difficulty=state.difficulty,
    )

    # Calculate score delta
    if result.is_correct:
        score_delta = 10.0 if not state.hint_used_for_current else 8.0
        state.correct += 1
    else:
        score_delta = -2.0
        state.incorrect += 1
    state.score += score_delta

    # Save to DB
    await _save_answer(
        state,
        text,
        is_correct=result.is_correct,
        explanation=result.explanation,
        score_delta=score_delta,
        article_reference=result.article_reference,
        rag_chunks=result.rag_chunks_used,
        hint_used=state.hint_used_for_current,
        response_time_ms=response_time_ms,
    )

    # Send feedback
    feedback_data: dict = {
        "is_correct": result.is_correct,
        "explanation": result.explanation,
        "article_reference": result.article_reference,
        "score_delta": score_delta,
    }
    if not result.is_correct:
        feedback_data["correct_answer"] = result.correct_answer
    await _send(ws, "quiz.feedback", feedback_data)

    # Send progress
    await _send_progress(ws, state)

    # Next question
    await _next_question(ws, state)


async def _handle_skip(ws: WebSocket, state: _SoloQuizState) -> None:
    """Skip the current question."""
    if state.finished or state.current_q is None:
        await _send_error(ws, "No active question", "no_question")
        return

    if state.timer_task and not state.timer_task.done():
        state.timer_task.cancel()

    state.skipped += 1
    await _save_answer(state, "(skipped)", is_correct=False, explanation="Skipped", score_delta=0.0)
    await _send_progress(ws, state)
    await _next_question(ws, state)


async def _handle_hint(ws: WebSocket, state: _SoloQuizState) -> None:
    """Send a hint for the current question with a penalty."""
    if state.finished or state.current_q is None:
        await _send_error(ws, "No active question", "no_question")
        return

    if state.hint_used_for_current:
        await _send_error(ws, "Hint already used for this question", "hint_already_used")
        return

    state.hint_used_for_current = True
    penalty = -2.0
    state.score += penalty

    hint_text = state.current_q.hint or "Review the relevant articles of 127-FZ."

    await _send(ws, "quiz.hint", {
        "text": hint_text,
        "penalty": penalty,
    })


async def _send_progress(ws: WebSocket, state: _SoloQuizState) -> None:
    """Send current quiz progress."""
    await _send(ws, "quiz.progress", {
        "current": state.current_question,
        "total": state.total_questions,
        "correct": state.correct,
        "incorrect": state.incorrect,
        "skipped": state.skipped,
        "score": state.score,
    })


async def _save_answer(
    state: _SoloQuizState,
    user_answer: str,
    *,
    is_correct: bool,
    explanation: str,
    score_delta: float = 0.0,
    article_reference: str | None = None,
    rag_chunks: list | None = None,
    hint_used: bool = False,
    response_time_ms: int | None = None,
) -> None:
    """Persist an answer to the database."""
    if state.current_q is None:
        return
    async with async_session() as db:
        answer = KnowledgeAnswer(
            session_id=state.session_id,
            user_id=state.user_id,
            question_number=state.current_question,
            question_text=state.current_q.text,
            question_category=state.current_q.category or "general",
            user_answer=user_answer,
            is_correct=is_correct,
            explanation=explanation,
            article_reference=article_reference,
            score_delta=score_delta,
            rag_chunks_used=rag_chunks,
            hint_used=hint_used,
            response_time_ms=response_time_ms,
        )
        db.add(answer)
        await db.commit()


async def _finish_solo_quiz(ws: WebSocket, state: _SoloQuizState) -> None:
    """Finalize solo quiz, calculate results, update DB, send completed."""
    if state.finished:
        return
    state.finished = True

    if state.timer_task and not state.timer_task.done():
        state.timer_task.cancel()

    results = await calculate_quiz_results(
        session_id=state.session_id,
        user_id=state.user_id,
    )

    # Update DB session
    async with async_session() as db:
        db_session = await db.get(KnowledgeQuizSession, state.session_id)
        if db_session:
            db_session.status = QuizSessionStatus.completed
            db_session.ended_at = datetime.now(timezone.utc)
            db_session.correct_answers = state.correct
            db_session.incorrect_answers = state.incorrect
            db_session.skipped = state.skipped
            db_session.score = state.score
            started = db_session.started_at
            if started:
                db_session.duration_seconds = int(
                    (datetime.now(timezone.utc) - started).total_seconds()
                )
            await db.commit()

    await _send(ws, "quiz.completed", {"results": results})


# ══════════════════════════════════════════════════════════════════════════════
# PVP ARENA MODE
# ══════════════════════════════════════════════════════════════════════════════

PVP_TOTAL_ROUNDS = 10


async def _handle_find_opponent(
    ws: WebSocket,
    user_id: uuid.UUID,
    username: str,
    data: dict,
) -> None:
    """Create a PvP challenge and wait for opponents."""
    max_players = int(data.get("max_players", 2))
    if max_players not in (2, 4):
        max_players = 2
    category = data.get("category")

    challenge_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=PVP_CHALLENGE_EXPIRY_SEC)

    # Save challenge to DB
    async with async_session() as db:
        challenge = QuizChallenge(
            id=uuid.UUID(challenge_id),
            challenger_id=user_id,
            category=category,
            max_players=max_players,
            is_active=True,
            accepted_by=[],
            expires_at=expires_at,
        )
        db.add(challenge)
        await db.commit()

    # Track in memory
    _pvp_challenges[challenge_id] = {
        "challenger_ws": ws,
        "challenger_id": user_id,
        "challenger_name": username,
        "max_players": max_players,
        "category": category,
        "accepted": [],  # list of (ws, user_id, username)
        "expires_at": expires_at,
    }

    await _send(ws, "pvp.searching", {
        "challenge_id": challenge_id,
        "max_players": max_players,
        "expires_in_seconds": PVP_CHALLENGE_EXPIRY_SEC,
    })

    # Broadcast challenge to all connected knowledge WS users (except challenger)
    for uid, conn_ws in _knowledge_connections.items():
        if uid != user_id:
            await _send(conn_ws, "pvp.challenge", {
                "challenge_id": challenge_id,
                "challenger_name": username,
                "category": category,
                "max_players": max_players,
            })

    # Schedule expiry
    asyncio.create_task(_challenge_expiry_timer(challenge_id))


async def _challenge_expiry_timer(challenge_id: str) -> None:
    """Expire challenge after timeout if not enough players joined."""
    try:
        await asyncio.sleep(PVP_CHALLENGE_EXPIRY_SEC)
        challenge = _pvp_challenges.pop(challenge_id, None)
        if challenge is None:
            return  # Already started or cancelled

        # Mark expired in DB
        async with async_session() as db:
            db_challenge = await db.get(QuizChallenge, uuid.UUID(challenge_id))
            if db_challenge and db_challenge.is_active:
                db_challenge.is_active = False
                await db.commit()

        # Notify challenger
        await _send(challenge["challenger_ws"], "error", {
            "message": "Challenge expired, no opponents found",
            "code": "challenge_expired",
        })
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("Challenge expiry error: %s", e)


async def _handle_accept_challenge(
    ws: WebSocket,
    user_id: uuid.UUID,
    username: str,
    data: dict,
) -> None:
    """Accept a PvP challenge. When enough players join, start the match."""
    challenge_id = data.get("challenge_id")
    if not challenge_id:
        await _send_error(ws, "challenge_id required", "missing_field")
        return

    challenge = _pvp_challenges.get(challenge_id)
    if not challenge:
        await _send_error(ws, "Challenge not found or expired", "challenge_not_found")
        return

    if user_id == challenge["challenger_id"]:
        await _send_error(ws, "Cannot accept your own challenge", "self_challenge")
        return

    # Check if already accepted
    for _, uid, _ in challenge["accepted"]:
        if uid == user_id:
            await _send_error(ws, "Already accepted this challenge", "already_accepted")
            return

    challenge["accepted"].append((ws, user_id, username))

    # Notify challenger
    await _send(challenge["challenger_ws"], "pvp.opponent_found", {
        "opponent_name": username,
        "opponent_id": str(user_id),
    })

    # Notify acceptor
    await _send(ws, "pvp.opponent_found", {
        "opponent_name": challenge["challenger_name"],
        "opponent_id": str(challenge["challenger_id"]),
    })

    # Check if we have enough players
    needed = challenge["max_players"] - 1  # minus challenger
    if len(challenge["accepted"]) >= needed:
        # Remove from challenges, start match
        _pvp_challenges.pop(challenge_id, None)
        await _start_pvp_match(challenge)


async def _handle_decline_challenge(
    ws: WebSocket,
    user_id: uuid.UUID,
    data: dict,
) -> None:
    """Decline a PvP challenge (just ignore it)."""
    # Nothing to do server-side, just acknowledge
    challenge_id = data.get("challenge_id")
    await _send(ws, "pvp.decline.ok", {"challenge_id": challenge_id})


async def _start_pvp_match(challenge: dict) -> None:
    """Create a PvP session and start the match for all players."""
    session_id = uuid.uuid4()
    session_id_str = str(session_id)
    category = challenge.get("category")
    max_players = challenge["max_players"]

    # Collect all players: challenger + accepted
    all_players: list[tuple[WebSocket, uuid.UUID, str]] = [
        (challenge["challenger_ws"], challenge["challenger_id"], challenge["challenger_name"]),
    ]
    all_players.extend(challenge["accepted"])

    # Create session in DB
    async with async_session() as db:
        session = KnowledgeQuizSession(
            id=session_id,
            user_id=challenge["challenger_id"],
            mode=QuizMode.pvp,
            category=category,
            difficulty=3,
            total_questions=PVP_TOTAL_ROUNDS,
            max_players=max_players,
            status=QuizSessionStatus.active,
        )
        db.add(session)

        for _ws, uid, _name in all_players:
            participant = QuizParticipant(
                session_id=session_id,
                user_id=uid,
                score=0.0,
            )
            db.add(participant)
        await db.commit()

    # Update challenge in DB
    async with async_session() as db:
        db_challenge_id = challenge.get("challenge_db_id")
        # Find the challenge by challenger_id (most recent active)
        result = await db.execute(
            select(QuizChallenge)
            .where(
                QuizChallenge.challenger_id == challenge["challenger_id"],
                QuizChallenge.is_active == True,
            )
            .order_by(QuizChallenge.created_at.desc())
            .limit(1)
        )
        db_challenge = result.scalar_one_or_none()
        if db_challenge:
            db_challenge.is_active = False
            db_challenge.session_id = session_id
            db_challenge.accepted_by = [str(uid) for _, uid, _ in challenge["accepted"]]
            await db.commit()

    # Track PvP connections
    _pvp_connections[session_id_str] = list(all_players)

    # Notify all players
    players_data = [
        {"user_id": str(uid), "name": name}
        for _ws, uid, name in all_players
    ]
    for ws, _uid, _name in all_players:
        await _send(ws, "pvp.match_ready", {
            "session_id": session_id_str,
            "players": players_data,
            "total_rounds": PVP_TOTAL_ROUNDS,
        })

    # Start the PvP game loop in a background task
    asyncio.create_task(_pvp_game_loop(session_id_str, session_id, all_players, category))


async def _pvp_game_loop(
    session_id_str: str,
    session_id: uuid.UUID,
    players: list[tuple[WebSocket, uuid.UUID, str]],
    category: str | None,
) -> None:
    """Run the PvP quiz: generate questions, collect answers, judge rounds."""
    scores: dict[uuid.UUID, float] = {uid: 0.0 for _, uid, _ in players}

    try:
        for round_num in range(1, PVP_TOTAL_ROUNDS + 1):
            # Generate question
            question = await generate_question(
                mode=QuizMode.pvp,
                category=category,
                difficulty=3,
                question_number=round_num,
            )

            # Send question to all players
            q_data = {
                "text": question.text,
                "category": question.category,
                "difficulty": question.difficulty,
                "question_number": round_num,
                "total_questions": PVP_TOTAL_ROUNDS,
            }
            await _send_to_pvp_session(session_id_str, "quiz.question", q_data)
            await _send_to_pvp_session(session_id_str, "pvp.waiting_answers", {
                "question_number": round_num,
                "time_limit_seconds": PVP_ANSWER_TIMEOUT_SEC,
            })

            # Collect answers from all players (with timeout)
            answers: dict[uuid.UUID, str] = {}
            deadline = time.time() + PVP_ANSWER_TIMEOUT_SEC
            answer_futures: dict[uuid.UUID, asyncio.Task] = {}

            for ws, uid, _name in players:
                answer_futures[uid] = asyncio.create_task(
                    _wait_for_pvp_answer(ws, uid, deadline)
                )

            # Wait for all answers or timeout
            done, pending = await asyncio.wait(
                answer_futures.values(),
                timeout=PVP_ANSWER_TIMEOUT_SEC + 2,
                return_when=asyncio.ALL_COMPLETED,
            )

            for uid, task in answer_futures.items():
                if task.done() and not task.cancelled():
                    try:
                        answers[uid] = task.result()
                    except Exception:
                        answers[uid] = ""
                else:
                    task.cancel()
                    answers[uid] = ""

            # Evaluate all answers
            round_results = await evaluate_pvp_round(
                question=question,
                answers=answers,
            )

            # Build per-player result data and update scores
            player_results = []
            for ws, uid, name in players:
                result = round_results.get(uid)
                if result:
                    score_delta = result.score_delta
                    scores[uid] += score_delta
                    player_results.append({
                        "user_id": str(uid),
                        "name": name,
                        "answer": answers.get(uid, ""),
                        "score": scores[uid],
                        "score_delta": score_delta,
                        "is_correct": result.is_correct,
                        "comment": result.comment,
                    })
                else:
                    player_results.append({
                        "user_id": str(uid),
                        "name": name,
                        "answer": answers.get(uid, ""),
                        "score": scores[uid],
                        "score_delta": 0.0,
                        "is_correct": False,
                        "comment": "No evaluation available",
                    })

            # Save answers to DB
            async with async_session() as db:
                for uid, answer_text in answers.items():
                    r = round_results.get(uid)
                    answer_record = KnowledgeAnswer(
                        session_id=session_id,
                        user_id=uid,
                        question_number=round_num,
                        question_text=question.text,
                        question_category=question.category or "general",
                        user_answer=answer_text or "(no answer)",
                        is_correct=r.is_correct if r else False,
                        explanation=r.explanation if r else "Timeout",
                        article_reference=r.article_reference if r else None,
                        score_delta=r.score_delta if r else 0.0,
                    )
                    db.add(answer_record)
                await db.commit()

            # Send round results to all players
            await _send_to_pvp_session(session_id_str, "pvp.round_result", {
                "question": question.text,
                "question_number": round_num,
                "players": player_results,
                "correct_answer": question.correct_answer if hasattr(question, "correct_answer") else None,
                "explanation": round_results.get(next(iter(answers)), None)
                    and round_results[next(iter(answers))].explanation or "",
            })

            # Brief pause between rounds
            await asyncio.sleep(3)

        # ── All rounds complete ──
        # Calculate final rankings
        rankings = sorted(
            [
                {"user_id": str(uid), "name": name, "score": scores[uid]}
                for _, uid, name in players
            ],
            key=lambda x: x["score"],
            reverse=True,
        )
        for i, r in enumerate(rankings):
            r["rank"] = i + 1

        # Update DB
        async with async_session() as db:
            db_session = await db.get(KnowledgeQuizSession, session_id)
            if db_session:
                db_session.status = QuizSessionStatus.completed
                db_session.ended_at = datetime.now(timezone.utc)
                started = db_session.started_at
                if started:
                    db_session.duration_seconds = int(
                        (datetime.now(timezone.utc) - started).total_seconds()
                    )
                await db.commit()

            # Update participant scores and ranks
            for ranking in rankings:
                uid = uuid.UUID(ranking["user_id"])
                result = await db.execute(
                    select(QuizParticipant).where(
                        QuizParticipant.session_id == session_id,
                        QuizParticipant.user_id == uid,
                    )
                )
                participant = result.scalar_one_or_none()
                if participant:
                    participant.score = ranking["score"]
                    participant.final_rank = ranking["rank"]
            await db.commit()

        # Send final results
        await _send_to_pvp_session(session_id_str, "pvp.final_results", {
            "rankings": rankings,
            "total_rounds": PVP_TOTAL_ROUNDS,
        })

    except Exception as e:
        logger.error("PvP game loop error session=%s: %s", session_id_str, e, exc_info=True)
        await _send_to_pvp_session(session_id_str, "error", {
            "message": "Game error, session terminated",
            "code": "game_error",
        })
    finally:
        # Cleanup
        _pvp_connections.pop(session_id_str, None)


async def _wait_for_pvp_answer(ws: WebSocket, user_id: uuid.UUID, deadline: float) -> str:
    """Wait for a single player's answer within the time limit.

    Listens for text.message, ignores pings and other message types.
    Returns the answer text or empty string on timeout/error.
    """
    try:
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                return ""
            raw = await asyncio.wait_for(ws.receive_text(), timeout=remaining)
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            msg_type = msg.get("type")
            if msg_type == "text.message":
                return (msg.get("data") or {}).get("text", "")
            elif msg_type == "ping":
                await _send(ws, "pong", {})
            # Ignore other messages during answer collection
    except (asyncio.TimeoutError, WebSocketDisconnect, Exception):
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# MAIN WEBSOCKET HANDLER
# ══════════════════════════════════════════════════════════════════════════════

async def knowledge_websocket(websocket: WebSocket) -> None:
    """Main WebSocket handler for /ws/knowledge.

    Handles authentication, then dispatches messages to either
    AI Examiner (solo) or PvP Arena mode handlers.
    """
    await websocket.accept()
    user_id: uuid.UUID | None = None
    username: str = ""
    quiz_state: _SoloQuizState | None = None

    try:
        # ── Step 1: Authenticate ──
        auth_result = await _auth_websocket(websocket)
        if auth_result is None:
            await websocket.close(code=4001)
            return
        user_id, username = auth_result

        # Track connection for PvP challenge broadcasts
        _knowledge_connections[user_id] = websocket

        logger.info("WS Knowledge authenticated: user=%s (%s)", user_id, username)

        # ── Step 2: Message loop ──
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await _send_error(websocket, "Invalid JSON", "parse_error")
                continue

            msg_type = msg.get("type")
            data = msg.get("data") or {}

            # ── Keepalive ──
            if msg_type == "ping":
                await _send(websocket, "pong", {})

            # ── Solo quiz start ──
            elif msg_type == "quiz.start":
                if quiz_state and not quiz_state.finished:
                    await _send_error(websocket, "Quiz already in progress", "already_started")
                    continue
                quiz_state = await _start_solo_quiz(websocket, user_id, data)

            # ── Answer (solo mode) ──
            elif msg_type == "text.message":
                text = data.get("text", "").strip()
                if not text:
                    await _send_error(websocket, "Empty answer", "empty_text")
                    continue
                if quiz_state and not quiz_state.finished:
                    await _handle_answer(websocket, quiz_state, text)
                else:
                    await _send_error(websocket, "No active quiz session", "no_session")

            # ── Skip question (solo) ──
            elif msg_type == "quiz.skip":
                if quiz_state and not quiz_state.finished:
                    await _handle_skip(websocket, quiz_state)
                else:
                    await _send_error(websocket, "No active quiz session", "no_session")

            # ── Hint (solo) ──
            elif msg_type == "quiz.hint":
                if quiz_state and not quiz_state.finished:
                    await _handle_hint(websocket, quiz_state)
                else:
                    await _send_error(websocket, "No active quiz session", "no_session")

            # ── End quiz early (solo) ──
            elif msg_type == "quiz.end":
                if quiz_state and not quiz_state.finished:
                    await _finish_solo_quiz(websocket, quiz_state)
                else:
                    await _send_error(websocket, "No active quiz session", "no_session")

            # ── PvP: Find opponent ──
            elif msg_type == "pvp.find_opponent":
                await _handle_find_opponent(websocket, user_id, username, data)

            # ── PvP: Accept challenge ──
            elif msg_type == "pvp.accept_challenge":
                await _handle_accept_challenge(websocket, user_id, username, data)

            # ── PvP: Decline challenge ──
            elif msg_type == "pvp.decline_challenge":
                await _handle_decline_challenge(websocket, user_id, data)

            # ── Unknown ──
            else:
                await _send_error(
                    websocket,
                    f"Unknown message type: {msg_type}",
                    "unknown_type",
                )

    except WebSocketDisconnect:
        logger.info("WS Knowledge disconnected: user=%s", user_id)
    except json.JSONDecodeError:
        logger.warning("WS Knowledge: invalid JSON from user=%s", user_id)
        try:
            await websocket.close(code=1003)
        except Exception:
            pass
    except Exception as e:
        logger.error("WS Knowledge error user=%s: %s", user_id, e, exc_info=True)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        # Cleanup
        if user_id:
            _knowledge_connections.pop(user_id, None)

        # If solo quiz was in progress, mark as abandoned
        if quiz_state and not quiz_state.finished:
            quiz_state.finished = True
            if quiz_state.timer_task and not quiz_state.timer_task.done():
                quiz_state.timer_task.cancel()
            try:
                async with async_session() as db:
                    db_session = await db.get(KnowledgeQuizSession, quiz_state.session_id)
                    if db_session and db_session.status == QuizSessionStatus.active:
                        db_session.status = QuizSessionStatus.abandoned
                        db_session.ended_at = datetime.now(timezone.utc)
                        await db.commit()
            except Exception as e:
                logger.error("Failed to mark quiz as abandoned: %s", e)

        # Remove from any PvP session connections
        if user_id:
            for sid, conns in list(_pvp_connections.items()):
                _pvp_connections[sid] = [
                    (ws, uid, name) for ws, uid, name in conns if uid != user_id
                ]
                if not _pvp_connections[sid]:
                    _pvp_connections.pop(sid, None)
