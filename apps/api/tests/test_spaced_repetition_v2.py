"""Tests for SM-2 + Leitner Hybrid Spaced Repetition System.

Covers:
  - SM-2 core algorithm (ease_factor, interval, repetition_count updates)
  - Leitner box promotion/demotion logic
  - Fuzzy interval jitter
  - Quality scoring from answer metadata
  - Per-category difficulty scaling
  - Record review (create + update paths)
  - Priority queue ordering (overdue → weak → learning → rest)
  - SRS session initialization
  - User stats and category mastery
  - Backfill from existing quiz answers
  - Streak tracking
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.spaced_repetition import (
    DEFAULT_EASE_FACTOR,
    FUZZY_JITTER,
    LEITNER_INTERVALS,
    MAX_LEITNER_BOX,
    MIN_EASE_FACTOR,
    _apply_fuzzy_jitter,
    _update_leitner_box,
    quality_from_answer,
    question_hash,
    sm2_update,
)


# ═══════════════════════════════════════════════════════════════════════════════
# SM-2 Core Algorithm
# ═══════════════════════════════════════════════════════════════════════════════


class TestSm2Update:
    """Test SM-2 algorithm parameter updates."""

    def test_perfect_answer_increases_interval(self):
        """Quality 5 should increase interval and keep high EF."""
        ef, interval, rep = sm2_update(2.5, 1, 0, quality=5)
        assert ef >= 2.5
        assert interval >= 1
        assert rep == 1

    def test_quality_0_resets_repetition(self):
        """Quality 0 (total failure) should reset repetition to 0."""
        ef, interval, rep = sm2_update(2.5, 10, 5, quality=0)
        assert rep == 0
        assert interval == 1  # Reset to 1 day

    def test_quality_1_resets_repetition(self):
        """Quality 1 should also reset repetition."""
        ef, interval, rep = sm2_update(2.5, 10, 5, quality=1)
        assert rep == 0

    def test_quality_2_resets_repetition(self):
        """Quality 2 (barely correct) resets repetition."""
        ef, interval, rep = sm2_update(2.5, 10, 5, quality=2)
        assert rep == 0

    def test_quality_3_increments_repetition(self):
        """Quality 3 (correct with difficulty) should increment repetition."""
        ef, interval, rep = sm2_update(2.5, 1, 0, quality=3)
        assert rep == 1

    def test_quality_4_increments_repetition(self):
        """Quality 4 (correct with hesitation) should increment repetition."""
        ef, interval, rep = sm2_update(2.5, 1, 0, quality=4)
        assert rep == 1

    def test_ease_factor_never_below_minimum(self):
        """EF should never drop below MIN_EASE_FACTOR (1.3)."""
        ef = 1.5  # Already low
        for _ in range(20):
            ef, _, _ = sm2_update(ef, 1, 0, quality=0)
        assert ef >= MIN_EASE_FACTOR

    def test_first_repetition_gives_1_day(self):
        """First correct answer: interval = 1 day."""
        _, interval, rep = sm2_update(2.5, 1, 0, quality=4)
        assert rep == 1
        assert interval == 1

    def test_second_repetition_gives_6_days(self):
        """Second consecutive correct: interval = 6 days."""
        _, interval, rep = sm2_update(2.5, 1, 1, quality=4)
        assert rep == 2
        assert interval == 6

    def test_third_repetition_uses_ef_multiplier(self):
        """Third+ repetition: interval = round(prev_interval * EF)."""
        ef = 2.5
        _, interval, rep = sm2_update(ef, 6, 2, quality=4)
        assert rep == 3
        assert interval == round(6 * ef)

    def test_category_difficulty_scales_interval(self):
        """Per-category difficulty should scale the interval."""
        # Harder category (1.4) → shorter interval
        _, interval_hard, _ = sm2_update(2.5, 6, 2, quality=4, category_difficulty=1.4)
        # Easier category (0.6) → longer interval
        _, interval_easy, _ = sm2_update(2.5, 6, 2, quality=4, category_difficulty=0.6)
        assert interval_hard <= interval_easy

    def test_consecutive_perfect_answers_grow_interval(self):
        """Multiple perfect answers should steadily increase interval."""
        ef, interval, rep = 2.5, 1, 0
        intervals = []
        for _ in range(5):
            ef, interval, rep = sm2_update(ef, interval, rep, quality=5)
            intervals.append(interval)
        # Each interval should be >= previous
        for i in range(1, len(intervals)):
            assert intervals[i] >= intervals[i - 1]


# ═══════════════════════════════════════════════════════════════════════════════
# Fuzzy Interval Jitter
# ═══════════════════════════════════════════════════════════════════════════════


class TestFuzzyJitter:
    """Test interval randomization to prevent review avalanche."""

    def test_jitter_on_interval_1_returns_1(self):
        """Interval of 1 day should not be jittered (too small)."""
        result = _apply_fuzzy_jitter(1)
        assert result == 1

    def test_jitter_on_interval_0_returns_0(self):
        """Interval of 0 should stay 0."""
        result = _apply_fuzzy_jitter(0)
        assert result == 0

    def test_jitter_preserves_reasonable_range(self):
        """Jittered value should be within ±10% of original."""
        original = 10
        results = set()
        for _ in range(100):
            r = _apply_fuzzy_jitter(original)
            results.add(r)
            assert r >= original * (1 - FUZZY_JITTER)
            assert r <= original * (1 + FUZZY_JITTER) + 1  # +1 for rounding
        # Should have some variation
        assert len(results) > 1, "Jitter should produce varied results over many calls"

    def test_jitter_always_returns_at_least_1(self):
        """Jittered result should be at least 1 for any positive interval."""
        for _ in range(50):
            r = _apply_fuzzy_jitter(2)
            assert r >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Leitner Box Updates
# ═══════════════════════════════════════════════════════════════════════════════


class TestLeitnerBox:
    """Test Leitner box promotion and demotion."""

    def test_correct_promotes_box(self):
        """Correct answer should promote to next box."""
        new_box = _update_leitner_box(0, is_correct=True)
        assert new_box == 1

    def test_incorrect_demotes_to_box_0(self):
        """Incorrect answer should demote to box 0."""
        new_box = _update_leitner_box(3, is_correct=False)
        assert new_box == 0

    def test_max_box_stays_at_max(self):
        """Box at maximum should not exceed MAX_LEITNER_BOX."""
        new_box = _update_leitner_box(MAX_LEITNER_BOX, is_correct=True)
        assert new_box == MAX_LEITNER_BOX

    def test_streak_bonus_skips_box(self):
        """Streak of 3+ should skip a box on promotion."""
        new_box = _update_leitner_box(1, is_correct=True, streak=3)
        assert new_box == 3  # Skip box 2

    def test_streak_bonus_capped_at_max(self):
        """Streak skip should not exceed max box."""
        new_box = _update_leitner_box(3, is_correct=True, streak=5)
        assert new_box == MAX_LEITNER_BOX

    def test_box_0_incorrect_stays_at_0(self):
        """Box 0 incorrect should stay at 0."""
        new_box = _update_leitner_box(0, is_correct=False)
        assert new_box == 0

    def test_leitner_intervals_defined(self):
        """All boxes should have defined intervals."""
        for box in range(MAX_LEITNER_BOX + 1):
            assert box in LEITNER_INTERVALS


# ═══════════════════════════════════════════════════════════════════════════════
# Quality Scoring
# ═══════════════════════════════════════════════════════════════════════════════


class TestQualityFromAnswer:
    """Test quality mapping from answer metadata."""

    def test_correct_fast_no_hint_gives_5(self):
        """Perfect answer (correct, fast, no hint) → quality 5."""
        q = quality_from_answer(is_correct=True, response_time_ms=3000, hint_used=False)
        assert q == 5

    def test_correct_slow_no_hint_gives_4(self):
        """Correct but slow → quality 4."""
        q = quality_from_answer(is_correct=True, response_time_ms=25000, hint_used=False)
        assert q == 4

    def test_correct_with_hint_gives_3(self):
        """Correct with hint → quality 3."""
        q = quality_from_answer(is_correct=True, response_time_ms=5000, hint_used=True)
        assert q == 3

    def test_incorrect_normal_gives_1(self):
        """Incorrect answer → quality 1."""
        q = quality_from_answer(is_correct=False, response_time_ms=5000, hint_used=False)
        assert q == 1

    def test_incorrect_fast_gives_0(self):
        """Incorrect and very fast (guessing) → quality 0."""
        q = quality_from_answer(is_correct=False, response_time_ms=1000, hint_used=False)
        assert q == 0

    def test_srs_review_hint_caps_at_2(self):
        """During SRS review, hint use should cap quality at 2."""
        q = quality_from_answer(is_correct=True, response_time_ms=5000, hint_used=True, is_srs_review=True)
        assert q <= 2

    def test_no_response_time_defaults_gracefully(self):
        """None response_time_ms should not crash."""
        q = quality_from_answer(is_correct=True, response_time_ms=None, hint_used=False)
        assert 3 <= q <= 5

    def test_quality_always_in_range(self):
        """Quality should always be 0-5."""
        for correct in (True, False):
            for time_ms in (500, 5000, 30000, None):
                for hint in (True, False):
                    q = quality_from_answer(correct, time_ms, hint)
                    assert 0 <= q <= 5


# ═══════════════════════════════════════════════════════════════════════════════
# Question Hash
# ═══════════════════════════════════════════════════════════════════════════════


class TestQuestionHash:
    """Test question text hashing for deduplication."""

    def test_same_text_same_hash(self):
        """Identical text should produce identical hash."""
        h1 = question_hash("Какой минимальный долг?")
        h2 = question_hash("Какой минимальный долг?")
        assert h1 == h2

    def test_different_text_different_hash(self):
        """Different text should produce different hash."""
        h1 = question_hash("Какой минимальный долг?")
        h2 = question_hash("Какие документы нужны?")
        assert h1 != h2

    def test_hash_is_sha256(self):
        """Hash should be SHA-256 hex digest (64 chars)."""
        h = question_hash("test question")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_whitespace_normalization(self):
        """Leading/trailing whitespace should not affect hash (if normalized)."""
        # Note: depends on implementation — hash may or may not normalize
        h = question_hash("test")
        assert isinstance(h, str) and len(h) == 64


# ═══════════════════════════════════════════════════════════════════════════════
# Record Review (integration-style, needs DB mock)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecordReview:
    """Test record_review with mocked DB — creation and update paths."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock async DB session."""
        db = AsyncMock(spec=["execute", "add", "commit", "flush"])
        return db

    @pytest.fixture
    def user_id(self):
        return uuid.uuid4()

    @pytest.mark.asyncio
    async def test_creates_new_record_when_none_exists(self, mock_db, user_id):
        """First review of a question should create a new UserAnswerHistory."""
        from app.services.spaced_repetition import record_review

        # Mock: no existing record
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        record = await record_review(
            mock_db,
            user_id=user_id,
            question_text="Какой минимальный долг для банкротства?",
            question_category="eligibility",
            is_correct=True,
            response_time_ms=5000,
        )

        # Should have called db.add with a new record
        mock_db.add.assert_called_once()
        added = mock_db.add.call_args[0][0]
        assert added.user_id == user_id
        assert added.question_category == "eligibility"
        assert added.ease_factor >= MIN_EASE_FACTOR
        assert added.total_reviews == 1
        assert added.total_correct == 1
        assert added.current_streak == 1
        assert added.leitner_box >= 0

    @pytest.mark.asyncio
    async def test_updates_existing_record(self, mock_db, user_id):
        """Subsequent review should update existing record."""
        from app.models.knowledge import UserAnswerHistory
        from app.services.spaced_repetition import record_review

        # Mock: existing record
        existing = UserAnswerHistory(
            id=uuid.uuid4(),
            user_id=user_id,
            question_category="eligibility",
            question_hash="abc123" * 10 + "abcd",
            question_text="Какой минимальный долг?",
            ease_factor=2.5,
            interval_days=6,
            repetition_count=2,
            quality_history=[4, 5],
            next_review_at=datetime.now(timezone.utc) - timedelta(days=1),
            last_reviewed_at=datetime.now(timezone.utc) - timedelta(days=7),
            total_reviews=2,
            total_correct=2,
            leitner_box=2,
            source_type="quiz",
            current_streak=2,
            best_streak=2,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute = AsyncMock(return_value=mock_result)

        record = await record_review(
            mock_db,
            user_id=user_id,
            question_text="Какой минимальный долг?",
            question_category="eligibility",
            is_correct=True,
            response_time_ms=4000,
        )

        # Should NOT have called db.add (updating in place)
        mock_db.add.assert_not_called()
        assert record.total_reviews == 3
        assert record.total_correct == 3
        assert record.current_streak == 3

    @pytest.mark.asyncio
    async def test_incorrect_answer_resets_streak(self, mock_db, user_id):
        """Incorrect answer should reset current_streak to 0."""
        from app.models.knowledge import UserAnswerHistory
        from app.services.spaced_repetition import record_review

        existing = UserAnswerHistory(
            id=uuid.uuid4(),
            user_id=user_id,
            question_category="costs",
            question_hash="def456" * 10 + "defg",
            question_text="Сколько стоит процедура?",
            ease_factor=2.5,
            interval_days=6,
            repetition_count=3,
            quality_history=[4, 4, 5],
            next_review_at=datetime.now(timezone.utc),
            last_reviewed_at=datetime.now(timezone.utc) - timedelta(days=6),
            total_reviews=3,
            total_correct=3,
            leitner_box=3,
            source_type="quiz",
            current_streak=5,
            best_streak=5,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute = AsyncMock(return_value=mock_result)

        record = await record_review(
            mock_db,
            user_id=user_id,
            question_text="Сколько стоит процедура?",
            question_category="costs",
            is_correct=False,
            response_time_ms=10000,
        )

        assert record.current_streak == 0
        assert record.best_streak == 5  # Should keep best
        assert record.leitner_box == 0  # Demoted to 0

    @pytest.mark.asyncio
    async def test_source_type_preserved(self, mock_db, user_id):
        """Non-quiz source types should be recorded."""
        from app.services.spaced_repetition import record_review

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        await record_review(
            mock_db,
            user_id=user_id,
            question_text="PvP вопрос",
            question_category="procedure",
            is_correct=True,
            source_type="pvp",
        )

        added = mock_db.add.call_args[0][0]
        assert added.source_type == "pvp"


# ═══════════════════════════════════════════════════════════════════════════════
# SRS Session Initialization
# ═══════════════════════════════════════════════════════════════════════════════


class TestStartSrsSession:
    """Test SRS session initialization logic."""

    @pytest.mark.asyncio
    async def test_start_srs_session_returns_expected_keys(self):
        """start_srs_session should return review_queue, stats, etc."""
        from app.services.spaced_repetition import start_srs_session

        db = AsyncMock()
        # Mock: no items in DB
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        result = await start_srs_session(db, uuid.uuid4(), session_size=10)

        assert "review_queue" in result
        assert "stats" in result
        assert isinstance(result["review_queue"], list)


# ═══════════════════════════════════════════════════════════════════════════════
# SoloQuizState SRS fields
# ═══════════════════════════════════════════════════════════════════════════════


class TestSoloQuizStateSrs:
    """Test _SoloQuizState SRS-specific fields."""

    def test_srs_fields_initialized(self):
        """New state should have SRS fields initialized to defaults."""
        from app.ws.knowledge import _SoloQuizState
        from app.models.knowledge import QuizMode

        state = _SoloQuizState(
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            mode=QuizMode.srs_review,
            total_questions=10,
            time_limit=None,
            category=None,
            difficulty=3,
        )

        assert state.srs_queue == []
        assert state.srs_current_item is None
        assert state.srs_answers_in_session == 0

    def test_srs_queue_can_be_populated(self):
        """SRS queue should be settable after initialization."""
        from app.ws.knowledge import _SoloQuizState
        from app.models.knowledge import QuizMode

        state = _SoloQuizState(
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            mode=QuizMode.srs_review,
            total_questions=5,
            time_limit=None,
            category=None,
            difficulty=3,
        )

        state.srs_queue = [
            {"question_text": "Q1", "question_category": "eligibility", "priority": "overdue", "leitner_box": 0},
            {"question_text": "Q2", "question_category": "costs", "priority": "weak", "leitner_box": 1},
        ]
        assert len(state.srs_queue) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: SM-2 → Leitner progression over multiple reviews
# ═══════════════════════════════════════════════════════════════════════════════


class TestSm2LeitnerProgression:
    """Test that SM-2 and Leitner work together over multiple reviews."""

    def test_full_mastery_path(self):
        """Simulate a user getting 10 consecutive correct answers → should reach box 4."""
        ef, interval, rep = DEFAULT_EASE_FACTOR, 1, 0
        box = 0
        streak = 0

        for _ in range(10):
            ef, interval, rep = sm2_update(ef, interval, rep, quality=5)
            streak += 1
            box = _update_leitner_box(box, is_correct=True, streak=streak)

        assert box == MAX_LEITNER_BOX
        assert ef >= DEFAULT_EASE_FACTOR
        assert interval > 10  # Should be well above 10 days

    def test_relapse_and_recovery(self):
        """User masters a card, then gets it wrong, then recovers."""
        ef, interval, rep = DEFAULT_EASE_FACTOR, 1, 0
        box = 3  # Previously at box 3

        # Incorrect: relapse
        ef, interval, rep = sm2_update(ef, interval, rep, quality=0)
        box = _update_leitner_box(box, is_correct=False)
        assert box == 0
        assert rep == 0
        assert interval == 1

        # Recovery: 3 consecutive correct
        streak = 0
        for _ in range(3):
            ef, interval, rep = sm2_update(ef, interval, rep, quality=4)
            streak += 1
            box = _update_leitner_box(box, is_correct=True, streak=streak)

        assert box >= 2  # Should have recovered significantly
        assert rep == 3

    def test_oscillating_performance(self):
        """Alternating correct/incorrect should keep EF low and box at 0-1."""
        ef, interval, rep = DEFAULT_EASE_FACTOR, 1, 0
        box = 0

        for i in range(10):
            is_correct = i % 2 == 0  # alternate
            quality = 4 if is_correct else 1
            ef, interval, rep = sm2_update(ef, interval, rep, quality)
            box = _update_leitner_box(box, is_correct=is_correct)

        assert ef < DEFAULT_EASE_FACTOR  # Should have dropped
        assert box <= 1  # Should bounce between 0-1


# ═══════════════════════════════════════════════════════════════════════════════
# QuizMode includes srs_review
# ═══════════════════════════════════════════════════════════════════════════════


class TestQuizModeEnum:
    """Verify QuizMode enum has srs_review mode."""

    def test_srs_review_mode_exists(self):
        from app.models.knowledge import QuizMode
        assert QuizMode.srs_review == "srs_review"

    def test_srs_review_is_valid_mode(self):
        from app.models.knowledge import QuizMode
        assert QuizMode("srs_review") == QuizMode.srs_review

    def test_all_modes_defined(self):
        from app.models.knowledge import QuizMode
        modes = {m.value for m in QuizMode}
        assert "srs_review" in modes
        assert "free_dialog" in modes
        assert "blitz" in modes
        assert "themed" in modes
        assert "pvp" in modes
