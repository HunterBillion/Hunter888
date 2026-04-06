"""Extended tests for RAG pipeline (services/rag_legal.py).

Covers the v2 improvements:
  - DB-level keyword pre-filtering (ILIKE tokens)
  - tags_filter support in _build_where_clauses
  - Effectiveness score boost
  - Dynamic error_frequency calculation
  - RRF hybrid reranking
  - BlitzQuestionPool
  - Content hashing
  - Retrieval config validation
  - Cache key generation
"""

import hashlib
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.rag_legal import (
    BlitzQuestionPool,
    RAGContext,
    RAGResult,
    RetrievalConfig,
    _build_where_clauses,
    _hybrid_rerank,
    _keyword_score,
    _make_cache_key,
    _query_mentions_article,
    compute_content_hash,
)


# ═══════════════════════════════════════════════════════════════════════════════
# _build_where_clauses — tags_filter support
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildWhereClauses:
    def test_default_config(self):
        config = RetrievalConfig()
        where, params = _build_where_clauses(config)
        assert "is_active = true" in where
        assert len(params) == 0

    def test_category_filter(self):
        config = RetrievalConfig(category="eligibility")
        where, params = _build_where_clauses(config)
        assert "category = :filter_category" in where
        assert params["filter_category"] == "eligibility"

    def test_difficulty_range(self):
        config = RetrievalConfig(difficulty_range=(2, 4))
        where, params = _build_where_clauses(config)
        assert "difficulty_level BETWEEN" in where
        assert params["diff_lo"] == 2
        assert params["diff_hi"] == 4

    def test_court_practice_required(self):
        config = RetrievalConfig(require_court_practice=True)
        where, params = _build_where_clauses(config)
        assert "is_court_practice = true" in where

    def test_exclude_chunk_ids(self):
        ids = [uuid.uuid4(), uuid.uuid4()]
        config = RetrievalConfig(exclude_chunk_ids=ids)
        where, params = _build_where_clauses(config)
        assert "NOT IN" in where
        assert len(params) == 2

    def test_tags_filter(self):
        config = RetrievalConfig(tags_filter=["каверзный", "судебная_практика"])
        where, params = _build_where_clauses(config)
        assert "tags @>" in where
        assert "tags_filter" in params
        parsed = json.loads(params["tags_filter"])
        assert "каверзный" in parsed
        assert "судебная_практика" in parsed

    def test_combined_filters(self):
        config = RetrievalConfig(
            category="property",
            difficulty_range=(3, 5),
            require_court_practice=True,
            tags_filter=["пленум"],
        )
        where, params = _build_where_clauses(config)
        assert "category = :filter_category" in where
        assert "difficulty_level BETWEEN" in where
        assert "is_court_practice = true" in where
        assert "tags @>" in where


# ═══════════════════════════════════════════════════════════════════════════════
# Keyword scoring
# ═══════════════════════════════════════════════════════════════════════════════


class TestKeywordScoring:
    def test_full_match(self):
        score = _keyword_score("банкротство долг кредит", ["банкротство", "долг", "кредит"])
        assert score == 1.0

    def test_partial_match(self):
        score = _keyword_score("банкротство физических лиц", ["банкротство", "долг"])
        assert abs(score - 0.5) < 0.01

    def test_no_match(self):
        score = _keyword_score("погода сегодня", ["банкротство", "долг"])
        assert score == 0.0

    def test_empty_keywords(self):
        score = _keyword_score("любой текст", [])
        assert score == 0.0

    def test_case_insensitive(self):
        score = _keyword_score("БАНКРОТСТВО", ["банкротство"])
        assert score == 1.0

    def test_partial_word_match(self):
        """'банкротств' keyword should match 'банкротства' in text."""
        score = _keyword_score("Процедура банкротства", ["банкротств"])
        assert score > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Law article matching
# ═══════════════════════════════════════════════════════════════════════════════


class TestArticleMentions:
    def test_exact_match(self):
        assert _query_mentions_article("Согласно ст. 213.3", "ст. 213.3")

    def test_no_spaces_match(self):
        assert _query_mentions_article("ст.213.3 п.2", "ст. 213.3")

    def test_no_match(self):
        assert not _query_mentions_article("общий вопрос", "ст. 213.3")


# ═══════════════════════════════════════════════════════════════════════════════
# Hybrid RRF reranking
# ═══════════════════════════════════════════════════════════════════════════════


class TestHybridRerank:
    def _make_result(self, chunk_id=None, score=0.5, category="eligibility"):
        return RAGResult(
            chunk_id=chunk_id or uuid.uuid4(),
            category=category,
            fact_text="Test fact",
            law_article="ст. 213.3",
            relevance_score=score,
        )

    def test_merge_unique_results(self):
        config = RetrievalConfig(top_k=3)
        emb = [self._make_result(score=0.9), self._make_result(score=0.7)]
        kw = [self._make_result(score=0.8), self._make_result(score=0.6)]
        merged = _hybrid_rerank(emb, kw, config)
        assert len(merged) == 3

    def test_shared_results_ranked_higher(self):
        """Results appearing in both lists should get higher RRF score."""
        config = RetrievalConfig(top_k=3)
        shared_id = uuid.uuid4()
        emb = [self._make_result(chunk_id=shared_id, score=0.9)]
        kw = [self._make_result(chunk_id=shared_id, score=0.8), self._make_result(score=0.7)]
        merged = _hybrid_rerank(emb, kw, config)
        assert merged[0].chunk_id == shared_id

    def test_empty_embedding_results(self):
        config = RetrievalConfig(top_k=3)
        kw = [self._make_result(score=0.8)]
        merged = _hybrid_rerank([], kw, config)
        assert len(merged) == 1

    def test_relevance_score_normalized(self):
        config = RetrievalConfig(top_k=5)
        emb = [self._make_result(score=0.9)]
        kw = [self._make_result(score=0.8)]
        merged = _hybrid_rerank(emb, kw, config)
        for r in merged:
            assert 0 <= r.relevance_score <= 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# RAGContext
# ═══════════════════════════════════════════════════════════════════════════════


class TestRAGContextV2:
    def test_json_roundtrip(self):
        result = RAGResult(
            chunk_id=uuid.uuid4(),
            category="eligibility",
            fact_text="Порог 500К",
            law_article="127-ФЗ ст. 213.3",
            relevance_score=0.85,
            common_errors=["100К", "300К"],
            tags=["базовый"],
        )
        ctx = RAGContext(query="порог", results=[result], method="hybrid", retrieval_ms=15.3)
        json_str = ctx.to_json()
        restored = RAGContext.from_json(json_str)
        assert restored.query == "порог"
        assert restored.method == "hybrid"
        assert len(restored.results) == 1
        assert str(restored.results[0].chunk_id) == str(result.chunk_id)
        assert restored.results[0].tags == ["базовый"]

    def test_prompt_context_format(self):
        result = RAGResult(
            chunk_id=uuid.uuid4(),
            category="eligibility",
            fact_text="Порог 500К",
            law_article="127-ФЗ ст. 213.3",
            relevance_score=0.9,
            correct_response_hint="500 тысяч рублей",
        )
        ctx = RAGContext(query="test", results=[result])
        prompt = ctx.to_prompt_context()
        assert "Правовая база" in prompt
        assert "Порог 500К" in prompt
        assert "Подсказка" in prompt


# ═══════════════════════════════════════════════════════════════════════════════
# BlitzQuestionPool
# ═══════════════════════════════════════════════════════════════════════════════


class TestBlitzQuestionPool:
    def test_initial_state(self):
        pool = BlitzQuestionPool()
        assert pool.loaded is False
        assert pool.total == 0

    def test_get_question_unloaded(self):
        pool = BlitzQuestionPool()
        assert pool.get_question() is None

    def test_get_question_with_filters(self):
        pool = BlitzQuestionPool()
        pool._loaded = True
        pool._questions = [
            {"chunk_id": uuid.uuid4(), "category": "eligibility", "question": "Q1", "answer": "A1", "article": "ст.213.3", "difficulty": 2, "fact_text": "F1"},
            {"chunk_id": uuid.uuid4(), "category": "property", "question": "Q2", "answer": "A2", "article": "ст.213.25", "difficulty": 4, "fact_text": "F2"},
            {"chunk_id": uuid.uuid4(), "category": "eligibility", "question": "Q3", "answer": "A3", "article": "ст.213.4", "difficulty": 3, "fact_text": "F3"},
        ]

        # Filter by category
        q = pool.get_question(category="property")
        assert q is not None
        assert q["category"] == "property"

    def test_exclude_ids(self):
        pool = BlitzQuestionPool()
        pool._loaded = True
        id1 = uuid.uuid4()
        id2 = uuid.uuid4()
        pool._questions = [
            {"chunk_id": id1, "category": "eligibility", "question": "Q1", "answer": "A1", "article": "ст.213.3", "difficulty": 2, "fact_text": "F1"},
            {"chunk_id": id2, "category": "eligibility", "question": "Q2", "answer": "A2", "article": "ст.213.4", "difficulty": 3, "fact_text": "F2"},
        ]

        # Exclude id1
        q = pool.get_question(exclude_ids={id1})
        assert q is not None
        assert q["chunk_id"] == id2

    def test_difficulty_range_filter(self):
        pool = BlitzQuestionPool()
        pool._loaded = True
        pool._questions = [
            {"chunk_id": uuid.uuid4(), "category": "eligibility", "question": "Q1", "answer": "A1", "article": "ст.213.3", "difficulty": 1, "fact_text": "F1"},
            {"chunk_id": uuid.uuid4(), "category": "eligibility", "question": "Q2", "answer": "A2", "article": "ст.213.3", "difficulty": 5, "fact_text": "F2"},
        ]

        q = pool.get_question(difficulty_range=(4, 5))
        assert q is not None
        assert q["difficulty"] == 5


# ═══════════════════════════════════════════════════════════════════════════════
# Content hashing
# ═══════════════════════════════════════════════════════════════════════════════


class TestContentHash:
    def test_deterministic(self):
        h1 = compute_content_hash("Факт 1", "ст. 213.3")
        h2 = compute_content_hash("Факт 1", "ст. 213.3")
        assert h1 == h2

    def test_different_inputs_different_hashes(self):
        h1 = compute_content_hash("Факт 1", "ст. 213.3")
        h2 = compute_content_hash("Факт 2", "ст. 213.3")
        assert h1 != h2

    def test_hash_is_md5(self):
        h = compute_content_hash("test", "article")
        assert len(h) == 32  # md5 hex length


# ═══════════════════════════════════════════════════════════════════════════════
# Cache key generation
# ═══════════════════════════════════════════════════════════════════════════════


class TestCacheKey:
    def test_same_input_same_key(self):
        config = RetrievalConfig(category="eligibility")
        k1 = _make_cache_key("test query", config)
        k2 = _make_cache_key("test query", config)
        assert k1 == k2

    def test_different_query_different_key(self):
        config = RetrievalConfig()
        k1 = _make_cache_key("query 1", config)
        k2 = _make_cache_key("query 2", config)
        assert k1 != k2

    def test_different_config_different_key(self):
        k1 = _make_cache_key("test", RetrievalConfig(category="eligibility"))
        k2 = _make_cache_key("test", RetrievalConfig(category="property"))
        assert k1 != k2

    def test_key_has_prefix(self):
        k = _make_cache_key("test", RetrievalConfig())
        assert k.startswith("rag:ctx:")


# ═══════════════════════════════════════════════════════════════════════════════
# RetrievalConfig
# ═══════════════════════════════════════════════════════════════════════════════


class TestRetrievalConfig:
    def test_default_values(self):
        config = RetrievalConfig()
        assert config.top_k == 5
        assert config.min_relevance == 0.15
        assert config.category is None
        assert config.tags_filter is None
        assert config.mode == "free_dialog"

    def test_custom_values(self):
        config = RetrievalConfig(
            top_k=10,
            category="court",
            tags_filter=["пленум"],
            mode="blitz",
            require_court_practice=True,
        )
        assert config.top_k == 10
        assert config.tags_filter == ["пленум"]
        assert config.mode == "blitz"
        assert config.require_court_practice is True
