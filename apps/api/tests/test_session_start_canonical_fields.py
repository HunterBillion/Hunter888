"""TZ-2 Phase 4 — schema accepts canonical mode/runtime_type fields.

Pin the precedence rule in the start handler:

    body.mode (FE explicit) > custom_session_mode (legacy) > default
    body.runtime_type (FE explicit) > derive_runtime_type(...)

Also pins the `extra="forbid"` contract — unknown fields still 422.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.training import SessionStartRequest


def test_canonical_fields_accepted():
    body = SessionStartRequest(
        scenario_id=uuid.uuid4(),
        mode="call",
        runtime_type="crm_call",
        real_client_id=uuid.uuid4(),
        source="crm_voice",
    )
    assert body.mode == "call"
    assert body.runtime_type == "crm_call"


def test_legacy_fields_still_accepted():
    """Pages that haven't migrated yet still send custom_session_mode
    without mode/runtime_type — must not 422."""
    body = SessionStartRequest(
        scenario_id=uuid.uuid4(),
        custom_session_mode="chat",
        source="home",
    )
    assert body.mode is None
    assert body.runtime_type is None
    assert body.custom_session_mode == "chat"


def test_both_canonical_and_legacy_accepted():
    """Mid-migration pages send BOTH — backend prefers canonical, schema
    accepts both."""
    body = SessionStartRequest(
        scenario_id=uuid.uuid4(),
        mode="center",
        runtime_type="center_single_call",
        custom_session_mode="center",
        source="center",
    )
    assert body.mode == "center"
    assert body.runtime_type == "center_single_call"
    assert body.custom_session_mode == "center"


def test_unknown_field_still_rejected_422():
    """extra='forbid' contract from PR #17 must survive — adding mode/
    runtime_type doesn't open the door for arbitrary garbage."""
    with pytest.raises(ValidationError) as exc:
        SessionStartRequest(
            scenario_id=uuid.uuid4(),
            mode="chat",
            arbitrary_garbage_field="hello",  # type: ignore[call-arg]
        )
    # Pydantic v2 raises a "extra_forbidden" type for the unknown field.
    assert "extra_forbidden" in str(exc.value) or "Extra inputs" in str(exc.value)


def test_mode_and_runtime_type_default_to_none():
    """Pages that send neither (legacy /home quick-start) must not
    have these fields filled with anything — backend will derive."""
    body = SessionStartRequest(scenario_id=uuid.uuid4())
    assert body.mode is None
    assert body.runtime_type is None
