"""TZ-4 D5 — conversation policy engine contract tests.

Six checks × happy/sad paths plus warn-only vs enforce-mode toggling.

Each check has at least one positive (violation fires) and one
negative (clean reply) assertion. Persona-aware checks are exercised
by handcrafting a ``SessionPersonaSnapshot`` / ``MemoryPersona``
fixture; the legacy three checks run with mode + previous-replies
only so the test surface mirrors the production callsite shape.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.domain_event import DomainEvent
from app.models.persona import MemoryPersona, SessionPersonaSnapshot
from app.services import conversation_policy_engine as engine


# ── Helpers ──────────────────────────────────────────────────────────────


def _snapshot(
    *,
    full_name: str = "Иванов Петр Сергеевич",
    address_form: str = "вы",
    gender: str = "male",
) -> SessionPersonaSnapshot:
    return SessionPersonaSnapshot(
        session_id=uuid.uuid4(),
        lead_client_id=uuid.uuid4(),
        full_name=full_name,
        gender=gender,
        address_form=address_form,
        tone="neutral",
        captured_from="real_client",
        persona_version=1,
        mutation_blocked_count=0,
    )


def _persona_with_locked_slots(*slots: str) -> MemoryPersona:
    return MemoryPersona(
        id=uuid.uuid4(),
        lead_client_id=uuid.uuid4(),
        full_name="Иванов Петр",
        gender="male",
        address_form="вы",
        tone="neutral",
        version=1,
        do_not_ask_again_slots=list(slots),
        confirmed_facts={},
    )


# ── Check 1: too_long_for_mode ───────────────────────────────────────────


def test_too_long_call_mode_fires_at_4_sentences():
    """Call/center mode caps at 3 sentences. Reply with 4 → fires."""
    reply = "Здравствуйте. У меня есть предложение. Давайте обсудим. Это будет полезно."
    result = engine.audit_assistant_reply(reply=reply, mode="call")
    codes = [v.code.value for v in result.violations]
    assert "too_long_for_mode" in codes


def test_too_long_call_mode_clean_at_2_sentences():
    """Two short sentences in call mode is within the limit."""
    result = engine.audit_assistant_reply(reply="Понял. Перезвоню вам.", mode="call")
    codes = [v.code.value for v in result.violations]
    assert "too_long_for_mode" not in codes


def test_too_long_chat_mode_allows_more_sentences():
    """Chat caps at 5 — same 4-sentence reply is clean here."""
    reply = "Здравствуйте. У меня есть предложение. Давайте обсудим. Это будет полезно."
    result = engine.audit_assistant_reply(reply=reply, mode="chat")
    codes = [v.code.value for v in result.violations]
    assert "too_long_for_mode" not in codes


# ── Check 2: near_repeat ─────────────────────────────────────────────────


def test_near_repeat_high_severity():
    prev = "Здравствуйте, я Иван, звоню из банка."
    reply = "Здравствуйте, я Иван, звоню из банка."  # exact match
    result = engine.audit_assistant_reply(
        reply=reply, mode="chat", previous_assistant_replies=[prev],
    )
    matches = [v for v in result.violations if v.code.value == "near_repeat"]
    assert matches and matches[0].severity == "high"


def test_near_repeat_clean_when_distinct():
    prev = "Какой у вас доход?"
    reply = "Расскажите про вашу работу."
    result = engine.audit_assistant_reply(
        reply=reply, mode="chat", previous_assistant_replies=[prev],
    )
    codes = [v.code.value for v in result.violations]
    assert "near_repeat" not in codes


# ── Check 3: missing_next_step ───────────────────────────────────────────


def test_missing_next_step_chat_mode():
    """Chat reply with no next-step verb → fires."""
    result = engine.audit_assistant_reply(
        reply="Понятно, спасибо за информацию.", mode="chat",
    )
    codes = [v.code.value for v in result.violations]
    assert "missing_next_step" in codes


def test_missing_next_step_skipped_in_call_mode():
    """Call mode is short by design — next-step verb not enforced."""
    result = engine.audit_assistant_reply(
        reply="Понятно, спасибо.", mode="call",
    )
    codes = [v.code.value for v in result.violations]
    assert "missing_next_step" not in codes


def test_missing_next_step_clean_with_next_step_verb():
    result = engine.audit_assistant_reply(
        reply="Хорошо, я перезвоню вам через час и уточним детали.", mode="chat",
    )
    codes = [v.code.value for v in result.violations]
    assert "missing_next_step" not in codes


# ── Check 4: persona_conflict ────────────────────────────────────────────


def test_persona_conflict_fires_on_role_reversal():
    """Reply addresses listener as the snapshot's own first name —
    role-reversal pattern — fires the persona_conflict check."""
    snapshot = _snapshot(full_name="Иванов Петр Сергеевич")
    result = engine.audit_assistant_reply(
        reply="Уважаемый Иванов, я звоню по вашему вопросу.",
        mode="call",
        snapshot=snapshot,
    )
    codes = [v.code.value for v in result.violations]
    assert "persona_conflict" in codes


def test_persona_conflict_clean_when_no_snapshot():
    """Without a snapshot the check is skipped — legacy callers don't
    accidentally trigger it."""
    result = engine.audit_assistant_reply(
        reply="Иванов, что вы думаете?", mode="call",
    )
    codes = [v.code.value for v in result.violations]
    assert "persona_conflict" not in codes


# ── Check 5: asked_known_slot_again ──────────────────────────────────────


def test_asked_known_slot_again_fires_on_locked_slot():
    persona = _persona_with_locked_slots("city")
    result = engine.audit_assistant_reply(
        reply="В каком городе вы живёте?",
        mode="chat",
        persona=persona,
    )
    codes = [v.code.value for v in result.violations]
    assert "asked_known_slot_again" in codes


def test_asked_known_slot_again_clean_when_no_question_mark():
    """Mentioning a slot keyword in a confirmation/recap (no question
    mark) is not a re-ask."""
    persona = _persona_with_locked_slots("city")
    result = engine.audit_assistant_reply(
        reply="Понял, ваш город уже зафиксирован.",
        mode="chat",
        persona=persona,
    )
    codes = [v.code.value for v in result.violations]
    assert "asked_known_slot_again" not in codes


def test_asked_known_slot_again_skipped_when_slot_unlocked():
    persona = _persona_with_locked_slots()  # no locks
    result = engine.audit_assistant_reply(
        reply="В каком городе вы живёте?",
        mode="chat",
        persona=persona,
    )
    codes = [v.code.value for v in result.violations]
    assert "asked_known_slot_again" not in codes


# ── Check 6: unjustified_identity_change ─────────────────────────────────


def test_unjustified_identity_change_fires_on_ty_for_vy_snapshot():
    snapshot = _snapshot(address_form="вы")
    result = engine.audit_assistant_reply(
        reply="Скажи, ты будешь платить?", mode="call", snapshot=snapshot,
    )
    codes = [v.code.value for v in result.violations]
    assert "unjustified_identity_change" in codes


def test_unjustified_identity_change_skipped_for_auto_snapshot():
    """``auto`` form means the runtime hasn't locked an address — no
    enforcement direction yet."""
    snapshot = _snapshot(address_form="auto")
    result = engine.audit_assistant_reply(
        reply="Скажи, ты будешь платить?", mode="call", snapshot=snapshot,
    )
    codes = [v.code.value for v in result.violations]
    assert "unjustified_identity_change" not in codes


# ── Warn-only vs enforce ─────────────────────────────────────────────────


def test_should_block_is_false_in_warn_only_default():
    """Default config: enforce_enabled=False. Even a critical
    violation does not block — only the event fires."""
    snapshot = _snapshot(address_form="вы")
    result = engine.audit_assistant_reply(
        reply="Скажи, ты будешь платить?", mode="call", snapshot=snapshot,
    )
    assert result.enforce_active is False
    assert result.should_block is False
    # critical violation present
    assert any(v.severity == "critical" for v in result.violations)


def test_should_block_true_when_enforce_on_and_critical(monkeypatch):
    """Flip the flag → critical violation now blocks."""
    monkeypatch.setattr(
        engine.settings, "conversation_policy_enforce_enabled", True, raising=False,
    )
    snapshot = _snapshot(address_form="вы")
    result = engine.audit_assistant_reply(
        reply="Скажи, ты будешь платить?", mode="call", snapshot=snapshot,
    )
    assert result.enforce_active is True
    assert result.should_block is True


def test_should_block_false_when_enforce_on_but_only_low_severity(monkeypatch):
    """Enforce mode does NOT block on medium/high — only ``critical``."""
    monkeypatch.setattr(
        engine.settings, "conversation_policy_enforce_enabled", True, raising=False,
    )
    # missing_next_step is severity=low; near_repeat is high — neither blocks
    result = engine.audit_assistant_reply(
        reply="Понятно, хорошо.", mode="chat",
    )
    assert result.enforce_active is True
    # Violation present (missing_next_step) but severity is "low"
    assert any(v.code.value == "missing_next_step" for v in result.violations)
    assert result.should_block is False


# ── render_prompt ────────────────────────────────────────────────────────


def test_render_prompt_call_mode_short_form():
    out = engine.render_prompt(mode="call")
    assert "Звонок/центр" in out
    assert "1-2 короткими фразами" in out


def test_render_prompt_chat_mode_allows_more():
    out = engine.render_prompt(mode="chat")
    assert "Чат: отвечай кратко" in out
    assert "1-2 короткими фразами" not in out


def test_render_prompt_with_snapshot_adds_persona_block():
    snapshot = _snapshot(full_name="Алёна Васильева", address_form="вы")
    out = engine.render_prompt(mode="call", snapshot=snapshot)
    assert "Persona snapshot (TZ-4 §9)" in out
    assert "Алёна Васильева" in out
    assert "«вы»" in out


def test_render_prompt_without_snapshot_omits_persona_block():
    out = engine.render_prompt(mode="call")
    assert "Persona snapshot" not in out


# ── emit_violation ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_emit_violation_no_op_when_clean(monkeypatch):
    """Clean audit result → emit is a no-op (no events written)."""
    captured: list[dict] = []

    async def _emit(db, **kwargs):
        captured.append(kwargs)
        return _make_event()

    monkeypatch.setattr(engine, "emit_domain_event", _emit)

    result = engine.PolicyAuditResult(violations=[], enforce_active=False)
    events = await engine.emit_violation(
        SimpleNamespace(),
        result=result,
        session_id=uuid.uuid4(),
        lead_client_id=uuid.uuid4(),
        actor_id=None,
    )
    assert events == []
    assert captured == []


@pytest.mark.asyncio
async def test_emit_violation_writes_one_event_per_violation(monkeypatch):
    """Every violation → one ``conversation.policy_violation_detected``
    event with the correct code in payload."""
    captured: list[dict] = []

    async def _emit(db, **kwargs):
        captured.append(kwargs)
        return _make_event(kwargs.get("event_type"))

    monkeypatch.setattr(engine, "emit_domain_event", _emit)

    snapshot = _snapshot(address_form="вы")
    # Chat reply with: (a) ``ты`` for ``вы`` snapshot → critical
    # ``unjustified_identity_change``, plus (b) no next-step verb →
    # low ``missing_next_step``. Two violations exercises the per-
    # violation event fan-out.
    result = engine.audit_assistant_reply(
        reply="Понятно, ты сам разберись.",
        mode="chat",
        snapshot=snapshot,
    )
    assert len(result.violations) >= 2

    events = await engine.emit_violation(
        SimpleNamespace(),
        result=result,
        session_id=uuid.uuid4(),
        lead_client_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
    )
    assert len(events) == len(result.violations)
    for c in captured:
        assert c["event_type"] == "conversation.policy_violation_detected"
        assert c["payload"]["enforce_active"] is False  # warn-only default


@pytest.mark.asyncio
async def test_emit_violation_falls_back_to_session_id_when_no_lead(monkeypatch):
    """home_preview / pvp sessions have no lead_client_id — emit
    anchors on session_id instead so DomainEvent.lead_client_id stays
    NOT NULL (TZ-1 invariant)."""
    captured: list[dict] = []

    async def _emit(db, **kwargs):
        captured.append(kwargs)
        return _make_event()

    monkeypatch.setattr(engine, "emit_domain_event", _emit)

    sid = uuid.uuid4()
    result = engine.PolicyAuditResult(
        violations=[
            engine.PolicyViolation(
                code=engine.ViolationCode.MISSING_NEXT_STEP,
                severity="low",
                message="x",
                evidence={},
            )
        ],
        enforce_active=False,
    )
    await engine.emit_violation(
        SimpleNamespace(),
        result=result,
        session_id=sid,
        lead_client_id=None,
        actor_id=None,
    )
    assert captured[0]["lead_client_id"] == sid


# ── Test helpers — domain event factory ──────────────────────────────────


def _make_event(event_type: str = "conversation.policy_violation_detected") -> DomainEvent:
    return DomainEvent(
        id=uuid.uuid4(),
        lead_client_id=uuid.uuid4(),
        event_type=event_type,
        actor_type="system",
        source="test",
        payload_json={},
        idempotency_key=f"{event_type}:test",
        schema_version=1,
        correlation_id="test",
    )
