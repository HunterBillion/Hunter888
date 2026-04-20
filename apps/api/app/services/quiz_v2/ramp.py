"""DifficultyRamp — 5-step ladder of question types + session-length calculator.

Rungs (easy → hard):
  1. factoid    — recall a single fact (article number, amount threshold)
  2. procedure  — describe a procedure step-by-step
  3. edge_case  — apply law to an unusual/ambiguous situation
  4. multi      — enumerate 2+ conditions / requirements
  5. strategic  — pick among multiple valid legal strategies

Session length is variable: blitz always = 20 (fast shallow), themed
scales by difficulty × complexity, free_dialog is open-ended (0 = until
user ends).
"""

from __future__ import annotations

from enum import Enum


class QuestionType(str, Enum):
    factoid = "factoid"
    procedure = "procedure"
    edge_case = "edge_case"
    multi = "multi"
    strategic = "strategic"

    @property
    def ru_label(self) -> str:
        return {
            QuestionType.factoid:    "Факт",
            QuestionType.procedure:  "Процедура",
            QuestionType.edge_case:  "Нетипичная ситуация",
            QuestionType.multi:      "Множественные условия",
            QuestionType.strategic:  "Стратегия",
        }[self]


class DifficultyRamp:
    """Progresses question type across a session.

    Strategy:
      - Early questions = factoid (warm up the user)
      - Middle = procedure + multi
      - Late = edge_case + strategic (climax before outcome beat)
    """

    @staticmethod
    def rung_for_question(question_number: int, total_questions: int) -> QuestionType:
        """Deterministic ramp based on normalized progress (0..1)."""
        if total_questions <= 0:
            return QuestionType.factoid
        ratio = (question_number - 1) / max(1, total_questions - 1)
        ratio = max(0.0, min(1.0, ratio))
        if ratio < 0.25:
            return QuestionType.factoid
        if ratio < 0.45:
            return QuestionType.procedure
        if ratio < 0.65:
            return QuestionType.multi
        if ratio < 0.85:
            return QuestionType.edge_case
        return QuestionType.strategic

    @staticmethod
    def difficulty_for_rung(rung: QuestionType) -> int:
        """Map rung → legacy 1-5 difficulty for RAG retrieval."""
        return {
            QuestionType.factoid: 1,
            QuestionType.procedure: 2,
            QuestionType.multi: 3,
            QuestionType.edge_case: 4,
            QuestionType.strategic: 5,
        }[rung]


# Public shortcut
def rung_for_question(question_number: int, total_questions: int) -> QuestionType:
    return DifficultyRamp.rung_for_question(question_number, total_questions)


def compute_session_length(
    mode: str,
    *,
    difficulty: int = 3,
    user_level: int = 1,
    case_complexity: str | None = None,
) -> int:
    """Determine how many questions this session should have.

    Returns integer total_questions. For free_dialog mode returns 0 meaning
    "open-ended, end when user exits". Blitz is fixed at 20.

    Matrix:
      blitz                            → 20
      themed × simple                  → 10
      themed × tangled                 → 15
      themed × adversarial             → 20
      themed × (no case, legacy)       → 10 + (difficulty >= 4 ? 5 : 0)
      free_dialog                      → 0 (unlimited)

    Veteran boost: user_level >= 10 adds +5 to themed × tangled/adversarial.
    """
    if mode == "blitz":
        return 20

    if mode == "free_dialog":
        return 0  # open-ended

    # themed (or unknown → default to themed)
    if case_complexity == "simple":
        base = 10
    elif case_complexity == "tangled":
        base = 15
    elif case_complexity == "adversarial":
        base = 20
    else:
        # Legacy path — no case, just difficulty-based
        base = 10 + (5 if difficulty >= 4 else 0)

    if user_level >= 10 and case_complexity in ("tangled", "adversarial"):
        base += 5

    return min(base, 25)  # safety cap
