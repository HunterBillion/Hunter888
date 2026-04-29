"""Tests for app.services.arena_metrics — registration and observe-side surface.

PR A only defines the metric handles; PR B wires them into hot paths.
This test suite locks in the public surface so wiring code (PR B) can
trust label sets and method names without re-checking on every change.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def metrics_module():
    """Import once. ``prometheus_client`` registers metrics in a global
    ``REGISTRY`` that rejects duplicate registration, so we cannot reload.
    Tests are independent: they only call ``observe``/``inc`` on existing
    handles, never re-register.
    """
    import app.services.arena_metrics as m

    return m


def test_all_handles_present(metrics_module):
    expected = {
        "ARENA_AI_BOT_LATENCY",
        "ARENA_AI_JUDGE_LATENCY",
        "ARENA_QUEUE_WAIT",
        "ARENA_ROUND_DURATION",
        "ARENA_FINALIZE_ATTEMPTS",
        "ARENA_JUDGE_DEGRADED",
        "ARENA_DUEL_STATE_TRANSITIONS",
        "ARENA_WS_DISCONNECT",
    }
    actual = set(metrics_module.__all__)
    assert expected == actual, f"surface drift: missing={expected - actual} extra={actual - expected}"


def test_histograms_observe_safely(metrics_module):
    """Each histogram handle must accept .labels(...).observe(seconds)."""
    metrics_module.ARENA_AI_BOT_LATENCY.labels(provider="gemini", status="ok").observe(1.23)
    metrics_module.ARENA_AI_JUDGE_LATENCY.labels(judge_type="round", status="ok").observe(2.5)
    metrics_module.ARENA_QUEUE_WAIT.labels(mode="classic", outcome="matched").observe(15)
    metrics_module.ARENA_ROUND_DURATION.labels(
        mode="classic", round_no="1", end_reason="message_limit"
    ).observe(45)


def test_counters_inc_safely(metrics_module):
    metrics_module.ARENA_FINALIZE_ATTEMPTS.labels(outcome="win", already_completed="false").inc()
    metrics_module.ARENA_JUDGE_DEGRADED.labels(reason="timeout").inc()
    metrics_module.ARENA_DUEL_STATE_TRANSITIONS.labels(
        from_state="round_active", to_state="round_judging"
    ).inc()
    metrics_module.ARENA_WS_DISCONNECT.labels(phase="in_duel", reason="client_close").inc()


def test_metrics_appear_in_default_registry():
    """Without metrics_enabled, these still register on import; expose is gated."""
    from prometheus_client import REGISTRY

    # ``REGISTRY.collect()`` returns family base names. For Counter, the
    # exposition adds ``_total`` on the wire (e.g.
    # ``arena_finalize_attempts_total`` in /metrics output) but the
    # in-process family name is the bare ``arena_finalize_attempts``.
    expected_metric_names = {
        "arena_ai_bot_latency_seconds",
        "arena_ai_judge_latency_seconds",
        "arena_queue_wait_seconds",
        "arena_round_duration_seconds",
        "arena_finalize_attempts",
        "arena_judge_degraded",
        "arena_duel_state_transitions",
        "arena_ws_disconnect",
    }

    # Force-import so registration runs on a fresh interpreter session.
    import app.services.arena_metrics  # noqa: F401

    # ``REGISTRY.collect()`` yields each registered metric family; the family
    # name is the base name (no _bucket/_sum/_count suffix). This is the
    # public API for inspecting registrations.
    registered = {family.name for family in REGISTRY.collect()}
    missing = expected_metric_names - registered
    assert not missing, f"arena metrics not registered: {missing}"


def test_histogram_bucket_thresholds_match_slo(metrics_module):
    """Lock in operator-meaningful bucket thresholds — changing these silently
    would break dashboards / alerts that bucket on these exact edges.
    """
    # Re-importing the module re-registers; just check the bucket constants
    # the module exports indirectly via the metric definition.
    import app.services.arena_metrics as m

    assert 8.0 in m._AI_LATENCY_BUCKETS, "8s bucket needed for 'feels stuck' threshold"
    assert 12.0 in m._AI_LATENCY_BUCKETS, "12s bucket needed for judge SLO"
    assert 60 in m._QUEUE_WAIT_BUCKETS, "60s bucket needed for matchmaker timeout"
    assert 90 in m._ROUND_DURATION_BUCKETS, "90s bucket needed for round time-limit"
