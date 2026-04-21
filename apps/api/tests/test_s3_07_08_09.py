"""Tests for S3-07, S3-08, S3-09.

S3-07: Scoring L3/L8 sub-score normalization to unified [0,1] scale
S3-08: Anti-cheat sliding window (last 5 messages) + latency combo
S3-09: Stage Tracker hysteresis (threshold 0.25 + 3-msg confirmation)
"""

import inspect
import uuid

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# S3-07a: L3 sub-scores normalized to [0,1]
# ═══════════════════════════════════════════════════════════════════════════


class TestS307aL3Normalization:
    def test_empathy_score_range(self):
        """L3 empathy_score must be in [0, 1], not [0, 3.75]."""
        from app.services.scoring import _score_communication
        _, details = _score_communication(["Я понимаю ваши чувства, это важно"])
        assert 0 <= details["empathy_score"] <= 1.0

    def test_listening_score_range(self):
        from app.services.scoring import _score_communication
        _, details = _score_communication(["Привет", "Как дела"])
        assert 0 <= details["listening_score"] <= 1.0

    def test_pace_score_range(self):
        from app.services.scoring import _score_communication
        _, details = _score_communication(["Сообщение 1", "Сообщение 2", "Сообщение 3"])
        assert 0 <= details["pace_score"] <= 1.0

    def test_control_score_range(self):
        from app.services.scoring import _score_communication
        _, details = _score_communication(["Здравствуйте, спасибо за звонок"])
        assert 0 <= details["control_score"] <= 1.0

    def test_max_empathy_is_one(self):
        """Empathy found → score should be 1.0 (5/5)."""
        from app.services.scoring import _score_communication
        _, details = _score_communication(["Я вас понимаю, это неприятно"])
        assert details["empathy_score"] == 1.0

    def test_min_empathy_is_point_two(self):
        """No empathy → score should be 0.2 (1/5)."""
        from app.services.scoring import _score_communication
        _, details = _score_communication(["Просто текст без эмпатии"])
        assert details["empathy_score"] == 0.2

    def test_no_v3_rescale_in_subscores(self):
        """Sub-scores must NOT contain V3_RESCALE values (3.75 etc)."""
        from app.services.scoring import _score_communication
        _, details = _score_communication(["Здравствуйте, понимаю ваши чувства, спасибо"])
        for key in ("empathy_score", "listening_score", "pace_score", "control_score"):
            assert details[key] <= 1.0, f"{key}={details[key]} exceeds 1.0"


# ═══════════════════════════════════════════════════════════════════════════
# S3-07b: L8 sub-scores normalized to [0,1]
# ═══════════════════════════════════════════════════════════════════════════


class TestS307bL8Normalization:
    def test_patience_score_range(self):
        """L8 patience_score must be in [0, 1], not [0, 5]."""
        from app.services.scoring import _score_human_factor
        _, details = _score_human_factor(
            ["Я вас слушаю"], ["Клиент текст"], [], None,
        )
        assert 0 <= details["patience_score"] <= 1.0

    def test_empathy_check_score_range(self):
        from app.services.scoring import _score_human_factor
        _, details = _score_human_factor(
            ["Текст"], ["Клиент"], [{"state": "cold"}], None,
        )
        assert 0 <= details["empathy_check_score"] <= 1.0

    def test_composure_score_range(self):
        from app.services.scoring import _score_human_factor
        _, details = _score_human_factor(
            ["Текст"], ["Клиент"], [], None,
        )
        assert 0 <= details["composure_score"] <= 1.0

    def test_warmth_score_exists(self):
        """warmth_score must now be populated (was missing before S3-07)."""
        from app.services.scoring import _score_human_factor
        _, details = _score_human_factor(
            ["Текст"], ["Клиент"], [], None,
        )
        assert "warmth_score" in details
        assert 0 <= details["warmth_score"] <= 1.0

    def test_l3_l8_same_scale(self):
        """L3 empathy and L8 patience must both be [0,1] — same scale."""
        from app.services.scoring import _score_communication, _score_human_factor
        _, l3 = _score_communication(["Я вас понимаю"])
        _, l8 = _score_human_factor(["Спокойно"], ["Грубость!"], [{"state": "hostile"}], None)
        # Both must be in [0,1] — the whole point of S3-07
        assert l3["empathy_score"] <= 1.0
        assert l8["patience_score"] <= 1.0


# ═══════════════════════════════════════════════════════════════════════════
# S3-07c: Skill radar uses normalized scores correctly
# ═══════════════════════════════════════════════════════════════════════════


class TestS307cSkillRadar:
    def test_skill_radar_no_l3_sub_max(self):
        """skill_radar must NOT use _L3_SUB_MAX (removed in S3-07)."""
        from app.services.scoring import ScoreBreakdown
        source = inspect.getsource(ScoreBreakdown.skill_radar.fget)
        assert "_L3_SUB_MAX" not in source, \
            "_L3_SUB_MAX should be removed — sub-scores are now [0,1]"

    def test_skill_radar_no_l8_sub_max(self):
        """skill_radar must NOT use _L8_SUB_MAX (removed in S3-07)."""
        from app.services.scoring import ScoreBreakdown
        source = inspect.getsource(ScoreBreakdown.skill_radar.fget)
        assert "_L8_SUB_MAX" not in source, \
            "_L8_SUB_MAX should be removed — sub-scores are now [0,1]"

    def test_analytics_no_old_max_values(self):
        """analytics.py must not use old 3.75/5.0 max for L3/L8 sub-scores."""
        import pathlib
        source = pathlib.Path(__file__).parent.parent / "app" / "services" / "analytics.py"
        content = source.read_text()
        # Should not see _norm(xxx, 3.75) or _norm(xxx, 5) for sub-scores
        # (L4 and other layer scores still use _norm)
        lines = content.split("\n")
        for line in lines:
            if "composure" in line and "_norm" in line and "3.75" in line:
                pytest.fail(f"analytics.py still uses old max for composure: {line.strip()}")
            if "patience" in line and "_norm" in line and "5" in line:
                pytest.fail(f"analytics.py still uses old max for patience: {line.strip()}")


# ═══════════════════════════════════════════════════════════════════════════
# S3-08a: Anti-cheat sliding window
# ═══════════════════════════════════════════════════════════════════════════


class TestS308aSlidingWindow:
    def test_sliding_window_constant(self):
        from app.services.anti_cheat import SLIDING_WINDOW_SIZE
        assert SLIDING_WINDOW_SIZE == 5

    def test_sliding_window_in_check_behavioral(self):
        """check_behavioral must use sliding window, not all-pairs."""
        source = inspect.getsource(
            __import__("app.services.anti_cheat", fromlist=["check_behavioral"]).check_behavioral
        )
        assert "SLIDING_WINDOW_SIZE" in source
        assert "window_hits" in source
        assert "window_checks" in source

    def test_alternating_pattern_detected(self):
        """A,B,A,B pattern must be caught by sliding window."""
        from app.services.anti_cheat import check_behavioral
        uid = uuid.uuid4()
        msgs = []
        for i in range(10):
            text = "Привет клиент как дела расскажите подробнее" if i % 2 == 0 else "Да конечно я вас понимаю давайте обсудим"
            msgs.append({"sender_id": str(uid), "text": text})

        result = check_behavioral(msgs, uid)
        # A,B,A,B with window=5: A at i=0 matches A at i=2,4; B at i=1 matches B at i=3,5
        assert result.details["window_hits"] > 0

    def test_unique_messages_not_flagged(self):
        """All unique messages should not trigger similarity flag."""
        from app.services.anti_cheat import check_behavioral
        uid = uuid.uuid4()
        msgs = [
            {"sender_id": str(uid), "text": f"Уникальное сообщение номер {i} с разным содержимым"}
            for i in range(8)
        ]
        result = check_behavioral(msgs, uid)
        assert result.details["window_hits"] == 0

    def test_insufficient_messages_returns_clean(self):
        from app.services.anti_cheat import check_behavioral
        uid = uuid.uuid4()
        msgs = [{"sender_id": str(uid), "text": "hi"}, {"sender_id": str(uid), "text": "ok"}]
        result = check_behavioral(msgs, uid)
        assert result.score == 0.0
        assert result.flagged is False


# ═══════════════════════════════════════════════════════════════════════════
# S3-08b: Latency + response length combo
# ═══════════════════════════════════════════════════════════════════════════


class TestS308bLatencyCombo:
    def test_latency_combo_in_source(self):
        """check_behavioral must check latency + response length combo."""
        source = inspect.getsource(
            __import__("app.services.anti_cheat", fromlist=["check_behavioral"]).check_behavioral
        )
        assert "latency_ms" in source or "response_time_ms" in source
        assert "fast_long_responses" in source

    def test_fast_long_responses_flagged(self):
        """Fast responses (< 3s) with long text (> 50 words) should add anomaly."""
        from app.services.anti_cheat import check_behavioral
        uid = uuid.uuid4()
        long_text = " ".join(["слово"] * 60)
        msgs = [
            {"sender_id": str(uid), "text": long_text, "latency_ms": 1500},
            {"sender_id": str(uid), "text": long_text + " другое", "latency_ms": 2000},
            {"sender_id": str(uid), "text": long_text + " третье", "latency_ms": 1800},
        ]
        result = check_behavioral(msgs, uid)
        assert any("fast_long" in f for f in result.details.get("flags", []))

    def test_slow_responses_not_flagged_for_latency(self):
        """Slow responses should not trigger latency flag."""
        from app.services.anti_cheat import check_behavioral
        uid = uuid.uuid4()
        long_text = " ".join(["слово"] * 60)
        msgs = [
            {"sender_id": str(uid), "text": f"{long_text} {i}", "latency_ms": 10000}
            for i in range(5)
        ]
        result = check_behavioral(msgs, uid)
        assert not any("fast_long" in f for f in result.details.get("flags", []))


# ═══════════════════════════════════════════════════════════════════════════
# S3-09a: Stage Tracker threshold
# ═══════════════════════════════════════════════════════════════════════════


class TestS309aThreshold:
    def test_transition_threshold_raised(self):
        from app.services.stage_tracker import TRANSITION_THRESHOLD
        assert TRANSITION_THRESHOLD == 0.25, \
            f"TRANSITION_THRESHOLD should be 0.25, got {TRANSITION_THRESHOLD}"

    def test_hysteresis_confirmations_count(self):
        from app.services.stage_tracker import HYSTERESIS_CONFIRMATIONS
        assert HYSTERESIS_CONFIRMATIONS == 3


# ═══════════════════════════════════════════════════════════════════════════
# S3-09b: StageState has transition_confirmations
# ═══════════════════════════════════════════════════════════════════════════


class TestS309bStageState:
    def test_stage_state_has_confirmations(self):
        from app.services.stage_tracker import StageState
        state = StageState()
        assert hasattr(state, "transition_confirmations")
        assert state.transition_confirmations == {}

    def test_state_serialization_includes_tc(self):
        """_save_state must persist transition_confirmations."""
        source = inspect.getsource(
            __import__("app.services.stage_tracker", fromlist=["StageTracker"]).StageTracker._save_state
        )
        assert '"tc"' in source

    def test_state_deserialization_includes_tc(self):
        """_load_state must restore transition_confirmations."""
        source = inspect.getsource(
            __import__("app.services.stage_tracker", fromlist=["StageTracker"]).StageTracker._load_state
        )
        assert '"tc"' in source or "'tc'" in source
        assert "transition_confirmations" in source


# ═══════════════════════════════════════════════════════════════════════════
# S3-09c: Hysteresis in process_message
# ═══════════════════════════════════════════════════════════════════════════


class TestS309cHysteresis:
    def test_process_message_uses_hysteresis(self):
        """process_message must check HYSTERESIS_CONFIRMATIONS before transitioning."""
        source = inspect.getsource(
            __import__("app.services.stage_tracker", fromlist=["StageTracker"]).StageTracker.process_message
        )
        assert "HYSTERESIS_CONFIRMATIONS" in source
        assert "transition_confirmations" in source

    def test_single_match_does_not_transition(self):
        """A single keyword match must NOT cause stage transition (hysteresis)."""
        source = inspect.getsource(
            __import__("app.services.stage_tracker", fromlist=["StageTracker"]).StageTracker.process_message
        )
        # Must accumulate confirmations before transitioning
        assert "transition_confirmations.get" in source or "transition_confirmations[" in source

    def test_reset_on_no_match(self):
        """If no match in a message, confirmation counters must reset."""
        source = inspect.getsource(
            __import__("app.services.stage_tracker", fromlist=["StageTracker"]).StageTracker.process_message
        )
        assert "clear()" in source

    def test_clear_after_transition(self):
        """After successful transition, confirmations must be cleared."""
        source = inspect.getsource(
            __import__("app.services.stage_tracker", fromlist=["StageTracker"]).StageTracker.process_message
        )
        # There should be a clear() call inside the transition block
        # Count clear() calls — should be at least 2 (on no-match + on transition)
        clear_count = source.count(".clear()")
        assert clear_count >= 2, f"Expected ≥2 .clear() calls, found {clear_count}"


# ═══════════════════════════════════════════════════════════════════════════
# S3-09d: Stage keywords coverage
# ═══════════════════════════════════════════════════════════════════════════


class TestS309dKeywords:
    def test_all_7_stages_have_keywords(self):
        from app.services.stage_tracker import STAGE_KEYWORDS, STAGE_ORDER
        for stage in STAGE_ORDER:
            assert stage in STAGE_KEYWORDS, f"Missing keywords for stage: {stage}"
            assert len(STAGE_KEYWORDS[stage]["markers"]) >= 5, \
                f"Stage {stage} has too few markers ({len(STAGE_KEYWORDS[stage]['markers'])})"

    def test_stage_order_is_7(self):
        from app.services.stage_tracker import STAGE_ORDER
        assert len(STAGE_ORDER) == 7


# ═══════════════════════════════════════════════════════════════════════════
# Cross-cutting: S3-07/08/09 integration
# ═══════════════════════════════════════════════════════════════════════════


class TestCrossCutting:
    def test_normalize_function_exists(self):
        from app.services.scoring import _normalize
        assert _normalize(5.0, 10.0) == 0.5
        assert _normalize(0.0, 10.0) == 0.0
        assert _normalize(10.0, 10.0) == 1.0
        assert _normalize(15.0, 10.0) == 1.0  # Clamped

    def test_jaccard_similarity_symmetric(self):
        from app.services.anti_cheat import _jaccard_similarity
        assert _jaccard_similarity("a b c", "a b c") == 1.0
        assert _jaccard_similarity("a b c", "d e f") == 0.0
        sim1 = _jaccard_similarity("a b c d", "c d e f")
        sim2 = _jaccard_similarity("c d e f", "a b c d")
        assert sim1 == sim2  # Symmetric

    def test_scoring_total_not_affected(self):
        """S3-07 changes sub-score storage, NOT the total L3/L8 scores."""
        from app.services.scoring import _score_communication
        total, _ = _score_communication(["Здравствуйте, я вас понимаю, спасибо"])
        # L3 total is still 0-15 (after V3_RESCALE)
        assert 0 <= total <= 15.0

    def test_l8_total_not_affected(self):
        from app.services.scoring import _score_human_factor
        total, _ = _score_human_factor(["Спокойно"], ["Текст"], [], None)
        # L8 total is still 0-15
        assert 0 <= total <= 15.0
