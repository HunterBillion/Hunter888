"""TZ-4 §13.4.1 — AI quality dashboard endpoint contract tests.

Validates the aggregation in :mod:`app.api.ai_quality` without
spinning up a real database — the SQLAlchemy session is replaced
with a stub that returns a curated event list. Keeps the test
focused on the in-Python fold logic; SQL filters are exercised by
the broader integration suite.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.ai_quality import get_ai_quality_summary
from app.models.domain_event import DomainEvent


def _event(
    *,
    event_type: str,
    actor_id: uuid.UUID | None = None,
    payload: dict | None = None,
    minutes_ago: int = 5,
) -> DomainEvent:
    return DomainEvent(
        id=uuid.uuid4(),
        lead_client_id=uuid.uuid4(),
        event_type=event_type,
        actor_type="user" if actor_id else "system",
        actor_id=actor_id,
        source="test",
        occurred_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        payload_json=payload or {},
        idempotency_key=f"k-{uuid.uuid4()}",
        schema_version=1,
        correlation_id="test",
    )


def _user(role: str = "admin", *, team_id=None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=SimpleNamespace(value=role),
        team_id=team_id,
        full_name="Тестовый Админ",
        email="t@x",
    )


def _make_db(rows: list[tuple[DomainEvent, object | None]]):
    """Stub session that returns ``rows`` (event, actor) tuples from a
    single ``execute`` call. The endpoint iterates them in-Python."""
    db = SimpleNamespace()

    class _Result:
        def __init__(self, items):
            self._items = items

        def all(self):
            return list(self._items)

    async def _execute(_stmt):
        return _Result(rows)

    db.execute = AsyncMock(side_effect=_execute)
    return db


def _actor(name: str = "Менеджер Иван") -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), full_name=name, email="m@x")


@pytest.mark.asyncio
async def test_ai_quality_summary_groups_by_severity_and_manager():
    """Three policy violations from one manager + one persona conflict
    from another → totals, by_severity buckets, manager rows all
    coherent."""
    actor_a = _actor("Менеджер А")
    actor_b = _actor("Менеджер Б")
    rows = [
        (
            _event(
                event_type="conversation.policy_violation_detected",
                actor_id=actor_a.id,
                payload={"code": "near_repeat", "severity": "high", "session_id": str(uuid.uuid4())},
            ),
            actor_a,
        ),
        (
            _event(
                event_type="conversation.policy_violation_detected",
                actor_id=actor_a.id,
                payload={"code": "missing_next_step", "severity": "low"},
            ),
            actor_a,
        ),
        (
            _event(
                event_type="conversation.policy_violation_detected",
                actor_id=actor_a.id,
                payload={"code": "near_repeat", "severity": "high"},
            ),
            actor_a,
        ),
        (
            _event(
                event_type="persona.conflict_detected",
                actor_id=actor_b.id,
                payload={"attempted_field": "address_form"},
            ),
            actor_b,
        ),
    ]

    summary = await get_ai_quality_summary(
        days=7,
        recent_limit=10,
        user=_user("admin"),
        db=_make_db(rows),
    )

    assert summary.totals["policy_violations"] == 3
    assert summary.totals["persona_conflicts"] == 1
    assert summary.by_severity.high == 2
    assert summary.by_severity.low == 1

    by_code = {c.code: c.count for c in summary.by_code}
    assert by_code["near_repeat"] == 2
    assert by_code["missing_next_step"] == 1

    by_manager = {m.manager_name: m for m in summary.by_manager}
    assert by_manager["Менеджер А"].total == 3
    assert by_manager["Менеджер А"].persona_conflicts == 0
    assert by_manager["Менеджер Б"].total == 1
    assert by_manager["Менеджер Б"].persona_conflicts == 1


@pytest.mark.asyncio
async def test_ai_quality_summary_recent_feed_is_bounded():
    actor = _actor()
    rows = [
        (
            _event(
                event_type="conversation.policy_violation_detected",
                actor_id=actor.id,
                payload={"code": "near_repeat", "severity": "high"},
                minutes_ago=i,
            ),
            actor,
        )
        for i in range(50)
    ]

    summary = await get_ai_quality_summary(
        days=7,
        recent_limit=5,
        user=_user("admin"),
        db=_make_db(rows),
    )

    assert len(summary.recent) == 5
    assert summary.totals["policy_violations"] == 50


@pytest.mark.asyncio
async def test_ai_quality_summary_skips_slot_locked_in_manager_breakdown():
    """slot_locked is a *positive* signal — counted in totals but
    excluded from the per-manager "watch list" because no one is
    "in trouble" for confirming a slot."""
    actor = _actor()
    rows = [
        (
            _event(
                event_type="persona.slot_locked",
                actor_id=actor.id,
                payload={"slot_code": "city"},
            ),
            actor,
        )
    ]

    summary = await get_ai_quality_summary(
        days=7,
        recent_limit=10,
        user=_user("admin"),
        db=_make_db(rows),
    )

    assert summary.totals["slot_locked"] == 1
    assert summary.by_manager == []  # no row for slot-only manager


@pytest.mark.asyncio
async def test_ai_quality_summary_rop_with_no_team_returns_empty():
    summary = await get_ai_quality_summary(
        days=7,
        recent_limit=10,
        user=_user("rop", team_id=None),
        db=_make_db([]),
    )
    assert summary.totals == {
        "policy_violations": 0,
        "persona_conflicts": 0,
        "slot_locked": 0,
    }
    assert summary.by_manager == []
    assert summary.recent == []


@pytest.mark.asyncio
async def test_ai_quality_summary_empty_window_clean_response():
    summary = await get_ai_quality_summary(
        days=7,
        recent_limit=10,
        user=_user("admin"),
        db=_make_db([]),
    )
    assert summary.window_days == 7
    assert summary.totals["policy_violations"] == 0
    assert summary.by_severity.critical == 0
    assert summary.by_code == []
    assert summary.recent == []
