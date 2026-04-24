"""Regression tests for the parity/repair helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return SimpleNamespace(all=lambda: self._value or [])


@pytest.mark.asyncio
async def test_parity_report_aggregates_counts(monkeypatch):
    from app.services import client_domain_repair

    values = [
        10,  # total_interactions
        12,  # total_events
        11,  # total_projections
        2,  # interactions_without_event
        1,  # events_without_projection
        0,  # projections_without_interaction
        0,  # events_without_lead_client_id
    ]

    def _next_result(*_args, **_kwargs):
        return _Result(values.pop(0))

    db = SimpleNamespace()
    db.execute = AsyncMock(side_effect=_next_result)

    report = await client_domain_repair.parity_report(db)

    assert report == {
        "total_interactions": 10,
        "total_events": 12,
        "total_projections": 11,
        "interactions_without_domain_event_id": 2,
        "events_without_projection": 1,
        "projections_without_interaction": 0,
        "events_without_lead_client_id": 0,
    }
    assert values == []  # confirm exactly 7 queries executed
