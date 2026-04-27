"""DEPRECATED — see :mod:`app.services.conversation_policy_engine`.

Per TZ-4 §13.2.1 forbidden list, this module is preserved only as a
thin deprecated facade for the duration of the warn-only window. The
canonical implementation lives in
``app.services.conversation_policy_engine`` and ships the full §10.2
six-check surface; this module retains the legacy ``audit_assistant_
reply`` signature so existing tests that import from here keep working
during D5 → D7 migration.

Removed in D5
-------------

* ``conversation_policy_prompt(mode)`` — DELETED. Spec §13.2.1
  explicitly forbids the hard-coded RU prompt-text helper. Use
  :func:`app.services.conversation_policy_engine.render_prompt`
  instead, which accepts both ``mode`` and an optional ``snapshot``.

Kept as wrapper
---------------

* :func:`audit_assistant_reply` — delegates to
  :func:`engine.audit_assistant_reply` and downgrades the result to
  the legacy :class:`ConversationPolicyResult` shape. Behaviour is
  identical for the three legacy checks (``too_long_for_mode``,
  ``near_repeat``, ``missing_next_step``) — the persona-aware checks
  added in D5 don't fire from this entry point because the wrapper
  doesn't accept a snapshot. Callers that need persona-aware checks
  must import the engine directly.

D7 cutover removes this module entirely.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.conversation_policy_engine import (
    audit_assistant_reply as _engine_audit,
)


@dataclass(frozen=True)
class PolicyViolation:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class ConversationPolicyResult:
    violations: list[PolicyViolation] = field(default_factory=list)

    @property
    def is_ok(self) -> bool:
        return not self.violations


def audit_assistant_reply(
    *,
    reply: str,
    previous_assistant_replies: list[str] | None = None,
    mode: object = None,
) -> ConversationPolicyResult:
    """Deprecated wrapper. Use
    :func:`app.services.conversation_policy_engine.audit_assistant_reply`
    instead — the engine version supports the three persona-aware
    checks added in D5 (``persona_conflict``,
    ``asked_known_slot_again``, ``unjustified_identity_change``) when
    a snapshot/persona is supplied.

    The shim keeps callers compiling during the warn-only window;
    behaviour is identical for the three legacy checks.
    """
    result = _engine_audit(
        reply=reply,
        previous_assistant_replies=previous_assistant_replies,
        mode=mode,
    )
    legacy = [
        PolicyViolation(
            code=str(v.code),
            severity=v.severity,
            message=v.message,
        )
        for v in result.violations
    ]
    return ConversationPolicyResult(violations=legacy)


__all__ = [
    "ConversationPolicyResult",
    "PolicyViolation",
    "audit_assistant_reply",
]
