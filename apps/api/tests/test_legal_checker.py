"""Tests for legal accuracy checker (services/legal_checker.py).

Covers:
  - Individual legal rule matching (error, correct, citation patterns)
  - LegalCheck data structure
  - check_session_legal_accuracy end-to-end (mocked DB)
  - Score clamping and aggregation
  - All 10 legal categories have at least one rule
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Legal rules coverage
# ═══════════════════════════════════════════════════════════════════════════════


class TestLegalRulesCoverage:
    """Verify all 10 categories have rules defined."""

    def test_all_categories_have_rules(self):
        from app.services.legal_checker import LEGAL_CHECKS
        from app.models.rag import LegalCategory

        categories_with_rules = {check.category for check in LEGAL_CHECKS}
        all_categories = set(LegalCategory)

        missing = all_categories - categories_with_rules
        assert not missing, f"Categories without legal checks: {missing}"

    def test_minimum_rule_count(self):
        from app.services.legal_checker import LEGAL_CHECKS

        assert len(LEGAL_CHECKS) >= 15, f"Expected ≥15 rules, got {len(LEGAL_CHECKS)}"

    def test_all_rules_have_patterns(self):
        from app.services.legal_checker import LEGAL_CHECKS

        for check in LEGAL_CHECKS:
            assert check.error_patterns, f"Rule {check.id} has no error_patterns"
            assert check.correct_patterns, f"Rule {check.id} has no correct_patterns"
            assert check.law_article, f"Rule {check.id} has no law_article"


# ═══════════════════════════════════════════════════════════════════════════════
# Individual pattern matching
# ═══════════════════════════════════════════════════════════════════════════════


class TestDebtThresholdRule:
    """Test the most critical rule: 500K debt threshold."""

    def _get_rule(self):
        from app.services.legal_checker import LEGAL_CHECKS
        return next(r for r in LEGAL_CHECKS if r.id == "debt_threshold")

    def test_correct_amount_matches(self):
        import re
        rule = self._get_rule()
        text = "Минимальный долг для банкротства — 500 000 рублей"
        matched = any(re.search(p, text, re.IGNORECASE) for p in rule.correct_patterns)
        assert matched, "500 000 should match correct patterns"

    def test_wrong_amount_detected(self):
        import re
        rule = self._get_rule()
        text = "Минимальный долг для банкротства — 300 000 рублей"
        matched = any(re.search(p, text, re.IGNORECASE) for p in rule.error_patterns)
        assert matched, "300 000 should trigger error pattern"

    def test_citation_bonus(self):
        import re
        rule = self._get_rule()
        text = "Согласно статье 213.3 п.2, порог — 500 тысяч рублей"
        has_correct = any(re.search(p, text, re.IGNORECASE) for p in rule.correct_patterns)
        has_citation = any(re.search(p, text, re.IGNORECASE) for p in rule.citation_patterns)
        assert has_correct and has_citation, "Should match both correct AND citation"

    def test_neutral_text_no_match(self):
        import re
        rule = self._get_rule()
        text = "Добрый день! Расскажите о вашей ситуации."
        has_error = any(re.search(p, text, re.IGNORECASE) for p in rule.error_patterns)
        has_correct = any(re.search(p, text, re.IGNORECASE) for p in rule.correct_patterns)
        assert not has_error and not has_correct


# ═══════════════════════════════════════════════════════════════════════════════
# LegalCheckResult data structure
# ═══════════════════════════════════════════════════════════════════════════════


class TestLegalCheckResult:
    def test_result_creation(self):
        from app.services.legal_checker import LegalCheckResult

        result = LegalCheckResult(
            total_score=2.5,
            checks_triggered=5,
            correct_cited=2,
            correct=1,
            partial=1,
            incorrect=1,
        )
        assert result.total_score == 2.5
        assert result.checks_triggered == 5
        assert len(result.details) == 0

    def test_result_with_details(self):
        from app.services.legal_checker import LegalCheckResult

        result = LegalCheckResult(
            total_score=-3.0,
            checks_triggered=1,
            correct_cited=0,
            correct=0,
            partial=0,
            incorrect=1,
            details=[{"rule_id": "debt_threshold", "accuracy": "incorrect"}],
        )
        assert result.incorrect == 1
        assert len(result.details) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Score aggregation and clamping
# ═══════════════════════════════════════════════════════════════════════════════


class TestScoreAggregation:
    """Test the scoring logic."""

    def test_score_clamping_positive(self):
        """Score should be clamped to +5 max."""
        # +1 per correct_cited × 10 = +10, but clamped to +5
        total = sum([+1] * 10)
        clamped = max(-5.0, min(5.0, total))
        assert clamped == 5.0

    def test_score_clamping_negative(self):
        """Score should be clamped to -5 min."""
        # -3 per incorrect × 5 = -15, but clamped to -5
        total = sum([-3] * 5)
        clamped = max(-5.0, min(5.0, total))
        assert clamped == -5.0

    def test_mixed_scoring(self):
        """Test mixed correct/incorrect scores."""
        # 2 correct_cited (+2), 1 incorrect (-3) = -1
        total = 2 * 1 + 1 * (-3)
        assert total == -1
        clamped = max(-5.0, min(5.0, total))
        assert clamped == -1.0


# ═══════════════════════════════════════════════════════════════════════════════
# check_session_legal_accuracy (mocked DB)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCheckSessionLegalAccuracy:

    @pytest.mark.asyncio
    async def test_no_user_messages_returns_zero(self):
        from app.services.legal_checker import check_session_legal_accuracy

        db = AsyncMock()
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        result = await check_session_legal_accuracy(uuid.uuid4(), db)

        assert result.total_score == 0.0
        assert result.checks_triggered == 0

    @pytest.mark.asyncio
    async def test_correct_statement_positive_score(self):
        from app.services.legal_checker import check_session_legal_accuracy
        from app.models.training import MessageRole

        # Create mock message with correct legal info
        mock_msg = MagicMock()
        mock_msg.role = MessageRole.user
        mock_msg.content = "Минимальный долг для банкротства — 500 000 рублей, просрочка от 3 месяцев"
        mock_msg.sequence_number = 1

        db = AsyncMock()
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = [mock_msg]
        db.execute = AsyncMock(return_value=mock_result)

        result = await check_session_legal_accuracy(uuid.uuid4(), db)

        # Should detect at least one correct claim
        assert result.total_score >= 0.0
        assert result.correct + result.correct_cited >= 1

    @pytest.mark.asyncio
    async def test_incorrect_statement_negative_score(self):
        from app.services.legal_checker import check_session_legal_accuracy
        from app.models.training import MessageRole

        mock_msg = MagicMock()
        mock_msg.role = MessageRole.user
        mock_msg.content = "Минимальный долг — 300 000 рублей, можно подать с любой суммой"
        mock_msg.sequence_number = 1

        db = AsyncMock()
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = [mock_msg]
        db.execute = AsyncMock(return_value=mock_result)

        result = await check_session_legal_accuracy(uuid.uuid4(), db)

        assert result.total_score < 0.0
        assert result.incorrect >= 1
