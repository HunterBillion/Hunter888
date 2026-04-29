"""P0 (2026-04-29) Call Arc — pin the two-axis architecture.

Three contracts protected here:

1. ``no_stage_leak`` — when arc V1 is active, the AI prompt block produced
   by ``build_arc_prompt`` contains no STAGE_BEHAVIOR phrases from the
   legacy stage tracker. The whole point of P0 is that the AI no longer
   sees manager-script terminology.

2. ``no_close_call_1`` — for every shipped arc template, call 1 of N has
   non-empty ``must_not_happen`` constraints that include "не соглашаться"-
   style wording. This is the architectural answer to the user's concern
   that an unscripted AI would close the deal on the first call.

3. ``scoring_unchanged`` — StageTracker's scoring output (used by
   /results and analytics) is computed from its persisted state, not
   from prompt assembly. The arc never touches ``StageState`` or
   ``build_scoring_details``. We assert the function still works on
   a representative state and that none of its output references arc
   internals.
"""

from __future__ import annotations

import pytest

from app.services.call_arc import (
    CallArcStep,
    build_arc_prompt,
    get_arc_step,
)


# ── Test 1: no stage leakage in arc prompt ───────────────────────────────────

# Phrases the legacy StageTracker.build_stage_prompt() produces. If any of
# these appear in the arc block, we've reintroduced the leak the redesign
# was meant to remove.
_LEGACY_STAGE_PHRASES = (
    "STAGE_CONTEXT",
    "ПОВЕДЕНИЕ НА ЭТОМ ЭТАПЕ",
    "ЕСТЕСТВЕННОЕ СОСТОЯНИЕ КЛИЕНТА В ЭТОТ МОМЕНТ",
    "ЧТО УМЕСТНО РАСКРЫТЬ ПО НАСТРОЕНИЮ",
    "ЧТО МОЖЕШЬ РАСКРЫТЬ:",
    "АКТИВНЫЕ КАТЕГОРИИ ЛОВУШЕК",
    # Stage names from STAGE_ORDER — the AI must not learn the manager's
    # checklist vocabulary.
    "greeting",
    "qualification",
    "presentation",
    "objections",
    "appointment",
)


@pytest.mark.parametrize("call_n,total_n", [
    (1, 3), (2, 3), (3, 3),
    (1, 4), (2, 4), (3, 4), (4, 4),
    (1, 5), (3, 5), (5, 5),
])
def test_arc_prompt_has_no_stage_leak(call_n: int, total_n: int):
    step = get_arc_step(call_n, total_n)
    block = build_arc_prompt(step)
    for phrase in _LEGACY_STAGE_PHRASES:
        assert phrase not in block, (
            f"arc block leaks legacy stage phrase {phrase!r} at "
            f"call {call_n}/{total_n}: {block[:200]}"
        )


def test_arc_prompt_advertises_role_not_script():
    step = get_arc_step(1, 3)
    block = build_arc_prompt(step)
    assert "ТВОЯ РОЛЬ В ЭТОМ ЗВОНКЕ" in block
    assert "СОСТОЯНИЕ В НАЧАЛЕ" in block
    assert "ВНУТРЕННЯЯ ЦЕЛЬ" in block
    # The block must affirm that there is no script, otherwise the model
    # may hallucinate one from training data on similar tasks.
    assert "у тебя НЕТ скрипта" in block


def test_arc_prompt_renders_prev_calls_summary():
    step = get_arc_step(2, 3)
    summary = "Звонок 1: представился, договорились перезвонить в среду."
    block = build_arc_prompt(step, prev_calls_summary=summary)
    assert "ЧТО БЫЛО В ПРЕДЫДУЩИХ ЗВОНКАХ" in block
    assert summary in block


# ── Test 2: must_not_happen guards call 1 against premature close ────────────

@pytest.mark.parametrize("total_n", [3, 4, 5])
def test_call_1_forbids_closing(total_n: int):
    """First call in any cycle must explicitly forbid agreeing to purchase."""
    step = get_arc_step(call_number=1, total_calls=total_n)
    assert step.must_not_happen, (
        f"call 1 of {total_n} has empty must_not_happen — AI is free to "
        f"close on the first call, which collapses the multi-call product"
    )
    joined = " ".join(step.must_not_happen).lower()
    # Russian wording for "agree to buy / sign / commit". The exact phrasing
    # may evolve but the semantic must remain.
    assert any(
        kw in joined
        for kw in ("согласиться куп", "согласиться на услуг", "подписать", "соглас")
    ), f"call 1 of {total_n} must_not_happen lacks agreement-block: {step.must_not_happen!r}"


@pytest.mark.parametrize("total_n", [3, 4, 5])
def test_call_2_still_blocks_close(total_n: int):
    """Call 2 of any cycle still must not close — that is reserved for the final call."""
    step = get_arc_step(call_number=2, total_calls=total_n)
    if total_n == 2:  # (defensive — not currently shipped)
        return
    joined = " ".join(step.must_not_happen).lower()
    assert "соглас" in joined or "оконч" in joined or "услуг" in joined, (
        f"call 2 of {total_n}: {step.must_not_happen!r}"
    )


def test_final_call_allows_closing():
    """The final call MUST allow closing — otherwise the cycle never resolves."""
    for total_n in (3, 4, 5):
        step = get_arc_step(call_number=total_n, total_calls=total_n)
        # On the final call, must_not_happen is empty by design — the
        # client can say yes, no, or ask for one more day.
        assert step.must_not_happen == (), (
            f"final call {total_n}/{total_n} has restrictions {step.must_not_happen!r} "
            "— cycle would never resolve"
        )
        assert step.ok_to_happen, "final call must offer at least one closing path"


def test_unknown_total_calls_clamps_safely():
    """For total_calls outside 3..5, we fall back to nearest template, no crash."""
    for total_n in (1, 2, 6, 7, 99):
        for call_n in (1, total_n):
            step = get_arc_step(call_number=call_n, total_calls=total_n)
            assert isinstance(step, CallArcStep)
            assert step.call_number == call_n
            assert step.total_calls == total_n


# ── Test 3: scoring is unaffected by the arc ─────────────────────────────────

def test_stage_tracker_scoring_unchanged_by_arc():
    """build_scoring_details depends on persisted StageState, not on prompt
    assembly. Arc must not touch this path. We exercise it on a state that
    looks like a finished call and assert the output is structurally intact.
    """
    from app.services.stage_tracker import StageState, StageTracker

    state = StageState(
        current_stage=4,
        current_stage_name="presentation",
        stages_completed=[1, 2, 3],
        total_stages=7,
        stage_message_counts={1: 2, 2: 3, 3: 4, 4: 1},
    )
    tracker = StageTracker("sess-arc-scoring", redis=None)
    details = tracker.build_scoring_details(state)

    # Structural pins — these keys are consumed by /results and analytics.
    assert details["final_stage"] == 4
    assert details["final_stage_name"] == "presentation"
    assert details["total_stages"] == 7
    assert details["stages_completed"] == [1, 2, 3]
    assert "stage_message_counts" in details

    # And the output must NOT carry arc-internal fields — keeps the two
    # systems decoupled at the wire boundary.
    forbidden_keys = {"arc_step", "must_not_happen", "internal_goal"}
    assert forbidden_keys.isdisjoint(details.keys()), (
        f"scoring details leaked arc internals: "
        f"{forbidden_keys & set(details.keys())}"
    )


# ── Bonus: settings flag default + idempotency ───────────────────────────────

def test_call_arc_v1_default_off():
    """Default-off rollout — flipping CALL_ARC_V1 must be opt-in per env."""
    from app.config import settings as fresh_settings
    assert fresh_settings.call_arc_v1 is False, (
        "call_arc_v1 default must stay False until pilot validates the new path"
    )


def test_arc_step_is_frozen_dataclass():
    step = get_arc_step(1, 3)
    with pytest.raises(Exception):
        step.client_state = "mutated"  # type: ignore[misc]
