"""SessionMemory — Redis-backed state for one quiz session.

Keys (TTL = 2h after last write):
  quiz_v2:session:{sid}:case      → JSON of QuizCase
  quiz_v2:session:{sid}:answers   → JSON list of {q_idx, correct, rung, chunk_id}
  quiz_v2:session:{sid}:personality → "professor" | "detective" | "blitz"
  quiz_v2:session:{sid}:total     → int total_questions

Why keep this separate from useKnowledgeStore (frontend): backend also needs
to read case + answer history to ground the NEXT question in what user
already got right/wrong (adaptive difficulty within a case).
"""

from __future__ import annotations

import json
import logging
import uuid

from app.core.redis_pool import get_redis
from app.services.quiz_v2.cases import QuizCase

logger = logging.getLogger(__name__)

TTL_SECONDS = 2 * 60 * 60  # 2 hours


def _k(session_id: uuid.UUID | str, suffix: str) -> str:
    return f"quiz_v2:session:{session_id}:{suffix}"


class SessionMemory:
    """Small facade around Redis for quiz-v2 per-session state."""

    @staticmethod
    async def put_case(session_id: uuid.UUID | str, case: QuizCase) -> None:
        try:
            r = get_redis()
            await r.setex(_k(session_id, "case"), TTL_SECONDS, json.dumps(case.to_redis_json(), ensure_ascii=False))
        except Exception as exc:
            logger.warning("quiz_v2.memory: put_case failed: %s", exc)

    @staticmethod
    async def get_case(session_id: uuid.UUID | str) -> QuizCase | None:
        try:
            r = get_redis()
            raw = await r.get(_k(session_id, "case"))
            if not raw:
                return None
            return QuizCase.from_redis_json(json.loads(raw))
        except Exception as exc:
            logger.warning("quiz_v2.memory: get_case failed: %s", exc)
            return None

    @staticmethod
    async def put_personality(session_id: uuid.UUID | str, personality: str) -> None:
        try:
            r = get_redis()
            await r.setex(_k(session_id, "personality"), TTL_SECONDS, personality)
        except Exception as exc:
            logger.warning("quiz_v2.memory: put_personality failed: %s", exc)

    @staticmethod
    async def get_personality(session_id: uuid.UUID | str) -> str | None:
        try:
            r = get_redis()
            val = await r.get(_k(session_id, "personality"))
            if val is None:
                return None
            return val.decode() if isinstance(val, bytes) else str(val)
        except Exception as exc:
            logger.warning("quiz_v2.memory: get_personality failed: %s", exc)
            return None

    @staticmethod
    async def put_total(session_id: uuid.UUID | str, total: int) -> None:
        try:
            r = get_redis()
            await r.setex(_k(session_id, "total"), TTL_SECONDS, str(total))
        except Exception as exc:
            logger.warning("quiz_v2.memory: put_total failed: %s", exc)

    @staticmethod
    async def get_total(session_id: uuid.UUID | str) -> int | None:
        try:
            r = get_redis()
            val = await r.get(_k(session_id, "total"))
            if val is None:
                return None
            s = val.decode() if isinstance(val, bytes) else str(val)
            return int(s)
        except Exception:
            return None

    @staticmethod
    async def append_answer(
        session_id: uuid.UUID | str,
        *,
        q_idx: int,
        correct: bool,
        rung: str,
        chunk_id: str | None = None,
    ) -> None:
        """Append one answer result to the history list.

        Stored as JSON-serialized list (small, usually <30 items per session)
        rather than Redis list to keep single-read semantics for grounding.
        """
        try:
            r = get_redis()
            key = _k(session_id, "answers")
            raw = await r.get(key)
            history = json.loads(raw) if raw else []
            history.append({"q_idx": q_idx, "correct": bool(correct), "rung": rung, "chunk_id": chunk_id})
            await r.setex(key, TTL_SECONDS, json.dumps(history, ensure_ascii=False))
        except Exception as exc:
            logger.warning("quiz_v2.memory: append_answer failed: %s", exc)

    @staticmethod
    async def get_answers(session_id: uuid.UUID | str) -> list[dict]:
        try:
            r = get_redis()
            raw = await r.get(_k(session_id, "answers"))
            if not raw:
                return []
            return json.loads(raw)
        except Exception:
            return []

    @staticmethod
    async def clear(session_id: uuid.UUID | str) -> None:
        try:
            r = get_redis()
            for suf in ("case", "answers", "personality", "total"):
                await r.delete(_k(session_id, suf))
        except Exception as exc:
            logger.warning("quiz_v2.memory: clear failed: %s", exc)

    @staticmethod
    async def weak_rungs(session_id: uuid.UUID | str) -> list[str]:
        """Return rungs where user answered incorrectly more than correctly.

        Useful signal for CaseRouter to pick next-question emphasis.
        """
        answers = await SessionMemory.get_answers(session_id)
        if not answers:
            return []
        from collections import defaultdict
        totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [correct, total]
        for a in answers:
            rung = a.get("rung", "factoid")
            totals[rung][1] += 1
            if a.get("correct"):
                totals[rung][0] += 1
        weak = [r for r, (c, t) in totals.items() if t >= 2 and c * 2 < t]
        return weak
