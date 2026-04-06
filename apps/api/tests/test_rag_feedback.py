"""Tests for RAG feedback loop service (services/rag_feedback.py).

Covers:
  - Chunk usage logging
  - Answer outcome recording
  - Feedback collection from training/pvp/quiz/blitz
  - Effectiveness recalculation
  - Analytics queries
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# log_chunk_usage tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestLogChunkUsage:
    """Test chunk retrieval logging."""

    @pytest.mark.asyncio
    async def test_logs_single_chunk(self, mock_db):
        from app.services.rag_legal import log_chunk_usage

        chunk_id = uuid.uuid4()
        user_id = uuid.uuid4()

        await log_chunk_usage(
            mock_db,
            chunk_ids=[chunk_id],
            user_id=user_id,
            source_type="quiz",
            retrieval_method="embedding",
        )

        # Should add a ChunkUsageLog object
        mock_db.add.assert_called_once()
        # Should update retrieval_count on chunks
        mock_db.execute.assert_called()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_logs_multiple_chunks(self, mock_db):
        from app.services.rag_legal import log_chunk_usage

        chunk_ids = [uuid.uuid4() for _ in range(3)]
        user_id = uuid.uuid4()

        await log_chunk_usage(
            mock_db,
            chunk_ids=chunk_ids,
            user_id=user_id,
            source_type="training",
            source_id=uuid.uuid4(),
        )

        # Should add 3 log entries
        assert mock_db.add.call_count == 3

    @pytest.mark.asyncio
    async def test_empty_chunk_ids_noop(self, mock_db):
        from app.services.rag_legal import log_chunk_usage

        await log_chunk_usage(
            mock_db,
            chunk_ids=[],
            user_id=uuid.uuid4(),
            source_type="quiz",
        )

        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_error_handled_gracefully(self, mock_db):
        from app.services.rag_legal import log_chunk_usage

        mock_db.flush = AsyncMock(side_effect=Exception("DB down"))

        # Should NOT raise — non-critical
        await log_chunk_usage(
            mock_db,
            chunk_ids=[uuid.uuid4()],
            user_id=uuid.uuid4(),
            source_type="blitz",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# record_chunk_outcome tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecordChunkOutcome:
    """Test answer outcome recording."""

    @pytest.mark.asyncio
    async def test_correct_answer_increments_count(self, mock_db):
        from app.services.rag_legal import record_chunk_outcome

        chunk_id = uuid.uuid4()

        await record_chunk_outcome(
            mock_db,
            chunk_id=chunk_id,
            user_id=uuid.uuid4(),
            source_type="quiz",
            answer_correct=True,
        )

        # Should call execute (to update correct_answer_count)
        assert mock_db.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_incorrect_answer_increments_error_frequency(self, mock_db):
        from app.services.rag_legal import record_chunk_outcome

        await record_chunk_outcome(
            mock_db,
            chunk_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            source_type="training",
            answer_correct=False,
        )

        # incorrect_answer_count + error_frequency both updated = 2 execute calls
        assert mock_db.execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_discovered_error_stored(self, mock_db):
        from app.services.rag_legal import record_chunk_outcome

        # Mock finding existing usage log
        mock_result = AsyncMock()
        mock_log = MagicMock()
        mock_log.was_answered = False
        mock_result.scalar_one_or_none.return_value = mock_log
        mock_db.execute = AsyncMock(return_value=mock_result)

        source_id = uuid.uuid4()
        await record_chunk_outcome(
            mock_db,
            chunk_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            source_type="quiz",
            source_id=source_id,
            answer_correct=False,
            discovered_error="Назвал порог 300 000 вместо 500 000",
        )

        assert mock_log.discovered_error == "Назвал порог 300 000 вместо 500 000"


# ═══════════════════════════════════════════════════════════════════════════════
# Feedback collector tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecordQuizFeedback:
    """Test quiz answer feedback collection."""

    @pytest.mark.asyncio
    async def test_records_multiple_answers(self, mock_db):
        from app.services.rag_feedback import record_quiz_feedback

        quiz_id = uuid.uuid4()
        user_id = uuid.uuid4()
        chunk1 = uuid.uuid4()
        chunk2 = uuid.uuid4()

        with patch("app.services.rag_feedback.log_chunk_usage", new_callable=AsyncMock) as mock_log, \
             patch("app.services.rag_feedback.record_chunk_outcome", new_callable=AsyncMock) as mock_outcome:

            count = await record_quiz_feedback(
                mock_db,
                quiz_session_id=quiz_id,
                user_id=user_id,
                answers=[
                    {"chunk_id": str(chunk1), "is_correct": True, "user_answer": "500 000 руб", "score_delta": 1.0},
                    {"chunk_id": str(chunk2), "is_correct": False, "user_answer": "300 000 руб", "score_delta": -1.0},
                ],
            )

        assert count == 2
        assert mock_outcome.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_answers_without_chunk_id(self, mock_db):
        from app.services.rag_feedback import record_quiz_feedback

        with patch("app.services.rag_feedback.log_chunk_usage", new_callable=AsyncMock), \
             patch("app.services.rag_feedback.record_chunk_outcome", new_callable=AsyncMock) as mock_outcome:

            count = await record_quiz_feedback(
                mock_db,
                quiz_session_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                answers=[
                    {"is_correct": True, "user_answer": "test"},  # no chunk_id
                ],
            )

        assert count == 0
        mock_outcome.assert_not_called()


class TestRecordBlitzFeedback:
    """Test blitz question feedback."""

    @pytest.mark.asyncio
    async def test_records_single_blitz_answer(self, mock_db):
        from app.services.rag_feedback import record_blitz_feedback

        with patch("app.services.rag_feedback.log_chunk_usage", new_callable=AsyncMock) as mock_log, \
             patch("app.services.rag_feedback.record_chunk_outcome", new_callable=AsyncMock) as mock_outcome:

            await record_blitz_feedback(
                mock_db,
                user_id=uuid.uuid4(),
                chunk_id=uuid.uuid4(),
                is_correct=True,
                user_answer="500 тысяч",
            )

        mock_log.assert_called_once()
        mock_outcome.assert_called_once()


class TestRecordTrainingFeedback:
    """Test training session feedback collection."""

    @pytest.mark.asyncio
    async def test_records_validation_results(self, mock_db):
        from app.services.rag_feedback import record_training_feedback

        chunk_id = uuid.uuid4()

        with patch("app.services.rag_feedback.log_chunk_usage", new_callable=AsyncMock), \
             patch("app.services.rag_feedback.record_chunk_outcome", new_callable=AsyncMock) as mock_outcome:

            count = await record_training_feedback(
                mock_db,
                session_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                validation_results=[
                    {
                        "chunk_id": str(chunk_id),
                        "accuracy": "incorrect",
                        "manager_statement": "Порог 300 тысяч",
                        "score_delta": -3.0,
                        "explanation": "Правильно: 500 тысяч",
                    },
                ],
            )

        assert count == 1
        mock_outcome.assert_called_once()
        # Verify answer_correct is False for "incorrect" accuracy
        _, kwargs = mock_outcome.call_args
        assert kwargs["answer_correct"] is False


class TestRecordPvpFeedback:
    """Test PvP duel feedback collection."""

    @pytest.mark.asyncio
    async def test_high_score_counts_as_correct(self, mock_db):
        from app.services.rag_feedback import record_pvp_feedback

        chunk_id = uuid.uuid4()

        with patch("app.services.rag_feedback.record_chunk_outcome", new_callable=AsyncMock) as mock_outcome:

            count = await record_pvp_feedback(
                mock_db,
                duel_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                round_number=1,
                judge_results=[
                    {"chunk_id": str(chunk_id), "score": 8, "feedback": "Хороший ответ"},
                ],
            )

        assert count == 1
        _, kwargs = mock_outcome.call_args
        assert kwargs["answer_correct"] is True  # 8 >= 6

    @pytest.mark.asyncio
    async def test_low_score_counts_as_incorrect(self, mock_db):
        from app.services.rag_feedback import record_pvp_feedback

        with patch("app.services.rag_feedback.record_chunk_outcome", new_callable=AsyncMock) as mock_outcome:

            await record_pvp_feedback(
                mock_db,
                duel_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                round_number=1,
                judge_results=[
                    {"chunk_id": str(uuid.uuid4()), "score": 3, "feedback": "Слабо"},
                ],
            )

        _, kwargs = mock_outcome.call_args
        assert kwargs["answer_correct"] is False  # 3 < 6


# ═══════════════════════════════════════════════════════════════════════════════
# Effectiveness recalculation tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecalculateChunkEffectiveness:
    """Test periodic aggregation job."""

    @pytest.mark.asyncio
    async def test_calculates_effectiveness(self, mock_db):
        from app.services.rag_legal import recalculate_chunk_effectiveness

        # Mock chunk with 8 correct, 2 incorrect (80% effectiveness)
        mock_chunk = MagicMock()
        mock_chunk.correct_answer_count = 8
        mock_chunk.incorrect_answer_count = 2
        mock_chunk.effectiveness_score = None
        mock_chunk.common_errors = ["старая ошибка"]

        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = [mock_chunk]

        # Second call for discovered errors
        mock_error_result = AsyncMock()
        mock_error_result.fetchall.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_result, mock_error_result])
        mock_db.commit = AsyncMock()

        updated = await recalculate_chunk_effectiveness(mock_db)

        assert updated == 1
        assert mock_chunk.effectiveness_score == 0.8  # 8/(8+2)

    @pytest.mark.asyncio
    async def test_skips_chunks_below_min_answers(self, mock_db):
        from app.services.rag_legal import recalculate_chunk_effectiveness

        mock_chunk = MagicMock()
        mock_chunk.correct_answer_count = 1
        mock_chunk.incorrect_answer_count = 1
        # Total = 2, below MIN_ANSWERS = 3

        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = [mock_chunk]

        mock_error_result = AsyncMock()
        mock_error_result.fetchall.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_result, mock_error_result])
        mock_db.commit = AsyncMock()

        updated = await recalculate_chunk_effectiveness(mock_db)

        # Query includes WHERE >= 3, but mock bypasses that
        # The function body checks again: total >= MIN_ANSWERS
        assert updated == 0
