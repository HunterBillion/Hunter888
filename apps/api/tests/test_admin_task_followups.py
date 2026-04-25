"""Admin observability endpoint for TZ-2 §12 TaskFollowUp.

Pins the response shape so the FE admin section can rely on it.
The endpoint itself is read-only — no mutations to verify, just
filtering, pagination, and the two distributions (`by_status`,
`by_reason`).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _result(rows=(), scalar=0):
    """Build a mock SQLAlchemy result. ``rows`` mimics .scalars().all();
    ``scalar`` mimics .scalar_one(). For aggregate GROUP BY queries the
    result is iterable of tuples — pass a list of tuples to ``rows``."""
    r = MagicMock()
    r.scalars.return_value = MagicMock(all=MagicMock(return_value=list(rows)))
    r.scalar_one = MagicMock(return_value=scalar)
    r.all = MagicMock(return_value=list(rows))
    return r


@pytest.mark.asyncio
async def test_get_task_followups_returns_canonical_shape():
    from datetime import UTC, datetime
    import uuid as _u

    from app.api.client_domain_ops import get_task_followups

    row = SimpleNamespace(
        id=_u.uuid4(),
        lead_client_id=_u.uuid4(),
        session_id=_u.uuid4(),
        domain_event_id=_u.uuid4(),
        reason="needs_followup",
        channel="phone",
        due_at=datetime.now(UTC),
        status="pending",
        auto_generated=True,
        created_at=datetime.now(UTC),
        completed_at=None,
    )

    # Endpoint issues 4 queries in this order:
    # 1) count, 2) page rows, 3) group-by status, 4) group-by reason.
    # AsyncMock side_effect returns one value per call.
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[
        _result(scalar=1),                                          # count
        _result(rows=[row]),                                        # page
        _result(rows=[("pending", 5), ("done", 3)]),                # status groupby
        _result(rows=[("needs_followup", 4), ("callback_requested", 1)]),  # reason groupby
    ])

    payload = await get_task_followups(
        status_filter=None, reason=None, page=1, per_page=50, db=db, _user=object()
    )

    assert payload["total"] == 1
    assert payload["page"] == 1
    assert payload["per_page"] == 50
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    # Canonical fields exposed to admin UI
    for key in ("id", "lead_client_id", "session_id", "domain_event_id",
                "reason", "channel", "due_at", "status", "auto_generated"):
        assert key in item
    assert payload["by_status"] == {"pending": 5, "done": 3}
    assert payload["by_reason"] == {"needs_followup": 4, "callback_requested": 1}


@pytest.mark.asyncio
async def test_get_task_followups_rejects_unknown_status_filter():
    from app.api.client_domain_ops import get_task_followups

    payload = await get_task_followups(
        status_filter="nonsense_status",
        reason=None,
        page=1, per_page=50,
        db=MagicMock(),
        _user=object(),
    )
    assert payload["items"] == []
    assert payload["total"] == 0
    assert "error" in payload
    assert "nonsense_status" in payload["error"]


@pytest.mark.asyncio
async def test_get_task_followups_rejects_unknown_reason_filter():
    from app.api.client_domain_ops import get_task_followups

    payload = await get_task_followups(
        status_filter=None,
        reason="totally_made_up_reason",
        page=1, per_page=50,
        db=MagicMock(),
        _user=object(),
    )
    assert payload["items"] == []
    assert "error" in payload
    assert "totally_made_up_reason" in payload["error"]


@pytest.mark.asyncio
async def test_filter_values_match_canonical_catalogs():
    """Whatever the FE sends as a filter must match the catalog the
    policy enforces — drift between filter validation and policy CHECK
    would silently allow garbage filters that always return empty."""
    from app.api.client_domain_ops import get_task_followups
    from app.services.task_followup_policy import REASONS, STATUSES

    # Round-trip every legitimate value to ensure the filter validator
    # does NOT reject them. Using a minimal DB that returns nothing.
    def _empty_db():
        # Each get_task_followups call issues 4 queries; provide an empty
        # result for each so the validator can reach the "no error" branch.
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _result(scalar=0),
            _result(rows=[]),
            _result(rows=[]),
            _result(rows=[]),
        ])
        return db

    for s in STATUSES:
        payload = await get_task_followups(
            status_filter=s, reason=None, page=1, per_page=10,
            db=_empty_db(), _user=object(),
        )
        assert "error" not in payload, f"status={s!r} unexpectedly rejected"

    for r in REASONS:
        payload = await get_task_followups(
            status_filter=None, reason=r, page=1, per_page=10,
            db=_empty_db(), _user=object(),
        )
        assert "error" not in payload, f"reason={r!r} unexpectedly rejected"
