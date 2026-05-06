"""PR-MC regression tests for the multiple-choice enricher.

Pin the contract:
  - chunks with cached choices skip the LLM round-trip
  - shuffle never returns the same order (well, it might 1/6, but the
    correct_choice_index always tracks the actual position of the
    correct text, regardless of shuffle outcome)
  - questions without a derivable correct answer return unchanged
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.knowledge_quiz import (
    QuizQuestion,
    enrich_question_with_choices,
)


@pytest.mark.asyncio
async def test_enrich_uses_cached_choices_from_chunk(db_session):
    """If LegalKnowledgeChunk.choices is already populated, skip the LLM."""
    from app.models.rag import LegalKnowledgeChunk

    chunk = LegalKnowledgeChunk(
        id=uuid.uuid4(),
        category="eligibility",
        fact_text="Минимальный долг для подачи заявления о банкротстве — 500 000 руб.",
        law_article="127-ФЗ ст. 213.3",
        choices=["500 000 руб", "100 000 руб", "1 000 000 руб"],
        correct_choice_index=0,
    )
    db_session.add(chunk)
    await db_session.commit()

    q = QuizQuestion(
        question_text="Минимальный долг?",
        category="eligibility",
        difficulty=3,
        chunk_id=chunk.id,
    )

    # Patch the LLM call so we can assert it was NOT used (cache hit)
    with patch(
        "app.services.knowledge_quiz._generate_mc_distractors",
        new=AsyncMock(side_effect=AssertionError("LLM should not be called on cache hit")),
    ):
        result = await enrich_question_with_choices(db_session, q)

    assert result.choices == ["500 000 руб", "100 000 руб", "1 000 000 руб"]
    assert result.correct_choice_index == 0


@pytest.mark.asyncio
async def test_enrich_calls_llm_when_chunk_has_no_choices(db_session):
    """When choices column is empty, LLM is called and the result is cached."""
    from app.models.rag import LegalKnowledgeChunk

    chunk = LegalKnowledgeChunk(
        id=uuid.uuid4(),
        category="eligibility",
        fact_text="Срок процедуры реализации имущества — до 6 месяцев.",
        law_article="127-ФЗ ст. 213.24",
        correct_response_hint="6 месяцев",
        # No choices yet
    )
    db_session.add(chunk)
    await db_session.commit()

    q = QuizQuestion(
        question_text="Сколько длится реализация имущества?",
        category="eligibility",
        difficulty=3,
        chunk_id=chunk.id,
        blitz_answer="6 месяцев",
    )

    fake_distractors = ["12 месяцев", "30 дней"]
    with patch(
        "app.services.knowledge_quiz._generate_mc_distractors",
        new=AsyncMock(return_value=fake_distractors),
    ):
        result = await enrich_question_with_choices(db_session, q)

    assert result.choices is not None
    assert len(result.choices) == 3
    assert result.correct_choice_index is not None
    # The correct text must be at the recorded index
    assert result.choices[result.correct_choice_index] == "6 месяцев"
    # Both distractors are present
    assert "12 месяцев" in result.choices
    assert "30 дней" in result.choices

    # Cache: re-fetching the chunk shows the choices stored
    await db_session.refresh(chunk)
    assert chunk.choices is not None and len(chunk.choices) == 3
    assert chunk.correct_choice_index is not None


@pytest.mark.asyncio
async def test_distractor_fn_imports_asyncio_at_module_level():
    """Regression for the prod NameError (2026-05-06): the
    _generate_mc_distractors function references ``asyncio.wait_for``
    and ``asyncio.TimeoutError``. Without ``import asyncio`` at module
    level, the very first call raised NameError BEFORE reaching the
    try/except wrapper, so the enricher silently fell through to the
    fallback path and every prod session ended up free-text.

    Confirms the import + that the function returns either real LLM
    distractors or the safe fallback list — never raises NameError.
    """
    from app.services import knowledge_quiz as kq

    # Import surface check: asyncio must be in the module's namespace.
    assert hasattr(kq, "asyncio"), "knowledge_quiz must import asyncio"

    # Simulate LLM unavailable — the function should hit the except
    # branch (which uses asyncio.TimeoutError) and return fallback,
    # NOT raise NameError.
    with patch(
        "app.services.knowledge_quiz.generate_response",
        new=AsyncMock(side_effect=RuntimeError("LLM down")),
    ):
        result = await kq._generate_mc_distractors(
            question_text="?",
            correct_answer="X",
        )
    assert isinstance(result, list)
    assert len(result) == 2  # generic fallback


@pytest.mark.asyncio
async def test_enrich_returns_unchanged_when_no_correct_answer():
    """If neither blitz_answer nor RAG result is available, return the
    question untouched so the caller falls back to free text."""
    db = AsyncMock()
    q = QuizQuestion(
        question_text="?",
        category="x",
        difficulty=1,
        chunk_id=None,  # no chunk lookup
    )
    result = await enrich_question_with_choices(db, q)
    assert result.choices is None
    assert result.correct_choice_index is None
