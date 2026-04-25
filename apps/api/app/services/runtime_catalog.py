"""Canonical TZ-2 runtime catalogs (mode / runtime_type / completion_reason).

Single source of truth for the catalog values used by:
* DB-level CHECK constraints on ``training_sessions``
* Pydantic request/response schemas
* the runtime_finalizer (Phase 1) when writing terminal records

Extending the catalog is a 3-step change: update the frozenset here,
update the matching Alembic CHECK migration, and update any consumer
(frontend dropdown, finalize tests) that hard-codes the values. The
test ``test_runtime_catalog_in_lockstep_with_check_constraint`` pins
this contract so a code-only change without the migration fails CI.
"""

from __future__ import annotations


# §6.2 — only these three modes are accepted at session start.
MODES: frozenset[str] = frozenset({"chat", "call", "center"})

# §6.3 — full runtime-type catalog. Each value implies a specific
# (mode × CRM-link × source) shape; see ``derive_runtime_type``.
RUNTIME_TYPES: frozenset[str] = frozenset({
    "training_simulation",
    "training_real_case",
    "crm_call",
    "crm_chat",
    "center_single_call",
})

# §6.6 — how the terminal event was triggered. Different from §6.5
# ``terminal_outcome`` (business result) — this is the "what closed the
# session" lever for analytics. Kept narrower than ``TerminalReason``
# in completion_policy.py because the latter mixes diagnostic flavours
# (judge_failed, ws_disconnect) that aren't business causes.
COMPLETION_REASONS: frozenset[str] = frozenset({
    "explicit_end",
    "client_hangup",
    "operator_hangup",
    "timeout",
    "guard_block",
    "system_failure",
    "redirected",
})


def derive_runtime_type(
    *,
    mode: str | None,
    has_real_client: bool,
    source: str | None,
) -> str:
    """Pick a §6.3 runtime_type from the (mode, real_client, source) shape.

    Used as a fallback when the FE doesn't send `runtime_type` explicitly
    yet (Phase 4 work). Centralised here so the FE migration can move at
    its own pace without diverging from the canonical mapping.

    Rules:
      * source == "center"     → ``center_single_call`` (regardless of mode)
      * has_real_client and source startswith "crm"
          mode == "call"  → ``crm_call``
          mode == "chat"  → ``crm_chat``
      * has_real_client (any other source) → ``training_real_case``
      * else → ``training_simulation``
    """
    src = (source or "").lower()
    m = (mode or "").lower()
    if src == "center":
        return "center_single_call"
    if has_real_client and src.startswith("crm"):
        if m == "call":
            return "crm_call"
        if m == "chat":
            return "crm_chat"
    if has_real_client:
        return "training_real_case"
    return "training_simulation"
