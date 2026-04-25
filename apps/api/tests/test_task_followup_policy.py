"""TaskFollowUp policy (TZ-2 §12) — Phase 2.

Pin the §12 catalogs and the (outcome → reason / mode → channel) mappings
so any drift between the policy code, the CHECK constraints, and the
spec is caught at unit time. The dual-write integration with
``crm_followup.ensure_followup_for_session`` is exercised separately
in test_crm_followup.py (kept narrow there to avoid fixture overlap).
"""

from __future__ import annotations

import pytest

from app.services.task_followup_policy import (
    CHANNELS,
    REASONS,
    STATUSES,
    channel_for_mode,
    reason_for_outcome,
)


def test_reasons_match_spec():
    assert REASONS == frozenset({
        "callback_requested",
        "client_requests_later",
        "need_documents_or_time",
        "continue_next_call",
        "needs_followup",
        "documents_required",
        "consent_pending",
        "manual",
    })


def test_channels_match_spec():
    assert CHANNELS == frozenset({"phone", "chat", "email", "meeting", "sms"})


def test_statuses_match_spec():
    assert STATUSES == frozenset({"pending", "in_progress", "done", "cancelled"})


@pytest.mark.parametrize(
    "outcome, expected_reason",
    [
        ("callback_requested", "callback_requested"),
        ("CALLBACK_REQUESTED", "callback_requested"),  # case-insensitive
        ("callback", "callback_requested"),
        ("needs_followup", "needs_followup"),
        ("continue_next_call", "continue_next_call"),
        ("continue_later", "continue_next_call"),
        ("documents_required", "documents_required"),
        ("need_documents", "documents_required"),
        ("client_requests_later", "client_requests_later"),
        ("consent_pending", "consent_pending"),
    ],
)
def test_reason_for_outcome_maps_known_outcomes(outcome, expected_reason):
    assert reason_for_outcome(outcome) == expected_reason


def test_reason_for_outcome_returns_manual_for_unknown():
    assert reason_for_outcome(None) == "manual"
    assert reason_for_outcome("") == "manual"
    assert reason_for_outcome("garbage") == "manual"
    assert reason_for_outcome("deal_agreed") == "manual"  # not a follow-up case


@pytest.mark.parametrize(
    "mode, expected_channel",
    [
        ("call", "phone"),
        ("chat", "chat"),
        ("center", "phone"),
        ("CALL", "phone"),  # case-insensitive
        (None, None),
        ("", None),
        ("unknown_mode", None),
    ],
)
def test_channel_for_mode_maps_modes(mode, expected_channel):
    assert channel_for_mode(mode) == expected_channel


def test_reason_always_in_check_catalog():
    """Sanity: every reason the policy can produce must be in the
    DB CHECK catalog. This catches cases where a new outcome is added
    to _OUTCOME_TO_REASON but the migration's CHECK isn't updated."""
    from app.services.task_followup_policy import _OUTCOME_TO_REASON
    for reason in _OUTCOME_TO_REASON.values():
        assert reason in REASONS, f"reason {reason!r} not in REASONS catalog"
    assert "manual" in REASONS  # fallback must also be in the catalog


def test_channel_always_in_check_catalog():
    """Same sanity for channel mapping."""
    for mode in ("call", "chat", "center"):
        ch = channel_for_mode(mode)
        if ch is not None:
            assert ch in CHANNELS, f"channel {ch!r} not in CHANNELS catalog"
