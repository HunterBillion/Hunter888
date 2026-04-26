"""Pin the response shape FE depends on for the canonical-mode read.

The TZ-2 §6.2/6.3 canonical runtime fields (`mode`, `runtime_type`) live
on `TrainingSession` in the ORM but used to be silently dropped by
`SessionResponse` because the schema didn't declare them. This test fails
on the pre-fix code: removing either field from the schema again would
reintroduce the FE drift the call-page strict-mode read depends on.
"""

from __future__ import annotations

import pytest


def test_session_response_declares_canonical_mode_field():
    from app.schemas.training import SessionResponse

    fields = SessionResponse.model_fields
    assert "mode" in fields, (
        "SessionResponse must expose `mode` so /training/[id]/call/page.tsx "
        "can read the canonical TZ-2 §6.2 field instead of "
        "custom_params.session_mode (legacy fallback only)."
    )


def test_session_response_declares_canonical_runtime_type_field():
    from app.schemas.training import SessionResponse

    fields = SessionResponse.model_fields
    assert "runtime_type" in fields, (
        "SessionResponse must expose `runtime_type` (TZ-2 §6.3) so callers "
        "can distinguish training_simulation / training_real_case / crm_call "
        "/ crm_chat / center_single_call without re-deriving from mode."
    )


def test_session_response_canonical_fields_serialize_from_orm_attrs():
    """ORM-to-schema round-trip: when the session row carries a canonical
    mode/runtime_type, the response must surface them verbatim. Catches a
    silent typing mismatch where the ORM column is `String(20)` but the
    schema field is, say, an Enum that drops unknowns."""
    from types import SimpleNamespace
    from datetime import datetime, UTC

    from app.schemas.training import SessionResponse

    fake_orm = SimpleNamespace(
        id=__import__("uuid").uuid4(),
        scenario_id=None,
        lead_client_id=None,
        status="active",
        mode="call",
        runtime_type="crm_call",
        started_at=datetime.now(UTC),
        ended_at=None,
        duration_seconds=0,
        score_script_adherence=None,
        score_objection_handling=None,
        score_communication=None,
        score_anti_patterns=None,
        score_result=None,
        score_total=None,
        score_chain_traversal=None,
        score_trap_handling=None,
        score_human_factor=None,
        score_narrative=None,
        score_legal=None,
        scoring_details=None,
        emotion_timeline=None,
        feedback_text=None,
        client_story_id=None,
        call_number_in_story=None,
        custom_params=None,
        real_client_id=None,
        custom_character_id=None,
        source_session_id=None,
    )
    response = SessionResponse.model_validate(fake_orm, from_attributes=True)
    assert response.mode == "call"
    assert response.runtime_type == "crm_call"
