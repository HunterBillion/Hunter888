"""WebSocket handler for Knowledge Quiz (127-FZ knowledge testing).

Supports:
- AI Examiner mode (solo, text-based Q&A)
- PvP Arena mode (2-4 players, real-time competition via Redis)

Protocol:
  Client -> Server:
    auth                  - JWT token (first message, same as training WS)
    quiz.start            - {mode, category?, difficulty?, max_players?, session_size?}
    text.message          - {text: string} (user's answer)
    srs.stats             - {} (request SRS statistics)
    srs.mastery           - {} (request per-category mastery breakdown)
    quiz.skip             - {} (skip current question)
    quiz.hint             - {} (request hint, -2 points penalty)
    quiz.end              - {} (end quiz early)

    # PvP specific:
    pvp.find_opponent     - {max_players: 2|4, category?}
    pvp.accept_challenge  - {challenge_id: string}
    pvp.decline_challenge - {challenge_id: string}
    pvp.answer            - {text: string, round_number: int}
    pvp.cancel_search     - {}
    pvp.play_with_bot     - {}

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

    # SRS specific:
    srs.session_info      - {stats, category_breakdown, session_size, estimated_time_minutes}
    srs.progress          - {question_number, answered_in_session, leitner_box_before/after, streak, ...}
    srs.stats             - {total_items, overdue_count, avg_ef, accuracy_pct, leitner_distribution, ...}
    srs.mastery           - {categories: [{category, total, mastered, overdue, mastery_pct, accuracy_pct}]}

    # PvP specific:
    pvp.searching         - {challenge_id, max_players, expires_in_seconds}
    pvp.player_joined     - {player_name, players_count, players_needed}
    pvp.challenge         - {challenge_id, challenger_name, category, max_players}
    pvp.match_ready       - {session_id, players, total_rounds}
    pvp.round_question    - {question_text, category, difficulty, round_number, total_rounds, time_limit_seconds}
    pvp.player_answered   - {user_id} (content hidden)
    pvp.round_result      - {round_number, question, players, correct_answer, explanation, article_ref}
    pvp.scoreboard        - {players: [{user_id, name, total_score, correct_count}]}
    pvp.final_results     - {rankings, total_rounds, contains_bot}
    pvp.no_opponents      - {offer_bot: true}
    pvp.bot_joined        - {bot_name, bot_id}
    pvp.player_disconnected  - {user_id, grace_seconds}
    pvp.player_reconnected   - {user_id}
    pvp.player_replaced_by_bot - {original_user_id, bot_id}
    pvp.match_state_restore  - {full state for reconnect}

    error                 - {message, code}
"""

import asyncio
import json
import logging
import random
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
    DebateSession,
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
    evaluate_answer_v2,
    evaluate_pvp_round,
    generate_question,
    generate_follow_up,
    generate_guiding_hint,
    get_total_questions,
    get_time_limit_seconds,
    get_user_weak_areas,
    calculate_quiz_results,
    calculate_blitz_speed_bonus,
    themed_difficulty_range,
)
from app.services.spaced_repetition import (
    record_review as srs_record_review,
    get_review_priority_queue as srs_get_review_queue,
    start_srs_session,
    get_user_srs_stats,
    get_category_mastery,
)
from app.services.ai_personalities import (
    PersonalityConfig,
    get_personality,
    get_personality_reaction,
)
from app.services.rag_legal import blitz_pool, RetrievalConfig, retrieve_legal_context
from app.core.ws_rate_limiter import knowledge_limiter
from app.services.arena_redis import (
    ArenaRedis,
    get_arena_redis,
    MATCH_EVENTS_CHANNEL,
    GLOBAL_EVENTS_CHANNEL,
)
from app.services.arena_round_collector import (
    calculate_speed_bonuses,
    wait_for_all_answers,
)
from app.services.content_filter import filter_answer_text, filter_user_input, detect_jailbreak

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

AUTH_TIMEOUT_SEC = 10.0
BLITZ_TIME_LIMIT_SEC = 60
PVP_ROUND_TIME_LIMIT_SEC = 45
PVP_CHALLENGE_EXPIRY_SEC = 60
PVP_TOTAL_ROUNDS = 10


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
    from app.core.deps import _is_user_blacklisted, _is_token_revoked
    if await _is_user_blacklisted(str(user_id)):
        await _send(ws, "auth.error", {"message": "Token has been revoked"})
        return None

    # Per-token JTI revocation
    jti = payload.get("jti")
    if jti and await _is_token_revoked(jti):
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

        # V2: Adaptive difficulty & personality
        self.consecutive_correct: int = 0
        self.consecutive_incorrect: int = 0
        self.current_difficulty: int = difficulty
        self.best_streak: int = 0
        self.personality: PersonalityConfig | None = None
        self.follow_up_counter: int = 0
        self.pending_follow_up: bool = False
        self.session_start_time: float = time.time()
        self.asked_chunk_ids: set[uuid.UUID] = set()
        self.previous_questions: list[str] = []

        # SRS Review Mode state
        self.srs_queue: list[dict] = []  # preloaded review items from start_srs_session
        self.srs_current_item: dict | None = None  # currently shown SRS item (has leitner_box, streak, etc.)
        self.srs_answers_in_session: int = 0  # number of SRS items answered this session

    def update_adaptive_difficulty(self, is_correct: bool) -> int:
        """Update difficulty based on answer streaks. Returns new difficulty."""
        if is_correct:
            self.consecutive_correct += 1
            self.consecutive_incorrect = 0
            if self.consecutive_correct > self.best_streak:
                self.best_streak = self.consecutive_correct
            if self.consecutive_correct >= 3:
                self.current_difficulty = min(5, self.current_difficulty + 1)
                self.consecutive_correct = 0
        else:
            self.consecutive_incorrect += 1
            self.consecutive_correct = 0
            if self.consecutive_incorrect >= 2:
                self.current_difficulty = max(1, self.current_difficulty - 1)
                self.consecutive_incorrect = 0
        return self.current_difficulty

    def should_follow_up(self) -> bool:
        """Check if this is a follow-up turn (every 3rd answer in free_dialog)."""
        if self.mode != QuizMode.free_dialog:
            return False
        self.follow_up_counter += 1
        return self.follow_up_counter % 3 == 0


# ── Session limits for free_dialog ──
FREE_DIALOG_SOFT_LIMIT = 30
FREE_DIALOG_HARD_LIMIT = 50
FREE_DIALOG_TIME_LIMIT = 1800  # 30 minutes


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

    # ── SRS Review Mode: preload review queue ──
    srs_queue: list[dict] = []
    if mode == QuizMode.srs_review:
        try:
            async with async_session() as srs_db:
                srs_session_data = await start_srs_session(
                    srs_db, user_id,
                    category=category,
                    session_size=int(data.get("session_size", 10)),
                )
                srs_queue = srs_session_data.get("review_queue", [])
                await _send(ws, "srs.session_info", {
                    "stats": srs_session_data.get("stats", {}),
                    "category_breakdown": srs_session_data.get("category_breakdown", []),
                    "session_size": len(srs_queue),
                    "estimated_time_minutes": srs_session_data.get("estimated_time_minutes", 5),
                })
        except Exception:
            logger.warning("SRS session init failed, falling back to themed mode", exc_info=True)
            mode = QuizMode.themed

    total_questions = get_total_questions(mode) if not srs_queue else len(srs_queue)
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

    # V2: Select AI personality
    ai_personality_pref = data.get("ai_personality")
    personality = get_personality(mode_str, ai_personality_pref)

    # Save personality to DB session
    async with async_session() as db:
        db_session = await db.get(KnowledgeQuizSession, session_id)
        if db_session:
            db_session.ai_personality = personality.name
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
    state.personality = personality

    # SRS: store preloaded queue into state
    if srs_queue:
        state.srs_queue = srs_queue

    # Send quiz.ready with personality data
    await _send(ws, "quiz.ready", {
        "session_id": str(session_id),
        "mode": mode.value,
        "total_questions": total_questions,
        "time_limit_per_question": time_limit,
        "ai_personality": {
            "name": personality.name,
            "display_name": personality.display_name,
            "avatar_emoji": personality.avatar_emoji,
            "greeting": personality.greeting,
        },
    })

    # Debate / Mock Court: start debate session instead of generating questions
    if mode in (QuizMode.debate, QuizMode.mock_court):
        await _start_debate_session(ws, state, data)
        return state

    # Case Study: generate a case overview first, then questions
    if mode == QuizMode.case_study:
        try:
            from app.services.rag_legal import retrieve_legal_context as _rag_retrieve
            async with async_session() as rag_db:
                ctx = await _rag_retrieve("реальный судебный кейс банкротство", rag_db, top_k=2)
                if ctx and ctx.chunks:
                    case_text = ctx.chunks[0].text[:1500]
                else:
                    case_text = (
                        "Гражданин Иванов И.И. обратился в арбитражный суд с заявлением "
                        "о признании его банкротом. Общая сумма долга — 2.5 млн руб. "
                        "Единственное жилье — квартира 45 кв.м. Есть автомобиль 2018 г.в."
                    )
        except Exception:
            case_text = (
                "Гражданин Иванов И.И. обратился в арбитражный суд с заявлением "
                "о признании его банкротом. Общая сумма долга — 2.5 млн руб."
            )
        await _send(ws, "case_study.overview", {
            "case_text": case_text,
            "instruction": "Прочитайте описание дела. Далее последуют вопросы по нему.",
        })

    # ── quiz_v2: start case-driven session (2026-04-18) ──────────────────────
    # Feature-flagged. When enabled and mode supports cases (not blitz/srs),
    # we pick a case, store session state in Redis, emit case.intro BEFORE
    # the first question so the UI can show the case card.
    try:
        from app.services.quiz_v2.integration import start_session_v2, _is_enabled
        if _is_enabled() and mode.value not in ("blitz", "srs_review", "pvp", "debate", "mock_court"):
            # 2026-04-18: derive user_level from user progress (best-effort)
            _user_level = 1
            try:
                from app.models.progress import UserProgress as _UP
                async with async_session() as _lvl_db:
                    _up_res = await _lvl_db.execute(
                        select(_UP).where(_UP.user_id == user_id)
                    )
                    _up = _up_res.scalar_one_or_none()
                    if _up and _up.current_level:
                        _user_level = int(_up.current_level)
            except Exception as _lvl_exc:
                logger.debug("quiz_v2: user_level lookup failed (using 1): %s", _lvl_exc)

            v2_res = await start_session_v2(
                session_id=session_id,
                mode=mode.value,
                user_level=_user_level,
                user_id=str(user_id),
                personality="detective" if (personality.name == "detective" or "detect" in (personality.name or "").lower()) else "professor",
                difficulty=3,
                category=state.category,
            )
            if v2_res is not None:
                # Override session length to match case complexity
                state.total_questions = v2_res.total_questions
                # ── TTS intro audio (2026-04-18 Этап 2) ───────────────────
                # Best-effort: synth via navy.api; fires a follow-up
                # case.intro.audio event so the card can render
                # immediately and audio streams in when ready.
                await _send(ws, "case.intro", {
                    "case_id": v2_res.case.case_id,
                    "complexity": v2_res.case.complexity,
                    "intro_text": v2_res.intro_text,
                    "total_questions": v2_res.total_questions,
                    "personality": v2_res.personality,
                })
                try:
                    from app.services.quiz_v2.voice import synth_case_intro_audio
                    audio_data_url = await synth_case_intro_audio(
                        v2_res.intro_text, v2_res.personality,
                    )
                    if audio_data_url:
                        await _send(ws, "case.intro.audio", {
                            "case_id": v2_res.case.case_id,
                            "audio_url": audio_data_url,
                        })
                except Exception as _tts_exc:
                    logger.warning("quiz_v2.ws.tts_intro failed: %s", _tts_exc)
    except Exception as _v2_exc:
        logger.warning("quiz_v2.ws.start hook failed: %s", _v2_exc)

    # Generate and send first question
    await _next_question(ws, state)
    return state


async def _next_question(ws: WebSocket, state: _SoloQuizState) -> None:
    """Generate the next question and send it to the client."""

    # V2: Soft/hard limits for free_dialog
    if state.mode == QuizMode.free_dialog:
        elapsed = time.time() - state.session_start_time
        if state.current_question >= FREE_DIALOG_HARD_LIMIT or elapsed >= FREE_DIALOG_TIME_LIMIT:
            await _send(ws, "quiz.system_message", {
                "text": "Сессия завершена. Подводим итоги!",
            })
            await _finish_solo_quiz(ws, state)
            return
        if state.current_question == FREE_DIALOG_SOFT_LIMIT:
            await _send(ws, "quiz.soft_limit", {
                "text": f"Вы ответили на {FREE_DIALOG_SOFT_LIMIT} вопросов! "
                        "Хотите продолжить или подвести итоги?",
                "questions_answered": state.current_question,
                "can_continue": True,
            })

    if state.current_question >= state.total_questions:
        await _finish_solo_quiz(ws, state)
        return

    state.current_question += 1
    state.hint_used_for_current = False

    question: QuizQuestion | None = None

    # ── SRS Review Mode: serve questions from preloaded queue ──
    if state.mode == QuizMode.srs_review and state.srs_queue:
        srs_item = state.srs_queue.pop(0)
        state.srs_current_item = srs_item
        question = QuizQuestion(
            question_text=srs_item["question_text"],
            category=srs_item["question_category"],
            difficulty=max(1, min(5, 6 - (srs_item.get("leitner_box", 0) + 1))),
            expected_article="",
            question_number=state.current_question,
            total_questions=state.total_questions,
            generation_strategy=f"srs_{srs_item.get('priority', 'review')}",
        )

    # V2: Blitz mode — try BlitzQuestionPool first
    if question is None and state.mode == QuizMode.blitz and blitz_pool.loaded:
        blitz_q = blitz_pool.get_question(
            category=state.category,
            difficulty_range=(
                max(1, state.current_difficulty - 1),
                min(5, state.current_difficulty + 1),
            ),
            exclude_ids=state.asked_chunk_ids,
        )
        if blitz_q:
            question = QuizQuestion(
                question_text=blitz_q["question"],
                category=blitz_q["category"],
                difficulty=blitz_q["difficulty"],
                expected_article=blitz_q["article"],
                question_number=state.current_question,
                total_questions=state.total_questions,
                chunk_id=blitz_q["chunk_id"],
                blitz_answer=blitz_q["answer"],
                generation_strategy="blitz_pool",
            )
            state.asked_chunk_ids.add(blitz_q["chunk_id"])

    # SM-2: Adaptive SRS injection for regular (non-SRS) modes
    # Ratio: if many overdue items → more frequent injection (every 2nd); otherwise every 4th
    if question is None and state.mode not in (QuizMode.srs_review, QuizMode.blitz):
        try:
            from app.services.spaced_repetition import get_review_priority_queue
            async with async_session() as srs_db:
                overdue_queue = await get_review_priority_queue(
                    srs_db, state.user_id, category=state.category, limit=5,
                )
                overdue_count = len(overdue_queue)
                # Adaptive ratio: 10+ overdue → every 2nd; 5+ → every 3rd; else every 4th
                if overdue_count >= 10:
                    inject_every = 2
                elif overdue_count >= 5:
                    inject_every = 3
                else:
                    inject_every = 4
                if overdue_queue and state.current_question % inject_every == 0:
                    srs_item = overdue_queue[0]
                    state.srs_current_item = srs_item
                    question = QuizQuestion(
                        question_text=srs_item["question_text"],
                        category=srs_item["question_category"],
                        difficulty=state.current_difficulty,
                        expected_article="",
                        question_number=state.current_question,
                        total_questions=state.total_questions,
                        generation_strategy=f"srs_{srs_item['priority']}",
                    )
        except Exception:
            logger.debug("SRS priority queue unavailable", exc_info=True)

    # Generate via LLM if no pool question
    if question is None:
        async with async_session() as db:
            weak_areas = await get_user_weak_areas(state.user_id, db)

            # V2: Use adaptive difficulty instead of fixed
            diff = state.current_difficulty

            # V2: Themed mode uses progressive difficulty
            if state.mode == QuizMode.themed:
                diff_range = themed_difficulty_range(state.current_question, state.total_questions)
                diff = (diff_range[0] + diff_range[1]) // 2

            try:
                async with asyncio.timeout(15):
                    question = await generate_question(
                        db,
                        mode=state.mode,
                        category=state.category,
                        difficulty=diff,
                        question_number=state.current_question,
                        user_weak_areas=weak_areas,
                        used_chunk_ids=state.asked_chunk_ids,
                    )
            except (TimeoutError, Exception) as exc:
                logger.warning("generate_question timeout/error (q=%d): %s", state.current_question, exc)
                # Fallback: hardcoded question so the quiz doesn't hang
                question = QuizQuestion(
                    question_text="Какие последствия наступают для должника после признания его банкротом согласно ФЗ-127?",
                    category=state.category or "general",
                    difficulty=diff,
                    expected_article="ФЗ-127",
                    question_number=state.current_question,
                    total_questions=state.total_questions,
                    generation_strategy="timeout_fallback",
                )

    state.current_q = question
    # Track question text for dedup
    if question:
        state.previous_questions.append(question.question_text)
    state.question_start_time = time.time()
    if question.chunk_id:
        state.asked_chunk_ids.add(question.chunk_id)

    # V2: Add personality comment and hint_available flag
    hint_available = state.mode != QuizMode.blitz

    question_msg: dict = {
        "text": question.question_text,
        "category": question.category,
        "difficulty": question.difficulty,
        "question_number": state.current_question,
        "total_questions": state.total_questions,
        "hint_available": hint_available,
        "current_difficulty": state.current_difficulty,
    }

    # ── quiz_v2: wrap question with narrative frame (2026-04-18) ─────────
    # Non-fatal: on any error we ship the bare text as before.
    try:
        from app.services.quiz_v2.integration import shape_next_question_v2, _is_enabled
        if _is_enabled():
            v2_shape = await shape_next_question_v2(
                session_id=state.session_id,
                question_number=state.current_question,
                bare_question_text=question.question_text,
            )
            if v2_shape is not None:
                question_msg["text"] = v2_shape.wrapped_text
                question_msg["bare_text"] = v2_shape.bare_text  # for logs / debug
                question_msg["beat"] = v2_shape.beat.value
                question_msg["beat_label"] = v2_shape.beat.ru_label
                question_msg["rung"] = v2_shape.rung.value
    except Exception as _v2_exc:
        logger.warning("quiz_v2.ws.shape_question failed: %s", _v2_exc)

    # SRS mode: include Leitner box and review metadata
    if state.mode == QuizMode.srs_review and state.srs_current_item:
        question_msg["srs_meta"] = {
            "leitner_box": state.srs_current_item.get("leitner_box", 0),
            "current_streak": state.srs_current_item.get("current_streak", 0),
            "total_reviews": state.srs_current_item.get("total_reviews", 0),
            "priority": state.srs_current_item.get("priority", "review"),
            "remaining_in_queue": len(state.srs_queue),
        }
    # Also mark injected SRS questions in regular modes
    elif question.generation_strategy and question.generation_strategy.startswith("srs_"):
        question_msg["is_srs_review"] = True
    await _send(ws, "quiz.question", question_msg)

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

    # Security: filter user input (jailbreak + profanity)
    if detect_jailbreak(text):
        logger.warning("Jailbreak attempt in knowledge quiz from user")
    text, _input_violations = filter_user_input(text)

    # 2026-04-18: removed legacy "human_moment retry" path.
    # Reason: it intercepted off-topic / typo replies BEFORE the garbage
    # detector and returned a generic "Это не совсем по теме" without the
    # correct answer and without counting as wrong. User feedback:
    # "нет объяснения! и очень медленно работает!"
    # New behavior: every off-topic/garbage answer falls through to
    # evaluate_answer() which ALWAYS surfaces the correct answer via
    # question.blitz_answer or expected_article + no silent retries.

    # Cancel blitz timer
    if state.timer_task and not state.timer_task.done():
        state.timer_task.cancel()

    response_time_ms = int((time.time() - state.question_start_time) * 1000)

    # 2026-04-18: STREAMING EVALUATION
    # Replaced awaited full-JSON call with generator that yields:
    #   verdict event → ✓/✖ visible in <1-2s (fast paths are instant)
    #   chunk events  → text appears token-by-token for slow LLM path
    #   final event   → structured feedback when done
    # Client sees immediate ✓/✖ + streaming explanation instead of 5-8s silence.
    personality_prompt = state.personality.system_prompt if state.personality else None
    _ = personality_prompt  # reserved for future streaming prompt flavor
    result = None
    stream_question_id = state.current_question
    async with async_session() as db:
        try:
            from app.services.knowledge_quiz import evaluate_answer_streaming
            async with asyncio.timeout(30):
                async for event in evaluate_answer_streaming(
                    db,
                    question=state.current_q,
                    user_answer=text,
                    mode=state.mode,
                ):
                    etype = event.get("type")
                    if etype == "verdict":
                        await _send(ws, "quiz.feedback.verdict", {
                            "question_number": stream_question_id,
                            "is_correct": event.get("is_correct", False),
                            "correct_answer": event.get("correct_answer"),
                            "article_reference": event.get("article_reference"),
                            "fast_path": event.get("fast_path"),
                        })
                    elif etype == "chunk":
                        await _send(ws, "quiz.feedback.chunk", {
                            "question_number": stream_question_id,
                            "text": event.get("text", ""),
                        })
                    elif etype == "final":
                        result = event.get("feedback")
        except (TimeoutError, Exception) as exc:
            logger.warning("evaluate_answer_streaming timeout/error: %s", exc)

    if result is None:
        from app.services.knowledge_quiz import QuizFeedback
        result = QuizFeedback(
            is_correct=False,
            explanation="Не удалось оценить ответ из-за таймаута. Попробуйте ответить развёрнуто.",
            article_reference="",
            score_delta=0.0,
        )

    # Calculate score delta
    speed_bonus = 0.0
    if result.is_correct:
        score_delta = 10.0 if not state.hint_used_for_current else 8.0
        state.correct += 1
        # V2: Blitz speed bonus
        if state.mode == QuizMode.blitz:
            speed_bonus = calculate_blitz_speed_bonus(response_time_ms)
            score_delta += speed_bonus
    else:
        score_delta = -2.0
        state.incorrect += 1
    state.score += score_delta

    # V2: Update adaptive difficulty
    new_difficulty = state.update_adaptive_difficulty(result.is_correct)

    # ── quiz_v2: record answer in session memory (2026-04-18) ────────────
    try:
        from app.services.quiz_v2.integration import record_answer_v2, _is_enabled
        from app.services.quiz_v2.ramp import DifficultyRamp
        if _is_enabled():
            rung_v2 = DifficultyRamp.rung_for_question(state.current_question, state.total_questions)
            await record_answer_v2(
                session_id=state.session_id,
                q_idx=state.current_question,
                correct=bool(result.is_correct),
                rung=rung_v2,
                chunk_id=str(state.current_q.chunk_id) if state.current_q.chunk_id else None,
            )
    except Exception as _v2_exc:
        logger.warning("quiz_v2.ws.record_answer failed: %s", _v2_exc)

    # V2: Get personality reaction
    personality_comment = ""
    if state.personality:
        personality_comment = get_personality_reaction(
            state.personality,
            result.is_correct,
            state.consecutive_correct,
            correct_answer=result.correct_answer_summary,
        )

    # Save to DB
    await _save_answer(
        state,
        text,
        is_correct=result.is_correct,
        explanation=result.explanation,
        score_delta=score_delta,
        article_reference=result.article_reference,
        rag_chunks=None,
        hint_used=state.hint_used_for_current,
        response_time_ms=response_time_ms,
    )

    # SM-2 spaced repetition: record review for long-term tracking
    _is_srs = state.mode == QuizMode.srs_review
    _source = "srs_review" if _is_srs else (
        "blitz" if state.mode == QuizMode.blitz else "quiz"
    )
    srs_history_record = None
    try:
        async with async_session() as srs_db:
            srs_history_record = await srs_record_review(
                srs_db,
                user_id=state.user_id,
                question_text=state.current_q.question_text,
                question_category=state.current_q.category,
                is_correct=result.is_correct,
                response_time_ms=response_time_ms,
                hint_used=state.hint_used_for_current,
                source_type=_source,
                is_srs_review=_is_srs,
            )
            await srs_db.commit()
    except Exception:
        logger.debug("SRS record_review failed", exc_info=True)

    # SRS Review Mode: send detailed progress with box/streak changes
    if _is_srs and srs_history_record is not None:
        state.srs_answers_in_session += 1
        _old_item = state.srs_current_item or {}
        await _send(ws, "srs.progress", {
            "question_number": state.current_question,
            "total_in_session": state.total_questions,
            "answered_in_session": state.srs_answers_in_session,
            "remaining": len(state.srs_queue),
            "is_correct": result.is_correct,
            "leitner_box_before": _old_item.get("leitner_box", 0),
            "leitner_box_after": srs_history_record.leitner_box,
            "current_streak": srs_history_record.current_streak,
            "best_streak": srs_history_record.best_streak,
            "ease_factor": round(srs_history_record.ease_factor, 2),
            "next_review_days": srs_history_record.interval_days,
            "category": state.current_q.category,
        })
        state.srs_current_item = None  # reset for next question

    # Send feedback with V2 fields
    feedback_data: dict = {
        "is_correct": result.is_correct,
        "explanation": result.explanation,
        "article_reference": result.article_reference,
        "score_delta": score_delta,
        "personality_comment": personality_comment,
        "current_difficulty": new_difficulty,
        "streak": state.consecutive_correct,
        "best_streak": state.best_streak,
    }
    if speed_bonus > 0:
        feedback_data["speed_bonus"] = speed_bonus
    if not result.is_correct:
        feedback_data["correct_answer"] = result.correct_answer_summary
    await _send(ws, "quiz.feedback", feedback_data)

    # Send progress
    await _send_progress(ws, state)

    # V2: Check for follow-up question
    if state.should_follow_up() and state.current_q:
        follow_up_text = await generate_follow_up(
            state.current_q,
            text,
            result.is_correct,
            personality_prompt=personality_prompt,
        )
        if follow_up_text:
            state.pending_follow_up = True
            await _send(ws, "quiz.follow_up", {
                "text": follow_up_text,
                "is_optional": True,
            })
            return  # Wait for follow-up answer or skip

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

    # V2: Block hints in blitz mode
    if state.mode == QuizMode.blitz:
        await _send_error(ws, "Подсказки недоступны в блиц-режиме!", "hint_blocked_blitz")
        return

    if state.hint_used_for_current:
        await _send_error(ws, "Hint already used for this question", "hint_already_used")
        return

    state.hint_used_for_current = True
    penalty = -2.0
    state.score += penalty

    # V2: Use guiding hint generator with personality
    personality_name = state.personality.name if state.personality else None
    hint_text = await generate_guiding_hint(state.current_q, personality_name)

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
            question_text=state.current_q.question_text,
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

        # ── RAG Feedback: record quiz answer outcome ──
        try:
            if rag_chunks and isinstance(rag_chunks, list):
                from app.services.rag_feedback import record_quiz_feedback
                feedback_answers = []
                for chunk_ref in rag_chunks[:3]:
                    cid = chunk_ref if isinstance(chunk_ref, str) else str(chunk_ref)
                    feedback_answers.append({
                        "chunk_id": cid,
                        "is_correct": is_correct,
                        "user_answer": user_answer,
                        "score_delta": score_delta,
                    })
                if feedback_answers:
                    await record_quiz_feedback(
                        db,
                        quiz_session_id=state.session_id,
                        user_id=state.user_id,
                        answers=feedback_answers,
                    )
        except Exception as _rag_err:
            logger.warning("RAG feedback recording failed for session=%s: %s", state.session_id, _rag_err)


async def _finish_solo_quiz(ws: WebSocket, state: _SoloQuizState) -> None:
    """Finalize solo quiz, calculate results, update DB, send completed."""
    if state.finished:
        return
    state.finished = True

    if state.timer_task and not state.timer_task.done():
        state.timer_task.cancel()

    # ── quiz_v2: clear session state (2026-04-18) ─────────────────────────
    try:
        from app.services.quiz_v2.integration import end_session_v2, _is_enabled
        if _is_enabled():
            await end_session_v2(state.session_id)
    except Exception as _v2_exc:
        logger.warning("quiz_v2.ws.end_session failed: %s", _v2_exc)

    # Update DB session and calculate results
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

        results = await calculate_quiz_results(db_session, db)
        # Convert dataclass to dict for JSON serialization and extension
        from dataclasses import asdict
        results_data = asdict(results) if hasattr(results, '__dataclass_fields__') else (results if isinstance(results, dict) else {"score": 0})

        # --- Gamification: XP, streaks, achievements ---
        try:
            from app.services.arena_xp import (
                calculate_arena_xp, update_arena_streak, apply_arena_xp_to_progress,
            )
            from app.services.gamification import check_arena_achievements

            await update_arena_streak(
                user_id=state.user_id,
                correct_in_session=state.correct,
                total_in_session=state.correct + state.incorrect + state.skipped,
                answer_streak_at_end=getattr(state, "best_streak", 0),
                db=db,
            )

            from app.models.progress import ManagerProgress
            prog_r = await db.execute(
                select(ManagerProgress).where(ManagerProgress.user_id == state.user_id)
            )
            prog = prog_r.scalar_one_or_none()
            streak_days = prog.arena_daily_streak if prog else 0

            xp_info = calculate_arena_xp(
                mode=state.mode,
                score=state.score,
                correct=state.correct,
                total=max(1, state.correct + state.incorrect + state.skipped),
                streak_days=streak_days,
            )
            await apply_arena_xp_to_progress(state.user_id, xp_info["total"], db)

            # EventBus handles arena achievements + notifications
            from app.services.event_bus import event_bus, GameEvent, EVENT_ARENA_COMPLETED
            await event_bus.emit(GameEvent(
                kind=EVENT_ARENA_COMPLETED,
                user_id=state.user_id,
                db=db,
                payload={"mode": state.mode, "score": state.score, "xp": xp_info},
            ))
            await db.commit()

            results_data["xp_earned"] = xp_info
        except Exception as e:
            logger.warning("Gamification hook error in quiz completion: %s", e, exc_info=True)

    # --- Arena Points + Season Pass progression ---
    try:
        from app.services.arena_points import award_arena_points, AP_RATES
        from app.services.season_pass import advance_season

        # Determine AP source based on quiz score
        if state.score >= 80:
            ap_source = "knowledge_session_high"
        elif state.score >= 50:
            ap_source = "knowledge_session_mid"
        else:
            ap_source = "knowledge_session_low"

        async with async_session() as ap_db:
            ap_balance = await award_arena_points(ap_db, state.user_id, ap_source)
            season_result = await advance_season(state.user_id, AP_RATES[ap_source], ap_db)
            await ap_db.commit()

        results_data["ap_earned"] = {
            "amount": AP_RATES[ap_source],
            "source": ap_source,
            "balance": ap_balance,
            "season": season_result,
        }
    except Exception as e:
        logger.warning("AP/Season hook error in quiz completion: %s", e, exc_info=True)

    # --- Behavioral Intelligence: track behavior + update emotion profile ---
    try:
        from app.services.behavior_tracker import analyze_session_behavior, save_behavior_snapshot
        from app.services.manager_emotion_profiler import update_emotion_profile
        from app.services.progress_detector import detect_trends

        # Build message list from DB answers for behavior analysis
        async with async_session() as db_beh:
            from app.models.knowledge import KnowledgeAnswer
            ans_result = await db_beh.execute(
                select(KnowledgeAnswer)
                .where(KnowledgeAnswer.session_id == state.session_id)
                .order_by(KnowledgeAnswer.question_number)
            )
            answers = ans_result.scalars().all()
            messages_for_behavior = [
                {
                    "role": "user",
                    "content": a.user_answer or "",
                    "response_time_ms": a.response_time_ms,
                    "sequence": a.question_number,
                }
                for a in answers if a.user_answer and a.user_answer != "(skipped)"
            ]

            if messages_for_behavior:
                analysis = analyze_session_behavior(
                    user_id=state.user_id,
                    session_id=state.session_id,
                    session_type="quiz",
                    messages=messages_for_behavior,
                )
                snapshot = await save_behavior_snapshot(analysis, db_beh)
                await update_emotion_profile(
                    user_id=state.user_id,
                    db=db_beh,
                    session_snapshot=snapshot,
                    session_score=state.score,
                )
                await db_beh.commit()

                # Detect trends (non-blocking, runs periodically)
                try:
                    await detect_trends(state.user_id, db_beh, period_days=7)
                    await db_beh.commit()
                except Exception:
                    pass

                logger.info(
                    "Behavioral hooks: user=%s confidence=%.0f stress=%.0f",
                    state.user_id, analysis.confidence_score, analysis.stress_level,
                )
    except Exception as e:
        logger.warning("Behavioral hook error in quiz completion: %s", e, exc_info=True)

    # SRS Review Mode: append SRS completion summary
    if state.mode == QuizMode.srs_review:
        try:
            async with async_session() as srs_db:
                srs_stats = await get_user_srs_stats(srs_db, state.user_id)
                mastery = await get_category_mastery(srs_db, state.user_id)
            results_data["srs_summary"] = {
                "items_reviewed": state.srs_answers_in_session,
                "accuracy_pct": round(
                    (state.correct / max(1, state.correct + state.incorrect)) * 100, 1
                ),
                "updated_stats": srs_stats,
                "category_mastery": mastery,
            }
        except Exception:
            logger.debug("SRS completion summary failed", exc_info=True)

    # Send separate ap.earned message for CelebrationListener
    if "ap_earned" in results_data:
        await _send(ws, "ap.earned", results_data["ap_earned"])

    await _send(ws, "quiz.completed", {"results": results_data})

    # GAP-2 fix: Auto-backfill SRS from quiz answers
    try:
        from app.services.spaced_repetition import backfill_from_quiz_answers
        async with async_session() as srs_db:
            backfilled = await backfill_from_quiz_answers(srs_db, user_id)
            if backfilled:
                await srs_db.commit()
                logger.info("SRS backfilled %d records for user %s after quiz", backfilled, user_id)
    except Exception:
        logger.debug("SRS backfill after quiz failed (non-critical)", exc_info=True)

    # Send achievement notifications separately for toast display
    if results_data.get("achievements_earned"):
        for ach in results_data["achievements_earned"]:
            await _send(ws, "achievement.earned", ach)


# ══════════════════════════════════════════════════════════════════════════════
# PVP ARENA MODE — Redis-based state machine
# ══════════════════════════════════════════════════════════════════════════════


async def _handle_find_opponent(
    ws: WebSocket,
    user_id: uuid.UUID,
    username: str,
    data: dict,
) -> None:
    """Create a PvP challenge via Redis and broadcast to all workers."""
    # ── Level gate: PvP knowledge quiz requires level 5+ ──
    from app.services.arena_gates import can_access_feature
    from app.models.progress import ManagerProgress
    async with async_session() as db:
        prog_r = await db.execute(
            select(ManagerProgress).where(ManagerProgress.user_id == user_id)
        )
        prog = prog_r.scalar_one_or_none()
        user_level = prog.current_level if prog else 1
    if not can_access_feature(user_level, "pvp"):
        await _send_error(ws, "PvP арена доступна с уровня 5", "level_gate")
        return

    arena = get_arena_redis()

    # Check if user is already in an active match
    active_match = await arena.get_user_active_match(str(user_id))
    if active_match:
        await _send_error(ws, "Already in an active match", "already_in_match")
        return

    try:
        max_players = int(data.get("max_players", 2))
    except (ValueError, TypeError):
        max_players = 2
    if max_players not in (2, 4):
        max_players = 2
    category = data.get("category")

    challenge_id = str(uuid.uuid4())
    expires_at = time.time() + PVP_CHALLENGE_EXPIRY_SEC

    # Save challenge to DB
    async with async_session() as db:
        challenge = QuizChallenge(
            id=uuid.UUID(challenge_id),
            challenger_id=user_id,
            category=category,
            max_players=max_players,
            is_active=True,
            accepted_by=[],
            expires_at=datetime.fromtimestamp(expires_at, tz=timezone.utc),
        )
        db.add(challenge)
        await db.commit()

    # Create challenge in Redis
    await arena.create_challenge(
        challenge_id=challenge_id,
        challenger_id=str(user_id),
        challenger_name=username,
        category=category,
        max_players=max_players,
        expires_at=expires_at,
    )

    await _send(ws, "pvp.searching", {
        "challenge_id": challenge_id,
        "max_players": max_players,
        "expires_in_seconds": PVP_CHALLENGE_EXPIRY_SEC,
    })

    # Broadcast challenge to all connected clients via Redis Pub/Sub
    await arena.publish_global_event({
        "type": "pvp.challenge",
        "challenge_id": challenge_id,
        "challenger_id": str(user_id),
        "challenger_name": username,
        "category": category,
        "max_players": max_players,
    })

    # Block 5: Also broadcast via notification WS (reaches users not on Arena page)
    try:
        from app.services.arena_notifications import broadcast_arena_notification

        cat_display = category or "Любая"
        await broadcast_arena_notification(
            "arena.challenge",
            {
                "challenger_name": username,
                "category": cat_display,
                "challenge_id": challenge_id,
                "max_players": max_players,
            },
            exclude_user_id=user_id,
        )
    except Exception:
        logger.debug("Notification broadcast failed for PvP challenge", exc_info=True)

    # Schedule expiry
    asyncio.create_task(_challenge_expiry_timer(ws, user_id, challenge_id))


async def _challenge_expiry_timer(
    ws: WebSocket, challenger_id: uuid.UUID, challenge_id: str,
) -> None:
    """Expire challenge after timeout if not enough players joined."""
    try:
        await asyncio.sleep(PVP_CHALLENGE_EXPIRY_SEC)
        arena = get_arena_redis()
        challenge = await arena.get_challenge(challenge_id)
        if challenge is None or not challenge.is_active:
            return  # Already started or cancelled

        await arena.expire_challenge(challenge_id)

        # Mark expired in DB
        async with async_session() as db:
            db_challenge = await db.get(QuizChallenge, uuid.UUID(challenge_id))
            if db_challenge and db_challenge.is_active:
                db_challenge.is_active = False
                await db.commit()

        # Notify challenger: offer bot fallback
        await _send(ws, "pvp.no_opponents", {"offer_bot": True})

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

    arena = get_arena_redis()

    # Check if user is already in a match
    active_match = await arena.get_user_active_match(str(user_id))
    if active_match:
        await _send_error(ws, "Already in an active match", "already_in_match")
        return

    challenge = await arena.get_challenge(challenge_id)
    if challenge is None or not challenge.is_active:
        await _send_error(ws, "Challenge not found or expired", "challenge_not_found")
        return

    # Atomic accept via Redis Lua script
    accepted, is_full = await arena.accept_challenge(
        challenge_id=challenge_id,
        user_id=str(user_id),
        user_name=username,
        max_players=challenge.max_players,
    )

    if not accepted:
        await _send_error(ws, "Cannot accept this challenge", "accept_failed")
        return

    # Broadcast player joined event
    updated_challenge = await arena.get_challenge(challenge_id)
    accepted_count = len(updated_challenge.accepted_by) if updated_challenge else 0

    await arena.publish_global_event({
        "type": "pvp.player_joined",
        "challenge_id": challenge_id,
        "player_name": username,
        "player_id": str(user_id),
        "players_count": accepted_count + 1,  # +1 for challenger
        "players_needed": challenge.max_players,
    })

    # If match is full, start the game
    if is_full and updated_challenge:
        await _start_pvp_match_redis(arena, challenge_id, updated_challenge)


async def _handle_decline_challenge(
    ws: WebSocket,
    user_id: uuid.UUID,
    data: dict,
) -> None:
    """Decline a PvP challenge."""
    challenge_id = data.get("challenge_id")
    await _send(ws, "pvp.decline.ok", {"challenge_id": challenge_id})


async def _handle_pvp_answer(
    ws: WebSocket,
    user_id: uuid.UUID,
    data: dict,
) -> None:
    """Handle a PvP answer submission (simultaneous mode)."""
    arena = get_arena_redis()

    session_id = await arena.get_user_active_match(str(user_id))
    if not session_id:
        await _send_error(ws, "Not in an active match", "no_active_match")
        return

    text = data.get("text", "").strip()
    round_number = data.get("round_number")

    if not text:
        await _send_error(ws, "Empty answer", "empty_text")
        return

    # Validate round_number: must be a positive integer within valid range
    if round_number is None:
        await _send_error(ws, "Missing round_number", "invalid_field")
        return
    try:
        round_number = int(round_number)
        if round_number < 1 or round_number > 50:  # Sane upper bound
            raise ValueError("out of range")
    except (ValueError, TypeError):
        await _send_error(ws, "Invalid round_number", "invalid_field")
        return

    # Security: filter user input for PvP (jailbreak + profanity)
    text, _input_violations = filter_user_input(text)
    if round_number is None:
        await _send_error(ws, "round_number required", "missing_field")
        return

    # Real-time anti-cheat (lightweight, non-blocking)
    try:
        from app.services.nlp_cheat_detector import real_time_check
        _rt_response_ms = data.get("response_time_ms")
        _rt_question = data.get("question_text", "")
        _rt_check = real_time_check(text, response_time_ms=_rt_response_ms, question_text=_rt_question)
        if _rt_check.get("should_flag_for_review"):
            logger.warning(
                "Real-time cheat flag: user=%s, flags=%s, risk=%s",
                user_id,
                _rt_check.get("flags"),
                _rt_check.get("risk_level"),
            )
    except Exception:
        pass  # Never block answer submission due to cheat detection

    result = await arena.submit_answer(
        session_id=session_id,
        round_number=int(round_number),
        user_id=str(user_id),
        answer_text=text,
    )

    if not result.accepted:
        await _send_error(ws, result.reason or "Answer not accepted", "answer_rejected")
        return

    # Broadcast that this player answered (without content!)
    await arena.publish_match_event(session_id, {
        "type": "pvp.player_answered",
        "user_id": str(user_id),
        "round_number": round_number,
    })

    # If all answered, the game loop will detect this via polling


async def _handle_cancel_search(
    ws: WebSocket,
    user_id: uuid.UUID,
) -> None:
    """Cancel PvP opponent search."""
    # Find and expire any active challenges by this user
    arena = get_arena_redis()
    active_ids = await arena.get_active_challenges()
    for cid in active_ids:
        challenge = await arena.get_challenge(cid)
        if challenge and challenge.challenger_id == str(user_id) and challenge.is_active:
            await arena.expire_challenge(cid)
            # Update DB
            async with async_session() as db:
                db_challenge = await db.get(QuizChallenge, uuid.UUID(cid))
                if db_challenge and db_challenge.is_active:
                    db_challenge.is_active = False
                    await db.commit()
            break
    await _send(ws, "pvp.search_cancelled", {})


async def _handle_play_with_bot(
    ws: WebSocket,
    user_id: uuid.UUID,
    username: str,
) -> None:
    """Start a PvP match with an AI bot (fallback when no opponents found)."""
    arena = get_arena_redis()

    # Check not already in match
    active_match = await arena.get_user_active_match(str(user_id))
    if active_match:
        await _send_error(ws, "Already in an active match", "already_in_match")
        return

    bot_id = f"bot_{uuid.uuid4().hex[:8]}"
    bot_names = ["AI Юрист", "AI Знаток", "AI Арбитр"]
    bot_name = random.choice(bot_names)

    # Notify bot joined
    await _send(ws, "pvp.bot_joined", {"bot_name": bot_name, "bot_id": bot_id})

    session_id = str(uuid.uuid4())

    players_info = [
        {"user_id": str(user_id), "name": username, "is_bot": False, "rating": 1500.0},
        {"user_id": bot_id, "name": bot_name, "is_bot": True, "rating": 1500.0},
    ]

    # Create session in DB
    async with async_session() as db:
        session = KnowledgeQuizSession(
            id=uuid.UUID(session_id),
            user_id=user_id,
            mode=QuizMode.pvp,
            category=None,
            difficulty=3,
            total_questions=PVP_TOTAL_ROUNDS,
            max_players=2,
            status=QuizSessionStatus.active,
        )
        db.add(session)
        participant = QuizParticipant(
            session_id=uuid.UUID(session_id),
            user_id=user_id,
            score=0.0,
        )
        db.add(participant)
        await db.commit()

    # Create match in Redis
    await arena.create_match(
        session_id=session_id,
        players_info=players_info,
        total_rounds=PVP_TOTAL_ROUNDS,
        category=None,
        contains_bot=True,
    )

    # Notify match ready
    await _send(ws, "pvp.match_ready", {
        "session_id": session_id,
        "players": players_info,
        "total_rounds": PVP_TOTAL_ROUNDS,
    })

    # Start game loop
    asyncio.create_task(_pvp_game_loop_redis(session_id))


async def _start_pvp_match_redis(
    arena: ArenaRedis,
    challenge_id: str,
    challenge: "ChallengeData",
) -> None:
    """Create a PvP session from a filled challenge and start the game loop."""
    from app.services.arena_redis import ChallengeData

    session_id = str(uuid.uuid4())

    # Build players list
    players_info = [
        {
            "user_id": challenge.challenger_id,
            "name": challenge.challenger_name,
            "is_bot": False,
            "rating": 1500.0,
        },
    ]
    for accepted in challenge.accepted_by:
        players_info.append({
            "user_id": accepted["user_id"],
            "name": accepted["name"],
            "is_bot": False,
            "rating": 1500.0,
        })

    # Create session in DB
    async with async_session() as db:
        session = KnowledgeQuizSession(
            id=uuid.UUID(session_id),
            user_id=uuid.UUID(challenge.challenger_id),
            mode=QuizMode.pvp,
            category=challenge.category,
            difficulty=3,
            total_questions=PVP_TOTAL_ROUNDS,
            max_players=challenge.max_players,
            status=QuizSessionStatus.active,
        )
        db.add(session)

        for p in players_info:
            if not p["is_bot"]:
                participant = QuizParticipant(
                    session_id=uuid.UUID(session_id),
                    user_id=uuid.UUID(p["user_id"]),
                    score=0.0,
                )
                db.add(participant)
        await db.commit()

    # Update challenge in DB
    async with async_session() as db:
        db_challenge = await db.get(QuizChallenge, uuid.UUID(challenge_id))
        if db_challenge:
            db_challenge.is_active = False
            db_challenge.session_id = uuid.UUID(session_id)
            db_challenge.accepted_by = [a["user_id"] for a in challenge.accepted_by]
            await db.commit()

    # Create match in Redis
    await arena.create_match(
        session_id=session_id,
        players_info=players_info,
        total_rounds=PVP_TOTAL_ROUNDS,
        category=challenge.category,
        contains_bot=False,
    )

    # Broadcast match ready to all players via Pub/Sub
    await arena.publish_global_event({
        "type": "pvp.match_ready",
        "session_id": session_id,
        "players": players_info,
        "total_rounds": PVP_TOTAL_ROUNDS,
    })

    # Start the game loop
    asyncio.create_task(_pvp_game_loop_redis(session_id))


def _get_round_difficulty(round_num: int, total: int, rating_profile: dict | None = None) -> int:
    """Progressive difficulty adjusted by Arena PvP rating.

    Base: rounds 1-3 easy, 4-7 medium, 8-10 hard.
    Arena adjustment: if rating_profile provided, clamp to rating-based range.
    """
    progress = round_num / total
    if progress <= 0.3:
        base = random.randint(1, 2)
    elif progress <= 0.7:
        base = random.randint(2, 4)
    else:
        base = random.randint(4, 5)

    if rating_profile and rating_profile.get("has_pvp_data"):
        lo, hi = rating_profile["difficulty_range"]
        return max(lo, min(hi, base))
    return base


async def _generate_bot_answer(
    question: QuizQuestion,
    target_accuracy: float = 0.7,
) -> str:
    """Generate a bot answer for PvP. Simple heuristic-based."""
    should_be_correct = random.random() < target_accuracy

    if should_be_correct and question.rag_context and question.rag_context.has_results:
        top = question.rag_context.results[0]
        # Rephrase correct answer
        sentences = top.fact_text.split(".")
        if len(sentences) > 2:
            answer = ". ".join(sentences[:2]) + "."
        else:
            answer = top.fact_text
        if random.random() > 0.5 and top.law_article:
            answer += f" (ст. {top.law_article})"
        return answer

    # Plausible wrong or generic answer
    generic_wrong = [
        "Полагаю, что в данном случае применяются общие нормы гражданского законодательства.",
        "Думаю, это регулируется статьями ГК РФ, а не 127-ФЗ напрямую.",
        "Если не ошибаюсь, данный вопрос решается судом по усмотрению.",
        "Не уверен точно, но кажется срок составляет 3 месяца.",
        "По моему мнению, это зависит от конкретных обстоятельств дела.",
    ]
    return random.choice(generic_wrong)


async def _replace_with_bot_after_grace(
    arena,
    session_id: str,
    user_id: str,
    grace_seconds: int = 60,
) -> None:
    """After grace period, if player hasn't reconnected, replace with bot."""
    await asyncio.sleep(grace_seconds)
    try:
        # Check if player reconnected during grace
        still_disconnected = not await arena.check_reconnect(user_id)
        player = await arena.get_player(session_id, user_id)
        if player and not player.connected and still_disconnected:
            bot_id = f"bot_replace_{user_id[:8]}"
            bot_name = f"Бот ({player.name})"
            # Update player record to bot
            await arena.update_player_score(session_id, bot_id, 0, 0)  # Initialize bot player
            await arena.set_player_connected(session_id, user_id, False)
            await arena.clear_user_active_match(user_id)
            await arena.publish_match_event(session_id, {
                "type": "pvp.player_replaced_by_bot",
                "original_user_id": user_id,
                "bot_id": bot_id,
                "bot_name": bot_name,
            })
            logger.info(
                "Player %s replaced by bot %s in session %s after %ds grace",
                user_id, bot_id, session_id, grace_seconds,
            )
    except Exception as e:
        logger.error("Failed to replace player %s with bot: %s", user_id, e)


async def _pvp_game_loop_redis(session_id: str) -> None:
    """Run the PvP quiz using Redis state machine.

    This runs on ONE worker (acquired via distributed lock).
    Events are broadcast via Redis Pub/Sub to all connected workers.
    """
    arena = get_arena_redis()

    # Acquire distributed lock — only one worker runs the game
    if not await arena.acquire_game_lock(session_id):
        logger.debug("Game lock already held for session=%s, skipping", session_id)
        return

    try:
        match_data = await arena.get_match(session_id)
        if not match_data:
            logger.error("Match not found in Redis: session=%s", session_id)
            return

        player_ids = match_data.player_ids
        total_rounds = match_data.total_rounds
        category = match_data.category
        contains_bot = match_data.contains_bot
        previous_questions: list[str] = []

        # Get arena difficulty profile for players (Block 5: Cross-Module)
        _arena_rating_profile = None
        try:
            from app.services.arena_difficulty import get_arena_difficulty_profile
            async with async_session() as _db:
                profiles = []
                for pid in player_ids:
                    p = await get_arena_difficulty_profile(uuid.UUID(pid), _db)
                    if p.get("has_pvp_data"):
                        profiles.append(p)
                if profiles:
                    # Use the LOWER-rated player's profile (fairness)
                    _arena_rating_profile = min(profiles, key=lambda x: x["rating"])
        except Exception:
            pass  # Graceful degradation: use default progressive difficulty

        for round_num in range(1, total_rounds + 1):
            # Extend lock heartbeat
            await arena.extend_game_lock(session_id, 120)
            await arena.set_match_round(session_id, round_num)

            difficulty = _get_round_difficulty(round_num, total_rounds, _arena_rating_profile)

            # Generate question
            async with async_session() as db:
                question = await generate_question(
                    db,
                    mode=QuizMode.pvp,
                    category=category,
                    difficulty=difficulty,
                    question_number=round_num,
                    total_questions=total_rounds,
                    previous_questions=previous_questions,
                )
            previous_questions.append(question.question_text)

            # Count real players (non-bot) for expected answers
            players = await arena.get_all_players(session_id)
            real_player_count = sum(1 for p in players if not p.is_bot)
            expected_answers = real_player_count  # Bots answer separately

            # Start round in Redis
            await arena.start_round(
                session_id=session_id,
                round_number=round_num,
                question={
                    "text": question.question_text,
                    "category": question.category,
                    "difficulty": question.difficulty,
                },
                expected_answers=expected_answers,
                timeout_seconds=PVP_ROUND_TIME_LIMIT_SEC,
            )

            # Broadcast question to all players
            await arena.publish_match_event(session_id, {
                "type": "pvp.round_question",
                "question_text": question.question_text,
                "category": question.category,
                "difficulty": question.difficulty,
                "round_number": round_num,
                "total_rounds": total_rounds,
                "time_limit_seconds": PVP_ROUND_TIME_LIMIT_SEC,
            })

            # Generate bot answers (with realistic delay)
            bot_players = [p for p in players if p.is_bot]
            for bot in bot_players:
                bot_delay = random.uniform(5, 20)
                asyncio.create_task(
                    _submit_bot_answer(arena, session_id, round_num, bot.user_id, question, bot_delay)
                )

            # Wait for all answers (real players + bots) or timeout
            all_answered = await wait_for_all_answers(
                arena, session_id, round_num,
                expected_count=len(player_ids),  # All players including bots (bots submit via _submit_bot_answer)
                timeout_seconds=PVP_ROUND_TIME_LIMIT_SEC + 5,  # Extra buffer for bot delays
            )

            # Collect all answers
            answers = await arena.get_round_answers(session_id, round_num)

            # Fill missing answers (timeout)
            for pid in player_ids:
                if pid not in answers:
                    answers[pid] = {"text": "", "submitted_at": None}

            # Build player_answers for evaluation
            # Get round start time for response_time calculation
            round_started = await arena.get_round_started_at(session_id, round_num)
            player_answers = []
            for pid in player_ids:
                ans = answers.get(pid, {"text": "", "submitted_at": None})
                if ans.get("submitted_at") and round_started:
                    resp_ms = int((ans["submitted_at"] - round_started) * 1000)
                else:
                    resp_ms = PVP_ROUND_TIME_LIMIT_SEC * 1000
                player_answers.append({
                    "user_id": pid,
                    "answer": ans.get("text", ""),
                    "response_time_ms": max(0, resp_ms),
                })

            # Evaluate all answers via AI judge
            async with async_session() as db:
                evaluation = await evaluate_pvp_round(
                    db,
                    question=question,
                    player_answers=player_answers,
                )

            # Parse evaluation results
            eval_players = evaluation.get("players", [])
            eval_by_uid = {}
            for ep in eval_players:
                eval_by_uid[ep.get("user_id", "")] = ep

            # Calculate speed bonuses
            speed_rankings = await arena.get_speed_rankings(session_id, round_num)
            speed_bonuses = calculate_speed_bonuses(speed_rankings, eval_players)

            # Update scores in Redis and build result data
            player_results = []
            for pid in player_ids:
                ep = eval_by_uid.get(pid, {})
                score = ep.get("score", 0)
                is_correct = ep.get("is_correct", False)
                bonus = speed_bonuses.get(pid, 0)
                total_score = score + bonus

                # Phase C (2026-04-20): power-up multiplier.
                # If the player armed a ×2 usage before this round, apply
                # it to the combined (answer + speed) score and consume
                # the arm. Only real players; bots have no session with
                # lifeline/powerup Redis state.
                powerup_multiplier = 1.0
                powerup_kind: str | None = None
                if not pid.startswith("bot_"):
                    try:
                        from app.services.arena.powerups import (
                            peek_active as _pu_peek,
                            pop_active_multiplier as _pu_pop,
                        )
                        powerup_kind = await _pu_peek(
                            session_id=session_id, user_id=pid,
                        )
                        if powerup_kind:
                            powerup_multiplier = await _pu_pop(
                                session_id=session_id, user_id=pid,
                            )
                    except Exception:  # noqa: BLE001 — powerup is best-effort
                        logger.debug(
                            "powerup apply failed session=%s user=%s",
                            session_id, pid, exc_info=True,
                        )
                scored_total = total_score * powerup_multiplier

                await arena.update_player_score(session_id, pid, scored_total, is_correct)

                player_data = await arena.get_player(session_id, pid)
                player_results.append({
                    "user_id": pid,
                    "name": player_data.name if player_data else pid,
                    "answer": filter_answer_text(answers.get(pid, {}).get("text", "(no answer)"))[0],
                    "score": ep.get("score", 0),
                    "speed_bonus": bonus,
                    "is_correct": is_correct,
                    "comment": ep.get("comment", ""),
                    # Expose power-up application to the UI so the client
                    # can render a "×2 применено!" flash over the result.
                    "powerup_applied": powerup_kind if powerup_multiplier != 1.0 else None,
                    "powerup_multiplier": powerup_multiplier,
                })

            # Save answers to DB + SRS tracking
            async with async_session() as db:
                for pid in player_ids:
                    if pid.startswith("bot_"):
                        continue  # Don't persist bot answers
                    ans = answers.get(pid, {})
                    ep = eval_by_uid.get(pid, {})
                    _pvp_is_correct = ep.get("is_correct", False)
                    answer_record = KnowledgeAnswer(
                        session_id=uuid.UUID(session_id),
                        user_id=uuid.UUID(pid),
                        question_number=round_num,
                        question_text=question.question_text,
                        question_category=question.category or "general",
                        user_answer=ans.get("text", "(no answer)"),
                        is_correct=_pvp_is_correct,
                        explanation=ep.get("comment", ""),
                        article_reference=question.expected_article,
                        score_delta=ep.get("score", 0) + speed_bonuses.get(pid, 0),
                    )
                    db.add(answer_record)

                    # SM-2: record PvP answer for spaced repetition
                    try:
                        await srs_record_review(
                            db,
                            user_id=uuid.UUID(pid),
                            question_text=question.question_text,
                            question_category=question.category or "general",
                            is_correct=_pvp_is_correct,
                            response_time_ms=None,
                            hint_used=False,
                            source_type="pvp",
                        )
                    except Exception:
                        logger.debug("SRS record_review failed for PvP user=%s", pid)
                await db.commit()

            # Broadcast round result
            await arena.publish_match_event(session_id, {
                "type": "pvp.round_result",
                "round_number": round_num,
                "question": question.question_text,
                "correct_answer": evaluation.get("correct_answer", ""),
                "explanation": evaluation.get("explanation", ""),
                "article_ref": question.expected_article,
                "players": player_results,
            })

            # Broadcast scoreboard
            all_players = await arena.get_all_players(session_id)
            scoreboard = sorted(
                [
                    {
                        "user_id": p.user_id,
                        "name": p.name,
                        "total_score": p.score,
                        "correct_count": p.correct,
                    }
                    for p in all_players
                ],
                key=lambda x: x["total_score"],
                reverse=True,
            )
            await arena.publish_match_event(session_id, {
                "type": "pvp.scoreboard",
                "players": scoreboard,
            })

            # Pause between rounds
            if round_num < total_rounds:
                await asyncio.sleep(3)

        # ═══ MATCH COMPLETE ═══
        await _finalize_match(arena, session_id, player_ids, contains_bot)

    except Exception as e:
        logger.error("PvP game loop error session=%s: %s", session_id, e, exc_info=True)
        arena_err = get_arena_redis()
        await arena_err.publish_match_event(session_id, {
            "type": "error",
            "message": "Game error, session terminated",
            "code": "game_error",
        })
    finally:
        await arena.release_game_lock(session_id)
        await arena.cleanup_match(session_id)


async def _submit_bot_answer(
    arena: ArenaRedis,
    session_id: str,
    round_number: int,
    bot_id: str,
    question: QuizQuestion,
    delay: float,
) -> None:
    """Submit a bot answer after a realistic delay."""
    try:
        await asyncio.sleep(delay)
        bot_answer = await _generate_bot_answer(question)
        await arena.submit_answer(session_id, round_number, bot_id, bot_answer)
    except Exception as e:
        logger.error("Bot answer error: %s", e)


async def _finalize_match(
    arena: ArenaRedis,
    session_id: str,
    player_ids: list[str],
    contains_bot: bool,
) -> None:
    """Finalize PvP match: anti-cheat, ratings, rankings, DB update, broadcast."""
    # Calculate final rankings from Redis
    all_players = await arena.get_all_players(session_id)
    rankings = sorted(
        [
            {
                "user_id": p.user_id,
                "name": p.name,
                "score": p.score,
                "correct": p.correct,
                "is_bot": p.is_bot,
                "rating_delta": 0.0,
            }
            for p in all_players
        ],
        key=lambda x: x["score"],
        reverse=True,
    )
    for i, r in enumerate(rankings):
        r["rank"] = i + 1

    # ── Anti-cheat check (only for real players in non-bot matches) ──
    anti_cheat_flags = []
    flagged_users: set[str] = set()

    if not contains_bot:
        try:
            from app.services.anti_cheat import run_anti_cheat, save_anti_cheat_result

            # Collect player answers from Redis for anti-cheat analysis
            player_answer_messages: dict[str, list[dict]] = {}
            match_data = await arena.get_match(session_id)
            total_r = match_data.total_rounds if match_data else 10
            for rnd in range(1, total_r + 1):
                raw_answers = await arena.get_round_answers(session_id, rnd)
                if raw_answers:
                    for uid_str, answer_json in raw_answers.items():
                        if uid_str.startswith("bot_"):
                            continue
                        if uid_str not in player_answer_messages:
                            player_answer_messages[uid_str] = []
                        player_answer_messages[uid_str].append({
                            "role": "user",
                            "text": answer_json if isinstance(answer_json, str) else str(answer_json),
                            "round": rnd,
                        })

            async with async_session() as db:
                for pid in player_ids:
                    if pid.startswith("bot_"):
                        continue
                    try:
                        pid_messages = player_answer_messages.get(pid, [])
                        result = await run_anti_cheat(
                            user_id=uuid.UUID(pid),
                            duel_id=uuid.UUID(session_id),
                            messages=pid_messages,
                            db=db,
                        )
                        if result and result.overall_flagged:
                            await save_anti_cheat_result(result, db)
                            anti_cheat_flags.append({
                                "user_id": pid,
                                "action": result.recommended_action,
                            })
                            if result.recommended_action in ("rating_freeze", "disqualification"):
                                flagged_users.add(pid)
                    except Exception as e:
                        logger.warning("Anti-cheat check failed for user=%s: %s", pid, e)
        except ImportError:
            logger.warning("Anti-cheat module not available")

    # ── FIX-5 (v13): Single transaction for ratings + session + participants ──
    # Previously used 3 separate async_session() contexts. If rating commit
    # succeeded but session update failed, state was inconsistent.
    async with async_session() as db:
        # Update ratings (only real players, not flagged, no bots)
        if not contains_bot:
            try:
                from app.services.arena_rating import update_arena_rating_after_pvp

                eligible_rankings = [
                    r for r in rankings
                    if not r["is_bot"] and r["user_id"] not in flagged_users
                ]

                if len(eligible_rankings) >= 2:
                    deltas = await update_arena_rating_after_pvp(
                        session_id=uuid.UUID(session_id),
                        rankings=eligible_rankings,
                        db=db,
                    )
                    for r in rankings:
                        r["rating_delta"] = deltas.get(r["user_id"], 0.0)
            except Exception as e:
                logger.error("Failed to update arena ratings: %s", e)

        # Update session status
        db_session = await db.get(KnowledgeQuizSession, uuid.UUID(session_id))
        if db_session:
            db_session.status = QuizSessionStatus.completed
            db_session.ended_at = datetime.now(timezone.utc)
            db_session.contains_bot = contains_bot
            db_session.anti_cheat_flags = anti_cheat_flags if anti_cheat_flags else None
            db_session.rating_changes_applied = not contains_bot and not flagged_users
            started = db_session.started_at
            if started:
                db_session.duration_seconds = int(
                    (datetime.now(timezone.utc) - started).total_seconds()
                )

        # Update participant scores and ranks
        for ranking in rankings:
            if ranking["is_bot"]:
                continue
            uid = uuid.UUID(ranking["user_id"])
            result = await db.execute(
                select(QuizParticipant).where(
                    QuizParticipant.session_id == uuid.UUID(session_id),
                    QuizParticipant.user_id == uid,
                )
            )
            participant = result.scalar_one_or_none()
            if participant:
                participant.score = ranking["score"]
                participant.final_rank = ranking["rank"]
                participant.correct_answers = ranking["correct"]

        await db.commit()

    # ── Gamification: XP, streaks, achievements for each human player ──
    pvp_achievements: dict[str, list] = {}
    try:
        from app.services.arena_xp import (
            calculate_arena_xp, update_arena_streak, apply_arena_xp_to_progress,
        )
        from app.services.gamification import check_arena_achievements
        from app.models.progress import ManagerProgress

        async with async_session() as db:
            for ranking in rankings:
                if ranking["is_bot"]:
                    continue
                uid = uuid.UUID(ranking["user_id"])
                is_win = ranking["rank"] == 1

                await update_arena_streak(
                    user_id=uid,
                    correct_in_session=ranking.get("correct", 0),
                    total_in_session=PVP_TOTAL_ROUNDS,
                    answer_streak_at_end=0,
                    db=db,
                )

                prog_r = await db.execute(
                    select(ManagerProgress).where(ManagerProgress.user_id == uid)
                )
                prog = prog_r.scalar_one_or_none()
                streak_days = prog.arena_daily_streak if prog else 0

                opponent_rating = None
                player_rating_val = None
                try:
                    from app.services.arena_rating import get_arena_rating as _get_ar
                    player_r = await _get_ar(uid, db)
                    player_rating_val = player_r.rating
                    if is_win and len(rankings) >= 2:
                        loser = next((r for r in rankings if r["rank"] == 2 and not r["is_bot"]), None)
                        if loser:
                            opp_r = await _get_ar(uuid.UUID(loser["user_id"]), db)
                            opponent_rating = opp_r.rating
                except Exception:
                    pass

                xp_info = calculate_arena_xp(
                    mode="pvp",
                    score=ranking["score"],
                    correct=ranking.get("correct", 0),
                    total=PVP_TOTAL_ROUNDS,
                    streak_days=streak_days,
                    is_pvp_win=is_win,
                    pvp_opponent_rating=opponent_rating,
                    player_rating=player_rating_val,
                )
                await apply_arena_xp_to_progress(uid, xp_info["total"], db)

                # EventBus handles PvP achievements + notifications
                from app.services.event_bus import event_bus, GameEvent, EVENT_PVP_COMPLETED
                await event_bus.emit(GameEvent(
                    kind=EVENT_PVP_COMPLETED,
                    user_id=uid,
                    db=db,
                    payload={"is_win": is_win, "rank": ranking["rank"], "xp": xp_info},
                ))

                ranking["xp_earned"] = xp_info

            await db.commit()
    except Exception as e:
        logger.warning("PvP gamification hook error: %s", e, exc_info=True)

    # ── Arena Points + Season Pass for PvP Knowledge Arena ──
    try:
        from app.services.arena_points import award_arena_points, AP_RATES
        from app.services.season_pass import advance_season
        async with async_session() as ap_db:
            for ranking in rankings:
                if ranking["is_bot"]:
                    continue
                uid = uuid.UUID(ranking["user_id"])
                is_win = ranking["rank"] == 1
                ap_source = "pvp_win" if is_win else "pvp_loss"
                ap_balance = await award_arena_points(ap_db, uid, ap_source)
                season_result = await advance_season(uid, AP_RATES[ap_source], ap_db)
                ranking["ap_earned"] = {
                    "amount": AP_RATES[ap_source],
                    "source": ap_source,
                    "balance": ap_balance,
                    "season": season_result,
                }
            await ap_db.commit()
    except Exception as e:
        logger.warning("PvP Knowledge AP/Season hook error: %s", e, exc_info=True)

    await arena.complete_match(session_id)

    # Broadcast final results
    await arena.publish_match_event(session_id, {
        "type": "pvp.final_results",
        "rankings": rankings,
        "total_rounds": PVP_TOTAL_ROUNDS,
        "contains_bot": contains_bot,
        "achievements": pvp_achievements,
    })


# ══════════════════════════════════════════════════════════════════════════════
# PUB/SUB LISTENER — bridges Redis events to WebSocket
# ══════════════════════════════════════════════════════════════════════════════

async def _pubsub_listener(
    ws: WebSocket,
    user_id: uuid.UUID,
    arena: ArenaRedis,
) -> None:
    """Background task: listen to Redis Pub/Sub and forward events to this WS client.

    Subscribes to:
    - Global events (challenges, match_ready broadcasts)
    - Match-specific events (when user joins a match)
    """
    pubsub = arena.redis.pubsub()
    try:
        await arena.subscribe_global_events(pubsub)

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                event = json.loads(message["data"])
            except (json.JSONDecodeError, TypeError):
                continue

            event_type = event.get("type", "")

            # Don't send challenges back to the challenger
            if event_type == "pvp.challenge":
                if event.get("challenger_id") == str(user_id):
                    continue

            # pvp.match_ready — subscribe to match channel if user is a participant
            if event_type == "pvp.match_ready":
                players = event.get("players", [])
                is_participant = any(
                    p.get("user_id") == str(user_id) for p in players
                )
                if is_participant:
                    match_session_id = event.get("session_id")
                    if match_session_id:
                        await arena.subscribe_match_events(match_session_id, pubsub)

            # pvp.player_joined — notify relevant users
            if event_type == "pvp.player_joined":
                pass  # Forward to all

            # Forward event to this WebSocket client
            await _send(ws, event_type, event)

    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as e:
        logger.debug("PubSub listener error for user=%s: %s", user_id, e)
    finally:
        try:
            await pubsub.unsubscribe()
            await pubsub.aclose()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# DOC_11: 7 NEW KNOWLEDGE MODE HANDLERS
# ══════════════════════════════════════════════════════════════════════════════


async def _handle_rapid_blitz(ws: WebSocket, state: _SoloQuizState, db: AsyncSession) -> None:
    """Rapid Blitz: 10 questions, 30s each, binary scoring (right/wrong).

    Like blitz but FASTER. Level 7 required.
    Scoring: +10 for correct, 0 for incorrect (no partial credit).
    """
    # rapid_blitz uses same flow as blitz with shorter timer — handled by
    # _next_question + _handle_answer with time_limit=30 from get_time_limit_seconds.
    # This handler is called on quiz.start if mode is rapid_blitz.
    # Timer fires _handle_rapid_blitz_timeout if 30s expire.
    pass  # Flow handled by existing _start_solo_quiz / _handle_answer


async def _handle_case_study(ws: WebSocket, state: _SoloQuizState, text: str) -> None:
    """Case Study: Present a court case, ask 5-7 follow-up questions.

    Open-ended answers evaluated by LLM. Scoring: 0-10 per question.
    Level 6 required.
    """
    if state.finished or state.current_q is None:
        await _send_error(ws, "No active question", "no_question")
        return

    text, _ = filter_user_input(text)
    response_time_ms = int((time.time() - state.question_start_time) * 1000)

    if state.timer_task and not state.timer_task.done():
        state.timer_task.cancel()

    # Evaluate open-ended answer via LLM (0-10 scoring)
    personality_prompt = state.personality.system_prompt if state.personality else None
    async with async_session() as eval_db:
        result = await evaluate_answer_v2(
            eval_db,
            question=state.current_q,
            user_answer=text,
            mode=state.mode,
            personality_prompt=personality_prompt,
        )

    # Case study: 0-10 scoring per question
    if result.is_correct:
        score_delta = 10.0
        state.correct += 1
    else:
        # Partial credit: LLM may give partial marks
        score_delta = 3.0  # partial credit for attempted answer
        state.incorrect += 1
    state.score += score_delta

    state.update_adaptive_difficulty(result.is_correct)

    await _save_answer(state, text, is_correct=result.is_correct,
                       explanation=result.explanation, score_delta=score_delta,
                       article_reference=result.article_reference,
                       rag_chunks=None, hint_used=state.hint_used_for_current,
                       response_time_ms=response_time_ms)

    await _send(ws, "quiz.feedback", {
        "is_correct": result.is_correct,
        "explanation": result.explanation,
        "article_reference": result.article_reference,
        "score_delta": score_delta,
        "current_difficulty": state.current_difficulty,
        "streak": state.consecutive_correct,
    })
    await _send_progress(ws, state)
    await _next_question(ws, state)


async def _handle_debate_round(
    ws: WebSocket, state: _SoloQuizState, text: str,
) -> None:
    """Debate mode: Player argues FOR or AGAINST a legal position.

    5-7 round dialogue with AI. AI argues opposite side.
    Each round: player submits argument, AI responds, AI scores argument quality.
    Level 8 required.
    """
    from app.models.knowledge import DebateSession
    from app.services.llm import generate_response

    if state.finished:
        await _send_error(ws, "Debate session finished", "finished")
        return

    text, _ = filter_user_input(text)

    # Load or create debate session
    async with async_session() as db:
        debate = (await db.execute(
            select(DebateSession).where(
                DebateSession.quiz_session_id == state.session_id,
            )
        )).scalar_one_or_none()

        if not debate:
            await _send_error(ws, "No active debate session", "no_debate")
            return

        rounds_data = list(debate.rounds_data or [])
        current_round = len(rounds_data) + 1

        if current_round > debate.total_rounds:
            await _send_error(ws, "All debate rounds completed", "debate_complete")
            return

        # Generate AI counter-argument and score
        scoring_prompt = (
            f"Ты — AI-судья юридической дебатов на тему: '{debate.topic}'.\n"
            f"Позиция игрока: {debate.position}. Позиция AI: {debate.ai_position}.\n"
            f"Раунд {current_round}/{debate.total_rounds}.\n\n"
            f"Аргумент игрока:\n{text}\n\n"
            f"1. Оцени качество аргумента от 0 до 10 (legal_score).\n"
            f"2. Дай контраргумент от лица оппонента ({debate.ai_position}).\n"
            f"3. Кратко прокомментируй сильные и слабые стороны.\n\n"
            f"Формат ответа (JSON):\n"
            f'{{"score": 7, "counter_argument": "...", "feedback": "..."}}'
        )

        try:
            ai_response = await generate_response(
                system_prompt="Ты — справедливый судья юридических дебатов по 127-ФЗ.",
                messages=[{"role": "user", "content": scoring_prompt}],
                max_tokens=800,
                task_type="judge",
                prefer_provider="cloud",
            )
            # Parse response — try JSON, fallback to raw
            import json as _json
            try:
                parsed = _json.loads(ai_response)
                round_score = float(parsed.get("score", 5))
                counter_arg = str(parsed.get("counter_argument", ai_response))
                feedback = str(parsed.get("feedback", ""))
            except (_json.JSONDecodeError, ValueError):
                round_score = 5.0
                counter_arg = ai_response
                feedback = ""
        except Exception as e:
            logger.error("Debate AI response failed: %s", e)
            round_score = 5.0
            counter_arg = "Не удалось сгенерировать ответ."
            feedback = ""

        round_score = max(0.0, min(10.0, round_score))
        state.score += round_score

        round_entry = {
            "round_number": current_round,
            "player_argument": text,
            "ai_response": counter_arg,
            "score": round_score,
            "feedback": feedback,
        }
        rounds_data.append(round_entry)
        debate.rounds_data = rounds_data
        db.add(debate)
        await db.commit()

    # Send round result
    await _send(ws, "debate.round_result", {
        "round_number": current_round,
        "total_rounds": debate.total_rounds,
        "your_score": round_score,
        "ai_counter_argument": counter_arg,
        "feedback": feedback,
        "cumulative_score": state.score,
    })

    if current_round >= debate.total_rounds:
        # Debate complete
        state.finished = True
        await _send(ws, "debate.completed", {
            "total_score": state.score,
            "max_possible": debate.total_rounds * 10,
            "rounds": rounds_data,
        })
        await _finish_solo_quiz(ws, state)
    else:
        await _send(ws, "debate.next_round", {
            "round_number": current_round + 1,
            "topic": debate.topic,
            "your_position": debate.position,
        })


async def _handle_mock_court_round(
    ws: WebSocket, state: _SoloQuizState, text: str,
) -> None:
    """Mock Court: Simulated court hearing. Player is the lawyer, AI is the judge.

    Uses DebateSession model with strict legal evaluation.
    Level 11 required.
    """
    # Reuses debate handler with stricter scoring prompt
    from app.models.knowledge import DebateSession
    from app.services.llm import generate_response

    if state.finished:
        await _send_error(ws, "Court session finished", "finished")
        return

    text, _ = filter_user_input(text)

    async with async_session() as db:
        debate = (await db.execute(
            select(DebateSession).where(
                DebateSession.quiz_session_id == state.session_id,
            )
        )).scalar_one_or_none()

        if not debate:
            await _send_error(ws, "No active court session", "no_session")
            return

        rounds_data = list(debate.rounds_data or [])
        current_round = len(rounds_data) + 1

        if current_round > debate.total_rounds:
            state.finished = True
            await _finish_solo_quiz(ws, state)
            return

        scoring_prompt = (
            f"Ты — арбитражный судья. Рассматриваешь дело о банкротстве.\n"
            f"Тема: '{debate.topic}'.\n"
            f"Раунд {current_round}/{debate.total_rounds}.\n\n"
            f"Выступление представителя должника (игрок):\n{text}\n\n"
            f"Оцени строго по критериям:\n"
            f"1. Юридическая точность (ссылки на статьи 127-ФЗ)\n"
            f"2. Логика аргументации\n"
            f"3. Процессуальная корректность\n"
            f"Выстави оценку 0-10 и задай уточняющий вопрос как судья.\n\n"
            f'Формат (JSON): {{"score": N, "judge_question": "...", "feedback": "..."}}'
        )

        try:
            ai_response = await generate_response(
                system_prompt="Ты — строгий арбитражный судья РФ, специалист по делам о банкротстве.",
                messages=[{"role": "user", "content": scoring_prompt}],
                max_tokens=800,
                task_type="judge",
                prefer_provider="cloud",
            )
            import json as _json
            try:
                parsed = _json.loads(ai_response)
                round_score = float(parsed.get("score", 4))
                judge_q = str(parsed.get("judge_question", ai_response))
                feedback = str(parsed.get("feedback", ""))
            except (_json.JSONDecodeError, ValueError):
                round_score = 4.0
                judge_q = ai_response
                feedback = ""
        except Exception as e:
            logger.error("Mock court AI response failed: %s", e)
            round_score = 4.0
            judge_q = "Уточните вашу позицию."
            feedback = ""

        round_score = max(0.0, min(10.0, round_score))
        state.score += round_score

        round_entry = {
            "round_number": current_round,
            "player_statement": text,
            "judge_response": judge_q,
            "score": round_score,
            "feedback": feedback,
        }
        rounds_data.append(round_entry)
        debate.rounds_data = rounds_data
        db.add(debate)
        await db.commit()

    await _send(ws, "court.round_result", {
        "round_number": current_round,
        "total_rounds": debate.total_rounds,
        "your_score": round_score,
        "judge_question": judge_q,
        "feedback": feedback,
        "cumulative_score": state.score,
    })

    if current_round >= debate.total_rounds:
        state.finished = True
        await _send(ws, "court.verdict", {
            "total_score": state.score,
            "max_possible": debate.total_rounds * 10,
            "rounds": rounds_data,
            "verdict": "Удовлетворено" if state.score >= debate.total_rounds * 6 else "Отказано",
        })
        await _finish_solo_quiz(ws, state)
    else:
        await _send(ws, "court.next_round", {
            "round_number": current_round + 1,
            "judge_question": judge_q,
        })


async def _handle_article_deep_dive(ws: WebSocket, state: _SoloQuizState, text: str) -> None:
    """Article Deep Dive: Focus on ONE article of 127-FZ.

    10 increasingly detailed questions about that article.
    Progressive difficulty within session.
    Level 9 required.
    """
    # Uses standard _handle_answer flow — the deep dive difference is in question generation.
    # The article focus is set via state.category and questions are generated with
    # increasing difficulty automatically by the adaptive difficulty system.
    await _handle_answer(ws, state, text)


async def _handle_daily_challenge_answer(ws: WebSocket, state: _SoloQuizState, text: str) -> None:
    """Daily Challenge: Same questions for everyone, compete on leaderboard.

    10 daily questions, global leaderboard.
    Level 5 required.
    """
    # Same scoring as blitz — binary correct/incorrect
    await _handle_answer(ws, state, text)


async def _handle_team_quiz_answer(ws: WebSocket, state: _SoloQuizState, text: str) -> None:
    """Team Quiz placeholder: 2v2 knowledge battle.

    Simplified: matchmake 4 players, split into teams, alternating questions.
    Team score = sum of both members' correct answers.
    Level 10 required.

    NOTE: Full team matchmaking is handled via PvP arena Redis.
    This handler covers the answer evaluation for team members.
    """
    # Uses standard answer flow — team scoring aggregated at match level
    await _handle_answer(ws, state, text)


async def _start_debate_session(
    ws: WebSocket, state: _SoloQuizState, data: dict,
) -> None:
    """Initialize a debate or mock_court session with a topic and positions."""
    from app.models.knowledge import DebateSession
    from app.services.rag_legal import retrieve_legal_context

    topic = data.get("topic")
    if not topic:
        # Generate a debate topic from RAG
        try:
            async with async_session() as rag_db:
                ctx = await retrieve_legal_context("спорный вопрос банкротства", rag_db, top_k=1)
                if ctx and ctx.chunks:
                    topic = f"Вопрос по {ctx.chunks[0].article}: правомерность процедуры"
                else:
                    topic = "Обоснованность признания гражданина банкротом при наличии единственного жилья"
        except Exception:
            topic = "Обоснованность признания гражданина банкротом при наличии единственного жилья"

    position = data.get("position", "pro")
    ai_position = "contra" if position == "pro" else "pro"
    total_rounds = 7 if state.mode == QuizMode.debate else 10

    async with async_session() as db:
        debate = DebateSession(
            quiz_session_id=state.session_id,
            topic=topic,
            position=position,
            ai_position=ai_position,
            total_rounds=total_rounds,
            rounds_data=[],
        )
        db.add(debate)
        await db.commit()

    mode_label = "Дебаты" if state.mode == QuizMode.debate else "Судебное заседание"
    await _send(ws, f"{'debate' if state.mode == QuizMode.debate else 'court'}.started", {
        "session_id": str(state.session_id),
        "topic": topic,
        "your_position": position,
        "ai_position": ai_position,
        "total_rounds": total_rounds,
        "mode_label": mode_label,
        "instruction": (
            f"{mode_label} начинается! Тема: {topic}. "
            f"Ваша позиция: {'ЗА' if position == 'pro' else 'ПРОТИВ'}. "
            f"Представьте свой первый аргумент."
        ),
    })


# ══════════════════════════════════════════════════════════════════════════════
# MAIN WEBSOCKET HANDLER
# ══════════════════════════════════════════════════════════════════════════════

async def knowledge_websocket(websocket: WebSocket) -> None:
    """Main WebSocket handler for /ws/knowledge.

    Handles authentication, then dispatches messages to either
    AI Examiner (solo) or PvP Arena mode handlers.
    Starts a background Pub/Sub listener for PvP events.
    """
    await websocket.accept()
    user_id: uuid.UUID | None = None
    username: str = ""
    quiz_state: _SoloQuizState | None = None
    pubsub_task: asyncio.Task | None = None

    try:
        # ── Step 1: Authenticate ──
        auth_result = await _auth_websocket(websocket)
        if auth_result is None:
            await websocket.close(code=4001)
            return
        user_id, username = auth_result

        logger.info("WS Knowledge authenticated: user=%s (%s)", user_id, username)

        # ── Step 1b: Start Pub/Sub listener for PvP events ──
        arena = get_arena_redis()
        pubsub_task = asyncio.create_task(
            _pubsub_listener(websocket, user_id, arena)
        )

        # ── Step 1c: Check for reconnect (PvP match in progress) ──
        reconnect_session = await arena.check_reconnect(str(user_id))
        if reconnect_session:
            await arena.clear_reconnect(str(user_id))
            await arena.set_player_connected(reconnect_session, str(user_id), True)

            # Subscribe to match channel
            match_pubsub = arena.redis.pubsub()
            await arena.subscribe_match_events(reconnect_session, match_pubsub)

            # Send current match state
            match_data = await arena.get_match(reconnect_session)
            if match_data and match_data.status == "active":
                players = await arena.get_all_players(reconnect_session)
                await _send(websocket, "pvp.match_state_restore", {
                    "session_id": reconnect_session,
                    "players": [
                        {
                            "user_id": p.user_id,
                            "name": p.name,
                            "score": p.score,
                            "correct": p.correct,
                            "is_bot": p.is_bot,
                        }
                        for p in players
                    ],
                    "current_round": match_data.current_round,
                    "total_rounds": match_data.total_rounds,
                })
                await arena.publish_match_event(reconnect_session, {
                    "type": "pvp.player_reconnected",
                    "user_id": str(user_id),
                })

        # ── Step 2: Message loop ──
        _rate_limiter = knowledge_limiter()
        # Phase D (2026-04-20): idle heartbeat + hang kill (mirror of
        # /ws/pvp). Hung clients (mobile goes to background, broken WiFi)
        # previously stayed connected indefinitely; now 30s of silence
        # triggers a server ping, 120s triggers a hard close.
        _KN_IDLE_PING_SEC = 30
        _KN_IDLE_KILL_SEC = 120
        _kn_last_msg_at = time.time()
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=_KN_IDLE_PING_SEC,
                )
                _kn_last_msg_at = time.time()
            except asyncio.TimeoutError:
                if time.time() - _kn_last_msg_at > _KN_IDLE_KILL_SEC:
                    logger.info(
                        "Knowledge WS idle-kill user=%s (no msg for %.0fs)",
                        user_id, time.time() - _kn_last_msg_at,
                    )
                    try:
                        await websocket.close(code=1001)
                    except Exception:
                        pass
                    break
                try:
                    await _send(websocket, "ping", {})
                except Exception:
                    break
                continue
            if not _rate_limiter.is_allowed():
                await _send_error(websocket, "Too many messages", "rate_limited")
                continue

            # L6c fix: per-user rate limit across all connections (Redis).
            from app.core.ws_rate_limiter import check_user_rate_limit
            if not await check_user_rate_limit(str(user_id), scope="knowledge"):
                await _send_error(
                    websocket,
                    "Слишком много сообщений со всех ваших сессий.",
                    "rate_limited_user",
                )
                continue
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

            # ── Answer (solo mode) — supports both "text.message" and "answer" from frontend ──
            elif msg_type in ("text.message", "answer"):
                # T2 fix: bound WS text input at 10KB. Quiz answers are
                # typically short, but unbounded input could stuff the LLM
                # eval prompt and cause OOM / timeout.
                _WS_MAX_TEXT_CHARS = 10_000
                raw_text = (data.get("text") or msg.get("content") or "").strip()
                if len(raw_text) > _WS_MAX_TEXT_CHARS:
                    logger.warning(
                        "WS knowledge answer truncated from %d to %d chars",
                        len(raw_text), _WS_MAX_TEXT_CHARS,
                    )
                text = raw_text[:_WS_MAX_TEXT_CHARS]
                if not text:
                    await _send_error(websocket, "Empty answer", "empty_text")
                    continue
                if quiz_state and not quiz_state.finished:
                    # Route to mode-specific handler
                    if quiz_state.mode == QuizMode.debate:
                        await _handle_debate_round(websocket, quiz_state, text)
                    elif quiz_state.mode == QuizMode.mock_court:
                        await _handle_mock_court_round(websocket, quiz_state, text)
                    elif quiz_state.mode == QuizMode.case_study:
                        await _handle_case_study(websocket, quiz_state, text)
                    elif quiz_state.mode == QuizMode.article_deep_dive:
                        await _handle_article_deep_dive(websocket, quiz_state, text)
                    elif quiz_state.mode == QuizMode.daily_challenge:
                        await _handle_daily_challenge_answer(websocket, quiz_state, text)
                    elif quiz_state.mode == QuizMode.team_quiz:
                        await _handle_team_quiz_answer(websocket, quiz_state, text)
                    else:
                        await _handle_answer(websocket, quiz_state, text)
                else:
                    await _send_error(websocket, "No active quiz session", "no_session")

            # ── Skip question (solo) ──
            elif msg_type in ("quiz.skip", "skip"):
                if quiz_state and not quiz_state.finished:
                    await _handle_skip(websocket, quiz_state)
                else:
                    await _send_error(websocket, "No active quiz session", "no_session")

            # ── Hint (solo) ──
            elif msg_type in ("quiz.hint", "hint_request"):
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

            # ── V2: Follow-up answer/skip ──
            elif msg_type == "quiz.follow_up_response":
                if quiz_state and not quiz_state.finished and quiz_state.pending_follow_up:
                    action = data.get("action", "skip")
                    quiz_state.pending_follow_up = False
                    if action == "answer":
                        text_fu = data.get("text", "").strip()
                        if text_fu:
                            # Evaluate follow-up answer (lightweight, no score impact)
                            await _send(websocket, "quiz.follow_up_feedback", {
                                "text": "Спасибо за развёрнутый ответ! Продолжаем.",
                            })
                    # Proceed to next question regardless
                    await _next_question(websocket, quiz_state)
                elif quiz_state and not quiz_state.finished:
                    await _next_question(websocket, quiz_state)

            # ── SRS: Get user SRS stats ──
            elif msg_type == "srs.stats":
                try:
                    async with async_session() as srs_db:
                        stats = await get_user_srs_stats(srs_db, user_id)
                        await _send(websocket, "srs.stats", stats)
                except Exception:
                    logger.debug("SRS stats failed", exc_info=True)
                    await _send_error(websocket, "Failed to load SRS stats", "srs_error")

            # ── SRS: Get category mastery breakdown ──
            elif msg_type == "srs.mastery":
                try:
                    async with async_session() as srs_db:
                        mastery = await get_category_mastery(srs_db, user_id)
                        await _send(websocket, "srs.mastery", {"categories": mastery})
                except Exception:
                    logger.debug("SRS mastery failed", exc_info=True)
                    await _send_error(websocket, "Failed to load mastery data", "srs_error")

            # ── PvP: Find opponent ──
            elif msg_type == "pvp.find_opponent":
                await _handle_find_opponent(websocket, user_id, username, data)

            # ── PvP: Accept challenge ──
            elif msg_type == "pvp.accept_challenge":
                await _handle_accept_challenge(websocket, user_id, username, data)

            # ── PvP: Decline challenge ──
            elif msg_type == "pvp.decline_challenge":
                await _handle_decline_challenge(websocket, user_id, data)

            # ── PvP: Submit answer (simultaneous mode) ──
            elif msg_type == "pvp.answer":
                await _handle_pvp_answer(websocket, user_id, data)

            # ── PvP: Cancel search ──
            elif msg_type == "pvp.cancel_search":
                await _handle_cancel_search(websocket, user_id)

            # ── PvP: Play with bot (fallback) ──
            elif msg_type == "pvp.play_with_bot":
                await _handle_play_with_bot(websocket, user_id, username)

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
        # Cancel Pub/Sub listener
        if pubsub_task and not pubsub_task.done():
            pubsub_task.cancel()
            try:
                await pubsub_task
            except asyncio.CancelledError:
                pass

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

        # Handle PvP disconnect: set reconnect grace period + auto-replace with bot
        if user_id:
            try:
                arena = get_arena_redis()
                active_match = await arena.get_user_active_match(str(user_id))
                if active_match:
                    match_data = await arena.get_match(active_match)
                    if match_data and match_data.status == "active":
                        await arena.set_player_connected(active_match, str(user_id), False)
                        await arena.set_reconnect_grace(str(user_id), active_match)
                        await arena.publish_match_event(active_match, {
                            "type": "pvp.player_disconnected",
                            "user_id": str(user_id),
                            "grace_seconds": 60,
                        })
                        # Schedule bot replacement after grace period expires
                        asyncio.create_task(
                            _replace_with_bot_after_grace(
                                arena, active_match, str(user_id), grace_seconds=60,
                            )
                        )
            except Exception as e:
                logger.error("Failed to handle PvP disconnect: %s", e)
