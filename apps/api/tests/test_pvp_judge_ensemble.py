from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.models.pvp import DuelDifficulty
from app.services.rag_legal import RAGContext


def _judge_payload(*, selling: int, acting: int, legal: int, summary: str, tip: str, articles: list[str]) -> str:
    return json.dumps(
        {
            "selling_score": selling,
            "selling_breakdown": {
                "objection_handling": max(0, min(15, selling // 3)),
                "persuasion": max(0, min(10, selling // 5)),
            },
            "acting_score": acting,
            "acting_breakdown": {
                "archetype_authenticity": max(0, min(10, acting // 3)),
            },
            "legal_accuracy": legal,
            "legal_details": [{"claim": "ст. 213.3", "accuracy": "correct_cited", "explanation": "ok"}],
            "flags": [],
            "summary": summary,
            "coaching_tip": tip,
            "ideal_reply": "Уточните порог долга и срок просрочки.",
            "key_articles": articles,
        }
    )


@pytest.mark.asyncio
async def test_judge_round_ensemble_uses_median_and_primary_result() -> None:
    from app.services import pvp_judge

    rag = RAGContext(query="q", results=[], method="hybrid", retrieval_ms=1.0)
    llm_responses = [
        SimpleNamespace(content=_judge_payload(selling=40, acting=18, legal=14, summary="strict", tip="tip-1", articles=["ст. 213.3"])),
        SimpleNamespace(content=_judge_payload(selling=30, acting=24, legal=16, summary="balanced", tip="tip-2", articles=["ст. 71"])),
        SimpleNamespace(content=_judge_payload(selling=10, acting=6, legal=5, summary="coach", tip="tip-3", articles=["ст. 213.25"])),
    ]

    with patch("app.services.pvp_judge.retrieve_legal_context", AsyncMock(return_value=rag)), \
         patch("app.services.pvp_judge.generate_response", AsyncMock(side_effect=llm_responses)) as llm_mock, \
         patch("app.services.pvp_judge.log_chunk_usage", AsyncMock()), \
         patch("app.services.pvp_judge.record_chunk_outcome", AsyncMock()):
        with patch.object(settings, "pvp_judge_ensemble_enabled", True), \
             patch.object(settings, "pvp_judge_ensemble_size", 3), \
             patch.object(settings, "pvp_judge_ensemble_quorum", 2):
            seller_score, client_score = await pvp_judge.judge_round(
                dialog=[{"role": "seller", "text": "Ответ с опорой на 127-ФЗ"}],
                seller_id=uuid.uuid4(),
                client_id=uuid.uuid4(),
                seller_name="Seller",
                client_name="Client",
                archetype="skeptic",
                difficulty=DuelDifficulty.easy,
                round_number=1,
                db=AsyncMock(),
            )

    assert llm_mock.await_count == 3
    assert seller_score.degraded is False
    assert client_score.degraded is False

    # Medians over successful judges:
    # selling: median(40,30,10)=30; legal: median(14,16,5)=14; acting: median(18,24,6)=18.
    assert seller_score.selling_score == 30
    assert seller_score.legal_accuracy == 14
    assert client_score.acting_score == 18

    # Primary result should be the one closest to median seller total (30+16=46).
    assert seller_score.coaching_tip == "tip-2"
    assert seller_score.key_articles == ["ст. 213.3", "ст. 71", "ст. 213.25"]


@pytest.mark.asyncio
async def test_judge_round_ensemble_quorum_failure_degrades_to_neutral() -> None:
    from app.services import pvp_judge

    rag = RAGContext(query="q", results=[], method="hybrid", retrieval_ms=1.0)
    llm_responses = [
        SimpleNamespace(content=_judge_payload(selling=34, acting=21, legal=11, summary="ok", tip="tip-ok", articles=["ст. 213.3"])),
        SimpleNamespace(content="not-json"),
        SimpleNamespace(content="also-not-json"),
    ]

    with patch("app.services.pvp_judge.retrieve_legal_context", AsyncMock(return_value=rag)), \
         patch("app.services.pvp_judge.generate_response", AsyncMock(side_effect=llm_responses)) as llm_mock, \
         patch("app.services.pvp_judge.log_chunk_usage", AsyncMock()), \
         patch("app.services.pvp_judge.record_chunk_outcome", AsyncMock()):
        with patch.object(settings, "pvp_judge_ensemble_enabled", True), \
             patch.object(settings, "pvp_judge_ensemble_size", 3), \
             patch.object(settings, "pvp_judge_ensemble_quorum", 2):
            seller_score, client_score = await pvp_judge.judge_round(
                dialog=[{"role": "seller", "text": "test"}],
                seller_id=uuid.uuid4(),
                client_id=uuid.uuid4(),
                seller_name="Seller",
                client_name="Client",
                archetype="skeptic",
                difficulty=DuelDifficulty.easy,
                round_number=1,
                db=AsyncMock(),
            )

    assert llm_mock.await_count == 3
    assert seller_score.degraded is True
    assert seller_score.degraded_reason == "panel_quorum_failed"
    assert client_score.degraded is True
    assert client_score.degraded_reason == "panel_quorum_failed"
    assert seller_score.selling_score == 25
    assert seller_score.legal_accuracy == 10
    assert client_score.acting_score == 15
