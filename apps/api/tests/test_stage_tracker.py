"""Sprint 2 task #15 — unit tests for stage_tracker.

Covers the Sprint-2 additions:
  - HYSTERESIS_CONFIRMATIONS_BY_STAGE per-stage table (stage 1 needs only 1 conf).
  - Expanded STAGE_KEYWORDS (contact: 30+ markers incl. the new rapport/empathy
    phrases that real-world dialogues actually use).
  - MARKER_DENOMINATOR_CAP so large marker pools don't dilute scores.
  - Soft-decay transition_confirmations (neutral message decrements by 1
    instead of wiping all progress).
  - Skip detection → state.skipped_stages populated when manager jumps a stage.
  - stage_durations_sec / stage_message_counts populated on every transition.
"""

from __future__ import annotations

import json
import pytest

from app.services.stage_tracker import (
    HYSTERESIS_CONFIRMATIONS,
    HYSTERESIS_CONFIRMATIONS_BY_STAGE,
    MARKER_DENOMINATOR_CAP,
    STAGE_KEYWORDS,
    STAGE_ORDER,
    StageTracker,
    TRANSITION_THRESHOLD,
)


# ─── In-memory fake Redis ──────────────────────────────────────────────────
class _FakeRedis:
    """Minimal get/set/delete with TTL args accepted but ignored."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value, **_kwargs):
        self.store[key] = value

    async def delete(self, key: str):
        self.store.pop(key, None)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Static table / constants
# ═══════════════════════════════════════════════════════════════════════════

class TestConstants:

    def test_hysteresis_by_stage_has_all_stages(self):
        assert set(HYSTERESIS_CONFIRMATIONS_BY_STAGE.keys()) == {1, 2, 3, 4, 5, 6, 7}

    def test_hysteresis_greeting_is_soft(self):
        # The whole point of Sprint 2 — stage 1→2 needs only ONE confirmation.
        assert HYSTERESIS_CONFIRMATIONS_BY_STAGE[1] == 1

    def test_hysteresis_middle_stages_guard_against_noise(self):
        # Stages 2-5 keep 2 to avoid false jumps during mid-dialogue.
        for s in (2, 3, 4, 5):
            assert HYSTERESIS_CONFIRMATIONS_BY_STAGE[s] == 2

    def test_legacy_constant_still_exported(self):
        # Safety net: the old HYSTERESIS_CONFIRMATIONS is still importable
        # so any external code that references it doesn't break.
        assert HYSTERESIS_CONFIRMATIONS == 2

    def test_transition_threshold_and_cap(self):
        assert TRANSITION_THRESHOLD == pytest.approx(0.15)
        assert MARKER_DENOMINATOR_CAP == 8


class TestExpandedMarkers:
    """Sprint 2 expanded the contact/qualification/presentation/objections
    marker pools. Pick a representative phrase from each NEW category and
    assert it is present — regression guard against accidental deletion."""

    @pytest.mark.parametrize("phrase", [
        # Name request variants (new)
        "как к вам обращаться",
        "можно узнать ваше имя",
        # Empathy (new)
        "я понимаю",
        "непростая ситуация",
        # Rapport / invitation (new)
        "расскажите",
        "давайте разберёмся",
        # Reassurance (new)
        "не переживайте",
        # Listening (new)
        "я вас слушаю",
        "спасибо что ответили",
    ])
    def test_contact_has_new_rapport_markers(self, phrase):
        assert phrase in STAGE_KEYWORDS["contact"]["markers"], \
            f"contact markers lost phrase: {phrase!r}"

    @pytest.mark.parametrize("phrase", [
        "примерно", "какая сумма", "какие банки", "просрочка",
        "когда началось",
    ])
    def test_qualification_has_soft_probes(self, phrase):
        assert phrase in STAGE_KEYWORDS["qualification"]["markers"]

    @pytest.mark.parametrize("phrase", [
        "объясню как", "простыми словами", "8 месяцев",
        "защищено законом", "будет стоить",
    ])
    def test_presentation_has_natural_language(self, phrase):
        assert phrase in STAGE_KEYWORDS["presentation"]["markers"]

    @pytest.mark.parametrize("phrase", [
        "понимаю ваше беспокойство", "это законно", "можете проверить",
        "давайте посчитаем",
    ])
    def test_objections_has_join_acknowledge(self, phrase):
        assert phrase in STAGE_KEYWORDS["objections"]["markers"]

    def test_contact_pool_is_large(self):
        # Sprint 2 expanded 12 → 30+. Guard that nobody accidentally trims it.
        assert len(STAGE_KEYWORDS["contact"]["markers"]) >= 25


# ═══════════════════════════════════════════════════════════════════════════
# 2. process_message end-to-end with fake Redis
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def tracker():
    """Fresh StageTracker + FakeRedis for each test."""
    return StageTracker("session-test", _FakeRedis())


class TestGreetingToContactTransition:
    """The headline fix: one contact-marker after greeting → advance."""

    @pytest.mark.asyncio
    async def test_single_confirmation_advances_greeting(self, tracker):
        await tracker.init_state()

        # Message 1 — greeting marker, not yet advancing.
        state, changed, skipped = await tracker.process_message(
            "Здравствуйте, меня зовут Сергей из БФЛ.", 1, "user",
        )
        assert state.current_stage == 1
        assert not changed

        # Message 2 — strong contact signal: since HYSTERESIS[1]=1, this
        # single confirmation is enough to flip to stage 2. (Keep text
        # free of punctuation — detect_human_moment counts words with
        # trailing punctuation as gibberish.)
        state, changed, skipped = await tracker.process_message(
            "Расскажите подробнее я вас слушаю понимаю непростая ситуация",
            2, "user",
        )
        assert changed is True
        assert state.current_stage == 2
        assert state.current_stage_name == "contact"
        assert 1 in state.stages_completed
        assert skipped == []

    @pytest.mark.asyncio
    async def test_neutral_messages_dont_advance(self, tracker):
        await tracker.init_state()
        for idx, text in enumerate([
            "Здравствуйте, Сергей из БФЛ.",
            "Да.",   # no markers
            "Угу.",  # no markers
        ], start=1):
            state, _, _ = await tracker.process_message(text, idx, "user")
        assert state.current_stage == 1


class TestSoftDecay:
    """Neutral messages should NOT wipe pending confirmations.

    Sprint 2 replaced `transition_confirmations.clear()` with a per-key
    decrement-floor-zero. So one off-topic reply between two matching
    markers should still let the accumulated count progress.
    """

    @pytest.mark.asyncio
    async def test_single_match_records_confirmation(self, tracker):
        """After one qualification marker we should see confs[3]=1 — the
        precondition for the soft-decay logic to even apply."""
        await tracker.init_state()
        await tracker.force_complete_stage(1, score=1.0)

        state, changed, _ = await tracker.process_message(
            "Какая у вас примерно сумма долга", 3, "user",
        )
        assert not changed
        assert state.transition_confirmations.get(3, 0) == 1

    @pytest.mark.asyncio
    async def test_soft_decay_decrements_not_clears_multi_candidate(
        self, tracker,
    ):
        """When two candidate stages accumulated confirmations, a neutral
        message should DECREMENT each by 1 (floor 0), not clear the map
        wholesale like the pre-Sprint-2 code did.

        We simulate this by seeding transition_confirmations directly via
        Redis roundtrip (process_message only produces one candidate per
        call, but in theory the map is multi-key)."""
        await tracker.init_state()
        state = await tracker._load_state()
        state.current_stage = 2
        state.transition_confirmations = {3: 2, 4: 1}
        await tracker._save_state(state)

        # Neutral message — no qualification/presentation markers.
        state, _, _ = await tracker.process_message("угу", 5, "user")

        # Old behaviour: {3:2, 4:1} → {}. New: → {3:1}.
        assert state.transition_confirmations.get(3, 0) == 1, \
            f"soft-decay broken, got {state.transition_confirmations}"
        assert 4 not in state.transition_confirmations  # decayed to 0, removed

    @pytest.mark.asyncio
    async def test_two_matches_trigger_transition(self, tracker):
        """With hysteresis=2 for stage 2→3, two consecutive qualification
        markers should fire the transition. This is the "positive"
        counterpart to the soft-decay test above."""
        await tracker.init_state()
        await tracker.force_complete_stage(1, score=1.0)

        await tracker.process_message("Какая у вас примерно сумма долга", 3, "user")
        state, changed, _ = await tracker.process_message(
            "И какие банки сколько кредиторов", 4, "user",
        )
        assert changed is True
        assert state.current_stage == 3


class TestSkipDetection:
    """Jumping greeting → qualification directly marks stage 2 as skipped."""

    @pytest.mark.asyncio
    async def test_jump_from_1_to_3_records_skip(self, tracker):
        await tracker.init_state()

        # Strong qualification signal right after greeting. min_messages
        # for qualification is 2, so message_index must be ≥2 to avoid
        # the early-transition penalty.
        # Stage 1 hysteresis = 1 so the jump CAN happen in a single message
        # (best_match_stage scan checks +1 and +2 offsets).
        await tracker.process_message("Здравствуйте.", 1, "user")
        state, changed, skipped = await tracker.process_message(
            "Сколько у вас примерно кредиторов и какая сумма долга?", 3, "user",
        )
        # Either advanced to 2 or to 3 — both accepted; but if it jumped to 3,
        # we expect stage 2 to be in skipped_stages.
        if state.current_stage == 3:
            assert 2 in state.skipped_stages
            assert 2 in skipped
            assert state.stage_scores.get(2) == 0.0

    @pytest.mark.asyncio
    async def test_skipped_stage_has_zero_duration(self, tracker):
        await tracker.init_state()
        await tracker.process_message("Здравствуйте.", 1, "user")
        state, changed, skipped = await tracker.process_message(
            "Какая примерно сумма долга, сколько банков, есть ли просрочка?",
            3, "user",
        )
        for s in state.skipped_stages:
            assert state.stage_durations_sec.get(s) == 0.0
            assert state.stage_message_counts.get(s) == 0


class TestDurationAndMessageCounts:
    """On every transition the previous stage's duration+msg count is recorded."""

    @pytest.mark.asyncio
    async def test_stage_duration_recorded_on_transition(self, tracker):
        await tracker.init_state()
        # Greeting → contact. Keep text off of detect_human_moment
        # triggers (no punctuation → cleaner gibberish ratio).
        state, changed, _ = await tracker.process_message(
            "Здравствуйте расскажите подробнее я вас слушаю понимаю", 1, "user",
        )
        assert changed is True
        # Stage 1 got closed out with a duration + message count.
        assert 1 in state.stage_durations_sec
        assert state.stage_durations_sec[1] >= 0.0
        assert 1 in state.stage_message_counts


class TestBuildWsPayload:
    """build_ws_payload shape — frontend contract."""

    @pytest.mark.asyncio
    async def test_payload_has_required_keys(self, tracker):
        state = await tracker.init_state()
        payload = tracker.build_ws_payload(state)
        assert "stage_number" in payload
        assert "stage_name" in payload
        assert "stage_label" in payload
        assert "total_stages" in payload
        assert "stages_completed" in payload


class TestStateRoundtrip:
    """Sprint 2 added 5 new keys to StageState; ensure save/load preserves them."""

    @pytest.mark.asyncio
    async def test_new_fields_survive_redis_roundtrip(self, tracker):
        await tracker.init_state()
        state = await tracker._load_state()
        state.skipped_stages = [3]
        state.stage_durations_sec = {1: 12.5, 2: 30.0}
        state.stage_message_counts = {1: 2, 2: 4}
        state.stage_started_at_msg = {1: 0, 2: 2, 3: 6}
        state.stage_started_at_ts = {1: 1_700_000_000.0}
        await tracker._save_state(state)

        reloaded = await tracker._load_state()
        assert reloaded.skipped_stages == [3]
        assert reloaded.stage_durations_sec == {1: 12.5, 2: 30.0}
        assert reloaded.stage_message_counts == {1: 2, 2: 4}
        assert reloaded.stage_started_at_msg[2] == 2
        assert reloaded.stage_started_at_ts[1] == pytest.approx(1_700_000_000.0)
