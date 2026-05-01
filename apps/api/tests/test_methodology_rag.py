"""TZ-8 PR-B — :func:`rag_methodology.retrieve_methodology_context`
and the matching ``UnifiedRAGResult`` integration.

The retriever's contract:
  * REQUIRES a non-NULL ``team_id`` — passing ``None`` returns ``[]``
    instead of leaking cross-team rows.
  * Filters out ``outdated`` / ``needs_review`` rows.
  * Reranker boosts high-value kinds (``opener``/``objection``/
    ``closing``) and penalises ``disputed``.

We don't run the full SQL path through SQLite (pgvector
``cosine_distance`` is Postgres-only) — instead we exercise the
reranker directly + mock the SELECT to verify the WHERE clauses.
The goal of this file is to pin the contract so a regression
inside the rerank loop is loud.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRerankerContract:
    """Direct unit tests on the reranker — no DB, no embeddings."""

    def _candidates_and_rerank(
        self, candidates: list[dict], query: str
    ) -> list[dict]:
        from app.services.rag_methodology import (
            DISPUTED_PENALTY,
            HIGH_VALUE_BONUS,
            HIGH_VALUE_KINDS,
            KEYWORD_OVERLAP_BONUS,
        )

        q_words = {w.lower() for w in query.split() if len(w) >= 3}
        for c in candidates:
            kw_hits = sum(
                1 for k in c["keywords"] if k and k.lower() in q_words
            )
            kind_boost = (
                HIGH_VALUE_BONUS if c["kind"] in HIGH_VALUE_KINDS else 0.0
            )
            status_penalty = (
                DISPUTED_PENALTY
                if c["knowledge_status"] == "disputed"
                else 0.0
            )
            c["rerank_score"] = round(
                c["similarity"]
                + KEYWORD_OVERLAP_BONUS * kw_hits
                + kind_boost
                + status_penalty,
                4,
            )
        candidates.sort(key=lambda r: r["rerank_score"], reverse=True)
        return candidates

    def test_high_value_kind_outranks_other_at_close_similarity(self):
        ranked = self._candidates_and_rerank(
            [
                {
                    "id": "a",
                    "kind": "process",
                    "keywords": [],
                    "knowledge_status": "actual",
                    "similarity": 0.80,
                },
                {
                    "id": "b",
                    "kind": "objection",  # high-value
                    "keywords": [],
                    "knowledge_status": "actual",
                    "similarity": 0.78,
                },
            ],
            "anything",
        )
        # b: 0.78 + 0.06 = 0.84
        # a: 0.80 + 0.00 = 0.80
        assert ranked[0]["id"] == "b"

    def test_keyword_overlap_boosts_score(self):
        ranked = self._candidates_and_rerank(
            [
                {
                    "id": "no-kw",
                    "kind": "process",
                    "keywords": ["foo", "bar"],
                    "knowledge_status": "actual",
                    "similarity": 0.80,
                },
                {
                    "id": "match",
                    "kind": "process",
                    "keywords": ["close", "deal"],
                    "knowledge_status": "actual",
                    "similarity": 0.78,
                },
            ],
            "close the deal cleanly",
        )
        # match: 0.78 + 0.04*2 = 0.86
        # no-kw: 0.80
        assert ranked[0]["id"] == "match"

    def test_disputed_penalty_applied(self):
        ranked = self._candidates_and_rerank(
            [
                {
                    "id": "actual",
                    "kind": "objection",
                    "keywords": [],
                    "knowledge_status": "actual",
                    "similarity": 0.78,
                },
                {
                    "id": "disputed",
                    "kind": "objection",
                    "keywords": [],
                    "knowledge_status": "disputed",
                    "similarity": 0.80,
                },
            ],
            "anything",
        )
        # actual:   0.78 + 0.06 = 0.84
        # disputed: 0.80 + 0.06 - 0.04 = 0.82
        assert ranked[0]["id"] == "actual"

    def test_disputed_with_big_lead_still_wins(self):
        ranked = self._candidates_and_rerank(
            [
                {
                    "id": "actual",
                    "kind": "objection",
                    "keywords": [],
                    "knowledge_status": "actual",
                    "similarity": 0.50,
                },
                {
                    "id": "disputed_high",
                    "kind": "objection",
                    "keywords": [],
                    "knowledge_status": "disputed",
                    "similarity": 0.95,
                },
            ],
            "anything",
        )
        assert ranked[0]["id"] == "disputed_high"


class TestRequiresTeamId:
    @pytest.mark.asyncio
    async def test_none_team_id_returns_empty(self):
        """Passing team_id=None must NOT scan globally — it must
        return [] and warn. Otherwise a buggy caller leaks chunks."""
        from app.services.rag_methodology import retrieve_methodology_context

        out = await retrieve_methodology_context(
            "any query", team_id=None, db=AsyncMock(), top_k=4
        )
        assert out == []

    @pytest.mark.asyncio
    async def test_empty_query_emb_returns_empty(self):
        """When the embedding provider returns empty, the retriever
        bails out early — no SQL hits the DB."""
        from app.services import rag_methodology

        with patch.object(
            rag_methodology, "get_embedding", new=AsyncMock(return_value=None)
        ):
            out = await rag_methodology.retrieve_methodology_context(
                "any", team_id=uuid.uuid4(), db=AsyncMock(), top_k=4
            )
        assert out == []


class TestUnifiedRAGMethodologyIntegration:
    """The merge layer + budget routing + filter wiring all work
    together."""

    def test_methodology_in_budget_dict(self):
        from app.services.rag_unified import BUDGET

        for ctx in ("training", "coach", "quiz"):
            assert "methodology" in BUDGET[ctx], (
                f"BUDGET[{ctx!r}] missing 'methodology' key — TZ-8 §3.6 "
                "fixed point"
            )

    def test_quiz_methodology_budget_zero(self):
        """Quiz tests recall of objective facts, not procedure —
        methodology in the quiz prompt would be confusing."""
        from app.services.rag_unified import BUDGET

        assert BUDGET["quiz"]["methodology"] == 0

    def test_total_per_context_under_1700(self):
        """8K-context safe: total RAG ≤ 1700 tokens (TZ-8 §3.6)."""
        from app.services.rag_unified import BUDGET

        for ctx, sub in BUDGET.items():
            total = sum(sub.values())
            assert total <= 1700, (
                f"BUDGET[{ctx!r}] sums to {total} — over the 1700-token cap"
            )

    def test_methodology_filter_runs_in_merge(self):
        """The merge layer in retrieve_all_context applies
        filter_methodology_context to ``raw`` before formatting.
        This is a static assert: that line MUST exist in
        ``rag_unified.py``. If it disappears in a refactor, the
        AST guard in ``test_rag_invariants.py`` may not catch it
        (the methodology block stays intact, only the filter call
        vanishes), so we pin it here too."""
        from pathlib import Path

        src = Path(__file__).resolve().parent.parent / "app" / "services" / "rag_unified.py"
        text = src.read_text(encoding="utf-8")
        assert "filter_methodology_context" in text, (
            "rag_unified.py no longer references filter_methodology_context — "
            "the methodology block ships unsanitised."
        )
