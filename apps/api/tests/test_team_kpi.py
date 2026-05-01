"""KPI target endpoint contract tests.

Pins request/response shape for the FE inline editor + the PATCH
"explicit-null clears, missing key keeps" semantics. Pure unit checks
on Pydantic schemas + helper logic — DB-backed integration tests live
elsewhere (out of pilot blocking scope).
"""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.api.team_kpi import (
    KpiTargetBulkResponse,
    KpiTargetResponse,
    KpiTargetUpdateRequest,
)


# ── PATCH semantics ─────────────────────────────────────────────────────


def test_patch_request_distinguishes_missing_from_explicit_null():
    """The endpoint relies on `model_dump(exclude_unset=True)` to tell
    "field omitted → leave existing value" from "field=null → clear it".
    Pin that contract with the schema directly so a future Pydantic
    upgrade can't silently break it."""
    # Field omitted → not in dump.
    body = KpiTargetUpdateRequest()
    dumped_omitted = body.model_dump(exclude_unset=True)
    assert "target_sessions_per_month" not in dumped_omitted

    # Field explicitly null → IS in dump as None.
    body = KpiTargetUpdateRequest(target_sessions_per_month=None)
    dumped_null = body.model_dump(exclude_unset=True)
    assert "target_sessions_per_month" in dumped_null
    assert dumped_null["target_sessions_per_month"] is None


def test_patch_request_accepts_typical_values():
    body = KpiTargetUpdateRequest(
        target_sessions_per_month=20,
        target_avg_score=72.5,
        target_max_days_without_session=7,
    )
    blob = body.model_dump(exclude_unset=True)
    assert blob == {
        "target_sessions_per_month": 20,
        "target_avg_score": 72.5,
        "target_max_days_without_session": 7,
    }


def test_patch_request_rejects_negative_sessions():
    with pytest.raises(ValidationError):
        KpiTargetUpdateRequest(target_sessions_per_month=-1)


def test_patch_request_rejects_negative_max_days():
    with pytest.raises(ValidationError):
        KpiTargetUpdateRequest(target_max_days_without_session=-3)


def test_patch_request_rejects_score_out_of_range():
    with pytest.raises(ValidationError):
        KpiTargetUpdateRequest(target_avg_score=-0.5)
    with pytest.raises(ValidationError):
        KpiTargetUpdateRequest(target_avg_score=101.0)


def test_patch_request_accepts_score_at_bounds():
    KpiTargetUpdateRequest(target_avg_score=0.0)
    KpiTargetUpdateRequest(target_avg_score=100.0)


# ── Response shape ──────────────────────────────────────────────────────


def test_response_shape_serializable_with_nulls():
    """Brand-new manager has no targets — endpoint returns synthetic row
    with all targets = null. Confirm Pydantic accepts and serialises
    cleanly to JSON."""
    resp = KpiTargetResponse(
        user_id=uuid.uuid4(),
        target_sessions_per_month=None,
        target_avg_score=None,
        target_max_days_without_session=None,
        updated_by=None,
        created_at=None,
        updated_at=None,
    )
    blob = resp.model_dump(mode="json")
    assert blob["target_sessions_per_month"] is None
    assert blob["target_avg_score"] is None
    assert blob["target_max_days_without_session"] is None
    assert blob["created_at"] is None


def test_bulk_response_empty_team():
    """ROP without team_id (admin who hasn't been assigned to one) gets
    an empty list, not a 500."""
    resp = KpiTargetBulkResponse(targets=[])
    blob = resp.model_dump(mode="json")
    assert blob == {"targets": []}


def test_bulk_response_with_mixed_targets():
    targets = [
        KpiTargetResponse(
            user_id=uuid.uuid4(),
            target_sessions_per_month=20,
            target_avg_score=72.5,
            target_max_days_without_session=7,
            updated_by=None,
            created_at="2026-05-01T10:00:00+00:00",
            updated_at="2026-05-01T10:00:00+00:00",
        ),
        KpiTargetResponse(
            user_id=uuid.uuid4(),
            target_sessions_per_month=None,
            target_avg_score=80.0,
            target_max_days_without_session=None,
            updated_by=None,
            created_at=None,
            updated_at=None,
        ),
    ]
    resp = KpiTargetBulkResponse(targets=targets)
    blob = resp.model_dump(mode="json")
    assert len(blob["targets"]) == 2
    assert blob["targets"][0]["target_sessions_per_month"] == 20
    assert blob["targets"][1]["target_sessions_per_month"] is None
