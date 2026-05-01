"""TZ-8 PR-D — methodology telemetry contract.

Three contracts under test:

  1. ``log_methodology_retrieval`` writes a ``ChunkUsageLog`` row
     with ``chunk_kind='methodology'``, the right ``chunk_id``, and
     swallows DB exceptions (best-effort).
  2. ``record_methodology_outcome`` patches an existing row's
     ``answer_correct`` / ``score_delta`` without overwriting
     unrelated fields.
  3. ``get_methodology_chunk_stats`` returns the expected shape
     (counts + correct_rate + by_source_type breakdown).

We don't exercise the retrieval-side wiring (rag_methodology +
rag_unified.retrieve_all_context) end-to-end here because it
needs pgvector cosine_distance which SQLite can't run. The
``test_methodology_rag.py`` from PR-B already covers the in-Python
parts of that flow.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
async def team_with_user(db_session):
    """Persist one team + one user (the manager who triggers retrieval)."""
    from app.models.user import Team, User

    team = Team(name="Telemetry team")
    db_session.add(team)
    await db_session.commit()
    await db_session.refresh(team)

    user = User(
        email=f"telemetry_{uuid.uuid4().hex[:8]}@example.test",
        hashed_password="x",
        full_name="Telemetry User",
        team_id=team.id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return team, user


@pytest.fixture
async def methodology_chunk(db_session, team_with_user):
    """Persist one MethodologyChunk so the FK isn't required (it's gone in
    PR-D) but we have a real id to log against."""
    from app.models.methodology import MethodologyChunk, MethodologyKind

    team, _ = team_with_user
    chunk = MethodologyChunk(
        team_id=team.id,
        title="Telemetry chunk",
        body="…",
        kind=MethodologyKind.opener.value,
    )
    db_session.add(chunk)
    await db_session.commit()
    await db_session.refresh(chunk)
    return chunk


# ── Logging ────────────────────────────────────────────────────────────


class TestLogRetrieval:
    @pytest.mark.asyncio
    async def test_writes_row_with_correct_discriminator(
        self, db_session, team_with_user, methodology_chunk
    ):
        from app.models.rag import ChunkUsageLog
        from app.services.methodology_telemetry import log_methodology_retrieval
        from sqlalchemy import select

        _, user = team_with_user
        log_id = await log_methodology_retrieval(
            db_session,
            user_id=user.id,
            chunk_id=methodology_chunk.id,
            source_type="coach",
            query_text="how to handle objection",
            relevance_score=0.84,
            retrieval_rank=2,
        )
        assert log_id is not None
        await db_session.commit()

        row = (
            await db_session.execute(
                select(ChunkUsageLog).where(ChunkUsageLog.id == log_id)
            )
        ).scalar_one()
        assert row.chunk_kind == "methodology"
        assert row.chunk_id == methodology_chunk.id
        assert row.user_id == user.id
        assert row.source_type == "coach"
        assert row.relevance_score == pytest.approx(0.84)
        assert row.retrieval_rank == 2
        assert row.was_answered is False  # outcome not recorded yet

    @pytest.mark.asyncio
    async def test_swallows_db_failure(self, monkeypatch):
        """Best-effort contract: when the DB blows up, return None,
        don't raise — the user-facing retrieval must still succeed.
        """
        from app.services.methodology_telemetry import log_methodology_retrieval

        bad_db = AsyncMock()
        bad_db.add = AsyncMock(side_effect=RuntimeError("postgres exploded"))
        bad_db.flush = AsyncMock(side_effect=RuntimeError("nope"))

        out = await log_methodology_retrieval(
            bad_db,
            user_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            source_type="training",
        )
        assert out is None  # logged, swallowed


# ── Outcome ────────────────────────────────────────────────────────────


class TestRecordOutcome:
    @pytest.mark.asyncio
    async def test_patches_existing_row_with_correct_flag(
        self, db_session, team_with_user, methodology_chunk
    ):
        from app.models.rag import ChunkUsageLog
        from app.services.methodology_telemetry import (
            log_methodology_retrieval,
            record_methodology_outcome,
        )
        from sqlalchemy import select

        _, user = team_with_user
        log_id = await log_methodology_retrieval(
            db_session,
            user_id=user.id,
            chunk_id=methodology_chunk.id,
            source_type="training",
        )
        assert log_id is not None
        await db_session.commit()

        ok = await record_methodology_outcome(
            db_session,
            log_id,
            answer_correct=True,
            score_delta=12.5,
            user_answer_excerpt="re-stated the price after handling the objection",
        )
        assert ok is True
        await db_session.commit()

        row = (
            await db_session.execute(
                select(ChunkUsageLog).where(ChunkUsageLog.id == log_id)
            )
        ).scalar_one()
        assert row.was_answered is True
        assert row.answer_correct is True
        assert row.score_delta == pytest.approx(12.5)
        assert "re-stated the price" in (row.user_answer_excerpt or "")
        # Discriminator + chunk_id untouched.
        assert row.chunk_kind == "methodology"
        assert row.chunk_id == methodology_chunk.id

    @pytest.mark.asyncio
    async def test_truncates_long_excerpts(
        self, db_session, team_with_user, methodology_chunk
    ):
        from app.models.rag import ChunkUsageLog
        from app.services.methodology_telemetry import (
            log_methodology_retrieval,
            record_methodology_outcome,
        )
        from sqlalchemy import select

        _, user = team_with_user
        log_id = await log_methodology_retrieval(
            db_session,
            user_id=user.id,
            chunk_id=methodology_chunk.id,
            source_type="training",
        )
        await db_session.commit()

        long_excerpt = "x" * 1500
        await record_methodology_outcome(
            db_session, log_id, answer_correct=False,
            user_answer_excerpt=long_excerpt,
        )
        await db_session.commit()

        row = (
            await db_session.execute(
                select(ChunkUsageLog).where(ChunkUsageLog.id == log_id)
            )
        ).scalar_one()
        assert len(row.user_answer_excerpt or "") <= 500


# ── Aggregation (read side) ────────────────────────────────────────────


class TestChunkStats:
    @pytest.mark.asyncio
    async def test_counts_and_rates(
        self, db_session, team_with_user, methodology_chunk
    ):
        from app.services.methodology_telemetry import (
            log_methodology_retrieval,
            record_methodology_outcome,
            get_methodology_chunk_stats,
        )

        _, user = team_with_user

        # Three retrievals: 2 answered correctly, 1 answered incorrectly.
        for source in ("coach", "coach", "training"):
            log_id = await log_methodology_retrieval(
                db_session,
                user_id=user.id,
                chunk_id=methodology_chunk.id,
                source_type=source,
            )
            await record_methodology_outcome(
                db_session,
                log_id,
                answer_correct=(source == "coach"),  # coach=True, training=False
            )
        await db_session.commit()

        stats = await get_methodology_chunk_stats(
            db_session, chunk_id=methodology_chunk.id, days=30
        )
        assert stats["chunk_id"] == str(methodology_chunk.id)
        assert stats["retrieval_count"] == 3
        assert stats["answered_count"] == 3
        assert stats["correct_count"] == 2
        assert stats["correct_rate"] == pytest.approx(2 / 3)
        assert stats["by_source_type"] == {"coach": 2, "training": 1}
        assert stats["last_used_at"] is not None

    @pytest.mark.asyncio
    async def test_no_data_returns_zero_counts_and_none_rate(
        self, db_session, methodology_chunk
    ):
        from app.services.methodology_telemetry import get_methodology_chunk_stats

        stats = await get_methodology_chunk_stats(
            db_session, chunk_id=methodology_chunk.id, days=30
        )
        assert stats["retrieval_count"] == 0
        assert stats["answered_count"] == 0
        assert stats["correct_count"] == 0
        assert stats["correct_rate"] is None
        assert stats["last_used_at"] is None
        assert stats["by_source_type"] == {}


# ── Model + migration smoke ────────────────────────────────────────────


class TestChunkKindSchema:
    @pytest.mark.asyncio
    async def test_chunk_kind_defaults_to_legal(
        self, db_session, team_with_user
    ):
        """Pre-PR-D rows had no discriminator. The migration backfills
        them as 'legal'. New rows created without an explicit kind
        also land as 'legal' (server_default).
        """
        from app.models.rag import ChunkUsageLog
        from sqlalchemy import select

        _, user = team_with_user
        log = ChunkUsageLog(
            chunk_id=uuid.uuid4(),
            user_id=user.id,
            source_type="training",
        )
        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)
        assert log.chunk_kind == "legal"

    @pytest.mark.asyncio
    async def test_chunk_kind_accepts_three_values(
        self, db_session, team_with_user
    ):
        """All three discriminators round-trip through the column."""
        from app.models.rag import ChunkUsageLog
        from sqlalchemy import select

        _, user = team_with_user
        for kind in ("legal", "wiki", "methodology"):
            db_session.add(
                ChunkUsageLog(
                    chunk_id=uuid.uuid4(),
                    chunk_kind=kind,
                    user_id=user.id,
                    source_type="training",
                )
            )
        await db_session.commit()

        rows = (
            await db_session.execute(
                select(ChunkUsageLog.chunk_kind).where(
                    ChunkUsageLog.user_id == user.id
                )
            )
        ).scalars().all()
        assert set(rows) >= {"legal", "wiki", "methodology"}
