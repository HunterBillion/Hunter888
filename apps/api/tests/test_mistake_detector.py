"""P1 (2026-04-29) Coaching mistake detector — rule-by-rule contracts.

Each rule has its own block. Tests use a fake redis (an in-memory dict
async-shim) so the detector exercises its full Redis read/write path
without touching a real instance.

Contracts pinned here:

  • flag default OFF
  • monologue: warn over 200 chars no question, alert over 350
  • no_open_question: silent first 2 turns, fires on turn 3 if no "?"
  • early_pricing: fires only when stage < 4 AND text matches pricing
  • repeated_argument: fires after 3 near-duplicate manager phrases
  • talk_ratio_high: fires once total chars >= 200 AND user/total > 0.7
  • re-emit suppressed within MIN_REEMIT_S
  • assistant turn never produces a mistake
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.services.mistake_detector import (
    MIN_REEMIT_S,
    MONOLOGUE_THRESHOLD,
    MONOLOGUE_THRESHOLD_ALERT,
    Mistake,
    evaluate_user_turn,
    record_assistant_turn,
    reset,
)


class _FakeRedis:
    """Minimal async stub — enough for the detector's get/set/delete with TTL."""

    def __init__(self):
        self._data: dict[str, str] = {}

    async def get(self, key):
        return self._data.get(key)

    async def set(self, key, value, ex=None):
        self._data[key] = value

    async def delete(self, key):
        self._data.pop(key, None)


@pytest.fixture
def redis():
    return _FakeRedis()


# ── Default flag ─────────────────────────────────────────────────────────────


def test_flag_default_off():
    from app.config import settings
    assert settings.coaching_mistake_detector_v1 is False, (
        "P1 detector must default to OFF until pilot validates"
    )


# ── monologue ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_monologue_warn_at_threshold(redis):
    text = "ну вот мы предлагаем процедуру банкротства " * 8  # ~330 chars no ?
    assert MONOLOGUE_THRESHOLD <= len(text) < MONOLOGUE_THRESHOLD_ALERT
    fired = await evaluate_user_turn(redis, "s1", text, current_stage=1)
    types = {m.type for m in fired}
    assert "monologue" in types
    m = next(m for m in fired if m.type == "monologue")
    assert m.severity == "warn"


@pytest.mark.asyncio
async def test_monologue_alert_above_high_threshold(redis):
    text = "ну вот мы предлагаем процедуру банкротства физических лиц " * 8  # >350
    assert len(text) >= MONOLOGUE_THRESHOLD_ALERT
    fired = await evaluate_user_turn(redis, "s1", text, current_stage=1)
    m = next(m for m in fired if m.type == "monologue")
    assert m.severity == "alert"


@pytest.mark.asyncio
async def test_monologue_suppressed_when_question_present(redis):
    text = "ну вот мы предлагаем процедуру банкротства " * 8 + " подходит?"
    fired = await evaluate_user_turn(redis, "s1", text, current_stage=1)
    assert "monologue" not in {m.type for m in fired}


# ── no_open_question ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_open_question_silent_first_two_turns(redis):
    fired1 = await evaluate_user_turn(redis, "s2", "добрый день", current_stage=1)
    fired2 = await evaluate_user_turn(redis, "s2", "у нас есть предложение", current_stage=1)
    assert "no_open_question" not in {m.type for m in fired1}
    assert "no_open_question" not in {m.type for m in fired2}


@pytest.mark.asyncio
async def test_no_open_question_fires_on_turn_3_without_question(redis):
    await evaluate_user_turn(redis, "s2", "добрый день", current_stage=1)
    await evaluate_user_turn(redis, "s2", "у нас есть предложение", current_stage=1)
    fired = await evaluate_user_turn(redis, "s2", "очень хорошее", current_stage=1)
    assert "no_open_question" in {m.type for m in fired}


@pytest.mark.asyncio
async def test_no_open_question_resets_on_open_question(redis):
    # Three turns with an interrogative present → no fire.
    for t in ("здравствуйте", "у вас сейчас есть кредиты?", "понятно"):
        await evaluate_user_turn(redis, "s3", t, current_stage=1)
    # Now bombard with non-questions but within the window — still no fire.
    fired = await evaluate_user_turn(redis, "s3", "понятно очень хорошо", current_stage=1)
    assert "no_open_question" not in {m.type for m in fired}


# ── early_pricing ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_early_pricing_fires_when_stage_below_4(redis):
    fired = await evaluate_user_turn(
        redis, "s4", "у нас цена 50 тысяч за процедуру", current_stage=2,
    )
    assert "early_pricing" in {m.type for m in fired}


@pytest.mark.asyncio
async def test_early_pricing_silent_at_presentation_stage(redis):
    fired = await evaluate_user_turn(
        redis, "s4", "стоимость процедуры 50 тысяч", current_stage=4,
    )
    assert "early_pricing" not in {m.type for m in fired}


@pytest.mark.asyncio
async def test_early_pricing_silent_when_no_pricing_mentioned(redis):
    fired = await evaluate_user_turn(
        redis, "s4", "у нас отличное предложение для вас", current_stage=2,
    )
    assert "early_pricing" not in {m.type for m in fired}


# ── repeated_argument ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_repeated_argument_fires_on_third_repeat(redis):
    line = "у нас процедура банкротства поможет списать долги"
    f1 = await evaluate_user_turn(redis, "s5", line, current_stage=2)
    f2 = await evaluate_user_turn(redis, "s5", line, current_stage=2)
    f3 = await evaluate_user_turn(redis, "s5", line, current_stage=2)
    assert "repeated_argument" not in {m.type for m in f1}
    assert "repeated_argument" not in {m.type for m in f2}
    assert "repeated_argument" in {m.type for m in f3}


@pytest.mark.asyncio
async def test_repeated_argument_ignores_short_acks(redis):
    for _ in range(4):
        fired = await evaluate_user_turn(redis, "s6", "да", current_stage=2)
    assert "repeated_argument" not in {m.type for m in fired}


# ── talk_ratio_high ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_talk_ratio_silent_below_min_volume(redis):
    fired = await evaluate_user_turn(
        redis, "s7", "короткое сообщение менеджера", current_stage=1,
    )
    assert "talk_ratio_high" not in {m.type for m in fired}


@pytest.mark.asyncio
async def test_talk_ratio_fires_when_manager_dominates(redis):
    """As soon as cumulative manager char volume passes the floor and ratio
    is above 0.7, the rule fires exactly once (then re-emit suppression
    keeps it quiet for ``MIN_REEMIT_S``).
    """
    fired_any = False
    for _ in range(8):
        f = await evaluate_user_turn(
            redis, "s8", "ну смотрите я хочу рассказать вам про услугу", current_stage=1,
        )
        if "talk_ratio_high" in {m.type for m in f}:
            fired_any = True
            break
    assert fired_any, "talk_ratio_high never fired despite 70%+ manager volume"


# ── re-emit suppression ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_same_mistake_not_reemitted_within_window(redis):
    # Very long monologue twice in a row — should fire once, not twice.
    text = "вот смотрите мы предлагаем услугу " * 8
    f1 = await evaluate_user_turn(redis, "s9", text, current_stage=1)
    f2 = await evaluate_user_turn(redis, "s9", text, current_stage=1)
    assert "monologue" in {m.type for m in f1}
    assert "monologue" not in {m.type for m in f2}


# ── assistant turn never produces mistakes ───────────────────────────────────


@pytest.mark.asyncio
async def test_assistant_turn_never_produces_mistakes(redis):
    # record_assistant_turn returns nothing. Calling it can't produce events.
    result = await record_assistant_turn(redis, "s10", "привет, я слушаю")
    assert result is None


# ── reset clears state ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reset_clears_state(redis):
    await evaluate_user_turn(redis, "s11", "у нас отличная цена 50 тысяч", current_stage=2)
    await reset(redis, "s11")
    # Repeating same text should fire again as if first turn.
    fired = await evaluate_user_turn(redis, "s11", "у нас отличная цена 50 тысяч", current_stage=2)
    assert "early_pricing" in {m.type for m in fired}


# ── empty input is a no-op ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_text_is_noop(redis):
    fired = await evaluate_user_turn(redis, "s12", "", current_stage=1)
    assert fired == []
    fired_ws = await evaluate_user_turn(redis, "s12", "   \n  ", current_stage=1)
    assert fired_ws == []


# ── payload contract ─────────────────────────────────────────────────────────


def test_mistake_payload_shape():
    m = Mistake(type="monologue", severity="warn", hint="too long", detail={"chars": 250})
    payload = m.to_payload()
    assert payload["type"] == "monologue"
    assert payload["severity"] == "warn"
    assert payload["hint"] == "too long"
    assert payload["detail"] == {"chars": 250}
    assert "at" in payload and isinstance(payload["at"], float)
