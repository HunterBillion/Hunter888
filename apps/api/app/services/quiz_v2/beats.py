"""StoryBeat — narrative phase mapping for quiz sessions.

A case plays out across 5 beats, each centred on a real-world stage of
127-FZ proceedings:

  1. intake      — priyom zayavleniya, thresholds, obligations
  2. documents   — doc verification, fraud checks, property inventory
  3. obstacles   — creditor objections, disputed transactions, challenges
  4. property    — fate of assets, залог, single-dwelling, foreign assets
  5. outcome     — plan reorganization / realization / release

Beat mapping is session-length-aware: a 10-question session covers all 5
beats evenly; 15/20-question sessions dwell longer on harder beats
(obstacles + property for tangled/adversarial cases).
"""

from __future__ import annotations

from enum import Enum


import builtins as _builtins


class StoryBeat(str, Enum):
    # 2026-04-18: enum member `property` was shadowing Python built-in
    # `property` inside the class body (Python 3.12+ treats enum assignments as
    # regular attrs during class construction), breaking the `@property`
    # decorator below. Renamed internal attr to `property_fate`; .value stays
    # "property" for JSON / Redis backward-compat with seed files + frontend.
    intake = "intake"
    documents = "documents"
    obstacles = "obstacles"
    property_fate = "property"
    outcome = "outcome"

    @_builtins.property
    def ru_label(self) -> str:
        return {
            StoryBeat.intake:         "Приём заявления",
            StoryBeat.documents:      "Проверка документов",
            StoryBeat.obstacles:      "Осложнения и возражения",
            StoryBeat.property_fate:  "Судьба имущества",
            StoryBeat.outcome:        "Финал дела",
        }[self]

    @_builtins.property
    def icon(self) -> str:
        return {
            StoryBeat.intake:         "📋",
            StoryBeat.documents:      "📑",
            StoryBeat.obstacles:      "⚔️",
            StoryBeat.property_fate:  "🏠",
            StoryBeat.outcome:        "⚖️",
        }[self]


# Standard beat distributions per session length
# Each tuple = (beat, question_count)
_BEAT_PLAN_10 = [
    (StoryBeat.intake, 2),
    (StoryBeat.documents, 2),
    (StoryBeat.obstacles, 2),
    (StoryBeat.property_fate, 2),
    (StoryBeat.outcome, 2),
]
_BEAT_PLAN_15 = [
    (StoryBeat.intake, 2),
    (StoryBeat.documents, 3),
    (StoryBeat.obstacles, 4),      # <- dwell longer on conflict
    (StoryBeat.property_fate, 3),
    (StoryBeat.outcome, 3),
]
_BEAT_PLAN_20 = [
    (StoryBeat.intake, 3),
    (StoryBeat.documents, 4),
    (StoryBeat.obstacles, 5),
    (StoryBeat.property_fate, 4),
    (StoryBeat.outcome, 4),
]


def _beat_plan_for(total_questions: int) -> list[tuple[StoryBeat, int]]:
    if total_questions <= 10:
        return _BEAT_PLAN_10
    if total_questions <= 15:
        return _BEAT_PLAN_15
    return _BEAT_PLAN_20


def beat_for_question(question_number: int, total_questions: int) -> StoryBeat:
    """Return the StoryBeat this question falls into.

    question_number is 1-indexed. total_questions drives distribution.
    """
    if question_number < 1:
        return StoryBeat.intake
    plan = _beat_plan_for(total_questions)
    cursor = 0
    for beat, count in plan:
        cursor += count
        if question_number <= cursor:
            return beat
    # Past the end — stay in outcome
    return StoryBeat.outcome


def beat_progress(question_number: int, total_questions: int) -> tuple[StoryBeat, int, int]:
    """Return (beat, position_in_beat, beat_length) for UI progress display.

    Example: q=4 of 10 → (documents, 2, 2) meaning "2nd of 2 in Documents".
    """
    plan = _beat_plan_for(total_questions)
    cursor = 0
    for beat, count in plan:
        if question_number <= cursor + count:
            position = question_number - cursor
            return beat, max(1, position), count
        cursor += count
    return StoryBeat.outcome, 1, 1
