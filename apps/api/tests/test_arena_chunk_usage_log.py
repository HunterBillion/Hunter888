"""Tests for the chunk-usage telemetry врезка in pvp_judge.judge_round (PR-5).

Locks in the contract that closes methodology's feedback loop:

* When ``duel_id`` is supplied, every retrieved chunk is logged via
  ``log_chunk_usage`` with ``source_type="pvp_duel"`` and the duel id.
* When ``duel_id`` is None (calibration / replay path), telemetry is
  silently skipped — backward-compat with existing callers.
* When the judge degrades (LLM failure / parse error), per-chunk
  outcome recording is skipped — we don't pollute analytics with the
  neutral 25/15/10 fallback's "wrong" verdict.
* Per-chunk outcome derives from ``legal_details[*].accuracy``:
  ``correct``/``correct_cited`` → ``answer_correct=True``, anything
  else → ``answer_correct=False``. Chunks not mentioned in
  legal_details remain ``was_answered=False``.
* Logging failures NEVER block the judge path (defensive try/except).

The judge LLM call itself is mocked at the ``generate_response`` layer
so tests run without API keys; what we exercise is the telemetry
plumbing, not the LLM.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.pvp import DuelDifficulty
from app.services.rag_legal import RAGContext, RAGResult


def _make_rag_context(*, chunks: list[tuple[uuid.UUID, str]]) -> RAGContext:
    """Helper: build a RAGContext with given (chunk_id, law_article) pairs."""
    results = [
        RAGResult(
            chunk_id=cid,
            category="general",
            fact_text=f"Fact for {article}",
            law_article=article,
            relevance_score=0.9 - i * 0.1,
            knowledge_status="approved",
            common_errors=[],
            correct_response_hint="",
            difficulty_level=2,
            is_court_practice=False,
            court_case_reference=None,
            question_templates=[],
        )
        for i, (cid, article) in enumerate(chunks)
    ]
    return RAGContext(query="test query", results=results, method="hybrid", retrieval_ms=12.0)


def _judge_response_payload(legal_details: list[dict]) -> str:
    """Build a fake LLM JSON response for the judge."""
    import json
    return json.dumps({
        "selling_score": 35,
        "selling_breakdown": {"objection_handling": 12, "persuasion": 8, "structure": 8, "closing": 5, "legal_knowledge": 2},
        "acting_score": 22,
        "acting_breakdown": {"archetype_authenticity": 8, "emotional_depth": 7, "realism": 7},
        "legal_accuracy": 14,
        "legal_details": legal_details,
        "flags": [],
        "summary": "Test verdict",
        "coaching_tip": "Test tip",
        "ideal_reply": "Test ideal",
        "key_articles": [],
    })


@pytest.fixture
def fake_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def chunk_ids():
    return [uuid.uuid4(), uuid.uuid4()]


# ── 1. Skip telemetry when duel_id is None ─────────────────────────────────


@pytest.mark.asyncio
async def test_skips_log_chunk_usage_when_duel_id_is_none(fake_db, chunk_ids):
    """Calibration / replay callers don't pass duel_id → no telemetry call."""
    from app.services import pvp_judge

    rag = _make_rag_context(chunks=[(chunk_ids[0], "ст. 213.3")])
    fake_llm = MagicMock(content=_judge_response_payload([]))

    with patch("app.services.pvp_judge.retrieve_legal_context", AsyncMock(return_value=rag)), \
         patch("app.services.pvp_judge.generate_response", AsyncMock(return_value=fake_llm)), \
         patch("app.services.pvp_judge.log_chunk_usage", AsyncMock()) as mock_log, \
         patch("app.services.pvp_judge.record_chunk_outcome", AsyncMock()) as mock_outcome:
        await pvp_judge.judge_round(
            dialog=[{"role": "seller", "text": "При долге 500к..."}],
            seller_id=uuid.uuid4(), client_id=uuid.uuid4(),
            seller_name="P1", client_name="P2",
            archetype="aggressive_boss",
            difficulty=DuelDifficulty.medium,
            round_number=1,
            db=fake_db,
            duel_id=None,  # ← key
        )

    mock_log.assert_not_called()
    mock_outcome.assert_not_called()


# ── 2. Log_chunk_usage IS called with the right args when duel_id given ────


@pytest.mark.asyncio
async def test_logs_each_retrieved_chunk_when_duel_id_given(fake_db, chunk_ids):
    from app.services import pvp_judge

    rag = _make_rag_context(chunks=[
        (chunk_ids[0], "ст. 213.3"),
        (chunk_ids[1], "ст. 71"),
    ])
    fake_llm = MagicMock(content=_judge_response_payload([]))
    duel_id = uuid.uuid4()
    seller_id = uuid.uuid4()

    with patch("app.services.pvp_judge.retrieve_legal_context", AsyncMock(return_value=rag)), \
         patch("app.services.pvp_judge.generate_response", AsyncMock(return_value=fake_llm)), \
         patch("app.services.pvp_judge.log_chunk_usage", AsyncMock()) as mock_log, \
         patch("app.services.pvp_judge.record_chunk_outcome", AsyncMock()):
        await pvp_judge.judge_round(
            dialog=[{"role": "seller", "text": "test"}],
            seller_id=seller_id, client_id=uuid.uuid4(),
            seller_name="P1", client_name="P2",
            archetype="aggressive_boss",
            difficulty=DuelDifficulty.medium,
            round_number=1,
            db=fake_db,
            duel_id=duel_id,
        )

    mock_log.assert_awaited_once()
    call_kwargs = mock_log.call_args.kwargs
    assert call_kwargs["source_type"] == "pvp_duel"
    assert call_kwargs["source_id"] == duel_id
    assert call_kwargs["user_id"] == seller_id
    assert sorted(call_kwargs["chunk_ids"]) == sorted(chunk_ids)
    assert call_kwargs["retrieval_method"] == "hybrid"
    assert call_kwargs["query_text"] == "test"


# ── 3. record_chunk_outcome receives correct=True for "correct" verdicts ───


@pytest.mark.asyncio
async def test_records_correct_outcome_when_legal_details_say_correct(fake_db, chunk_ids):
    from app.services import pvp_judge

    rag = _make_rag_context(chunks=[
        (chunk_ids[0], "ст. 213.3"),
    ])
    legal_details = [
        {"claim": "Цитата ст. 213.3 — порог банкротства", "accuracy": "correct_cited"},
    ]
    fake_llm = MagicMock(content=_judge_response_payload(legal_details))
    duel_id = uuid.uuid4()

    captured_outcomes: list[dict] = []
    async def _capture_outcome(db, **kwargs):
        captured_outcomes.append(kwargs)

    with patch("app.services.pvp_judge.retrieve_legal_context", AsyncMock(return_value=rag)), \
         patch("app.services.pvp_judge.generate_response", AsyncMock(return_value=fake_llm)), \
         patch("app.services.pvp_judge.log_chunk_usage", AsyncMock()), \
         patch("app.services.pvp_judge.record_chunk_outcome", side_effect=_capture_outcome):
        await pvp_judge.judge_round(
            dialog=[{"role": "seller", "text": "Цитата ст. 213.3 — порог банкротства"}],
            seller_id=uuid.uuid4(), client_id=uuid.uuid4(),
            seller_name="P1", client_name="P2",
            archetype="aggressive_boss",
            difficulty=DuelDifficulty.medium,
            round_number=1,
            db=fake_db,
            duel_id=duel_id,
        )

    assert len(captured_outcomes) == 1
    assert captured_outcomes[0]["chunk_id"] == chunk_ids[0]
    assert captured_outcomes[0]["answer_correct"] is True
    assert captured_outcomes[0]["source_type"] == "pvp_duel"
    assert captured_outcomes[0]["source_id"] == duel_id


# ── 4. Incorrect verdict logged with answer_correct=False ──────────────────


@pytest.mark.asyncio
async def test_records_incorrect_outcome_when_legal_details_say_wrong(fake_db, chunk_ids):
    from app.services import pvp_judge

    rag = _make_rag_context(chunks=[(chunk_ids[0], "ст. 213.3")])
    legal_details = [
        {"claim": "Неправильная ссылка на ст. 213.3", "accuracy": "incorrect"},
    ]
    fake_llm = MagicMock(content=_judge_response_payload(legal_details))

    captured: list[dict] = []
    async def _capture(db, **kwargs):
        captured.append(kwargs)

    with patch("app.services.pvp_judge.retrieve_legal_context", AsyncMock(return_value=rag)), \
         patch("app.services.pvp_judge.generate_response", AsyncMock(return_value=fake_llm)), \
         patch("app.services.pvp_judge.log_chunk_usage", AsyncMock()), \
         patch("app.services.pvp_judge.record_chunk_outcome", side_effect=_capture):
        await pvp_judge.judge_round(
            dialog=[{"role": "seller", "text": "Неправильная ссылка на ст. 213.3"}],
            seller_id=uuid.uuid4(), client_id=uuid.uuid4(),
            seller_name="P1", client_name="P2",
            archetype="aggressive_boss",
            difficulty=DuelDifficulty.medium,
            round_number=1,
            db=fake_db,
            duel_id=uuid.uuid4(),
        )

    assert len(captured) == 1
    assert captured[0]["answer_correct"] is False


# ── 5. Chunk not mentioned in legal_details → outcome NOT recorded ─────────


@pytest.mark.asyncio
async def test_unmentioned_chunks_do_not_get_outcome(fake_db, chunk_ids):
    from app.services import pvp_judge

    # Two chunks retrieved, only one addressed in legal_details.
    rag = _make_rag_context(chunks=[
        (chunk_ids[0], "ст. 213.3"),  # addressed
        (chunk_ids[1], "ст. 71"),     # not addressed
    ])
    legal_details = [
        {"claim": "Про ст. 213.3", "accuracy": "correct"},
    ]
    fake_llm = MagicMock(content=_judge_response_payload(legal_details))

    captured: list[dict] = []
    async def _capture(db, **kwargs):
        captured.append(kwargs)

    with patch("app.services.pvp_judge.retrieve_legal_context", AsyncMock(return_value=rag)), \
         patch("app.services.pvp_judge.generate_response", AsyncMock(return_value=fake_llm)), \
         patch("app.services.pvp_judge.log_chunk_usage", AsyncMock()), \
         patch("app.services.pvp_judge.record_chunk_outcome", side_effect=_capture):
        await pvp_judge.judge_round(
            dialog=[{"role": "seller", "text": "Про ст. 213.3 банкротство"}],
            seller_id=uuid.uuid4(), client_id=uuid.uuid4(),
            seller_name="P1", client_name="P2",
            archetype="aggressive_boss",
            difficulty=DuelDifficulty.medium,
            round_number=1,
            db=fake_db,
            duel_id=uuid.uuid4(),
        )

    # Only the addressed chunk gets outcome.
    assert len(captured) == 1
    assert captured[0]["chunk_id"] == chunk_ids[0]


# ── 6. Degraded judge → outcome NOT recorded (don't pollute analytics) ─────


@pytest.mark.asyncio
async def test_degraded_judge_skips_outcome_recording(fake_db, chunk_ids):
    """When the judge LLM fails (timeout/error), we fall to the neutral
    25/15/10. Recording per-chunk outcomes from THAT verdict would teach
    the methodology dashboard that every chunk was "wrong" — that's
    misleading data. Skip outcome recording, keep just the retrieval log.
    """
    from app.services import pvp_judge

    rag = _make_rag_context(chunks=[(chunk_ids[0], "ст. 213.3")])
    # generate_response raises → judge falls into the except branch and
    # marks _degraded=True.
    failing_llm = AsyncMock(side_effect=Exception("LLM down"))

    with patch("app.services.pvp_judge.retrieve_legal_context", AsyncMock(return_value=rag)), \
         patch("app.services.pvp_judge.generate_response", failing_llm), \
         patch("app.services.pvp_judge.log_chunk_usage", AsyncMock()) as mock_log, \
         patch("app.services.pvp_judge.record_chunk_outcome", AsyncMock()) as mock_outcome:
        seller_score, _ = await pvp_judge.judge_round(
            dialog=[{"role": "seller", "text": "test"}],
            seller_id=uuid.uuid4(), client_id=uuid.uuid4(),
            seller_name="P1", client_name="P2",
            archetype="aggressive_boss",
            difficulty=DuelDifficulty.medium,
            round_number=1,
            db=fake_db,
            duel_id=uuid.uuid4(),
        )

    # Retrieval is still logged (it happened before the LLM call).
    mock_log.assert_awaited_once()
    # Outcome is NOT recorded — that's the degraded-skip rule.
    mock_outcome.assert_not_called()
    assert seller_score.degraded is True


# ── 7. Logging failures must NOT break the judge path ──────────────────────


@pytest.mark.asyncio
async def test_log_chunk_usage_exception_does_not_break_judge(fake_db, chunk_ids):
    from app.services import pvp_judge

    rag = _make_rag_context(chunks=[(chunk_ids[0], "ст. 213.3")])
    fake_llm = MagicMock(content=_judge_response_payload([]))
    failing_log = AsyncMock(side_effect=Exception("DB down"))

    with patch("app.services.pvp_judge.retrieve_legal_context", AsyncMock(return_value=rag)), \
         patch("app.services.pvp_judge.generate_response", AsyncMock(return_value=fake_llm)), \
         patch("app.services.pvp_judge.log_chunk_usage", failing_log), \
         patch("app.services.pvp_judge.record_chunk_outcome", AsyncMock()):
        seller_score, client_score = await pvp_judge.judge_round(
            dialog=[{"role": "seller", "text": "test"}],
            seller_id=uuid.uuid4(), client_id=uuid.uuid4(),
            seller_name="P1", client_name="P2",
            archetype="aggressive_boss",
            difficulty=DuelDifficulty.medium,
            round_number=1,
            db=fake_db,
            duel_id=uuid.uuid4(),
        )

    # Judge returns scores normally despite the logging failure.
    assert seller_score.total > 0
    assert seller_score.degraded is False


# ── 8. record_chunk_outcome exception also doesn't break ───────────────────


@pytest.mark.asyncio
async def test_record_chunk_outcome_exception_does_not_break_judge(fake_db, chunk_ids):
    from app.services import pvp_judge

    rag = _make_rag_context(chunks=[(chunk_ids[0], "ст. 213.3")])
    legal_details = [{"claim": "ст. 213.3", "accuracy": "correct"}]
    fake_llm = MagicMock(content=_judge_response_payload(legal_details))
    failing_outcome = AsyncMock(side_effect=Exception("DB down"))

    with patch("app.services.pvp_judge.retrieve_legal_context", AsyncMock(return_value=rag)), \
         patch("app.services.pvp_judge.generate_response", AsyncMock(return_value=fake_llm)), \
         patch("app.services.pvp_judge.log_chunk_usage", AsyncMock()), \
         patch("app.services.pvp_judge.record_chunk_outcome", failing_outcome):
        seller_score, _ = await pvp_judge.judge_round(
            dialog=[{"role": "seller", "text": "test"}],
            seller_id=uuid.uuid4(), client_id=uuid.uuid4(),
            seller_name="P1", client_name="P2",
            archetype="aggressive_boss",
            difficulty=DuelDifficulty.medium,
            round_number=1,
            db=fake_db,
            duel_id=uuid.uuid4(),
        )

    # Judge still completes and returns valid scores.
    assert seller_score.total > 0
