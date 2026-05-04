"""Weighted scoring for AI-initiated hangup decisions.

Background (2026-05-04, BUG 1 follow-up)
----------------------------------------
The first attempt at BUG 1 (PR #209) added an explicit ``[END_CALL]``
marker that the LLM is instructed to emit when it decides to hang up.
That works most of the time but the LLM is not 100% reliable about
following the system-prompt rule — production session screenshots
showed the AI saying "до свидания / разговор окончен / больше не
звоните" four times in a row after a manager was openly hostile, and
the call still didn't end.

The fallback path (substring without marker) requires
``current_emotion == "hostile" AND message_count >= 8``. Both gates
fail in plenty of legitimate scenarios:

* The user insults the AI on turn 3-4. FSM raises ``rudeness_detected``
  and emotion is *callback* or *cold* (not yet "hostile" by FSM rules)
  but the AI clearly intends to terminate.
* The user is grossly off-topic for 6 turns. AI politely says "всего
  доброго" while emotion is still *cold*.

Hard-AND of two strict conditions throws away every weaker but valid
signal. Industry pattern (Vapi, Retell, OpenAI Realtime): score a
weighted sum of the available signals and trigger above a threshold.
This module implements that for the substring-fallback path. The
``[END_CALL]`` marker still wins outright when present (handled in the
caller — it bypasses this scorer).

Calibration
-----------
Weights add up to roughly 1.4 in the *strong* hangup case ("polite
goodbye after insult, mid-conversation") and 0.45 in the *theatrical
exit* case ("LLM improvised a dramatic 'до свидания' on turn 2").
Threshold 0.65 sits in the gap.

Worked examples (see ``test_hangup_decision.py`` for the assertions):

* PROD CASE — kid-died-prank, cold→hostile, msg=10, substring, not
  question, rudeness_detected=True →
    0.40 + 0.30 + 0.20 + 0.20 + 0.30 = **1.40**  ⇒ trigger
* THEATRE — substring on turn 2, cold emotion, no insult →
    0.40 + 0.20 + 0  + 0  + 0  = **0.60**  ⇒ no trigger
* MARKER PATH — handled by caller, this scorer not consulted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


# Public weights — exposed so tests + audit notes can reference exact values.
W_SUBSTRING: Final[float] = 0.40        # farewell phrase in last sentence
W_EMOTION_HOSTILE: Final[float] = 0.30  # FSM already on hostile/callback
W_EMOTION_COLD: Final[float] = 0.15     # cold w/ enough turns elapsed
W_NOT_QUESTION: Final[float] = 0.20     # reply isn't inviting more
W_MSG_LONG: Final[float] = 0.20         # >=8 turns — real conversation
W_MSG_MEDIUM: Final[float] = 0.10       # 4..7 turns — some context
W_RUDENESS: Final[float] = 0.30         # FSM saw insult / counter-aggression
W_AI_FAREWELL_PRIOR: Final[float] = 0.20  # AI already said goodbye in a prior turn

THRESHOLD: Final[float] = 0.65

# Emotions that are themselves a strong "I'm done" signal.
HOSTILE_LIKE_EMOTIONS: Final[frozenset[str]] = frozenset({"hostile", "callback"})


@dataclass
class HangupSignals:
    """Inputs to the weighted decision. All fields are observable at the
    point in ``ws/training.py`` where the AI farewell check runs."""

    substring_hit: bool
    is_question: bool
    msg_count: int
    emotion: str
    rudeness_detected: bool = False
    ai_said_farewell_before: bool = False


@dataclass
class HangupDecision:
    """Verdict + audit trail. The ``breakdown`` dict makes it trivial to
    log why we triggered (or didn't) and is shipped into the WS event
    payload for FE/results-page introspection."""

    should_end: bool
    score: float
    threshold: float
    breakdown: dict[str, float]


def decide_hangup(signals: HangupSignals) -> HangupDecision:
    """Score the signals and return the decision."""
    # Strong substring requirement: without a farewell phrase in the
    # actual reply we never even consider hanging up via this path.
    if not signals.substring_hit:
        return HangupDecision(False, 0.0, THRESHOLD, {})

    breakdown: dict[str, float] = {}
    score = 0.0

    breakdown["substring_hit"] = W_SUBSTRING
    score += W_SUBSTRING

    if signals.emotion in HOSTILE_LIKE_EMOTIONS:
        breakdown["emotion_hostile_like"] = W_EMOTION_HOSTILE
        score += W_EMOTION_HOSTILE
    elif signals.emotion == "cold" and signals.msg_count >= 4:
        breakdown["emotion_cold_with_context"] = W_EMOTION_COLD
        score += W_EMOTION_COLD

    if not signals.is_question:
        breakdown["not_question"] = W_NOT_QUESTION
        score += W_NOT_QUESTION

    if signals.msg_count >= 8:
        breakdown["msg_count_long"] = W_MSG_LONG
        score += W_MSG_LONG
    elif signals.msg_count >= 4:
        breakdown["msg_count_medium"] = W_MSG_MEDIUM
        score += W_MSG_MEDIUM

    if signals.rudeness_detected:
        breakdown["rudeness_detected"] = W_RUDENESS
        score += W_RUDENESS

    if signals.ai_said_farewell_before:
        breakdown["ai_said_farewell_before"] = W_AI_FAREWELL_PRIOR
        score += W_AI_FAREWELL_PRIOR

    return HangupDecision(
        should_end=score >= THRESHOLD,
        score=round(score, 2),
        threshold=THRESHOLD,
        breakdown=breakdown,
    )


__all__ = [
    "HangupSignals",
    "HangupDecision",
    "decide_hangup",
    "THRESHOLD",
]
