"""Tests for the mode-switch coaching detector (BUG 3 fix).

Two layers:
  * pure ``classify_turn`` covers the keyword + heuristic logic
  * ``evaluate_mode_switch`` covers the rolling-window state machine
    against an in-memory fake Redis (no real Redis required).
"""
from __future__ import annotations

import json

import pytest

from app.services.coach_mode_switch import (
    MIN_OFF_TASK_BEFORE_SWITCH,
    classify_turn,
    evaluate_mode_switch,
)


# ── classify_turn ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text, expected",
    [
        # On-task: clear domain keyword.
        ("у меня долг 800 тысяч, что делать?", "on_task"),
        ("расскажите про 127-ФЗ", "on_task"),
        ("суд назначен на следующей неделе", "on_task"),
        ("банкротство — это законно?", "on_task"),
        # Off-task: trolling markers.
        ("я курьер пиццы, открывайте", "off_task"),
        ("ха-ха ну вы и шутник", "off_task"),
        ("идиот, отстань", "off_task"),
        # Off-task: heuristics.
        ("ок", "off_task"),                      # too short
        ("?!?!?!?", "off_task"),                 # repeated punctuation
        ("🤡🤡🤡🤡 чё", "off_task"),              # emoji density
        # Unknown: neutral text without strong signal.
        ("ну да", "unknown"),
        ("давайте уточним", "unknown"),
        ("хорошо, я слушаю", "unknown"),
        # Mixed: domain keyword wins over off-domain marker.
        ("ха-ха, вообще-то у меня долг 500к", "on_task"),
        # Empty / whitespace.
        ("", "unknown"),
        ("   ", "unknown"),
    ],
)
def test_classify_turn(text: str, expected: str) -> None:
    assert classify_turn(text) == expected


# ── evaluate_mode_switch ────────────────────────────────────────────────────


class _FakeRedis:
    """Bare-minimum stand-in: get/setex storing JSON strings in a dict."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        # Validate stored value is valid JSON — guards against accidental
        # serialisation regressions in _SwitchState.to_json().
        json.loads(value)
        self.store[key] = value


@pytest.mark.asyncio
async def test_no_fire_when_only_one_off_task() -> None:
    r = _FakeRedis()
    sid = "sess-1"
    await evaluate_mode_switch(r, sid, "ха-ха")              # off_task
    tip = await evaluate_mode_switch(r, sid, "у меня долг") # on_task
    # Only 1 off_task in prior < threshold (2) → no fire.
    assert tip is None


@pytest.mark.asyncio
async def test_fires_after_two_off_task_then_on_task() -> None:
    r = _FakeRedis()
    sid = "sess-2"
    await evaluate_mode_switch(r, sid, "я курьер пиццы")    # off_task #1
    await evaluate_mode_switch(r, sid, "Г-69 квартира")      # off_task #2 (short, no domain)
    tip = await evaluate_mode_switch(r, sid, "слушайте, у меня долг 800к, что делать?")
    assert tip is not None
    payload = tip.to_payload()
    assert payload["type"] == "mode_switch_to_on_task"
    assert payload["severity"] == "info"
    assert "перешёл" in payload["hint"] or "переход" in payload["hint"]


@pytest.mark.asyncio
async def test_fires_only_once_per_session() -> None:
    r = _FakeRedis()
    sid = "sess-3"
    await evaluate_mode_switch(r, sid, "ха-ха")
    await evaluate_mode_switch(r, sid, "🤡🤡🤡🤡 ха")
    tip1 = await evaluate_mode_switch(r, sid, "у меня долг и кредит")
    assert tip1 is not None
    # Round-trip another off→on cycle — must NOT fire again.
    await evaluate_mode_switch(r, sid, "пицца где?")
    await evaluate_mode_switch(r, sid, "иди отсюда")
    tip2 = await evaluate_mode_switch(r, sid, "так, про банкротство")
    assert tip2 is None