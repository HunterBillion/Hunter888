"""TZ-4 §13.4.1 — AI Quality dashboard endpoint.

Aggregates the runtime audit signals that D5 (conversation policy
engine) and D3 (persona memory) emit:

  * ``conversation.policy_violation_detected`` (six §10.2 codes)
  * ``persona.conflict_detected``
  * ``persona.slot_locked`` (positive signal — included for context)

Returns a single JSON document the FE renders inside the
``Методология → Качество AI`` sub-tab. Putting it under
``/admin/ai-quality/`` (not ``/team/...``) keeps the route grouped
with the other admin oversight surfaces (admin/knowledge,
admin/audit-log) — Команда панель остаётся фокусом на people-
management metrics.

Scope:
* admin → see every team's events
* rop → see events whose ``actor_id`` belongs to a user in the
  caller's ``team_id`` (mirrors the AuditLogPanel team-scope
  pattern in ``api/clients.py:497``).
"""
from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.database import get_db
from app.models.domain_event import DomainEvent
from app.models.user import User


router = APIRouter(prefix="/admin/ai-quality", tags=["admin", "ai-quality"])

_require_audit = require_role("rop", "admin")


# Event types covered by this dashboard. Pre-registered in
# ``ALLOWED_EVENT_TYPES`` (D1.1) so the SQL filter is safe to
# in-line as literals.
_TRACKED_EVENT_TYPES = (
    "conversation.policy_violation_detected",
    "persona.conflict_detected",
    "persona.slot_locked",
)


class SeverityBreakdown(BaseModel):
    low: int = 0
    medium: int = 0
    high: int = 0
    critical: int = 0


class CodeCount(BaseModel):
    code: str
    count: int


class ManagerBreakdown(BaseModel):
    manager_id: uuid.UUID | None = None
    manager_name: str | None = None
    total: int
    persona_conflicts: int
    by_severity: SeverityBreakdown


class RecentEvent(BaseModel):
    event_id: uuid.UUID
    event_type: str
    code: str | None = None
    severity: str | None = None
    session_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    manager_name: str | None = None
    occurred_at: datetime
    summary: str | None = None


class AiQualitySummary(BaseModel):
    window_days: int
    window_from: datetime
    window_to: datetime
    totals: dict[str, int] = Field(
        ...,
        description="Top-level counts: policy_violations, persona_conflicts, "
        "slot_locked_total.",
    )
    by_severity: SeverityBreakdown
    by_code: list[CodeCount]
    by_manager: list[ManagerBreakdown]
    recent: list[RecentEvent]


@router.get(
    "/summary",
    response_model=AiQualitySummary,
    summary="Aggregate AI-quality signals over a rolling window",
)
async def get_ai_quality_summary(
    days: int = Query(7, ge=1, le=90, description="Window size in days"),
    recent_limit: int = Query(20, ge=1, le=100),
    user: User = Depends(_require_audit),
    db: AsyncSession = Depends(get_db),
) -> AiQualitySummary:
    """Aggregate per-team / per-manager / per-severity counts plus a
    short feed of the most recent events.

    The endpoint runs a single ranged SELECT against ``domain_events``
    and aggregates in Python — avoids a fan of GROUP BY queries while
    the volume is still small (warn-only mode produces a handful per
    session). Once volume grows past a few thousand events per window
    we'd push the aggregation into SQL; for the pilot the in-memory
    fold is simpler and easier to extend.
    """
    now = datetime.now(UTC)
    window_from = now - timedelta(days=days)

    stmt = (
        select(DomainEvent, User)
        .outerjoin(User, User.id == DomainEvent.actor_id)
        .where(DomainEvent.event_type.in_(_TRACKED_EVENT_TYPES))
        .where(DomainEvent.occurred_at >= window_from)
        .order_by(DomainEvent.occurred_at.desc())
    )

    # Team scope for ROP — admin sees everything.
    if user.role.value == "rop":
        if not user.team_id:
            return _empty_summary(window_days=days, window_from=window_from, window_to=now)
        team_actors_subq = (
            select(User.id).where(User.team_id == user.team_id).scalar_subquery()
        )
        stmt = stmt.where(DomainEvent.actor_id.in_(team_actors_subq))

    rows = list((await db.execute(stmt)).all())

    severity_counts: Counter[str] = Counter()
    code_counts: Counter[str] = Counter()
    by_manager_raw: dict[uuid.UUID | None, _ManagerBucket] = defaultdict(_ManagerBucket)
    recent: list[RecentEvent] = []

    policy_total = 0
    persona_conflicts_total = 0
    slot_locked_total = 0

    for ev, actor in rows:
        payload = ev.payload_json or {}
        code = payload.get("code") if isinstance(payload, dict) else None
        severity = payload.get("severity") if isinstance(payload, dict) else None
        session_id_raw = payload.get("session_id") if isinstance(payload, dict) else None
        try:
            session_uuid = uuid.UUID(session_id_raw) if session_id_raw else None
        except (TypeError, ValueError):
            session_uuid = None

        manager_id = ev.actor_id
        manager_name = (actor.full_name or actor.email) if actor is not None else None

        # Top-level totals
        if ev.event_type == "conversation.policy_violation_detected":
            policy_total += 1
            if isinstance(severity, str) and severity in {"low", "medium", "high", "critical"}:
                severity_counts[severity] += 1
            if isinstance(code, str):
                code_counts[code] += 1
        elif ev.event_type == "persona.conflict_detected":
            persona_conflicts_total += 1
        elif ev.event_type == "persona.slot_locked":
            slot_locked_total += 1

        # Manager breakdown (skip ``persona.slot_locked`` — positive
        # signal, doesn't belong in a "watch list" rollup).
        if ev.event_type != "persona.slot_locked":
            bucket = by_manager_raw[manager_id]
            bucket.total += 1
            if ev.event_type == "persona.conflict_detected":
                bucket.persona_conflicts += 1
            if isinstance(severity, str):
                bucket.by_severity[severity] += 1
            if manager_name:
                bucket.manager_name = manager_name

        # Recent feed — bounded slice so the response stays small.
        if len(recent) < recent_limit:
            recent.append(
                RecentEvent(
                    event_id=ev.id,
                    event_type=ev.event_type,
                    code=code if isinstance(code, str) else None,
                    severity=severity if isinstance(severity, str) else None,
                    session_id=session_uuid,
                    manager_id=manager_id,
                    manager_name=manager_name,
                    occurred_at=ev.occurred_at,
                    summary=_summary_line(ev.event_type, code, severity),
                )
            )

    by_manager = [
        ManagerBreakdown(
            manager_id=mid,
            manager_name=b.manager_name,
            total=b.total,
            persona_conflicts=b.persona_conflicts,
            by_severity=SeverityBreakdown(
                low=b.by_severity.get("low", 0),
                medium=b.by_severity.get("medium", 0),
                high=b.by_severity.get("high", 0),
                critical=b.by_severity.get("critical", 0),
            ),
        )
        for mid, b in by_manager_raw.items()
    ]
    by_manager.sort(key=lambda m: m.total, reverse=True)

    by_code = [
        CodeCount(code=c, count=n)
        for c, n in sorted(code_counts.items(), key=lambda kv: kv[1], reverse=True)
    ]

    return AiQualitySummary(
        window_days=days,
        window_from=window_from,
        window_to=now,
        totals={
            "policy_violations": policy_total,
            "persona_conflicts": persona_conflicts_total,
            "slot_locked": slot_locked_total,
        },
        by_severity=SeverityBreakdown(
            low=severity_counts["low"],
            medium=severity_counts["medium"],
            high=severity_counts["high"],
            critical=severity_counts["critical"],
        ),
        by_code=by_code,
        by_manager=by_manager,
        recent=recent,
    )


@dataclass
class _ManagerBucket:
    """Internal aggregation accumulator for the per-manager rollup.

    Replaced the previous ``dict[uuid.UUID | None, dict[str, object]]``
    shape that needed nine ``# type: ignore`` comments because the
    union type inhibited inference. Typed dataclass eliminates them
    AND makes the eventual SQL-side ``GROUP BY`` migration a
    straight one-line replacement (build the dataclass from the row
    tuple instead of folding in Python).
    """

    total: int = 0
    persona_conflicts: int = 0
    by_severity: Counter[str] = field(default_factory=Counter)
    manager_name: str | None = None


def _empty_summary(
    *, window_days: int, window_from: datetime, window_to: datetime
) -> AiQualitySummary:
    return AiQualitySummary(
        window_days=window_days,
        window_from=window_from,
        window_to=window_to,
        totals={"policy_violations": 0, "persona_conflicts": 0, "slot_locked": 0},
        by_severity=SeverityBreakdown(),
        by_code=[],
        by_manager=[],
        recent=[],
    )


def _summary_line(event_type: str, code: str | None, severity: str | None) -> str | None:
    """Pre-render the human-readable hint the FE shows in the feed
    row. Stays here so the FE doesn't drift on Russian wording."""
    if event_type == "conversation.policy_violation_detected":
        sev_word = {
            "critical": "критично",
            "high": "высокая",
            "medium": "средняя",
            "low": "низкая",
        }.get(severity or "", "")
        return f"Полиси: {code or '—'}{f' ({sev_word})' if sev_word else ''}"
    if event_type == "persona.conflict_detected":
        return "Конфликт идентичности (snapshot drift)"
    if event_type == "persona.slot_locked":
        return f"Слот зафиксирован: {code or '—'}"
    return None
