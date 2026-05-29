"""Race-resolution test for PvP `_advance_round` (CLAUDE.md §4.1).

Audit fix BUG#3 (2026-05-29): both the round timer
(`_finish_round_after_timeout`) and the message-limit trigger
(`_maybe_finish_round`) can call `_advance_round` for the SAME round
concurrently. The `completed`/`round` guards at the top of the function do
NOT stop the second caller, because the original code released
`_duel_sessions_lock` before the slow `judge_round` LLM call without
marking the round as "advancing". Result: the round was judged twice —
duplicate `judge.score` emitted to players AND double LLM spend.

The fix claims the round under the lock (`session["_advancing_round"] ==
round_number`) so the second concurrent caller bails immediately.

Unlike the exam/KPI row-lock fixes, this race is on **in-memory** state
guarded by an `asyncio.Lock`, so it reproduces deterministically with
`asyncio.gather` and needs no database — the lock serialises the claim,
so exactly one caller proceeds post-fix (two proceed pre-fix).
"""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.ws import pvp


def _make_score(**over):
    """A judge score namespace with every attribute `_advance_round` reads."""
    base = dict(
        selling_score=30,
        acting_score=20,
        legal_accuracy=15,
        flags=[],
        legal_details={},
        coaching_tip="tip",
        ideal_reply="ideal",
        key_articles=[],
        degraded=False,
        degraded_reason=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


class _FakeAsyncSession:
    """Minimal async context manager standing in for `async_session()`.

    `judge_round` is mocked, so the yielded object is never actually used —
    we only need `async with async_session() as db:` to work.
    """

    async def __aenter__(self):
        return AsyncMock()

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_concurrent_advance_round_judges_once():
    """Two parallel `_advance_round` calls for the same round must judge it
    exactly once (BUG#3). Pre-fix this asserted-once call count was 2."""
    duel_id = uuid.uuid4()
    p1 = uuid.uuid4()
    p2 = uuid.uuid4()

    # round_number == 2 routes to `_finalize_duel` (mocked) instead of the
    # round-1 swap path, keeping the test focused on the claim guard.
    pvp._duel_sessions[duel_id] = {
        "completed": False,
        "round": 2,
        "player1_id": p1,
        "player2_id": p2,
        "player_names": {p1: "Alice", p2: "Bob"},
        "archetype": "skeptic",
        "difficulty": "medium",
        "round_started_at": None,  # skips the ARENA_ROUND_DURATION metric
        "is_pve": False,
    }

    judge_mock = AsyncMock(return_value=(_make_score(), _make_score()))

    try:
        with patch.object(pvp, "judge_round", judge_mock), \
             patch.object(pvp, "async_session", lambda: _FakeAsyncSession()), \
             patch.object(pvp, "_send_to_user", new=AsyncMock()), \
             patch.object(pvp, "_finalize_duel", new=AsyncMock()) as finalize_mock:
            # Genuinely parallel — not sequential awaits (CLAUDE.md §4.1).
            await asyncio.gather(
                pvp._advance_round(duel_id),
                pvp._advance_round(duel_id),
            )

        # The whole point of the claim guard: the round is judged ONCE even
        # though two callers raced in. Pre-fix code judged it twice.
        assert judge_mock.await_count == 1, (
            f"round judged {judge_mock.await_count}× — claim guard failed "
            "(BUG#3 regression: duplicate judging + double LLM spend)"
        )
        assert finalize_mock.await_count == 1

        # The round was claimed for this round number.
        assert pvp._duel_sessions[duel_id]["_advancing_round"] == 2
    finally:
        pvp._duel_sessions.pop(duel_id, None)


@pytest.mark.asyncio
async def test_advance_round_progression_not_blocked_across_rounds():
    """The claim flag is per-round (value == round_number), so advancing a
    LATER round must not be blocked by an earlier round's claim."""
    duel_id = uuid.uuid4()
    p1 = uuid.uuid4()
    p2 = uuid.uuid4()

    pvp._duel_sessions[duel_id] = {
        "completed": False,
        "round": 2,
        "player1_id": p1,
        "player2_id": p2,
        "player_names": {},
        "archetype": "skeptic",
        "difficulty": "medium",
        "round_started_at": None,
        "is_pve": False,
        "_advancing_round": 1,  # a PRIOR round was already claimed
    }

    judge_mock = AsyncMock(return_value=(_make_score(), _make_score()))
    try:
        with patch.object(pvp, "judge_round", judge_mock), \
             patch.object(pvp, "async_session", lambda: _FakeAsyncSession()), \
             patch.object(pvp, "_send_to_user", new=AsyncMock()), \
             patch.object(pvp, "_finalize_duel", new=AsyncMock()):
            await pvp._advance_round(duel_id)

        # round 2 != claimed round 1 → must proceed and judge.
        assert judge_mock.await_count == 1
        assert pvp._duel_sessions[duel_id]["_advancing_round"] == 2
    finally:
        pvp._duel_sessions.pop(duel_id, None)
