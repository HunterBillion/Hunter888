"""TZ-2 §8 runtime guard engine — Phase 3 minimum.

Centralises the start-of-session and end-of-session checks that the
spec lists as guards. Existing handlers in ``api/training.py`` and
``ws/training.py`` already do most of these as ad-hoc ``if`` blocks
scattered across the start handler. This module collects them into a
single ``evaluate_start_guards`` / ``evaluate_end_guards`` pair so:

  * Frontend gets a structured, code-stable error contract:
    ``{"detail": "...", "code": "guard_X", "details": {...}}``
  * Tests can assert one row per guard instead of grepping the handler
  * Future guards land here without growing the handler

Phase 3 ships 5 of the 12 spec guards — the ones that block real pilot
traffic. The remaining 7 (scenario_version_guard, session_uniqueness_guard,
runtime_status_guard etc.) are not currently failing in production and
can be added incrementally.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from app.services.profile_gate import required_profile_missing
from app.services.runtime_catalog import MODES, RUNTIME_TYPES, derive_runtime_type
from app.services.session_state import normalize_session_outcome

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GuardViolation:
    """Structured guard failure — turn into a 400/403 at the API layer."""

    code: str  # one of the GUARD_* constants below
    message: str
    details: dict[str, Any] | None = None


# Stable error codes — frontend can branch on these without parsing
# the human-readable message (which is i18n-bound). Some are pre-existing
# codes the FE has handled for months (profile_incomplete, session_mode_…);
# Phase 3B preserves them when migrating the inline checks into the engine.
GUARD_PROFILE_INCOMPLETE = "profile_incomplete"
GUARD_MODE_INVALID = "mode_invalid"
GUARD_RUNTIME_TYPE_INVALID = "runtime_type_invalid"
GUARD_LEAD_CLIENT_REQUIRED = "lead_client_required"
GUARD_TERMINAL_OUTCOME_REQUIRED = "terminal_outcome_required"
# Pre-existing code: api/training.py:504-512 used to raise this inline
# when a CRM-link session was requested without an explicit session_mode.
# Phase 3B moves the check here so it lives next to the related mode/
# runtime guards. FE doesn't currently branch on it — it's an internal
# contract violation (FE always sends mode now) but kept stable for
# backward compatibility with any non-canonical caller.
GUARD_SESSION_MODE_REQUIRED_FOR_CRM = "session_mode_required_for_crm"


def evaluate_start_guards(
    *,
    user: Any,
    preferences: dict | None = None,
    mode: str | None = None,
    runtime_type: str | None = None,
    real_client_id: uuid.UUID | str | None = None,
    source: str | None = None,
) -> list[GuardViolation]:
    """Run §8.1-8.2 start-of-session guards. Returns the list of
    violations — empty list = all clear.

    Caller (FastAPI handler) typically raises ``HTTPException(400, ...)``
    on the FIRST violation so the frontend gets one error at a time and
    can fix them sequentially. The full list is returned anyway so a
    bulk-validation UI (admin panel, integration tests) can show all
    issues at once.
    """
    violations: list[GuardViolation] = []

    # 1. profile_complete_guard — block real-case starts when manager
    # profile is missing required fields. Simulation paths bypass this
    # via the caller (this guard is unconditional, the handler chooses
    # whether to run it).
    missing = required_profile_missing(user, preferences=preferences)
    if missing:
        violations.append(
            GuardViolation(
                code=GUARD_PROFILE_INCOMPLETE,
                message=(
                    "Профиль менеджера не заполнен. "
                    f"Нужно дозаполнить: {', '.join(missing)}"
                ),
                details={"missing_fields": missing},
            )
        )

    # 2. mode_integrity_guard — when mode is explicitly provided, it
    # must be in the canonical set. Missing mode is allowed at this
    # phase (legacy paths still send custom_session_mode under
    # custom_params); the upcoming Phase 4 frontend work will start
    # sending mode explicitly.
    if mode is not None and mode not in MODES:
        violations.append(
            GuardViolation(
                code=GUARD_MODE_INVALID,
                message=f"Mode {mode!r} is not one of {sorted(MODES)}",
                details={"mode": mode, "allowed": sorted(MODES)},
            )
        )

    # 3. runtime_type_guard — same logic. Plus cross-check: if BOTH
    # mode and runtime_type were supplied, the derived value must
    # match (catches frontend bugs sending an inconsistent pair).
    if runtime_type is not None and runtime_type not in RUNTIME_TYPES:
        violations.append(
            GuardViolation(
                code=GUARD_RUNTIME_TYPE_INVALID,
                message=f"runtime_type {runtime_type!r} is not one of {sorted(RUNTIME_TYPES)}",
                details={"runtime_type": runtime_type, "allowed": sorted(RUNTIME_TYPES)},
            )
        )
    elif runtime_type is not None and mode is not None:
        derived = derive_runtime_type(
            mode=mode,
            has_real_client=real_client_id is not None,
            source=source,
        )
        if derived != runtime_type:
            violations.append(
                GuardViolation(
                    code=GUARD_RUNTIME_TYPE_INVALID,
                    message=(
                        f"Inconsistent runtime_type — payload says {runtime_type!r} "
                        f"but the (mode={mode!r}, real_client={bool(real_client_id)}, "
                        f"source={source!r}) shape implies {derived!r}"
                    ),
                    details={
                        "submitted": runtime_type,
                        "derived": derived,
                        "mode": mode,
                        "has_real_client": bool(real_client_id),
                        "source": source,
                    },
                )
            )

    # 4. lead_client_presence_guard — runtime_types that the spec
    # marks as "real_case" REQUIRE a real_client_id. Catches bugs
    # where frontend sends runtime_type=crm_call but forgot to attach
    # the client id (typical multi-tab race).
    runtime_for_check = runtime_type
    if runtime_for_check is None and mode is not None:
        runtime_for_check = derive_runtime_type(
            mode=mode,
            has_real_client=real_client_id is not None,
            source=source,
        )
    if runtime_for_check in {"crm_call", "crm_chat", "training_real_case", "center_single_call"}:
        if real_client_id is None:
            violations.append(
                GuardViolation(
                    code=GUARD_LEAD_CLIENT_REQUIRED,
                    message=(
                        f"runtime_type={runtime_for_check!r} requires a real_client_id "
                        "(simulation paths use training_simulation instead)"
                    ),
                    details={"runtime_type": runtime_for_check},
                )
            )

    # 5. session_mode_required_for_crm — CRM-card start (`real_client_id`
    # present in the request) MUST carry an explicit mode so the backend
    # doesn't silently default to chat for a voice-call entry. Pre-existing
    # check at api/training.py:504-512 — moved here so the start-handler
    # has one place to look for "what's wrong with this payload".
    if real_client_id is not None and mode is None:
        violations.append(
            GuardViolation(
                code=GUARD_SESSION_MODE_REQUIRED_FOR_CRM,
                message=(
                    "Для запуска тренировки из карточки клиента необходимо "
                    "указать режим (call/chat/center)."
                ),
                details={"real_client_id": str(real_client_id)},
            )
        )

    return violations


def evaluate_end_guards(
    *,
    mode: str | None,
    raw_outcome: str | None,
) -> list[GuardViolation]:
    """Run §8.3 end-of-session guards. Returns the list of violations.

    The single guard wired here is ``terminal_outcome_required_guard``:
    center sessions cannot end without one of {deal_agreed, deal_not_agreed,
    continue_next_call}. The check is delegated to
    ``session_state.validate_terminal_outcome`` so REST and WS handlers
    that already use it stay in lockstep without a second source of truth.
    """
    from app.services.session_state import validate_terminal_outcome

    violations: list[GuardViolation] = []
    ok, error = validate_terminal_outcome(
        mode=mode,
        outcome=normalize_session_outcome(raw_outcome) or raw_outcome,
    )
    if not ok:
        violations.append(
            GuardViolation(
                code=GUARD_TERMINAL_OUTCOME_REQUIRED,
                message=error or "terminal outcome is required for this session mode",
                details={"mode": mode, "raw_outcome": raw_outcome},
            )
        )
    return violations
