"""TZ-2 §18 runtime observability — in-process Prometheus counters.

The TZ-2 spec asks for three families of metrics that the original
implementation never wired up:

* ``blocked_starts``  — every guard violation that prevents a session
  from starting (or a `terminal_outcome_required` rejection on end). Lets
  SRE see **which** guard fires and how often, instead of only the
  per-user 4xx in nginx logs.

* ``finalize``        — every call into ``completion_policy.finalize_*``,
  labelled by ``completed_via`` (rest|ws|fsm|timeout|disconnect|pvp),
  ``outcome`` and ``already_completed``. Two readings come for free:
    * REST↔WS parity drift (the ratio of finalizes per ``completed_via``
      should track the ratio of started sessions per entry channel),
    * idempotent re-entry rate (``already_completed=true`` should be a
      tiny minority — a spike means a producer is double-finalizing).

* ``followup_gap``    — cases where the outcome **should** produce a
  follow-up by §12 policy but the helper returned None. Surfaces silent
  drops (no real_client_id, missing channel mapping, schema mismatch)
  that the test suite cannot catch because they depend on prod data
  shapes.

Mirrors ``client_domain.py:62-75`` style: in-process dict + threading
lock so a gunicorn worker is safe under both threads and asyncio.
Aggregation across workers happens at the Prometheus scrape layer.
The endpoint that renders text/plain lives in ``api/client_domain_ops.py``
to avoid spawning a second admin router for one URL.
"""

from __future__ import annotations

import threading
from collections import defaultdict


_lock = threading.Lock()

# (guard_code, mode, runtime_type, phase) → count
# phase ∈ {"start", "end"} — the same guard catalogue is used for both
# entrypoints, but the operational meaning is different (a `mode_invalid`
# at start means a misrouted CRM call; at end it never fires today but
# the dimension is reserved).
_blocked_starts: dict[tuple[str, str, str, str], int] = defaultdict(int)

# (completed_via, outcome, strict_mode, already_completed) → count
# Outcome is the canonical TZ-2 §6.5 catalog where we have it; otherwise
# the raw legacy outcome string. ``strict_mode`` mirrors
# ``settings.completion_policy_strict`` at emit time so the dashboard can
# bucket pre-/post-cutover counts without re-deploying.
_finalize: dict[tuple[str, str, str, str], int] = defaultdict(int)

# (reason, outcome, helper) → count
# helper ∈ {"task_followup_policy", "crm_followup"} — both producers can
# silently drop a follow-up; we want to see which one and why
# (reason = the policy code that explains the drop).
_followup_gap: dict[tuple[str, str, str], int] = defaultdict(int)


def record_blocked_start(
    *,
    guard_code: str,
    mode: str | None,
    runtime_type: str | None,
    phase: str = "start",
) -> None:
    """Bump a guard-violation counter. Safe to call on every 4xx raise.

    ``mode`` / ``runtime_type`` are coerced to ``"unknown"`` when the
    caller has not yet resolved them — this is the typical case for
    early guards (profile_incomplete fires before mode is parsed) and
    keeps the label set bounded so Prometheus cardinality stays sane.
    """
    key = (
        guard_code,
        mode or "unknown",
        runtime_type or "unknown",
        phase,
    )
    with _lock:
        _blocked_starts[key] += 1


def record_finalize(
    *,
    completed_via: str,
    outcome: str,
    strict_mode: bool,
    already_completed: bool,
) -> None:
    """Bump a finalizer counter. Called from ``completion_policy``."""
    key = (
        completed_via,
        outcome,
        "strict" if strict_mode else "shadow",
        "idempotent" if already_completed else "fresh",
    )
    with _lock:
        _finalize[key] += 1


def record_followup_gap(
    *,
    reason: str,
    outcome: str | None,
    helper: str,
) -> None:
    """Bump the followup-gap counter.

    ``reason`` is a short code explaining why no follow-up was created
    (``no_real_client``, ``manual_outcome``, ``no_lead_resolution``, …).
    ``outcome`` is the input outcome that the policy was trying to act
    on — combined with ``reason`` it tells the operator whether they
    are seeing legitimate "no follow-up needed" or a dropped real one.
    """
    key = (reason, outcome or "unknown", helper)
    with _lock:
        _followup_gap[key] += 1


def get_blocked_starts() -> dict[tuple[str, str, str, str], int]:
    with _lock:
        return dict(_blocked_starts)


def get_finalize_counters() -> dict[tuple[str, str, str, str], int]:
    with _lock:
        return dict(_finalize)


def get_followup_gap_counters() -> dict[tuple[str, str, str], int]:
    with _lock:
        return dict(_followup_gap)


def reset_for_tests() -> None:
    """Wipe counters between unit tests. Production code never calls this."""
    with _lock:
        _blocked_starts.clear()
        _finalize.clear()
        _followup_gap.clear()


__all__ = [
    "get_blocked_starts",
    "get_finalize_counters",
    "get_followup_gap_counters",
    "record_blocked_start",
    "record_finalize",
    "record_followup_gap",
    "reset_for_tests",
]
