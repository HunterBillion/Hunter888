"""Tests for real-time per-message anti-cheat checks."""

import time
import uuid

import pytest

from app.services.anti_cheat_realtime import (
    RealtimeCheckResult,
    check_message,
    cleanup_duel,
    init_player,
    FAST_RESPONSE_MAX_SECONDS,
    WARN_THRESHOLD,
    FLAG_THRESHOLD,
)


@pytest.fixture
def duel_setup():
    """Create a fresh duel with two players."""
    p1 = uuid.uuid4()
    p2 = uuid.uuid4()
    duel = uuid.uuid4()
    init_player(p1, duel)
    init_player(p2, duel)
    yield p1, p2, duel
    # Cleanup
    cleanup_duel(duel)


class TestBasicFlow:
    def test_normal_message_no_flags(self, duel_setup):
        p1, _, duel = duel_setup
        result = check_message(p1, duel, "Здравствуйте, давайте обсудим ваш долг.")
        assert result.warning_score_delta == 0.0
        assert result.flags == []
        assert not result.should_warn
        assert not result.should_flag

    def test_uninitialized_player_safe(self):
        """Unknown player should get empty result, not crash."""
        result = check_message(uuid.uuid4(), uuid.uuid4(), "test")
        assert isinstance(result, RealtimeCheckResult)
        assert result.warning_score_delta == 0.0


class TestFastLongDetection:
    def test_fast_long_response_flagged(self, duel_setup):
        p1, _, duel = duel_setup
        now = time.time()

        # First message sets the timestamp
        check_message(p1, duel, "Привет", timestamp=now)

        # Second message: 60+ words in 2 seconds → should flag
        long_text = " ".join(["слово"] * 60)
        result = check_message(p1, duel, long_text, timestamp=now + 2.0)

        assert result.warning_score_delta > 0
        assert any("fast_long" in f for f in result.flags)

    def test_fast_short_response_ok(self, duel_setup):
        p1, _, duel = duel_setup
        now = time.time()

        check_message(p1, duel, "Привет", timestamp=now)
        # Short message fast is fine
        result = check_message(p1, duel, "Да, конечно", timestamp=now + 1.0)
        assert result.warning_score_delta == 0.0

    def test_slow_long_response_ok(self, duel_setup):
        p1, _, duel = duel_setup
        now = time.time()

        check_message(p1, duel, "Привет", timestamp=now)
        long_text = " ".join(["слово"] * 60)
        # 10 seconds is plenty of time
        result = check_message(p1, duel, long_text, timestamp=now + 10.0)
        assert result.warning_score_delta == 0.0


class TestCopyPasteDetection:
    def test_identical_messages_flagged(self, duel_setup):
        p1, _, duel = duel_setup
        now = time.time()

        text = "Я предлагаю вам рассмотреть процедуру банкротства как выход из ситуации"
        check_message(p1, duel, text, timestamp=now)
        result = check_message(p1, duel, text, timestamp=now + 10.0)

        assert result.warning_score_delta > 0
        assert any("copy_paste" in f for f in result.flags)

    def test_different_messages_ok(self, duel_setup):
        p1, _, duel = duel_setup
        now = time.time()

        check_message(p1, duel, "Давайте обсудим вашу ситуацию с долгами", timestamp=now)
        result = check_message(
            p1, duel,
            "Какая у вас общая сумма задолженности перед кредиторами",
            timestamp=now + 10.0,
        )
        assert result.warning_score_delta == 0.0


class TestRapidFire:
    def test_rapid_long_message_flagged(self, duel_setup):
        p1, _, duel = duel_setup
        now = time.time()

        check_message(p1, duel, "Привет", timestamp=now)
        long_msg = " ".join(["текст"] * 25)  # 25 words > 20
        result = check_message(p1, duel, long_msg, timestamp=now + 1.0)  # < 1.5s

        assert result.warning_score_delta > 0
        assert any("rapid_fire" in f for f in result.flags)


class TestAccumulation:
    def test_warning_threshold(self, duel_setup):
        p1, _, duel = duel_setup
        now = time.time()

        # Spam fast long responses to accumulate score
        warned = False
        for i in range(10):
            long_text = " ".join(["слово"] * 60)
            result = check_message(p1, duel, long_text, timestamp=now + i * 2.0)
            if result.should_warn:
                warned = True
                break

        assert warned, "Should have triggered a warning after repeated violations"

    def test_flag_threshold(self, duel_setup):
        p1, _, duel = duel_setup
        now = time.time()

        flagged = False
        for i in range(15):
            long_text = " ".join(["слово"] * 60)
            result = check_message(p1, duel, long_text, timestamp=now + i * 2.0)
            if result.should_flag:
                flagged = True
                break

        assert flagged, "Should have been flagged after many violations"


class TestCleanup:
    def test_cleanup_returns_signals(self, duel_setup):
        p1, p2, duel = duel_setup
        now = time.time()

        check_message(p1, duel, "Привет", timestamp=now)
        check_message(p2, duel, "Здравствуйте", timestamp=now + 1.0)

        signals = cleanup_duel(duel)
        assert p1 in signals
        assert p2 in signals
        assert signals[p1]["total_messages"] == 1
        assert signals[p2]["total_messages"] == 1

    def test_cleanup_clears_state(self, duel_setup):
        p1, _, duel = duel_setup
        check_message(p1, duel, "test")
        cleanup_duel(duel)

        # After cleanup, player is unknown — should return empty result
        result = check_message(p1, duel, "test2")
        assert result.warning_score_delta == 0.0


class TestPlayerIsolation:
    def test_players_tracked_independently(self, duel_setup):
        p1, p2, duel = duel_setup
        now = time.time()

        # P1 sends copy-paste, P2 sends unique messages
        text = "Я предлагаю вам рассмотреть процедуру банкротства как выход из ситуации"
        check_message(p1, duel, text, timestamp=now)
        r1 = check_message(p1, duel, text, timestamp=now + 10.0)

        check_message(p2, duel, "Мне нужна помощь с долгами", timestamp=now)
        r2 = check_message(p2, duel, "Какие документы потребуются для подачи", timestamp=now + 10.0)

        assert r1.warning_score_delta > 0  # P1 flagged for copy-paste
        assert r2.warning_score_delta == 0.0  # P2 clean
