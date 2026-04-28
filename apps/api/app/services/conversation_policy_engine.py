"""Canonical conversation policy engine (TZ-4 §10).

Replaces ``app.services.conversation_policy`` (legacy) as the single
sanctioned authority on what an AI reply may and may not contain. Six
explicit checks with explainable violations, plus a prompt renderer
that injects the same rules into the LLM system prompt at build time.

Public surface
--------------

* :func:`audit_assistant_reply` — main entry point. Runs the six §10.2
  checks and returns a :class:`PolicyAuditResult` with severity-typed
  violations. Optional ``snapshot=`` and ``persona=`` arguments unlock
  the persona-aware checks (``persona_conflict``,
  ``unjustified_identity_change``, ``asked_known_slot_again``); without
  them only the three legacy checks (``too_long_for_mode``,
  ``near_repeat``, ``missing_next_step``) fire.

* :func:`render_prompt` — replaces the legacy ``conversation_policy_
  prompt(mode)`` from ``conversation_policy.py``. Same string output
  for callers that don't supply a snapshot; persona-aware variants
  appear when one is provided. Spec §13.2.1 forbids the legacy
  function — ``conversation_policy.py`` keeps a deprecated wrapper
  during the warn-only window for backward compatibility, then D7
  cutover removes the legacy module entirely.

* :func:`emit_violation` — async writer for
  ``conversation.policy_violation_detected`` (the 19th canonical event
  registered in D1.1). Used by WS handlers at the message-out boundary
  so every violation lands in the canonical event log even when the
  engine is in warn-only mode (no message blocking).

* :func:`enforce_enabled` — read of
  ``settings.conversation_policy_enforce_enabled``. Single import
  target so callers don't sprinkle the flag check; flip the flag once
  in config and the whole engine respects it.

Six checks (§10.2)
------------------

| code                            | severity | description |
|---------------------------------|----------|-------------|
| ``too_long_for_mode``           | medium   | reply > N sentences for the mode (call/center: 3, chat: 5) |
| ``near_repeat``                 | high     | reply ratio ≥ 0.86 vs. any of last 5 assistant replies |
| ``missing_next_step``           | low      | chat/center: no "next-step" verb in reply |
| ``persona_conflict``            | high     | reply mentions a name/role/gender that contradicts the snapshot |
| ``asked_known_slot_again``      | medium   | reply asks for a slot that's already in ``confirmed_facts`` |
| ``unjustified_identity_change`` | critical | reply attempts to switch ``address_form`` or refer to AI as different identity |

Warn-only vs. enforce
---------------------

The engine ships in **warn-only** mode by default. Per spec §12.3.1 the
flip to enforce comes after 7 days of warn-only telemetry and an FP
rate < 5%. Until then:

* The audit fn always runs.
* All violations are returned to the caller (and emitted via
  :func:`emit_violation` so admins can see counts).
* No message is ever blocked.

After enforce flips on, callers branch on
:attr:`PolicyAuditResult.should_block` and refuse to send the reply
when True. ``should_block`` only flips True for ``critical`` severity
+ enforce mode — medium/high warnings stay observational.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from typing import Any, Iterable, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.domain_event import DomainEvent
from app.models.persona import MemoryPersona, SessionPersonaSnapshot
from app.services.client_domain import emit_domain_event
from app.services.session_state import normalize_session_mode

logger = logging.getLogger(__name__)


# ── Violation taxonomy ───────────────────────────────────────────────────


class ViolationCode(str, Enum):
    """The six §10.2 codes. ``str`` mixin so a code is also a JSON-safe
    payload value without ``.value`` ceremony."""

    TOO_LONG_FOR_MODE = "too_long_for_mode"
    NEAR_REPEAT = "near_repeat"
    MISSING_NEXT_STEP = "missing_next_step"
    PERSONA_CONFLICT = "persona_conflict"
    ASKED_KNOWN_SLOT_AGAIN = "asked_known_slot_again"
    UNJUSTIFIED_IDENTITY_CHANGE = "unjustified_identity_change"


# Severity classes — only ``critical`` blocks in enforce mode. The other
# levels are observational and surface in the timeline / admin UI for
# coaching feedback.
_BLOCKING_SEVERITY = "critical"


_SEVERITY_BY_CODE: dict[ViolationCode, str] = {
    ViolationCode.TOO_LONG_FOR_MODE: "medium",
    ViolationCode.NEAR_REPEAT: "high",
    ViolationCode.MISSING_NEXT_STEP: "low",
    ViolationCode.PERSONA_CONFLICT: "high",
    ViolationCode.ASKED_KNOWN_SLOT_AGAIN: "medium",
    ViolationCode.UNJUSTIFIED_IDENTITY_CHANGE: "critical",
}


_HUMAN_MESSAGE: dict[ViolationCode, str] = {
    ViolationCode.TOO_LONG_FOR_MODE: "Ответ слишком длинный для режима",
    ViolationCode.NEAR_REPEAT: "Ответ почти повторяет предыдущую реплику AI",
    ViolationCode.MISSING_NEXT_STEP: "В ответе нет явного следующего шага",
    ViolationCode.PERSONA_CONFLICT: "Ответ противоречит идентичности клиента",
    ViolationCode.ASKED_KNOWN_SLOT_AGAIN: "Ответ запрашивает уже подтверждённый факт",
    ViolationCode.UNJUSTIFIED_IDENTITY_CHANGE: "Ответ меняет идентичность клиента без основания",
}


@dataclass(frozen=True)
class PolicyViolation:
    code: ViolationCode
    severity: str
    message: str
    evidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyAuditResult:
    """Result of :func:`audit_assistant_reply`.

    ``should_block`` is the bottom-line decision callers consult after
    audit: True only when enforce mode is ON **and** at least one
    violation has ``critical`` severity. Warn-only mode always returns
    False here (the violations still appear so they can be emitted).
    """

    violations: list[PolicyViolation]
    enforce_active: bool

    @property
    def is_clean(self) -> bool:
        return not self.violations

    @property
    def should_block(self) -> bool:
        if not self.enforce_active:
            return False
        return any(v.severity == _BLOCKING_SEVERITY for v in self.violations)


# ── Helpers ──────────────────────────────────────────────────────────────


_NEXT_STEP_RE = re.compile(
    r"(следующ|дальше|пришл|уточн|провер|созвон|перезвон|договор|решим|зафиксир)",
    flags=re.IGNORECASE,
)

_SENTENCE_SPLITTER = re.compile(r"[.!?]+")


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _max_sentences_for_mode(mode: str) -> int:
    return 3 if mode in {"call", "center"} else 5


def _count_sentences(reply: str) -> int:
    return sum(1 for s in _SENTENCE_SPLITTER.split(reply) if s.strip())


def _violation(code: ViolationCode, **evidence: Any) -> PolicyViolation:
    return PolicyViolation(
        code=code,
        severity=_SEVERITY_BY_CODE[code],
        message=_HUMAN_MESSAGE[code],
        evidence={k: v for k, v in evidence.items() if v is not None},
    )


# ── Six checks ──────────────────────────────────────────────────────────


def _check_too_long(reply: str, *, mode: str) -> PolicyViolation | None:
    n = _count_sentences(reply)
    limit = _max_sentences_for_mode(mode)
    if n > limit:
        return _violation(
            ViolationCode.TOO_LONG_FOR_MODE,
            mode=mode,
            sentence_count=n,
            limit=limit,
        )
    return None


def _check_near_repeat(
    reply: str, *, previous_replies: Sequence[str], threshold: float = 0.86
) -> PolicyViolation | None:
    cur = _normalize_text(reply)
    if not cur:
        return None
    for prev in previous_replies:
        prev_norm = _normalize_text(prev)
        if not prev_norm:
            continue
        if cur == prev_norm:
            return _violation(
                ViolationCode.NEAR_REPEAT,
                ratio=1.0,
                threshold=threshold,
            )
        ratio = SequenceMatcher(None, cur, prev_norm).ratio()
        if ratio >= threshold:
            return _violation(
                ViolationCode.NEAR_REPEAT,
                ratio=round(ratio, 4),
                threshold=threshold,
            )
    return None


def _check_missing_next_step(reply: str, *, mode: str) -> PolicyViolation | None:
    # Only chat/center surfaces this — call mode replies are short by
    # contract and don't carry next-step semantics in the same way.
    if mode not in {"chat", "center"}:
        return None
    text = _normalize_text(reply)
    if not text:
        return None
    if not _NEXT_STEP_RE.search(text):
        return _violation(ViolationCode.MISSING_NEXT_STEP, mode=mode)
    return None


# Persona-aware checks (only fire when a snapshot/persona is provided).


def _check_persona_conflict(
    reply: str,
    *,
    snapshot: SessionPersonaSnapshot,
) -> PolicyViolation | None:
    """Surface if the reply mentions an identity contradicting the
    snapshot. Heuristic: look for the snapshot's full_name as a baseline
    expectation, and flag when the reply explicitly addresses the
    *manager* as the snapshot's name (role-reversal) or refers to the
    client by a clearly different first-name token.

    The check is intentionally conservative — false positives surface
    in the warn-only counter and inform threshold tuning during the
    7-day observation window before enforce flips on.
    """
    text = _normalize_text(reply)
    if not text or not snapshot.full_name:
        return None
    name_tokens = [
        tok for tok in re.split(r"\s+", _normalize_text(snapshot.full_name)) if len(tok) >= 3
    ]
    if not name_tokens:
        return None
    # Role-reversal heuristic: the reply addresses the listener with a
    # client-style "вы, имя" pattern using the snapshot's own name.
    # That's a strong signal the AI confused identities.
    snapshot_first = name_tokens[0]
    role_reversal_re = re.compile(
        rf"(уважаем(ый|ая)\s+){{0,1}}{re.escape(snapshot_first)}\b", flags=re.IGNORECASE
    )
    if role_reversal_re.search(text):
        return _violation(
            ViolationCode.PERSONA_CONFLICT,
            evidence_kind="role_reversal_pattern",
            snapshot_full_name=snapshot.full_name,
            snapshot_first_token=snapshot_first,
        )
    return None


def _check_asked_known_slot(
    reply: str,
    *,
    persona: MemoryPersona,
) -> PolicyViolation | None:
    """If a slot is locked in ``do_not_ask_again_slots``, the reply
    must not ask for it again. Heuristic: each known slot has a small
    set of question-phrase triggers; a hit means the AI re-asked.
    """
    locked = set(persona.do_not_ask_again_slots or [])
    if not locked:
        return None
    text = _normalize_text(reply)
    if not text or "?" not in reply:
        # No question mark → not a re-ask. Even if a slot keyword
        # appears, it's likely confirmation/recap, not a fresh ask.
        return None

    # Each value is a frozenset of question-phrase fragments. Frozenset
    # (not tuple) eliminates the missing-trailing-comma footgun the
    # previous tuple form had — a single-string tuple needs ``("foo",)``
    # but a typo of ``("foo")`` made the entire entry a bare string.
    # The previous code papered over it with an isinstance(str) → tuple
    # promotion at the call site; using ``frozenset`` makes the typo
    # impossible (a single-string set is still iterable).
    triggers: dict[str, frozenset[str]] = {
        "full_name": frozenset({"как вас зовут", "ваше им", "представьтес"}),
        "phone": frozenset({"ваш телефон", "номер телефона", "по какому номеру"}),
        "email": frozenset({"ваш e-mail", "ваша почта", "электронн"}),
        "city": frozenset({"в каком городе", "ваш город", "из какого города"}),
        "age": frozenset({"сколько вам лет", "ваш возраст"}),
        "gender": frozenset({"вы мужчина", "вы женщина"}),
        "role_title": frozenset({"кем вы прихо", "ваша роль"}),
        "total_debt": frozenset({"сколько вы должн", "размер долга", "ваш долг"}),
        "creditors": frozenset({"кому вы должн", "перед каким", "ваши кредитор"}),
        "income": frozenset({"ваш доход", "сколько зарабат"}),
        "income_type": frozenset({"официально работ", "ваш доход офиц"}),
        "family_status": frozenset({"вы женат", "вы замуж", "вы в браке"}),
        "children_count": frozenset({"сколько у вас детей"}),
        "property_status": frozenset({"ваше имущество", "у вас квартира"}),
    }
    for slot_code in locked:
        triggers_for_slot = triggers.get(slot_code, frozenset())
        if any(t in text for t in triggers_for_slot):
            return _violation(
                ViolationCode.ASKED_KNOWN_SLOT_AGAIN,
                slot_code=slot_code,
            )
    return None


def _check_unjustified_identity_change(
    reply: str,
    *,
    snapshot: SessionPersonaSnapshot,
) -> PolicyViolation | None:
    """Reply attempts to switch the address-form (``вы``→``ты`` or vice
    versa) without an explicit profile update. Conservative: fires only
    when ``вы`` snapshot meets a clearly-``ты`` reply.
    """
    text = _normalize_text(reply)
    if not text:
        return None
    locked = (snapshot.address_form or "auto").lower()
    if locked not in {"вы", "formal"}:
        # ``ты`` / ``informal`` / ``auto`` — no enforcement direction.
        return None
    # Crude detection of a singular informal address: " ты " / "тебя" /
    # "тебе" appearing in client-direction text. Flag unless surrounded
    # by quotes (which suggests reported speech, not direct address).
    informal_re = re.compile(r"\b(ты|тебя|тебе|твоё|твой|твоя)\b")
    if informal_re.search(text):
        # Avoid common reported-speech patterns ("он сказал ты ...").
        if not re.search(r"(сказал|говорит|пишет|написал)\s+\S+\s+(ты|тебя)", text):
            return _violation(
                ViolationCode.UNJUSTIFIED_IDENTITY_CHANGE,
                snapshot_address_form=locked,
            )
    return None


# ── Public API ──────────────────────────────────────────────────────────


def enforce_enabled() -> bool:
    """Single import target for the enforce-mode flag. Centralised so a
    future config rename only changes one line."""
    return bool(getattr(settings, "conversation_policy_enforce_enabled", False))


def audit_assistant_reply(
    *,
    reply: str,
    mode: object | None = None,
    previous_assistant_replies: Iterable[str] | None = None,
    snapshot: SessionPersonaSnapshot | None = None,
    persona: MemoryPersona | None = None,
) -> PolicyAuditResult:
    """Run the six §10.2 checks against ``reply`` and return a result.

    The legacy three checks always run (``too_long_for_mode``,
    ``near_repeat``, ``missing_next_step``). The three persona-aware
    checks are skipped when their input is missing — call sites that
    haven't yet wired the snapshot / persona keep the existing
    behaviour without misleading violations.
    """
    normalized_mode = normalize_session_mode(mode) or "chat"
    previous = list(previous_assistant_replies or [])

    violations: list[PolicyViolation] = []

    if v := _check_too_long(reply, mode=normalized_mode):
        violations.append(v)
    if v := _check_near_repeat(reply, previous_replies=previous):
        violations.append(v)
    if v := _check_missing_next_step(reply, mode=normalized_mode):
        violations.append(v)
    if snapshot is not None:
        if v := _check_persona_conflict(reply, snapshot=snapshot):
            violations.append(v)
        if v := _check_unjustified_identity_change(reply, snapshot=snapshot):
            violations.append(v)
    if persona is not None:
        if v := _check_asked_known_slot(reply, persona=persona):
            violations.append(v)

    return PolicyAuditResult(
        violations=violations,
        enforce_active=enforce_enabled(),
    )


def render_prompt(
    *,
    mode: object | None = None,
    snapshot: SessionPersonaSnapshot | None = None,
) -> str:
    """Replace the legacy ``conversation_policy_prompt(mode)`` with a
    spec-aware renderer.

    Output is identical to the legacy function for the mode-only path
    so existing callers (``llm.py:2194,2584``) get drop-in behaviour.
    When a snapshot is provided, the renderer adds an explicit
    "address the client as <full_name>, formal `вы`" line so the
    LLM has structured persona context instead of inferring it from
    the system prompt prose.
    """
    normalized_mode = normalize_session_mode(mode) or "chat"
    length_rule = (
        "Звонок/центр: отвечай 1-2 короткими фразами, без лекций."
        if normalized_mode in {"call", "center"}
        else "Чат: отвечай кратко, максимум 4 предложения, если пользователь не просит подробности."
    )
    terminal_rule = (
        "В центре нельзя завершать без одного из исходов: договор согласован, договор не согласован, продолжить в другом звонке."
        if normalized_mode == "center"
        else "Не закрывай сценарий, если следующий шаг бизнес-логики ещё не зафиксирован."
    )
    base = (
        "\n\n## Conversation Policy Engine\n"
        f"- {length_rule}\n"
        "- Не повторяй вопрос, если факт уже был получен в предыдущих сообщениях.\n"
        "- Каждая существенная реплика должна фиксировать один факт или вести к одному следующему шагу.\n"
        "- Если не хватает данных, спроси только минимально нужный следующий вопрос.\n"
        "- Не меняй имя, пол, роль или обращение клиента без явного обновления профиля.\n"
        f"- {terminal_rule}\n"
    )
    if snapshot is not None and snapshot.full_name:
        addr = (snapshot.address_form or "auto").lower()
        addr_word = "«вы»" if addr in {"вы", "formal"} else "«ты»" if addr in {"ты", "informal"} else "по умолчанию"
        base += (
            "\n## Persona snapshot (TZ-4 §9)\n"
            f"- Клиент в этой сессии — {snapshot.full_name}.\n"
            f"- Обращайся {addr_word}, не меняй обращение мид-сессии.\n"
        )
    return base


# ── Event emission ──────────────────────────────────────────────────────


async def emit_violation(
    db: AsyncSession,
    *,
    result: PolicyAuditResult,
    session_id: uuid.UUID,
    lead_client_id: uuid.UUID | None,
    actor_id: uuid.UUID | None,
    source: str = "service.conversation_policy_engine",
) -> list[DomainEvent]:
    """Emit one ``conversation.policy_violation_detected`` event per
    violation in ``result``. No-op when ``result.is_clean``.

    The event log carries the full violation breakdown (code, severity,
    message, evidence) so the FE D6 sidebar badge can render counts
    without re-running the checker. Each event has a stable
    ``idempotency_key`` derived from session + code so a retry of the
    same audit run collapses.
    """
    if result.is_clean:
        return []

    events: list[DomainEvent] = []
    # lead_client_id may be NULL on home_preview / pvp / center sessions
    # — fall back to session_id reinterpreted as the correlation anchor,
    # same pattern as persona_memory.capture_for_session.
    anchor = lead_client_id or session_id

    for violation in result.violations:
        events.append(
            await emit_domain_event(
                db,
                lead_client_id=anchor,
                event_type="conversation.policy_violation_detected",
                actor_type="user" if actor_id else "system",
                actor_id=actor_id,
                source=source,
                aggregate_type="training_session",
                aggregate_id=session_id,
                session_id=session_id,
                payload={
                    "session_id": str(session_id),
                    "code": violation.code.value,
                    "severity": violation.severity,
                    "message": violation.message,
                    "evidence": violation.evidence,
                    "enforce_active": result.enforce_active,
                    "blocked": result.should_block
                    and violation.severity == _BLOCKING_SEVERITY,
                },
                # Stable per-(session, code) — repeated violations of the
                # same code within a session collapse so the timeline
                # doesn't fill with duplicates. The evidence dict still
                # captures the latest occurrence in payload.
                idempotency_key=(
                    f"conversation.policy_violation_detected:"
                    f"{session_id}:{violation.code.value}"
                ),
            )
        )
    return events


__all__ = [
    "PolicyAuditResult",
    "PolicyViolation",
    "ViolationCode",
    "audit_assistant_reply",
    "emit_violation",
    "enforce_enabled",
    "render_prompt",
]
