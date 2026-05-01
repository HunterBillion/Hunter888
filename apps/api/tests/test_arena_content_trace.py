"""Tests for arena content-trace bus events (Content→Arena PR-7).

Locks in the contract:

* publish_duel_started emits a single event with the right type and
  serialised payload (UUIDs as strings, archetype + difficulty + is_pve).
* publish_round_scored emits with chunk-id lists and score split.
* When the bus dual-write flag is OFF, no publish call is made.
* When publish raises (Redis down), the helper swallows — never raises.
* correlation_id is set to ``str(duel_id)`` so AuditLogConsumer can
  join arena.bus.audit log lines on the duel id.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services import arena_content_trace as act


@pytest.mark.asyncio
async def test_publish_duel_started_skips_when_bus_disabled():
    with patch("app.config.settings.arena_bus_dual_write_enabled", False), \
         patch("app.services.arena_bus.publish", new_callable=AsyncMock) as mock_pub:
        await act.publish_duel_started(
            duel_id=uuid.uuid4(),
            scenario_template_id=uuid.uuid4(),
            scenario_version_id=uuid.uuid4(),
            archetype="aggressive_boss",
            is_pve=True,
            difficulty="medium",
        )
    mock_pub.assert_not_called()


@pytest.mark.asyncio
async def test_publish_duel_started_emits_with_correct_envelope():
    duel_id = uuid.uuid4()
    template_id = uuid.uuid4()
    version_id = uuid.uuid4()

    with patch("app.config.settings.arena_bus_dual_write_enabled", True), \
         patch("app.services.arena_bus.publish", new_callable=AsyncMock) as mock_pub:
        await act.publish_duel_started(
            duel_id=duel_id,
            scenario_template_id=template_id,
            scenario_version_id=version_id,
            archetype="skeptical_analyst",
            is_pve=False,
            difficulty="hard",
        )

    mock_pub.assert_awaited_once()
    event = mock_pub.call_args.args[0]
    assert event.type == act.EVENT_DUEL_STARTED
    assert event.correlation_id == str(duel_id)
    assert event.producer == "arena_content_trace"
    assert event.payload == {
        "scenario_template_id": str(template_id),
        "scenario_version_id": str(version_id),
        "archetype_code": "skeptical_analyst",
        "is_pve": False,
        "difficulty": "hard",
    }


@pytest.mark.asyncio
async def test_publish_duel_started_handles_null_template():
    """Legacy duels with NULL template/version FKs still trace cleanly."""
    duel_id = uuid.uuid4()

    with patch("app.config.settings.arena_bus_dual_write_enabled", True), \
         patch("app.services.arena_bus.publish", new_callable=AsyncMock) as mock_pub:
        await act.publish_duel_started(
            duel_id=duel_id,
            scenario_template_id=None,
            scenario_version_id=None,
            archetype=None,
            is_pve=True,
        )

    event = mock_pub.call_args.args[0]
    assert event.payload["scenario_template_id"] is None
    assert event.payload["scenario_version_id"] is None
    assert event.payload["archetype_code"] is None


@pytest.mark.asyncio
async def test_publish_round_scored_serializes_chunk_id_lists():
    duel_id = uuid.uuid4()
    correct = [uuid.uuid4(), uuid.uuid4()]
    incorrect = [uuid.uuid4()]
    all_chunks = correct + incorrect + [uuid.uuid4()]

    with patch("app.config.settings.arena_bus_dual_write_enabled", True), \
         patch("app.services.arena_bus.publish", new_callable=AsyncMock) as mock_pub:
        await act.publish_round_scored(
            duel_id=duel_id,
            round_number=1,
            legal_chunk_ids=all_chunks,
            legal_chunk_ids_correct=correct,
            legal_chunk_ids_incorrect=incorrect,
            selling_score=42.0,
            legal_accuracy=15.5,
            degraded=False,
        )

    event = mock_pub.call_args.args[0]
    assert event.type == act.EVENT_ROUND_SCORED
    assert event.payload["round_number"] == 1
    assert event.payload["legal_chunk_ids"] == [str(c) for c in all_chunks]
    assert event.payload["legal_chunk_ids_correct"] == [str(c) for c in correct]
    assert event.payload["legal_chunk_ids_incorrect"] == [str(c) for c in incorrect]
    assert event.payload["selling_score"] == 42.0
    assert event.payload["legal_accuracy"] == 15.5
    assert event.payload["degraded"] is False


@pytest.mark.asyncio
async def test_publish_round_scored_skips_when_bus_disabled():
    with patch("app.config.settings.arena_bus_dual_write_enabled", False), \
         patch("app.services.arena_bus.publish", new_callable=AsyncMock) as mock_pub:
        await act.publish_round_scored(
            duel_id=uuid.uuid4(),
            round_number=2,
            legal_chunk_ids=[],
            legal_chunk_ids_correct=[],
            legal_chunk_ids_incorrect=[],
            selling_score=0.0,
            legal_accuracy=0.0,
            degraded=True,
        )
    mock_pub.assert_not_called()


@pytest.mark.asyncio
async def test_publish_swallows_publish_exception():
    """Best-effort contract: bus.publish raising never bubbles up."""
    failing = AsyncMock(side_effect=ConnectionError("redis down"))

    with patch("app.config.settings.arena_bus_dual_write_enabled", True), \
         patch("app.services.arena_bus.publish", failing):
        # Both helpers must succeed silently.
        await act.publish_duel_started(
            duel_id=uuid.uuid4(),
            scenario_template_id=None,
            scenario_version_id=None,
            archetype=None,
            is_pve=False,
        )
        await act.publish_round_scored(
            duel_id=uuid.uuid4(),
            round_number=1,
            legal_chunk_ids=[],
            legal_chunk_ids_correct=[],
            legal_chunk_ids_incorrect=[],
            selling_score=0.0,
            legal_accuracy=0.0,
            degraded=False,
        )
