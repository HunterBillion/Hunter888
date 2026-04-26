"""TZ-2 §18 — runtime observability counters.

Pure-unit tests for ``app.services.runtime_metrics``: each ``record_*``
helper bumps the right key, and ``reset_for_tests`` wipes state. The
endpoint that renders text/plain is exercised via integration tests
elsewhere; the service-level coverage here keeps the wiring honest
even if the endpoint signature drifts.
"""

from __future__ import annotations

import pytest

from app.services import runtime_metrics as rm


@pytest.fixture(autouse=True)
def _reset():
    rm.reset_for_tests()
    yield
    rm.reset_for_tests()


# ── blocked_starts ──────────────────────────────────────────────────────────


def test_record_blocked_start_buckets_by_full_label_set():
    rm.record_blocked_start(
        guard_code="profile_incomplete",
        mode="call",
        runtime_type="crm_call",
    )
    rm.record_blocked_start(
        guard_code="profile_incomplete",
        mode="call",
        runtime_type="crm_call",
    )
    rm.record_blocked_start(
        guard_code="lead_client_required",
        mode="call",
        runtime_type="crm_call",
    )
    snap = rm.get_blocked_starts()
    assert snap[("profile_incomplete", "call", "crm_call", "start")] == 2
    assert snap[("lead_client_required", "call", "crm_call", "start")] == 1


def test_record_blocked_start_coerces_unknown_to_string():
    """Early guards (profile_incomplete) fire before mode/runtime_type are
    parsed — caller passes None and we must not crash or explode the
    cardinality with a literal ``None`` label."""
    rm.record_blocked_start(
        guard_code="profile_incomplete",
        mode=None,
        runtime_type=None,
    )
    snap = rm.get_blocked_starts()
    assert snap[("profile_incomplete", "unknown", "unknown", "start")] == 1


def test_record_blocked_start_phase_label_separates_start_and_end():
    rm.record_blocked_start(
        guard_code="terminal_outcome_required",
        mode="center",
        runtime_type="center_single_call",
        phase="end",
    )
    snap = rm.get_blocked_starts()
    assert (
        "terminal_outcome_required",
        "center",
        "center_single_call",
        "end",
    ) in snap


# ── finalize ────────────────────────────────────────────────────────────────


def test_record_finalize_separates_fresh_and_idempotent():
    """The whole point of the freshness label: a producer double-finalizing
    must show as ``idempotent`` while the first call shows as ``fresh``."""
    rm.record_finalize(
        completed_via="rest",
        outcome="success",
        strict_mode=False,
        already_completed=False,
    )
    rm.record_finalize(
        completed_via="rest",
        outcome="success",
        strict_mode=False,
        already_completed=True,
    )
    snap = rm.get_finalize_counters()
    assert snap[("rest", "success", "shadow", "fresh")] == 1
    assert snap[("rest", "success", "shadow", "idempotent")] == 1


def test_record_finalize_strict_mode_label():
    rm.record_finalize(
        completed_via="ws",
        outcome="hangup",
        strict_mode=True,
        already_completed=False,
    )
    snap = rm.get_finalize_counters()
    assert snap[("ws", "hangup", "strict", "fresh")] == 1


# ── followup_gap ────────────────────────────────────────────────────────────


def test_record_followup_gap_tracks_helper_label():
    rm.record_followup_gap(
        reason="no_real_client",
        outcome="success",
        helper="task_followup_policy",
    )
    rm.record_followup_gap(
        reason="no_real_client",
        outcome="success",
        helper="crm_followup",
    )
    snap = rm.get_followup_gap_counters()
    assert snap[("no_real_client", "success", "task_followup_policy")] == 1
    assert snap[("no_real_client", "success", "crm_followup")] == 1


def test_record_followup_gap_with_none_outcome():
    rm.record_followup_gap(
        reason="manual_outcome",
        outcome=None,
        helper="task_followup_policy",
    )
    snap = rm.get_followup_gap_counters()
    assert snap[("manual_outcome", "unknown", "task_followup_policy")] == 1


# ── reset ───────────────────────────────────────────────────────────────────


def test_reset_for_tests_clears_all_three_families():
    rm.record_blocked_start(guard_code="x", mode="chat", runtime_type=None)
    rm.record_finalize(
        completed_via="rest", outcome="x", strict_mode=False, already_completed=False
    )
    rm.record_followup_gap(reason="x", outcome="x", helper="x")
    rm.reset_for_tests()
    assert rm.get_blocked_starts() == {}
    assert rm.get_finalize_counters() == {}
    assert rm.get_followup_gap_counters() == {}


# ── /admin/runtime/metrics endpoint ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_runtime_metrics_endpoint_renders_all_three_families():
    """Endpoint must emit `# HELP`/`# TYPE` lines for all three counter
    families — even when one family is empty — so a Prometheus scraper
    learns the metric names without seeing data first."""
    from app.api.client_domain_ops import get_runtime_metrics

    rm.record_blocked_start(
        guard_code="profile_incomplete",
        mode="call",
        runtime_type="crm_call",
    )
    rm.record_finalize(
        completed_via="rest",
        outcome="success",
        strict_mode=False,
        already_completed=False,
    )
    rm.record_followup_gap(
        reason="no_real_client",
        outcome="success",
        helper="task_followup_policy",
    )

    response = await get_runtime_metrics(_user=object())
    text = response.body.decode("utf-8")

    # All three families must declare their metric metadata
    assert "runtime_blocked_starts_total" in text
    assert "runtime_finalize_total" in text
    assert "runtime_followup_gap_total" in text
    assert "# HELP runtime_blocked_starts_total" in text
    assert "# TYPE runtime_blocked_starts_total counter" in text

    # Values from the three records above must surface
    assert 'guard="profile_incomplete"' in text
    assert 'completed_via="rest"' in text
    assert 'helper="task_followup_policy"' in text


@pytest.mark.asyncio
async def test_runtime_metrics_endpoint_works_with_empty_counters():
    """Cold-start scrape: every family advertises its metadata even with
    no data yet. Otherwise Prometheus assigns wrong type on first sample."""
    from app.api.client_domain_ops import get_runtime_metrics

    response = await get_runtime_metrics(_user=object())
    text = response.body.decode("utf-8")

    assert "# HELP runtime_blocked_starts_total" in text
    assert "# HELP runtime_finalize_total" in text
    assert "# HELP runtime_followup_gap_total" in text
