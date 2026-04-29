"""User-first Bug 2: stage auto-advance ceiling for all stages 1-6.

Pre-fix the auto-advance fallback only fired on stage 1. Stages 2-6
needed natural-keyword matches to progress, so a manager who went
off-script (or whose STT was poor) got stuck on the same stage and
the FE script-panel dots looked frozen — field-reported as "после
2 шага я уже сделал все но нихуя".

These tests pin:
  * stages 1-6 each force-advance once user_msg_index >= max_messages
  * stage 7 (closing) is terminal — never auto-advance past it
  * minimal score credit (0.1) is awarded so scoring still differs
    from "fully earned"
  * pending hysteresis confirmations are cleared on auto-advance —
    they belonged to the OLD stage's candidates and would mis-fire
    on the NEW stage otherwise
"""

import pytest
from unittest.mock import AsyncMock

from app.services.stage_tracker import (
    StageTracker,
    StageState,
    STAGE_KEYWORDS,
    STAGE_ORDER,
)


def _state_at(stage: int, msg_count_on_stage: int = 0) -> StageState:
    """Helper: construct a state where current stage = N and we have
    seen `msg_count_on_stage` user messages while on it."""
    return StageState(
        current_stage=stage,
        current_stage_name=STAGE_ORDER[stage - 1],
        stages_completed=list(range(1, stage)),
        total_stages=len(STAGE_ORDER),
        stage_message_counts={},
        stage_scores={},
        stage_started_at_msg={stage: 0},
        stage_started_at_ts={stage: 0.0},
        transition_confirmations={},
    )


def _make_tracker_with_state(state: StageState) -> StageTracker:
    """Build a StageTracker whose redis-load returns the given state and
    redis-save is a no-op AsyncMock — we only care about the in-memory
    state mutation logic."""
    tracker = StageTracker("sess1", redis=None)
    # Bypass redis: stub _load_state and _save_state.
    tracker._load_state = AsyncMock(return_value=state)  # type: ignore[method-assign]
    tracker._save_state = AsyncMock(return_value=None)  # type: ignore[method-assign]
    return tracker


@pytest.mark.parametrize(
    "stage_num, stage_name",
    [
        (1, "greeting"),
        (2, "contact"),
        (3, "qualification"),
        (4, "presentation"),
        (5, "objections"),
        (6, "appointment"),
    ],
)
@pytest.mark.asyncio
async def test_auto_advance_fires_for_every_advanceable_stage(stage_num, stage_name):
    """Pre-fix only stage 1 auto-advanced. Now all of 1-6 must."""
    state = _state_at(stage_num)
    tracker = _make_tracker_with_state(state)
    msg_index = STAGE_KEYWORDS[stage_name]["max_messages"]
    # Send a message that contains NO keywords (empty/neutral text) at
    # the ceiling — the only thing that should trigger advance is the
    # message_index >= max_messages fallback.
    new_state, changed, _ = await tracker.process_message(
        "ага", msg_index, "user",
    )
    assert changed is True, (
        f"Stage {stage_num} ({stage_name}) did not auto-advance at "
        f"msg_index={msg_index} (max_messages). Bug 2 still present."
    )
    assert new_state.current_stage == stage_num + 1
    # Minimal credit: scoring still distinguishes earned vs auto-advanced.
    assert new_state.stage_scores.get(stage_num) == 0.1


@pytest.mark.asyncio
async def test_closing_stage_never_auto_advances():
    """Stage 7 is terminal. Auto-advance would corrupt the FSM
    (current_stage = 8, off-by-one in STAGE_ORDER lookups)."""
    state = _state_at(7)
    tracker = _make_tracker_with_state(state)
    msg_index = STAGE_KEYWORDS["closing"]["max_messages"]
    new_state, changed, _ = await tracker.process_message(
        "понял спасибо", msg_index, "user",
    )
    # No transition out of closing.
    assert changed is False
    assert new_state.current_stage == 7


@pytest.mark.asyncio
async def test_auto_advance_clears_hysteresis():
    """If a partial transition was being accumulated for stage N+2 while
    we time-out advance to N+1, those confirmations are stale and must
    not roll over (they would push the next stage to advance early)."""
    state = _state_at(2)
    state.transition_confirmations = {4: 1}  # was building toward stage 4
    tracker = _make_tracker_with_state(state)
    msg_index = STAGE_KEYWORDS["contact"]["max_messages"]
    new_state, changed, _ = await tracker.process_message(
        "ага", msg_index, "user",
    )
    assert changed is True
    assert new_state.current_stage == 3
    assert new_state.transition_confirmations == {}


@pytest.mark.asyncio
async def test_auto_advance_skipped_when_below_ceiling():
    """Sanity: if message_index < max_messages and no keywords match,
    we MUST stay on the same stage. Auto-advance is a ceiling, not an
    eager fallback."""
    state = _state_at(2)
    tracker = _make_tracker_with_state(state)
    # contact max_messages = 8; pass 3 — well below.
    new_state, changed, _ = await tracker.process_message(
        "угу",  # no keywords
        3,
        "user",
    )
    assert changed is False
    assert new_state.current_stage == 2
