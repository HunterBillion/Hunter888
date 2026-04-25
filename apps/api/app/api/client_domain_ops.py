"""Admin-only operational endpoints for the unified client domain (TZ-1).

Read:
* ``GET  /admin/client-domain/dashboard``  — one-shot payload consumed by
  the admin UI. Combines parity, event-type distribution, flag state,
  recent events and a computed health verdict.
* ``GET  /admin/client-domain/parity``     — raw parity counters.
* ``GET  /admin/client-domain/event-types``— 24h default event-type mix.
* ``GET  /admin/client-domain/metrics``    — Prometheus text format.
* ``GET  /admin/client-domain/flags``      — current feature-flag state.
* ``GET  /admin/client-domain/recent-events`` — last N DomainEvents for
  debugging a single click-through.

Write:
* ``POST /admin/client-domain/self-test``  — emits a synthetic DomainEvent
  against a disposable LeadClient to verify the full pipeline round-trip.
  The synthetic records are deleted before the request returns.
* ``POST /admin/client-domain/repair/projections``
* ``POST /admin/client-domain/repair/events``

Restricted to ``admin``. Use sparingly during rollout; the parity numbers
should trend to zero once dual-write covers every producer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import require_role
from app.database import get_db
from app.models.crm_projection import CrmTimelineProjectionState
from app.models.domain_event import DomainEvent
from app.models.lead_client import LeadClient
from app.services.audit import write_audit_log
from app.services.client_domain import emit_domain_event, get_emit_counters
from app.services.client_domain_repair import (
    parity_report,
    repair_missing_events_for_interactions,
    repair_missing_projections,
)

router = APIRouter()


# ── Helpers ─────────────────────────────────────────────────────────────────


def _compute_health(report: dict[str, int]) -> dict[str, Any]:
    """Turn raw parity into a traffic-light verdict for the admin UI."""
    total_interactions = max(int(report.get("total_interactions", 0)), 1)
    without = int(report.get("interactions_without_domain_event_id", 0))
    parity_ratio = 1.0 - (without / total_interactions)

    events_no_lead = int(report.get("events_without_lead_client_id", 0))
    events_no_proj = int(report.get("events_without_projection", 0))

    if events_no_lead > 0:
        status = "red"
        reason = (
            f"{events_no_lead} DomainEvent без lead_client_id — это нарушение "
            "инварианта §13.4. Немедленно откатите последний деплой или "
            "свяжитесь с разработчиком."
        )
    elif without > 0 or events_no_proj > 0:
        status = "yellow"
        reason = (
            f"Найден legacy-drift: {without} interactions без DomainEvent, "
            f"{events_no_proj} events без projection. Запустите full-sweep "
            "репейр, затем повторно проверьте parity."
        )
    else:
        status = "green"
        reason = "Инварианты TZ-1 чисты. Dual-write работает корректно."

    return {
        "status": status,
        "reason": reason,
        "parity_ratio": round(parity_ratio, 6),
    }


async def _flag_state() -> dict[str, bool]:
    return {
        "client_domain_dual_write_enabled": bool(settings.client_domain_dual_write_enabled),
        "client_domain_cutover_read_enabled": bool(settings.client_domain_cutover_read_enabled),
        "client_domain_strict_emit": bool(settings.client_domain_strict_emit),
    }


async def _event_type_distribution(db: AsyncSession, hours: int) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(hours=hours)
    rows = (
        await db.execute(
            select(DomainEvent.event_type, func.count().label("cnt"))
            .where(DomainEvent.occurred_at >= since)
            .group_by(DomainEvent.event_type)
            .order_by(func.count().desc())
        )
    ).all()
    return {
        "since_hours": hours,
        "total": sum(int(r.cnt) for r in rows),
        "by_type": {r.event_type: int(r.cnt) for r in rows},
    }


async def _recent_events(db: AsyncSession, limit: int) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(DomainEvent)
            .order_by(DomainEvent.occurred_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": str(event.id),
            "event_type": event.event_type,
            "lead_client_id": str(event.lead_client_id) if event.lead_client_id else None,
            "actor_type": event.actor_type,
            "actor_id": str(event.actor_id) if event.actor_id else None,
            "source": event.source,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": str(event.aggregate_id) if event.aggregate_id else None,
            "session_id": str(event.session_id) if event.session_id else None,
            "correlation_id": event.correlation_id,
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            "schema_version": event.schema_version,
            "idempotency_key": event.idempotency_key,
        }
        for event in rows
    ]


# ── Read endpoints ──────────────────────────────────────────────────────────


@router.get("/admin/client-domain/dashboard")
async def get_dashboard(
    hours: int = Query(24, ge=1, le=24 * 30),
    events_limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("admin")),
) -> dict:
    report = await parity_report(db)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "parity": report,
        "health": _compute_health(report),
        "flags": await _flag_state(),
        "event_types": await _event_type_distribution(db, hours),
        "recent_events": await _recent_events(db, events_limit),
    }


@router.get("/admin/client-domain/parity")
async def get_parity_report(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("admin")),
) -> dict:
    return await parity_report(db)


@router.get("/admin/client-domain/event-types")
async def get_event_type_distribution(
    hours: int = Query(24, ge=1, le=24 * 30),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("admin")),
) -> dict:
    return await _event_type_distribution(db, hours)


@router.get("/admin/client-domain/flags")
async def get_flags(_user=Depends(require_role("admin"))) -> dict:
    """Read-only snapshot of client-domain feature flags.

    Flags are driven by env vars today — to change, edit ``.env.production``
    and restart the api container. The admin UI should surface this fact
    so an operator doesn't think the toggle is live.
    """
    return {
        "flags": await _flag_state(),
        "note": (
            "Flags are loaded from env vars at startup. To toggle cutover, "
            "edit /opt/hunter888/.env.production and restart the api "
            "container. Runtime toggle is intentionally disabled to avoid "
            "mid-request config drift."
        ),
    }


@router.get("/admin/client-domain/recent-events")
async def get_recent_events(
    limit: int = Query(20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("admin")),
) -> dict:
    return {"events": await _recent_events(db, limit)}


@router.get("/admin/client-domain/metrics")
async def get_prometheus_metrics(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("admin")),
) -> PlainTextResponse:
    """Prometheus-formatted observability for the client domain (TZ §17)."""
    report = await parity_report(db)
    totals_key_pairs = [
        ("client_domain_total_interactions", "total_interactions"),
        ("client_domain_total_events", "total_events"),
        ("client_domain_total_projections", "total_projections"),
        (
            "client_domain_interactions_without_domain_event_id",
            "interactions_without_domain_event_id",
        ),
        ("client_domain_events_without_projection", "events_without_projection"),
        (
            "client_domain_projections_without_interaction",
            "projections_without_interaction",
        ),
        ("client_domain_events_without_lead_client_id", "events_without_lead_client_id"),
    ]
    lines: list[str] = []
    for metric_name, key in totals_key_pairs:
        value = int(report.get(key, 0))
        lines.append(f"# HELP {metric_name} TZ-1 parity metric")
        lines.append(f"# TYPE {metric_name} gauge")
        lines.append(f"{metric_name} {value}")

    total_interactions = int(report.get("total_interactions", 0)) or 1
    without = int(report.get("interactions_without_domain_event_id", 0))
    parity_ratio = 1.0 - (without / total_interactions)
    lines.append(
        "# HELP client_domain_timeline_parity_ratio "
        "1 - (interactions_without_domain_event_id / total_interactions)"
    )
    lines.append("# TYPE client_domain_timeline_parity_ratio gauge")
    lines.append(f"client_domain_timeline_parity_ratio {parity_ratio:.6f}")

    # Per-emit counters (in-process, per worker). Aggregation across workers
    # happens at the Prometheus scraper level. Outcome label distinguishes
    # emitted / deduped (idempotency hit) / skipped (dual-write disabled) /
    # failed (caught exception) so dashboards can spot drift instantly.
    counters = get_emit_counters()
    if counters:
        lines.append(
            "# HELP client_domain_events_emitted_total "
            "DomainEvent emit attempts by event_type, source, actor_type, outcome"
        )
        lines.append("# TYPE client_domain_events_emitted_total counter")
        for (event_type, source_lbl, actor_type, outcome), count in sorted(counters.items()):
            labels = (
                f'event_type="{event_type}",source="{source_lbl}",'
                f'actor_type="{actor_type}",outcome="{outcome}"'
            )
            lines.append(f"client_domain_events_emitted_total{{{labels}}} {count}")

    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain")


# ── Write endpoints ─────────────────────────────────────────────────────────


@router.post("/admin/client-domain/self-test")
async def post_self_test(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("admin")),
) -> dict:
    """Round-trip test: create synthetic LeadClient + DomainEvent, verify
    the event survives a fresh read, then delete both. Returns timing +
    pass/fail for each step so the admin UI can render a coloured log.
    """
    steps: list[dict[str, Any]] = []
    synthetic_id = uuid.uuid4()
    marker = f"self-test:{uuid.uuid4()}"
    started = datetime.now(UTC)

    try:
        lead = LeadClient(
            id=synthetic_id,
            owner_user_id=user.id,
            team_id=getattr(user, "team_id", None),
            lifecycle_stage="new",
            work_state="active",
            status_tags=[],
            source_system="self_test",
            source_ref=marker,
        )
        db.add(lead)
        await db.flush()
        steps.append({"name": "create_lead_client", "status": "ok"})

        event = await emit_domain_event(
            db,
            lead_client_id=lead.id,
            event_type="self_test.ping",
            actor_type="system",
            actor_id=user.id,
            source="self_test",
            payload={"marker": marker, "initiated_by": str(user.id)},
            aggregate_type="self_test",
            aggregate_id=synthetic_id,
            idempotency_key=marker,
            correlation_id=marker,
        )
        steps.append({
            "name": "emit_domain_event",
            "status": "ok",
            "event_id": str(event.id),
            "idempotency_key": event.idempotency_key,
        })

        roundtrip = (
            await db.execute(
                select(DomainEvent).where(DomainEvent.idempotency_key == marker)
            )
        ).scalar_one_or_none()
        if roundtrip is None or roundtrip.id != event.id:
            raise RuntimeError("round-trip event not found")
        steps.append({"name": "roundtrip_read", "status": "ok"})

        await db.execute(
            delete(CrmTimelineProjectionState).where(
                CrmTimelineProjectionState.domain_event_id == event.id
            )
        )
        await db.execute(delete(DomainEvent).where(DomainEvent.id == event.id))
        await db.execute(delete(LeadClient).where(LeadClient.id == lead.id))
        await db.commit()
        steps.append({"name": "cleanup", "status": "ok"})
    except Exception as exc:
        await db.rollback()
        steps.append({"name": "error", "status": "fail", "error": str(exc)})
        return {
            "passed": False,
            "steps": steps,
            "started_at": started.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
        }

    # Audit even successful self-tests so we can trace who/when ran them.
    await write_audit_log(
        db,
        actor=user,
        action="client_domain.self_test",
        entity_type="admin_op",
        entity_id=None,
        old_values=None,
        new_values={"marker": marker, "passed": True, "step_count": len(steps)},
        request=request,
    )
    await db.commit()

    return {
        "passed": True,
        "steps": steps,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
    }


@router.post("/admin/client-domain/repair/projections")
async def post_repair_projections(
    request: Request,
    limit: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("admin")),
) -> dict:
    repaired = await repair_missing_projections(db, limit=limit)
    await write_audit_log(
        db,
        actor=user,
        action="client_domain.repair_projections",
        entity_type="admin_op",
        entity_id=None,
        old_values=None,
        new_values={"limit": limit, "repaired_projections": repaired},
        request=request,
    )
    await db.commit()
    return {"repaired_projections": repaired}


@router.post("/admin/client-domain/repair/events")
async def post_repair_events(
    request: Request,
    limit: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("admin")),
) -> dict:
    repaired = await repair_missing_events_for_interactions(db, limit=limit)
    await write_audit_log(
        db,
        actor=user,
        action="client_domain.repair_events",
        entity_type="admin_op",
        entity_id=None,
        old_values=None,
        new_values={"limit": limit, "repaired_events": repaired},
        request=request,
    )
    await db.commit()
    return {"repaired_events": repaired}
