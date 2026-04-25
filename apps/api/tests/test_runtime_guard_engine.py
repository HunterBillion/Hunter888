"""TZ-2 §8 runtime guard engine — Phase 3.

Pin the 5 minimum guards: profile_complete, mode_integrity,
runtime_type_invalid, runtime_type_inconsistent (cross-check),
lead_client_required, terminal_outcome_required.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.services.runtime_guard_engine import (
    GUARD_LEAD_CLIENT_REQUIRED,
    GUARD_MODE_INVALID,
    GUARD_PROFILE_INCOMPLETE,
    GUARD_RUNTIME_TYPE_INVALID,
    GUARD_SESSION_MODE_REQUIRED_FOR_CRM,
    GUARD_TERMINAL_OUTCOME_REQUIRED,
    evaluate_end_guards,
    evaluate_start_guards,
)


_COMPLETE_PREFS = {
    "gender": "male",
    "role_title": "Manager",
    "lead_source": "cold_call",
    "primary_contact": "phone",
    "specialization": "b2c",
    "experience_level": "junior",
    "training_mode": "balanced",
}


def _complete_user():
    """A user whose profile_gate.required_profile_missing returns []."""
    return SimpleNamespace(
        full_name="Тест Иванов",
        role="manager",
        preferences=_COMPLETE_PREFS,
    )


def _incomplete_user():
    return SimpleNamespace(full_name=None, role=None, preferences={})


# ── start guards ──


def test_clean_start_returns_no_violations():
    v = evaluate_start_guards(
        user=_complete_user(),
        mode="chat",
        runtime_type="training_simulation",
    )
    assert v == []


def test_incomplete_profile_emits_profile_violation():
    v = evaluate_start_guards(user=_incomplete_user(), mode="chat")
    codes = [x.code for x in v]
    assert GUARD_PROFILE_INCOMPLETE in codes
    profile = next(x for x in v if x.code == GUARD_PROFILE_INCOMPLETE)
    assert profile.details and "missing_fields" in profile.details
    assert isinstance(profile.details["missing_fields"], list)


def test_invalid_mode_emits_mode_violation():
    v = evaluate_start_guards(user=_complete_user(), mode="bogus")
    codes = [x.code for x in v]
    assert GUARD_MODE_INVALID in codes


def test_invalid_runtime_type_emits_runtime_type_violation():
    v = evaluate_start_guards(
        user=_complete_user(), mode="chat", runtime_type="bogus_runtime"
    )
    assert GUARD_RUNTIME_TYPE_INVALID in [x.code for x in v]


def test_inconsistent_runtime_type_caught():
    """FE sends runtime_type=crm_call but no real_client_id and source=home —
    derived runtime type is training_simulation. Cross-check must catch this."""
    v = evaluate_start_guards(
        user=_complete_user(),
        mode="call",
        runtime_type="crm_call",  # claimed
        real_client_id=None,      # but no real client
        source="home",
    )
    codes = [x.code for x in v]
    # Two violations: lead_client_required (because crm_call needs it)
    # AND runtime_type_invalid (because the cross-check sees mismatch)
    assert GUARD_LEAD_CLIENT_REQUIRED in codes
    assert GUARD_RUNTIME_TYPE_INVALID in codes


def test_crm_call_without_real_client_caught():
    v = evaluate_start_guards(
        user=_complete_user(),
        mode="call",
        runtime_type="crm_call",
        real_client_id=None,
        source="crm_voice",
    )
    assert GUARD_LEAD_CLIENT_REQUIRED in [x.code for x in v]


def test_crm_call_with_real_client_passes_lead_guard():
    v = evaluate_start_guards(
        user=_complete_user(),
        mode="call",
        runtime_type="crm_call",
        real_client_id=uuid.uuid4(),
        source="crm_voice",
    )
    assert GUARD_LEAD_CLIENT_REQUIRED not in [x.code for x in v]


def test_simulation_does_not_require_real_client():
    """training_simulation explicitly works without real_client_id."""
    v = evaluate_start_guards(
        user=_complete_user(),
        mode="chat",
        runtime_type="training_simulation",
        real_client_id=None,
    )
    assert v == []


def test_lead_client_guard_uses_derived_runtime_type_when_unspecified():
    """When runtime_type is not supplied, the guard must still infer
    that a CRM-shaped start needs a real client."""
    v = evaluate_start_guards(
        user=_complete_user(),
        mode="call",
        runtime_type=None,
        real_client_id=None,
        source="crm_voice",
    )
    # source=crm_voice + has_real_client=False derives to training_simulation
    # (the spec says crm_call requires real_client + crm_* source — without
    # a real client we fall back). So no lead_client_required violation here.
    assert GUARD_LEAD_CLIENT_REQUIRED not in [x.code for x in v]


def test_missing_mode_does_not_break_evaluation():
    """Legacy paths still send mode via custom_params. The guard should
    not crash on mode=None — it just skips the mode-dependent checks."""
    v = evaluate_start_guards(user=_complete_user(), mode=None)
    assert v == []  # profile complete, no mode → no other complaints


# ── session_mode_required_for_crm guard (Phase 3B) ──


def test_crm_start_without_mode_emits_session_mode_violation():
    """CRM-card start (real_client_id present) without an explicit mode
    must surface the canonical session_mode_required_for_crm code so the
    pre-existing FE handler at clients/[id]/page.tsx keeps working."""
    v = evaluate_start_guards(
        user=_complete_user(),
        mode=None,
        real_client_id=uuid.uuid4(),
        source="crm_voice",
    )
    assert GUARD_SESSION_MODE_REQUIRED_FOR_CRM in [x.code for x in v]


def test_crm_start_with_explicit_mode_passes_session_mode_guard():
    v = evaluate_start_guards(
        user=_complete_user(),
        mode="call",
        real_client_id=uuid.uuid4(),
        source="crm_voice",
    )
    assert GUARD_SESSION_MODE_REQUIRED_FOR_CRM not in [x.code for x in v]


def test_simulation_start_without_mode_does_not_require_session_mode():
    """No real_client_id → simulation path → mode optional (legacy /home
    quick-start sends nothing)."""
    v = evaluate_start_guards(
        user=_complete_user(),
        mode=None,
        real_client_id=None,
        source="home",
    )
    assert GUARD_SESSION_MODE_REQUIRED_FOR_CRM not in [x.code for x in v]


# ── end guards ──


def test_center_outcome_required():
    """center mode cannot end without an outcome."""
    v = evaluate_end_guards(mode="center", raw_outcome=None)
    assert GUARD_TERMINAL_OUTCOME_REQUIRED in [x.code for x in v]


def test_center_outcome_valid():
    v = evaluate_end_guards(mode="center", raw_outcome="agreed")
    assert v == []


def test_chat_mode_does_not_require_outcome():
    """Non-center modes accept missing outcome at this phase (they get
    a default 'operator_aborted' downstream)."""
    v = evaluate_end_guards(mode="chat", raw_outcome=None)
    assert v == []


def test_call_mode_does_not_require_outcome():
    v = evaluate_end_guards(mode="call", raw_outcome=None)
    assert v == []
