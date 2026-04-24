"""Regression tests for the bugs the 9-layer diagnostic flagged.

Each test fails on the pre-fix code and passes on the post-fix code.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


# ── F-L7-3/F-L7-4 — is_event_persisted guard ─────────────────────────────


def test_is_event_persisted_rejects_disabled_stub():
    from app.models.domain_event import DomainEvent
    from app.services.client_domain import is_event_persisted

    stub = DomainEvent(
        id=uuid.uuid4(),
        lead_client_id=uuid.uuid4(),
        event_type="x",
        actor_type="system",
        source="test",
        payload_json={},
        idempotency_key="disabled",
        schema_version=1,
    )
    assert is_event_persisted(stub) is False


def test_is_event_persisted_rejects_transient_no_created_at():
    from app.models.domain_event import DomainEvent
    from app.services.client_domain import is_event_persisted

    # Never flushed, no created_at — simulates the non-strict
    # failure path that used to poison ``metadata.domain_event_id``.
    transient = DomainEvent(
        id=uuid.uuid4(),
        lead_client_id=uuid.uuid4(),
        event_type="x",
        actor_type="system",
        source="test",
        payload_json={},
        idempotency_key="real-key",
        schema_version=1,
    )
    # no ``db.add`` → SQLAlchemy state is ``transient`` and
    # ``created_at`` is None.
    assert is_event_persisted(transient) is False


def test_is_event_persisted_rejects_none():
    from app.services.client_domain import is_event_persisted

    assert is_event_persisted(None) is False


# ── F-L7-2 — CompletionResult.failures tuple ─────────────────────────────


def test_completion_result_has_failures_field():
    from app.services.completion_policy import (
        CompletedVia,
        CompletionResult,
        TerminalOutcome,
        TerminalReason,
    )

    result = CompletionResult(
        session_id=uuid.uuid4(),
        outcome=TerminalOutcome.success,
        reason=TerminalReason.user_ended,
        completed_via=CompletedVia.rest,
        strict_mode=False,
        already_completed=False,
        events_emitted=(),
        followup_id=None,
    )
    assert result.failures == ()  # default empty tuple

    result_with_fail = CompletionResult(
        session_id=uuid.uuid4(),
        outcome=TerminalOutcome.success,
        reason=TerminalReason.user_ended,
        completed_via=CompletedVia.rest,
        strict_mode=False,
        already_completed=False,
        events_emitted=(),
        followup_id=None,
        failures=("crm:ValueError",),
    )
    assert "crm:ValueError" in result_with_fail.failures


# ── F-L8-2 — voice_params deep-copy ──────────────────────────────────────


@pytest.mark.asyncio
async def test_persona_snapshot_mirror_deep_copies_voice_params():
    from app.models.persona_snapshot import PersonaSnapshot
    from app.services import persona_snapshot as ps

    story_id = uuid.uuid4()
    session = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        lead_client_id=None,
        client_story_id=story_id,
        real_client_id=None,
    )
    shared_params = {"stability": 0.6, "similarity": 0.8}
    first = PersonaSnapshot(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        client_story_id=story_id,
        full_name="Анна",
        gender="female",
        archetype_code="anxious",
        persona_label="тревожная",
        voice_id="voice-1",
        voice_provider="elevenlabs",
        voice_params=shared_params,
        source_ref="session.start",
    )

    call_results = iter(
        [
            SimpleNamespace(scalar_one_or_none=lambda: None),
            SimpleNamespace(scalar_one_or_none=lambda: first),
        ]
    )
    added: list = []

    db = SimpleNamespace()
    db.execute = AsyncMock(side_effect=lambda *a, **k: next(call_results))
    db.add = lambda o: added.append(o)
    db.flush = AsyncMock()
    db.get = AsyncMock(return_value=None)

    new_snapshot = await ps.capture(
        db,
        session=session,
        full_name="ignored",
        gender="male",
        archetype_code="skeptic",
        voice_id="different",
        voice_provider="webspeech",
        source_ref="story.continue",
    )

    # The new snapshot owns a separate dict — mutating it does not
    # affect the first snapshot's JSONB value.
    assert new_snapshot.voice_params is not first.voice_params
    new_snapshot.voice_params["injected"] = True
    assert "injected" not in first.voice_params


# ── F-X-2 — env example has all new flags ────────────────────────────────


def test_env_example_has_phase_1_and_tz_1_flags():
    from pathlib import Path

    # tests/ → apps/api → apps → project root = parents[3]
    env_example = (
        Path(__file__).resolve().parents[3] / ".env.production.example"
    )
    text = env_example.read_text(encoding="utf-8")
    for key in (
        "CLIENT_DOMAIN_DUAL_WRITE_ENABLED",
        "CLIENT_DOMAIN_CUTOVER_READ_ENABLED",
        "CLIENT_DOMAIN_STRICT_EMIT",
        "COMPLETION_POLICY_STRICT",
        "COMPLETION_POLICY_EMIT_EVENT",
    ):
        assert key in text, f"{key} missing from .env.production.example"


# ── F-L6-3 — pending-events endpoints are rate-limited ───────────────────


def test_pending_events_endpoints_have_rate_limits():
    """Source-level check: both handlers must carry ``@limiter.limit(...)``.

    We grep the module text because ``slowapi``'s decorator wraps in a
    way that is easier to inspect at the source level than via
    ``inspect`` on the decorated object.
    """
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "app" / "api" / "pending_events.py"
    ).read_text(encoding="utf-8")
    assert "@limiter.limit(" in source, (
        "pending_events endpoints must decorate with @limiter.limit(...)"
    )
    # Expect two decorators: GET + POST
    assert source.count("@limiter.limit(") >= 2
