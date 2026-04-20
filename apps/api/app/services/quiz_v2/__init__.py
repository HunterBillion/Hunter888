"""quiz_v2 — narrative case-driven quiz engine.

Created 2026-04-18 as the redesign of knowledge_quiz scoring from a
disconnected Q&A into a story-driven investigation over one "case".

Modules:
  - cases.py        — QuizCase dataclass + hybrid Tier-A/B/C router
  - beats.py        — StoryBeat enum (intake → documents → obstacles → property → outcome)
  - ramp.py         — DifficultyRamp (factoid → procedure → edge_case → multi → strategic)
                      + compute_session_length(mode, difficulty, user_level)
  - presentation.py — wrap_question with personality (Professor / Detective)
  - memory.py       — Redis-backed SessionMemory (case, beat, answers, ladder)
  - integration.py  — bridge into existing knowledge_quiz.generate_question

All are opt-in via feature flag `USE_QUIZ_V2` (config.py). Legacy pipeline
stays untouched as rollback path.
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
]
