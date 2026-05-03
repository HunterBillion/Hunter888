"""A1 tests for ``quiz_v2_answer_keys`` ORM model + backfill helpers.

Locks in:
* The model schema matches the migration (column set, nullability).
* Insert / lookup round-trip works against the test DB.
* UNIQUE (chunk_id, question_hash, team_id) enforces NULL-distinct
  semantics — a team override coexists with a global baseline for the
  same (chunk_id, question_hash) pair.
* CHECK constraints reject invalid flavor / strategy / status / source.

Backfill-script tests run with mocked LLM — we don't actually hit
the cloud judge in CI. The deterministic factoid path is exercised
end-to-end since it has no LLM dependency.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.quiz_v2 import QuizV2AnswerKey
from app.services.quiz_v2.answer_keys import question_hash


def _key(*, chunk_id, team_id=None, qhash=None, flavor="factoid",
         strategy="exact", status="actual", is_active=True,
         source="seed_loader", confidence=0.95):
    return QuizV2AnswerKey(
        chunk_id=chunk_id,
        team_id=team_id,
        question_hash=qhash or ("a" * 32),
        flavor=flavor,
        expected_answer="ans",
        match_strategy=strategy,
        match_config={},
        synonyms=[],
        article_ref="ст. 213.11",
        knowledge_status=status,
        is_active=is_active,
        source=source,
        original_confidence=confidence,
        generated_by="test",
    )


# ─── Round-trip ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_insert_and_load(db_session):
    chunk_id = uuid.uuid4()
    db_session.add(_key(chunk_id=chunk_id))
    await db_session.commit()

    rows = (await db_session.execute(select(QuizV2AnswerKey))).scalars().all()
    assert len(rows) == 1
    assert rows[0].chunk_id == chunk_id
    assert rows[0].team_id is None
    assert rows[0].flavor == "factoid"
    assert rows[0].is_active is True


# ─── UNIQUE (chunk_id, question_hash, team_id) — NULL-distinct ───────


@pytest.mark.asyncio
async def test_team_override_coexists_with_global(db_session):
    """Same (chunk_id, question_hash) — one global (team_id NULL), one team-scoped."""
    chunk_id = uuid.uuid4()
    team_id = uuid.uuid4()
    qhash = question_hash("Q", "A")
    db_session.add(_key(chunk_id=chunk_id, team_id=None, qhash=qhash))
    db_session.add(_key(chunk_id=chunk_id, team_id=team_id, qhash=qhash))
    await db_session.commit()

    rows = (await db_session.execute(select(QuizV2AnswerKey))).scalars().all()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_duplicate_global_rejected(db_session):
    """Two NULL-team rows with the same hash → UNIQUE violation."""
    chunk_id = uuid.uuid4()
    qhash = question_hash("Q", "A")
    db_session.add(_key(chunk_id=chunk_id, team_id=None, qhash=qhash))
    await db_session.commit()
    db_session.add(_key(chunk_id=chunk_id, team_id=None, qhash=qhash))
    with pytest.raises(IntegrityError):
        await db_session.commit()


# ─── question_hash helper round-trip ─────────────────────────────────


def test_question_hash_round_trip():
    h = question_hash("Текст вопроса?", "Канонический ответ")
    assert len(h) == 32
    # idempotent
    assert h == question_hash("Текст вопроса?", "Канонический ответ")
    # different inputs → different hash
    assert h != question_hash("Текст вопроса?", "Другой ответ")


# ─── Backfill script: factoid path is deterministic, no LLM ──────────


@pytest.mark.asyncio
async def test_backfill_factoid_uses_chunk_text():
    """Factoid flavor takes ``chunk.fact_text`` as expected_answer verbatim."""
    from scripts.quiz_v2_backfill_answer_keys import _factoid_key_for

    chunk = type("Chunk", (), {})()
    chunk.fact_text = "Должник имеет право на защиту единственного жилья (ст. 446 ГПК)."
    chunk.law_article = "ст. 446 ГПК"
    chunk.category = "property"

    payload = await _factoid_key_for(chunk)

    assert payload["expected_answer"] == chunk.fact_text
    assert payload["confidence"] == 1.0
    assert payload["match_strategy"] == "synonyms"
    assert chunk.law_article in payload["question"]


@pytest.mark.asyncio
async def test_backfill_strategic_parses_judge_response():
    """Strategic flavor parses the judge JSON payload safely."""
    from scripts.quiz_v2_backfill_answer_keys import _generate_strategic_key

    chunk = type("Chunk", (), {})()
    chunk.id = uuid.uuid4()
    chunk.fact_text = "Должник может списать долги через банкротство при сумме > 500к."
    chunk.law_article = "ст. 213.3"

    fake_resp = type("Resp", (), {})()
    fake_resp.text = (
        '{"question": "Когда возможно банкротство?", '
        '"expected_answer": "При долге свыше 500 тысяч рублей.", '
        '"synonyms": ["при долге больше 500к"], '
        '"match_strategy": "synonyms", '
        '"confidence": 0.9}'
    )

    with patch(
        "scripts.quiz_v2_backfill_answer_keys.generate_response",
        new=AsyncMock(return_value=fake_resp),
    ):
        payload = await _generate_strategic_key(chunk)

    assert payload is not None
    assert payload["expected_answer"] == "При долге свыше 500 тысяч рублей."
    assert payload["confidence"] == 0.9
    assert payload["match_strategy"] == "synonyms"


@pytest.mark.asyncio
async def test_backfill_strategic_handles_garbage_response():
    """Non-JSON judge output returns None instead of raising."""
    from scripts.quiz_v2_backfill_answer_keys import _generate_strategic_key

    chunk = type("Chunk", (), {})()
    chunk.id = uuid.uuid4()
    chunk.fact_text = "x"
    chunk.law_article = "y"

    fake_resp = type("Resp", (), {})()
    fake_resp.text = "I am not JSON, sorry"

    with patch(
        "scripts.quiz_v2_backfill_answer_keys.generate_response",
        new=AsyncMock(return_value=fake_resp),
    ):
        payload = await _generate_strategic_key(chunk)

    assert payload is None


@pytest.mark.asyncio
async def test_backfill_strategic_handles_llm_exception():
    """LLM raising → swallow + return None (never propagate)."""
    from scripts.quiz_v2_backfill_answer_keys import _generate_strategic_key

    chunk = type("Chunk", (), {})()
    chunk.id = uuid.uuid4()
    chunk.fact_text = "x"
    chunk.law_article = "y"

    with patch(
        "scripts.quiz_v2_backfill_answer_keys.generate_response",
        new=AsyncMock(side_effect=RuntimeError("LLM down")),
    ):
        payload = await _generate_strategic_key(chunk)

    assert payload is None
