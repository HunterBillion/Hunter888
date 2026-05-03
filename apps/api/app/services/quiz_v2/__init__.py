"""quiz_v2 — narrative case-driven quiz engine + Path A grader/explainer.

Created 2026-04-18 as the redesign of knowledge_quiz scoring from a
disconnected Q&A into a story-driven investigation over one "case".

Extended 2026-05-03 (Path A, design doc ``docs/QUIZ_V2_ARENA_DESIGN.md``)
with the deterministic grader / LLM-explainer split that aligns the
quiz arena with the standard pattern shared by Kahoot/Quizizz/Slido.

Narrative modules (existing):
  - cases.py        — QuizCase dataclass + hybrid Tier-A/B/C router
  - beats.py        — StoryBeat enum (intake → documents → obstacles → property → outcome)
  - ramp.py         — DifficultyRamp (factoid → procedure → edge_case → multi → strategic)
  - presentation.py — wrap_question with personality (Professor / Detective)
  - memory.py       — Redis-backed SessionMemory (case, beat, answers, ladder)
  - integration.py  — bridge into existing knowledge_quiz.generate_question

Path A modules (A0 skeletons; A1–A4 fill in):
  - rollout.py      — is_quiz_v2_grader_enabled_for_user feature-flag gate
  - grader.py       — deterministic verdict (exact/synonyms/regex/keyword/embedding)
  - answer_keys.py  — ORM access for quiz_v2_answer_keys table
  - events.py       — server-issued answer_id + ArenaBus publish helpers

Narrative pipeline is gated by ``USE_QUIZ_V2``; the Path A grader is
gated independently by ``quiz_v2_grader_enabled`` plus the optional
``quiz_v2_grader_user_whitelist``. Both default OFF — legacy pipeline
remains the rollback path.
"""

from app.services.quiz_v2.cases import QuizCase, CaseRouter, load_seed_cases
from app.services.quiz_v2.beats import StoryBeat, beat_for_question
from app.services.quiz_v2.ramp import (
    DifficultyRamp,
    QuestionType,
    compute_session_length,
    rung_for_question,
)
from app.services.quiz_v2.presentation import wrap_question, Personality
from app.services.quiz_v2.memory import SessionMemory
from app.services.quiz_v2.voice import synth_case_intro_audio
from app.services.quiz_v2.rollout import is_quiz_v2_grader_enabled_for_user
from app.services.quiz_v2.events import new_answer_id
from app.services.quiz_v2.answer_keys import question_hash, AnswerKey

__all__ = [
    "QuizCase",
    "CaseRouter",
    "load_seed_cases",
    "StoryBeat",
    "beat_for_question",
    "DifficultyRamp",
    "QuestionType",
    "compute_session_length",
    "rung_for_question",
    "wrap_question",
    "Personality",
    "SessionMemory",
    "synth_case_intro_audio",
    "is_quiz_v2_grader_enabled_for_user",
    "new_answer_id",
    "question_hash",
    "AnswerKey",
]
