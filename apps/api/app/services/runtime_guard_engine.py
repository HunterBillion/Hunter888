"""TZ-2 §8 runtime guard engine — Phase 3 + 4 (deferred guards).

Centralises the start-of-session and end-of-session checks that the
spec lists as guards. Existing handlers in ``api/training.py`` and
``ws/training.py`` already do most of these as ad-hoc ``if`` blocks
scattered across the start handler. This module collects them into a
single ``evaluate_start_guards`` / ``evaluate_end_guards`` pair so:

  * Frontend gets a structured, code-stable error contract:
    ``{"detail": "...", "code": "guard_X", "details": {...}}``
  * Tests can assert one row per guard instead of grepping the handler
  * Future guards land here without growing the handler

Phase 3 shipped 5 spec guards (profile_complete, mode_integrity,
runtime_type, lead_client_presence, session_mode_required_for_crm)
plus terminal_outcome_required at end. Phase 4 adds the remaining 4
deferred guards — each behind a feature flag (default OFF) so they
can be rolled out one-at-a-time on staging/prod without redeploying:

  * ``lead_client_access_guard``    — RBAC: user must own the linked
    real_client (or be admin). Formalises the inline check at
    ``api/training.py:464-475``; flagged so behaviour is byte-identical
    until the flag flips, then the inline raise is removed.
  * ``session_uniqueness_guard``    — refuses to start a second active
    training session for the same (user, lead_client) pair. Catches
    duplicate-tab races + accidental re-clicks on /clients/[id].
  * ``runtime_status_guard``        — refuses to finalize a session
    that is already terminal (completed / abandoned / error). Belt-and-
    suspenders to the idempotent skip in completion_policy.
  * ``projection_safe_commit_guard``— refuses to finalize when the
    LeadClient projection target is missing or archived. Without this
    the projector raises mid-finalize and we stamp terminal columns
    on a session that no projection will ever pick up.

Each Phase 4 guard is a separate function (``evaluate_*_guard``) so the
caller picks which to invoke and can pass already-loaded entities (e.g.
the REST start handler already loaded ``RealClient`` for the inline RBAC
check — passing it in avoids a second SELECT).
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

# Phase 4 codes — added 2026-04-26. Each guard is opt-in via a feature
# flag in ``settings`` (see config.py ``tz2_guard_*_enabled``). Flag
# default OFF so the wired callsite is a no-op until a human flips it
# on staging, observes ``runtime_blocked_starts_total{guard="..."}`` for
# 24h, then promotes to prod.
GUARD_LEAD_CLIENT_ACCESS_DENIED = "lead_client_access_denied"
GUARD_SESSION_UNIQUENESS_VIOLATED = "session_uniqueness_violated"
GUARD_RUNTIME_STATUS_NOT_FINALIZABLE = "runtime_status_not_finalizable"
GUARD_PROJECTION_TARGET_MISSING = "projection_target_missing"


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


# ── Phase 4 guards (deferred) — each opt-in via settings flag ─────────────


async def evaluate_lead_client_access_guard(
    *,
    user: Any,
    real_client: Any | None,
    db: Any | None = None,
) -> GuardViolation | None:
    """RBAC: the user requesting a session against ``real_client`` must
    have access to it through ownership, team, or admin role.

    Access matrix (BUG-FIX 2026-05-05 — admin/ROP were previously
    blocked from running training against any client they didn't
    personally own, breaking demo/coaching/cross-team review flows):

      * ``admin``      — any client (for ops, audit, escalation).
      * ``manager``    — only own clients (``client.manager_id == user.id``).
      * ``rop``        — clients of any manager in ROP's team.
      * ``methodologist`` — DENIED (read-only role; cannot generate
        training data that would pollute the analytics pipeline).

    Caller passes the already-loaded ``real_client`` so this guard
    avoids a second SELECT for the ownership check. The team-membership
    branch is the only one that issues a DB read, and only when role==rop.

    Returns a violation if access is denied; None when access is OK
    (including the simulation case where ``real_client`` is None — no
    client to gate against).
    """
    if real_client is None:
        return None
    user_role = (getattr(user, "role", None) or "").lower()
    if hasattr(user_role, "value"):  # Enum
        user_role = user_role.value.lower()
    if user_role == "admin":
        return None

    owner_id = getattr(real_client, "manager_id", None)
    user_id = getattr(user, "id", None)

    # Owner path (manager hitting own client).
    if owner_id is not None and owner_id == user_id:
        return None

    # Team-lead path (ROP hitting a teammate's client). Requires DB to
    # check whether the client's owner is on the same team. Skipped if
    # caller didn't supply db — keeps the guard backwards-compatible
    # with old call sites that only passed the user/client pair.
    if user_role == "rop" and db is not None and owner_id is not None:
        user_team_id = getattr(user, "team_id", None)
        if user_team_id is not None:
            try:
                from sqlalchemy import select as _select
                from app.models.user import User as _User
                owner_row = (await db.execute(
                    _select(_User.team_id).where(_User.id == owner_id)
                )).scalar_one_or_none()
                if owner_row is not None and owner_row == user_team_id:
                    return None
            except Exception:
                logger.debug("rop team-access check failed", exc_info=True)

    return GuardViolation(
        code=GUARD_LEAD_CLIENT_ACCESS_DENIED,
        message=(
            "У вас нет прав на запуск сессии с этим клиентом — "
            "клиент принадлежит другому менеджеру."
        ),
        details={
            "real_client_id": str(getattr(real_client, "id", "")),
            "owner_id": str(owner_id) if owner_id else None,
        },
    )


async def evaluate_session_uniqueness_guard(
    db,
    *,
    user_id: uuid.UUID,
    real_client_id: uuid.UUID | str | None,
) -> GuardViolation | None:
    """Refuse to start a second active training session for the same
    (user, real_client) pair.

    Catches:
      * duplicate-tab race (user clicks "Позвонить" twice in 200ms)
      * accidental re-click on /clients/[id] after the page state didn't
        re-render the existing-call indicator yet

    Skipped when ``real_client_id`` is None (simulation sessions are
    legitimately concurrent — user can run multiple practice scenarios).

    Async because it issues a DB SELECT. Returns None when no other
    active session exists, otherwise a violation with the conflicting
    session id in details so the FE can offer "resume the existing
    call" instead of starting a new one.
    """
    if real_client_id is None:
        return None
    from sqlalchemy import select
    from app.models.training import SessionStatus, TrainingSession

    existing = (
        await db.execute(
            select(TrainingSession.id)
            .where(
                TrainingSession.user_id == user_id,
                TrainingSession.real_client_id == real_client_id,
                TrainingSession.status == SessionStatus.active,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is None:
        return None
    return GuardViolation(
        code=GUARD_SESSION_UNIQUENESS_VIOLATED,
        message=(
            "У вас уже есть активная сессия с этим клиентом. "
            "Завершите её или возобновите вместо запуска новой."
        ),
        details={
            "active_session_id": str(existing),
            "real_client_id": str(real_client_id),
        },
    )


def evaluate_runtime_status_guard(
    *,
    session: Any,
) -> GuardViolation | None:
    """Refuse to finalize a session that is already terminal.

    ``completion_policy.finalize_training_session`` already short-
    circuits on ``terminal_outcome != None`` (idempotent skip), but
    that path returns the cached ``CompletionResult`` silently — useful
    for the genuine REST↔WS race, not great for catching a buggy
    producer that calls finalize on a long-completed session.

    This guard makes the failure explicit at the entrypoint (4xx with
    a stable code) so the operator sees it in
    ``runtime_blocked_starts_total{phase="end"}`` instead of just a
    flat ``finalize_total{freshness="idempotent"}`` bump.

    Returns None when the session is in a finalize-able state
    (active or ending). Otherwise a violation with current status.
    """
    from app.models.training import SessionStatus

    status_attr = getattr(session, "status", None)
    if status_attr is None:
        # No session loaded — treat as finalize-able; the downstream
        # finalizer will 404 on its own.
        return None
    # SessionStatus enum or raw string — coerce to comparable string.
    raw = status_attr.value if hasattr(status_attr, "value") else str(status_attr)
    finalizeable = {SessionStatus.active.value}
    # ``ending`` is a TZ-2 §6.4 status value not yet on the enum (the ORM
    # column is the legacy 4-value enum). When it lands, accept it too.
    if raw in finalizeable or raw == "ending":
        return None
    return GuardViolation(
        code=GUARD_RUNTIME_STATUS_NOT_FINALIZABLE,
        message=(
            f"Сессия уже завершена со статусом '{raw}'. "
            "Повторное завершение не выполнено."
        ),
        details={
            "session_id": str(getattr(session, "id", "")),
            "current_status": raw,
        },
    )


async def evaluate_projection_safe_commit_guard(
    db,
    *,
    session: Any,
) -> GuardViolation | None:
    """Refuse to finalize when the LeadClient projection target is
    missing or archived.

    The completion_policy emits ``session.completed`` and dual-writes a
    timeline projection if ``session.real_client_id`` is set. If the
    LeadClient row is gone (data corruption, manual delete) or archived
    (work_state == archived), the projector raises mid-finalize and we
    end up with terminal columns stamped on a session whose CRM card
    will never see the event.

    Skipped for simulation sessions (no real_client_id → no projection
    target needed).

    Returns None when the projection can safely commit, otherwise a
    violation with the missing/archived state in details.
    """
    real_client_id = getattr(session, "real_client_id", None)
    if real_client_id is None:
        return None
    from app.models.lead_client import LeadClient

    lead = await db.get(LeadClient, real_client_id)
    if lead is None:
        return GuardViolation(
            code=GUARD_PROJECTION_TARGET_MISSING,
            message=(
                "Проекция CRM не может быть сохранена — карточка клиента "
                "удалена или ещё не создана. Завершение сессии отменено "
                "во избежание несогласованного состояния."
            ),
            details={
                "real_client_id": str(real_client_id),
                "reason": "lead_client_not_found",
            },
        )
    work_state = getattr(lead, "work_state", None)
    if work_state == "archived":
        return GuardViolation(
            code=GUARD_PROJECTION_TARGET_MISSING,
            message=(
                "Карточка клиента находится в архиве. Восстановите её "
                "перед завершением сессии."
            ),
            details={
                "lead_client_id": str(lead.id),
                "reason": "lead_client_archived",
            },
        )
    return None
