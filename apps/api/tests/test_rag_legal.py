"""Smoke tests for RAG legal pipeline: embedding cache, keyword retrieval, hybrid scoring."""

import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.rag_legal import (
    _cache_get,
    _cache_put,
    _embedding_cache,
    _keyword_score,
    check_embeddings_populated,
    RAGResult,
    RAGContext,
)


# ---------------------------------------------------------------------------
# Embedding LRU cache tests
# ---------------------------------------------------------------------------


class TestEmbeddingCache:
    def setup_method(self):
        _embedding_cache.clear()

    def test_cache_put_and_get(self):
        vec = [0.1] * 768
        _cache_put("test text", vec)
        result = _cache_get("test text")
        assert result == vec

    def test_cache_miss(self):
        result = _cache_get("nonexistent")
        assert result is None

    def test_cache_expiry(self):
        vec = [0.2] * 768
        _cache_put("expired text", vec)
        # Manually expire by backdating the timestamp
        _embedding_cache["expired text"] = (vec, time.monotonic() - 4000)
        result = _cache_get("expired text")
        assert result is None

    def test_cache_lru_eviction(self):
        """Cache should evict oldest entries when full."""
        from app.services.rag_legal import _EMBEDDING_CACHE_MAX

        for i in range(_EMBEDDING_CACHE_MAX + 5):
            _cache_put(f"text_{i}", [float(i)])

        assert len(_embedding_cache) == _EMBEDDING_CACHE_MAX
        # First 5 entries should be evicted
        assert _cache_get("text_0") is None
        assert _cache_get("text_4") is None
        # Last entry should exist
        assert _cache_get(f"text_{_EMBEDDING_CACHE_MAX + 4}") is not None

    def teardown_method(self):
        _embedding_cache.clear()


# ---------------------------------------------------------------------------
# Keyword scoring tests
# ---------------------------------------------------------------------------


class TestKeywordScore:
    def test_full_match(self):
        score = _keyword_score("банкротство долг кредит", ["банкротство", "долг", "кредит"])
        assert score == 1.0

    def test_partial_match(self):
        score = _keyword_score("банкротство физических лиц", ["банкротство", "долг"])
        assert abs(score - 0.5) < 0.01

    def test_no_match(self):
        score = _keyword_score("погода сегодня хорошая", ["банкротство", "долг"])
        assert score == 0.0

    def test_empty_keywords(self):
        score = _keyword_score("любой текст", [])
        assert score == 0.0

    def test_case_insensitive(self):
        score = _keyword_score("БАНКРОТСТВО ДОЛГ", ["банкротство", "долг"])
        assert score == 1.0


# ---------------------------------------------------------------------------
# RAGContext formatting tests
# ---------------------------------------------------------------------------


class TestRAGContext:
    def test_empty_context(self):
        ctx = RAGContext(query="test", results=[])
        assert not ctx.has_results
        assert ctx.to_prompt_context() == ""

    def test_context_with_results(self):
        result = RAGResult(
            chunk_id=uuid.uuid4(),
            category="eligibility",
            fact_text="Порог 500К рублей",
            law_article="127-ФЗ ст. 213.3",
            relevance_score=0.85,
            common_errors=["100 000 рублей"],
        )
        ctx = RAGContext(query="порог банкротства", results=[result], method="embedding")
        assert ctx.has_results
        prompt = ctx.to_prompt_context()
        assert "127-ФЗ" in prompt
        assert "Порог 500К рублей" in prompt
        assert "Частые ошибки" in prompt


# ---------------------------------------------------------------------------
# check_embeddings_populated tests (mocked DB)
# ---------------------------------------------------------------------------


class TestCheckEmbeddingsPopulated:
    @pytest.mark.asyncio
    async def test_no_facts_returns_true(self):
        """If no facts seeded, nothing to populate."""
        db = AsyncMock()
        # First call: populated count = 0
        mock_result1 = AsyncMock()
        mock_result1.scalar.return_value = 0
        # Second call: total count = 0
        mock_result2 = AsyncMock()
        mock_result2.scalar.return_value = 0
        db.execute = AsyncMock(side_effect=[mock_result1, mock_result2])

        result = await check_embeddings_populated(db)
        assert result is True

    @pytest.mark.asyncio
    async def test_fully_populated_returns_true(self):
        db = AsyncMock()
        mock_result1 = AsyncMock()
        mock_result1.scalar.return_value = 100
        mock_result2 = AsyncMock()
        mock_result2.scalar.return_value = 110
        db.execute = AsyncMock(side_effect=[mock_result1, mock_result2])

        result = await check_embeddings_populated(db)
        assert result is True  # 100/110 = 91% >= 80%

    @pytest.mark.asyncio
    async def test_under_threshold_returns_false(self):
        db = AsyncMock()
        mock_result1 = AsyncMock()
        mock_result1.scalar.return_value = 10
        mock_result2 = AsyncMock()
        mock_result2.scalar.return_value = 110
        db.execute = AsyncMock(side_effect=[mock_result1, mock_result2])

        result = await check_embeddings_populated(db)
        assert result is False  # 10/110 = 9% < 80%

    @pytest.mark.asyncio
    async def test_db_error_returns_true(self):
        """On error, assume populated to avoid blocking startup."""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("pgvector not installed"))

        result = await check_embeddings_populated(db)
        assert result is True


# ---------------------------------------------------------------------------
# Hybrid scoring integration (mocked)
# ---------------------------------------------------------------------------


class TestHybridScoringIntegration:
    """Verify _score_legal_accuracy combines regex + vector correctly."""

    @pytest.mark.asyncio
    async def test_regex_only_fallback(self):
        """When vector has 0 claims, should use 100% regex."""
        from app.services.scoring import _score_legal_accuracy

        mock_regex_result = AsyncMock()
        mock_regex_result.total_score = 2.0
        mock_regex_result.checks_triggered = 3
        mock_regex_result.correct_cited = 1
        mock_regex_result.correct = 1
        mock_regex_result.partial = 0
        mock_regex_result.incorrect = 1
        mock_regex_result.details = []

        with (
            patch(
                "app.services.scoring.check_session_legal_accuracy",
                new_callable=AsyncMock,
                return_value=mock_regex_result,
            ),
            patch(
                "app.services.scoring._score_legal_accuracy_vector",
                new_callable=AsyncMock,
                return_value=(0.0, {"method": "vector", "claims_checked": 0}),
            ),
        ):
            score, details = await _score_legal_accuracy(uuid.uuid4(), AsyncMock())

        assert details["scoring_method"] == "regex_only"
        assert score == 2.0  # 100% regex

    @pytest.mark.asyncio
    async def test_hybrid_combines_scores(self):
        """When vector has claims, should use 0.6 regex + 0.4 vector."""
        from app.services.scoring import _score_legal_accuracy

        mock_regex_result = AsyncMock()
        mock_regex_result.total_score = 3.0
        mock_regex_result.checks_triggered = 2
        mock_regex_result.correct_cited = 2
        mock_regex_result.correct = 0
        mock_regex_result.partial = 0
        mock_regex_result.incorrect = 0
        mock_regex_result.details = []

        with (
            patch(
                "app.services.scoring.check_session_legal_accuracy",
                new_callable=AsyncMock,
                return_value=mock_regex_result,
            ),
            patch(
                "app.services.scoring._score_legal_accuracy_vector",
                new_callable=AsyncMock,
                return_value=(1.0, {"method": "vector", "claims_checked": 2, "vector_checks": []}),
            ),
        ):
            score, details = await _score_legal_accuracy(uuid.uuid4(), AsyncMock())

        assert details["scoring_method"] == "hybrid"
        expected = 0.6 * 3.0 + 0.4 * 1.0  # 1.8 + 0.4 = 2.2
        assert abs(score - expected) < 0.01
