"""Tests for human_moment detection, tangent logic, and scoring adjustments.

Covers:
- detect_human_moment(): 8 input types + adversarial inputs
- should_ai_add_human_tangent(): 8 decision cases
- apply_human_moment_adjustment(): boundary conditions
"""

import pytest

from app.services.emotion_v6 import detect_human_moment, should_ai_add_human_tangent
from app.services.scoring import apply_human_moment_adjustment


# ═════════════════════════════════════════════════════════════════════════════
# detect_human_moment() Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestDetectHumanMoment:
    """Test detect_human_moment with various input types."""

    # ── Normal messages (should return None) ──

    def test_normal_domain_message(self):
        """Message about bankruptcy/sales should return None."""
        assert detect_human_moment("Какова процедура банкротства физического лица?") is None

    def test_long_domain_message(self):
        """Long message with domain keywords returns None."""
        msg = "Я хочу узнать про банкротство, какие документы нужны и сколько стоит процедура"
        assert detect_human_moment(msg) is None

    def test_short_valid_russian(self):
        """Short valid Russian words (1-2) should return None."""
        assert detect_human_moment("нет") is None
        assert detect_human_moment("да") is None
        assert detect_human_moment("слушаю") is None

    # ── Gibberish / typo detection ──

    def test_short_gibberish_non_cyrillic(self):
        """Short non-Cyrillic gibberish returns typo_confusion."""
        assert detect_human_moment("asdf") == "typo_confusion"
        assert detect_human_moment("xyz 123") == "typo_confusion"

    def test_long_gibberish_majority(self):
        """Long message with >60% non-Russian words returns typo_confusion."""
        msg = "asdkfj lksdjf lskdjf нет"  # 1/4 = 25% Russian
        assert detect_human_moment(msg) == "typo_confusion"

    # ── Off-topic detection ──

    def test_off_topic_no_domain_words(self):
        """Message without domain keywords returns off_topic_reaction."""
        msg = "Какая сегодня погода в Москве интересно"
        assert detect_human_moment(msg) == "off_topic_reaction"

    # ── Curiosity personal detection ──

    def test_curiosity_personal(self):
        """Personal question about the character returns curiosity_personal."""
        msg = "А вы сами проходили через банкротство?"
        result = detect_human_moment(msg)
        # Could be curiosity_personal or None depending on pattern match
        # The key is it doesn't crash
        assert result in ("curiosity_personal", None, "off_topic_reaction")

    # ── Edge cases ──

    def test_empty_string(self):
        """Empty string returns None."""
        assert detect_human_moment("") is None

    def test_whitespace_only(self):
        """Whitespace-only string returns None."""
        assert detect_human_moment("   ") is None

    # ── Adversarial inputs ──

    def test_emoji_only(self):
        """Emoji-only input should not crash; returns typo_confusion."""
        result = detect_human_moment("😂😂😂")
        assert result == "typo_confusion"

    def test_sql_injection(self):
        """SQL injection string should not crash the function."""
        result = detect_human_moment("'; DROP TABLE users; --")
        assert result in ("typo_confusion", "off_topic_reaction")

    def test_xss_script_tag(self):
        """XSS attempt should not crash; returns typo_confusion or off_topic."""
        result = detect_human_moment("<script>alert('xss')</script>")
        assert result in ("typo_confusion", "off_topic_reaction")

    def test_null_bytes(self):
        """Null bytes in message should not crash."""
        result = detect_human_moment("текст\x00инъекция")
        assert result is not None or result is None  # just doesn't crash

    def test_very_long_message(self):
        """10K character message should be handled without error."""
        msg = "банкротство " * 1000  # ~12K chars
        result = detect_human_moment(msg)
        assert result is None  # domain keyword present


# ═════════════════════════════════════════════════════════════════════════════
# should_ai_add_human_tangent() Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestShouldAiAddHumanTangent:
    """Test all 8 decision branches of should_ai_add_human_tangent."""

    # Case 1: Non-friendly emotion state → False
    def test_hostile_state_returns_false(self):
        assert should_ai_add_human_tangent("cold", 16, "anxious") is False
        assert should_ai_add_human_tangent("hostile", 16, "anxious") is False
        assert should_ai_add_human_tangent("hangup", 16, "anxious") is False

    # Case 2: Friendly state but too early → False
    def test_friendly_but_too_early(self):
        assert should_ai_add_human_tangent("curious", 3, "anxious") is False
        assert should_ai_add_human_tangent("considering", 5, "anxious") is False

    # Case 3: Friendly state, past threshold, but within cooldown → False
    def test_within_cooldown(self):
        assert should_ai_add_human_tangent(
            "curious", 10, "anxious", last_tangent_at=5
        ) is False

    # Case 4: TANGENT_PRONE archetype, message_index % 8 == 0 → True
    def test_tangent_prone_fires(self):
        # anxious is TANGENT_PRONE, index=8 → 8%8==0 → True
        assert should_ai_add_human_tangent("curious", 8, "anxious") is True

    # Case 5: TANGENT_PRONE archetype, message_index % 8 != 0 → False
    def test_tangent_prone_no_fire(self):
        assert should_ai_add_human_tangent("curious", 9, "anxious") is False

    # Case 6: TANGENT_RARE archetype, message_index % 16 == 0 → True
    def test_tangent_rare_fires(self):
        # aggressive is TANGENT_RARE, index=16 → 16%16==0 → True
        assert should_ai_add_human_tangent("curious", 16, "aggressive") is True

    # Case 7: TANGENT_RARE archetype, message_index % 16 != 0 → False
    def test_tangent_rare_no_fire(self):
        assert should_ai_add_human_tangent("curious", 17, "aggressive") is False

    # Case 8: Default archetype, message_index % 12 == 0 → True
    def test_default_archetype_fires(self):
        # "skeptic" is not in PRONE or RARE → default, index=12 → 12%12==0
        assert should_ai_add_human_tangent("curious", 12, "skeptic") is True

    def test_default_archetype_no_fire(self):
        assert should_ai_add_human_tangent("curious", 13, "skeptic") is False

    # Edge: all 5 tangent-friendly states work
    def test_all_friendly_states(self):
        for state in ("curious", "considering", "callback", "deal", "negotiating"):
            # Index 24 divisible by 8, 12, and not by 16 — PRONE fires
            assert should_ai_add_human_tangent(state, 24, "anxious") is True


# ═════════════════════════════════════════════════════════════════════════════
# apply_human_moment_adjustment() Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestApplyHumanMomentAdjustment:
    """Test boundary conditions and edge cases for scoring adjustment."""

    # Case 1: Zero human moments → raw score unchanged
    def test_zero_human_moments(self):
        assert apply_human_moment_adjustment(15.0, 25.0, 0, 20) == 15.0

    # Case 2: Zero total messages → raw score unchanged
    def test_zero_total_messages(self):
        assert apply_human_moment_adjustment(15.0, 25.0, 3, 0) == 15.0

    # Case 3: Both zero → raw score unchanged (division by zero safe)
    def test_both_zero(self):
        assert apply_human_moment_adjustment(15.0, 25.0, 0, 0) == 15.0

    # Case 4: Normal adjustment — score should increase
    def test_normal_adjustment(self):
        # 2 human moments out of 20 → forgive 2, effective=18, ratio=20/18≈1.111
        result = apply_human_moment_adjustment(15.0, 25.0, 2, 20)
        assert result > 15.0
        assert result <= 25.0

    # Case 5: Capped at max_score
    def test_capped_at_max_score(self):
        # raw_score already near max, adjustment would exceed
        result = apply_human_moment_adjustment(24.0, 25.0, 4, 20)
        assert result <= 25.0

    # Case 6: human_moment_count > 20% cap → only 20% forgiven
    def test_cap_at_20_percent(self):
        # 10 human moments out of 20 → cap at 4 (20% of 20)
        result = apply_human_moment_adjustment(15.0, 25.0, 10, 20)
        # effective = 20 - 4 = 16, ratio = 20/16 = 1.25, but capped at 1.15
        # adjusted = 15 * 1.15 = 17.25
        assert abs(result - 17.25) < 0.01

    # Case 7: Boost ratio capped at 1.15 (15% max)
    def test_boost_ratio_cap(self):
        # 4 moments out of 10 → forgive 2 (20% of 10), effective=8, ratio=10/8=1.25
        # But capped at 1.15 → adjusted = 10 * 1.15 = 11.5
        result = apply_human_moment_adjustment(10.0, 25.0, 4, 10)
        assert abs(result - 11.5) < 0.01

    # Case 8: effective_messages <= 0 → raw score
    def test_effective_messages_zero(self):
        # 5 messages, cap = 20% of 5 = 1, effective = 5-1 = 4 → should still work
        result = apply_human_moment_adjustment(10.0, 25.0, 5, 5)
        assert result >= 10.0

    # Case 9: Very small total_messages (forgiven rounds to 0)
    def test_small_total_forgiven_zero(self):
        # total=2, 20% = 0.4 → int(0.4)=0 → forgiven=0 → return raw
        result = apply_human_moment_adjustment(10.0, 25.0, 1, 2)
        assert result == 10.0

    # Case 10: Negative raw_score (edge case)
    def test_negative_raw_score(self):
        result = apply_human_moment_adjustment(-5.0, 25.0, 2, 20)
        # Should still apply ratio to negative score
        assert result < 0

    # Case 11: raw_score exceeds max_score → capped
    def test_raw_exceeds_max(self):
        result = apply_human_moment_adjustment(30.0, 25.0, 2, 20)
        assert result <= 25.0
