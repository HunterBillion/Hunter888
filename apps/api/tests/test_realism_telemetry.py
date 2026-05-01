"""(2026-05-01) Realism telemetry — snapshot tests + AST guard.

Pin the contract:
  * snapshot returns a dict with the expected keys (forward compat
    via ``snapshot_version``)
  * each realism flag round-trips correctly
  * ``call_eligible`` distinguishes call-mode from chat
  * ``count_active_realism_features`` excludes meta keys
  * ``call.realism_snapshot`` is in the DomainEvent allowlist
    (CLAUDE.md §3 invariant — every emit must be allowlisted)
  * snapshot is robust to settings objects missing newer flags
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.realism_telemetry import (
    count_active_realism_features,
    snapshot_realism_features,
)


def _full_settings(**overrides) -> SimpleNamespace:
    """Build a settings stub with every realism flag at its production
    value, then apply ``overrides``."""
    base = dict(
        call_arc_v1=True,
        call_arc_inject_reality=True,
        call_filler_v1=True,
        elevenlabs_streaming_enabled=True,
        stt_keyword_prompt_enabled=True,
        call_opener_persona_aware=True,
        adaptive_temperature_enabled=True,
        coaching_mistake_detector_v1=True,
        call_humanized_v2=True,
        call_humanized_v2_max_tokens=60,
        call_humanized_v2_scrub_mode="strip",
        call_humanized_v2_auto_opener=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_snapshot_returns_versioned_dict():
    snap = snapshot_realism_features(_full_settings(), session_mode="call")
    assert snap["snapshot_version"] == 1
    assert snap["session_mode"] == "call"
    assert snap["call_eligible"] is True


def test_snapshot_round_trips_each_flag():
    s = _full_settings()
    snap = snapshot_realism_features(s, session_mode="call")
    for flag in (
        "call_arc_v1", "call_arc_inject_reality", "call_filler_v1",
        "elevenlabs_streaming_enabled", "stt_keyword_prompt_enabled",
        "call_opener_persona_aware", "adaptive_temperature_enabled",
        "coaching_mistake_detector_v1", "call_humanized_v2",
        "call_humanized_v2_auto_opener",
    ):
        assert snap[flag] is True, f"flag {flag} did not round-trip"
    assert snap["call_humanized_v2_max_tokens"] == 60
    assert snap["call_humanized_v2_scrub_mode"] == "strip"


def test_call_eligible_false_for_chat():
    snap = snapshot_realism_features(_full_settings(), session_mode="chat")
    assert snap["call_eligible"] is False
    assert snap["session_mode"] == "chat"


def test_count_excludes_meta_and_scalars():
    """active_count counts only ON booleans, NOT version / mode / scalars."""
    s = _full_settings()
    snap = snapshot_realism_features(s, session_mode="call")
    n = count_active_realism_features(snap)
    # All 10 boolean flags above are True.
    assert n == 10, f"expected 10 active, got {n}: {snap!r}"


def test_count_drops_when_flags_off():
    s = _full_settings(call_arc_v1=False, call_filler_v1=False, adaptive_temperature_enabled=False)
    snap = snapshot_realism_features(s, session_mode="call")
    n = count_active_realism_features(snap)
    assert n == 7, f"expected 7 active after 3 OFFs, got {n}"


def test_snapshot_tolerates_missing_flag_attrs():
    """An older settings object that lacks newer flags must not crash —
    missing → False. This guards against rolling deploys where a hot
    container is still on yesterday's config schema."""
    sparse = SimpleNamespace(call_arc_v1=True)  # only 1 flag exists
    snap = snapshot_realism_features(sparse, session_mode="call")
    assert snap["call_arc_v1"] is True
    # Every other flag must default to False without raising AttributeError.
    assert snap["adaptive_temperature_enabled"] is False
    assert snap["call_filler_v1"] is False
    assert snap["call_humanized_v2_max_tokens"] == 0
    assert snap["call_humanized_v2_scrub_mode"] == "warn"


def test_realism_snapshot_event_type_in_allowlist():
    """CLAUDE.md §3 / TZ-1 invariant — every emit_domain_event call site
    must use an allowlisted ``event_type``. ``call.realism_snapshot`` is
    the new one we introduce; this guard pins it in the allowlist so
    a future refactor that removes it fails this test instead of
    silently dropping events."""
    from app.services.client_domain import ALLOWED_EVENT_TYPES
    assert "call.realism_snapshot" in ALLOWED_EVENT_TYPES


def test_snapshot_is_json_serialisable():
    """Persisted into JSONB scoring_details column AND emitted as
    DomainEvent payload. Both paths require strict JSON. No tuples,
    no datetimes, no dataclasses."""
    import json
    snap = snapshot_realism_features(_full_settings(), session_mode="call")
    json.dumps(snap)  # must not raise
