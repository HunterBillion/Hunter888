"""TZ-2 §6.2/6.3 runtime catalog (Phase 0).

Pin the catalog values + the (mode × CRM-link × source) → runtime_type
derivation so any drift between the constants here, the migration's
CHECK constraints, and the FE/BE consumers fails CI before prod.
"""

from __future__ import annotations

import pytest

from app.services.runtime_catalog import (
    COMPLETION_REASONS,
    MODES,
    RUNTIME_TYPES,
    derive_runtime_type,
)


def test_modes_match_spec():
    assert MODES == frozenset({"chat", "call", "center"})


def test_runtime_types_match_spec():
    assert RUNTIME_TYPES == frozenset({
        "training_simulation",
        "training_real_case",
        "crm_call",
        "crm_chat",
        "center_single_call",
    })


def test_completion_reasons_match_spec():
    assert COMPLETION_REASONS == frozenset({
        "explicit_end",
        "client_hangup",
        "operator_hangup",
        "timeout",
        "guard_block",
        "system_failure",
        "redirected",
    })


@pytest.mark.parametrize(
    "mode, has_real_client, source, expected",
    [
        # No real client — always simulation, regardless of mode/source
        ("chat", False, None, "training_simulation"),
        ("call", False, "home", "training_simulation"),
        ("chat", False, "constructor", "training_simulation"),
        # Real client + crm-prefixed source → CRM runtime
        ("call", True, "crm_voice", "crm_call"),
        ("chat", True, "crm_chat", "crm_chat"),
        # Real client + non-crm source → real_case (could be CRM-card-via-other-button)
        ("chat", True, "home", "training_real_case"),
        ("call", True, None, "training_real_case"),
        # source=center always wins (even without real client — center is its own runtime)
        ("call", False, "center", "center_single_call"),
        ("call", True, "center", "center_single_call"),
        ("chat", False, "center", "center_single_call"),
    ],
)
def test_derive_runtime_type_covers_spec_matrix(mode, has_real_client, source, expected):
    assert derive_runtime_type(
        mode=mode, has_real_client=has_real_client, source=source
    ) == expected


def test_derive_runtime_type_handles_none_mode():
    """Mode can be missing on legacy paths — derivation must still succeed,
    not raise. If has_real_client is False, falls through to simulation."""
    assert derive_runtime_type(
        mode=None, has_real_client=False, source=None
    ) == "training_simulation"
    assert derive_runtime_type(
        mode=None, has_real_client=True, source="home"
    ) == "training_real_case"


def test_derive_runtime_type_case_insensitive_source():
    """Some legacy stamps come in mixed case; derivation must normalise."""
    assert derive_runtime_type(
        mode="call", has_real_client=True, source="CRM_voice"
    ) == "crm_call"


def test_derive_returns_value_in_canonical_set():
    """Every output must be a valid runtime_type — guarantees the value
    won't fail the DB CHECK constraint."""
    matrix = [
        ("chat", False, None),
        ("call", True, "crm_voice"),
        ("call", True, "center"),
        (None, False, "weirdness"),
    ]
    for m, hc, s in matrix:
        rt = derive_runtime_type(mode=m, has_real_client=hc, source=s)
        assert rt in RUNTIME_TYPES, f"derive returned {rt!r} not in catalog for ({m},{hc},{s})"
