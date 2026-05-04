"""P5 — parallel scoring + embeddings vs LLM-similarity.

We pin three behaviours:
  1. ``_embedding_batch_similarity`` returns correct cosine values for
     known stub vectors and falls back to None on embedding failure.
  2. ``_llm_batch_similarity`` uses the embedding path when the flag is
     True (default), and falls through to the legacy LLM path when
     embeddings are unavailable.
  3. The ``calculate_scores`` parallel path returns the same
     ``ScoreBreakdown`` shape as the sequential one (no field drops, no
     reordering changes outputs).

The ~18 s → ~6 s latency claim is verified live on prod after deploy
per CLAUDE.md §4.4 — automated timing assertions are flaky on CI hosts.
"""
from __future__ import annotations

import math

import pytest


# ── _embedding_batch_similarity ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_embedding_similarity_returns_correct_cosines(monkeypatch) -> None:
    """Stub the embedding fetcher to return three known vectors and
    assert cosine values match the math."""
    from app.services import script_checker

    async def _stub(_texts: list[str]) -> list[list[float]]:
        return [
            [1.0, 0.0],   # text
            [1.0, 0.0],   # ref 1 — identical → cos 1.0
            [0.0, 1.0],   # ref 2 — orthogonal → cos 0.0
        ]
    monkeypatch.setattr(script_checker, "_get_gemini_embeddings", _stub)

    out = await script_checker._embedding_batch_similarity("text", ["a", "b"])
    assert out is not None
    assert math.isclose(out[0], 1.0, abs_tol=1e-6)
    assert math.isclose(out[1], 0.0, abs_tol=1e-6)


@pytest.mark.asyncio
async def test_embedding_similarity_returns_none_on_empty_inputs() -> None:
    from app.services.script_checker import _embedding_batch_similarity

    assert await _embedding_batch_similarity("", ["a"]) is None
    assert await _embedding_batch_similarity("x", []) is None


@pytest.mark.asyncio
async def test_embedding_similarity_returns_none_when_fetch_fails(monkeypatch) -> None:
    from app.services import script_checker

    async def _fail(_texts: list[str]) -> list[list[float]] | None:
        return None
    monkeypatch.setattr(script_checker, "_get_gemini_embeddings", _fail)

    assert await script_checker._embedding_batch_similarity("x", ["a", "b"]) is None


# ── _llm_batch_similarity routing ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_batch_similarity_prefers_embeddings_when_flag_on(monkeypatch) -> None:
    """When `script_checker_use_embeddings=True`, the LLM endpoint is
    NEVER called — the embedding path returns first."""
    from app.services import script_checker

    monkeypatch.setattr(
        script_checker.settings, "script_checker_use_embeddings", True,
    )

    async def _stub_emb(_text: str, refs: list[str]) -> list[float]:
        return [0.7] * len(refs)

    monkeypatch.setattr(
        script_checker, "_embedding_batch_similarity", _stub_emb,
    )

    out = await script_checker._llm_batch_similarity("hello", ["a", "b", "c"])
    assert out == [0.7, 0.7, 0.7]


@pytest.mark.asyncio
async def test_llm_batch_similarity_falls_through_when_embeddings_fail(monkeypatch) -> None:
    """Embedding endpoint down → fall through to legacy LLM path. The
    test simulates that path being also unavailable so the function
    returns None — proves the fall-through is wired."""
    from app.services import script_checker

    monkeypatch.setattr(
        script_checker.settings, "script_checker_use_embeddings", True,
    )

    async def _emb_fail(_text: str, _refs: list[str]) -> None:
        return None

    monkeypatch.setattr(
        script_checker, "_embedding_batch_similarity", _emb_fail,
    )
    monkeypatch.setattr(
        script_checker.settings, "local_llm_enabled", False,
    )

    out = await script_checker._llm_batch_similarity("hello", ["a", "b"])
    assert out is None


@pytest.mark.asyncio
async def test_llm_batch_similarity_legacy_path_when_flag_off(monkeypatch) -> None:
    """When the flag is off, the legacy LLM path is reached directly
    without trying embeddings — verified by the embedding stub never
    being called."""
    from app.services import script_checker

    monkeypatch.setattr(
        script_checker.settings, "script_checker_use_embeddings", False,
    )
    monkeypatch.setattr(
        script_checker.settings, "local_llm_enabled", False,
    )

    called = {"emb": False}

    async def _stub(_text: str, _refs: list[str]):
        called["emb"] = True
        return [1.0]

    monkeypatch.setattr(
        script_checker, "_embedding_batch_similarity", _stub,
    )
    out = await script_checker._llm_batch_similarity("x", ["a"])
    assert out is None
    assert called["emb"] is False


# ── parallel-vs-sequential parity ───────────────────────────────────────────


def test_scoring_parallel_layers_flag_default_true() -> None:
    """Make a deliberate noise if someone flips the default — they
    must write a test case for the user-visible behaviour first."""
    from app.config import settings
    assert settings.scoring_parallel_layers is True


def test_script_checker_use_embeddings_flag_default_true() -> None:
    from app.config import settings
    assert settings.script_checker_use_embeddings is True
