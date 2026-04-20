"""quiz_v2 integration bridge — called from existing WS / service entry points.

One-line ask from callers:
  - on session start    → start_session_v2(session_id, mode, user_level, personality, category)
  - on next question    → fetch_next_question_v2(session_id, question_number)
  - on answer evaluate  → record_answer_v2(session_id, q_idx, correct, rung, chunk_id)
  - on session end      → end_session_v2(session_id)

If feature flag USE_QUIZ_V2 is False OR any component fails, caller gets None
back and must fall through to the legacy path. Never raises.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Literal

from app.services.quiz_v2.beats import StoryBeat, beat_for_question
from app.services.quiz_v2.cases import CaseRouter, QuizCase
from app.services.quiz_v2.memory import SessionMemory
from app.services.quiz_v2.presentation import (
    Personality,
    build_case_intro,
    wrap_question,
)
from app.services.quiz_v2.ramp import (
    DifficultyRamp,
    QuestionType,
    compute_session_length,
)

logger = logging.getLogger(__name__)

_router = CaseRouter()


def _is_enabled() -> bool:
    """Feature-flag gate. Reads settings.use_quiz_v2 (default False)."""
    try:
        from app.config import settings
        return bool(getattr(settings, "use_quiz_v2", False))
    except Exception:
        return False


@dataclass
class V2StartResult:
    case: QuizCase
    total_questions: int
    personality: Personality
    intro_text: str


async def start_session_v2(
    *,
    session_id: uuid.UUID,
    mode: str,
    user_level: int = 1,
    user_id: str | None = None,
    personality: Personality = "professor",
    difficulty: int = 3,
    category: str | None = None,  # reserved for Tier-B template fill
) -> V2StartResult | None:
    """Start a quiz_v2 session: pick a case, compute length, store in Redis.

    Returns V2StartResult with intro text to emit as case.intro WS event.
    Returns None if v2 is disabled or blitz mode (blitz skips cases).
    """
    if not _is_enabled():
        return None
    if mode == "blitz":
        return None  # v2 doesn't apply to blitz

    # (category reserved for future Tier-B/C template-fill that targets a topic)
    _ = category

    try:
        case = await _router.pick_case(
            mode=mode, difficulty=difficulty, user_level=user_level,
            user_id=user_id, exclude_case_ids=None,
        )
        if case is None:
            return None

        total = compute_session_length(
            mode, difficulty=difficulty, user_level=user_level, case_complexity=case.complexity,
        )
        # free_dialog returns 0 meaning "open-ended" — v2 doesn't yet support this
        if total == 0:
            logger.info("quiz_v2: free_dialog open-ended — falling back to legacy")
            return None

        await SessionMemory.put_case(session_id, case)
        await SessionMemory.put_personality(session_id, personality)
        await SessionMemory.put_total(session_id, total)

        intro_text = build_case_intro(case, personality)
        logger.info(
            "quiz_v2.start: sid=%s case=%s complexity=%s total=%d personality=%s",
            session_id, case.case_id, case.complexity, total, personality,
        )
        return V2StartResult(
            case=case,
            total_questions=total,
            personality=personality,
            intro_text=intro_text,
        )
    except Exception as exc:
        logger.warning("quiz_v2.start_session_v2 failed: %s", exc, exc_info=True)
        return None


@dataclass
class V2NextQuestion:
    wrapped_text: str           # full text to send to client (with beat header etc.)
    bare_text: str              # original question text from the generator
    beat: StoryBeat
    rung: QuestionType
    difficulty: int             # 1-5 for RAG retrieval
    beat_hints: list[str]       # expected facts for THIS beat (grounding signal)


async def shape_next_question_v2(
    *,
    session_id: uuid.UUID,
    question_number: int,
    bare_question_text: str,
) -> V2NextQuestion | None:
    """Given a bare question (from existing RAG pipeline), wrap it with v2 narrative.

    Caller still goes through knowledge_quiz.generate_question() to get the
    bare text — quiz_v2 doesn't replace generation, only adds narrative layer.

    Returns None if v2 state missing (fall back to bare text).
    """
    if not _is_enabled():
        return None

    case = await SessionMemory.get_case(session_id)
    if case is None:
        return None
    personality_raw = await SessionMemory.get_personality(session_id) or "professor"
    personality: Personality = personality_raw if personality_raw in ("professor", "detective", "blitz") else "professor"  # type: ignore
    total = await SessionMemory.get_total(session_id) or 10

    beat = beat_for_question(question_number, total)
    rung = DifficultyRamp.rung_for_question(question_number, total)
    difficulty = DifficultyRamp.difficulty_for_rung(rung)
    beat_hints = case.expected_beats.get(beat.value, []) if isinstance(case.expected_beats, dict) else []

    wrapped = wrap_question(
        question_text=bare_question_text,
        case=case,
        beat=beat,
        question_number=question_number,
        total_questions=total,
        personality=personality,
        question_type=rung,
    )
    return V2NextQuestion(
        wrapped_text=wrapped,
        bare_text=bare_question_text,
        beat=beat,
        rung=rung,
        difficulty=difficulty,
        beat_hints=beat_hints,
    )


async def record_answer_v2(
    *,
    session_id: uuid.UUID,
    q_idx: int,
    correct: bool,
    rung: QuestionType | str,
    chunk_id: str | None = None,
) -> None:
    """Append answer to session memory (non-fatal on failure)."""
    if not _is_enabled():
        return
    try:
        rung_str = rung.value if isinstance(rung, QuestionType) else str(rung)
        await SessionMemory.append_answer(
            session_id, q_idx=q_idx, correct=correct, rung=rung_str, chunk_id=chunk_id,
        )
    except Exception as exc:
        logger.warning("quiz_v2.record_answer_v2 failed: %s", exc)


async def end_session_v2(session_id: uuid.UUID) -> None:
    """Clear v2 state for a finished session."""
    if not _is_enabled():
        return
    try:
        await SessionMemory.clear(session_id)
    except Exception:
        pass
