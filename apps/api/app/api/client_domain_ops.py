"""Admin-only operational endpoints for the unified client domain (TZ-1).

* ``GET  /admin/client-domain/parity`` — current counts used to gate cutover.
* ``GET  /admin/client-domain/metrics`` — Prometheus-formatted observability
  (gauges + timeline_parity_ratio, events_without_lead_client_id).
* ``GET  /admin/client-domain/event-types`` — distribution of DomainEvent
  types over the last 24h, for dashboards.
* ``POST /admin/client-domain/repair/projections`` — fill missing projections.
* ``POST /admin/client-domain/repair/events`` — backfill events for legacy
  interactions.

Restricted to ``admin``. Use sparingly during rollout; the numbers should
trend to zero once dual-write covers every producer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.database import get_db
from app.models.domain_event import DomainEvent
from app.services.client_domain_repair import (
    parity_report,
    repair_missing_events_for_interactions,
    repair_missing_projections,
)

router = APIRouter()


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
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (await db.execute(
        select(DomainEvent.event_type, func.count().label("cnt"))
        .where(DomainEvent.occurred_at >= since)
        .group_by(DomainEvent.event_type)
        .order_by(func.count().desc())
    )).all()
    return {
        "since_hours": hours,
        "total": sum(int(r.cnt) for r in rows),
        "by_type": {r.event_type: int(r.cnt) for r in rows},
    }


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
    lines.append("# HELP client_domain_timeline_parity_ratio "
                 "1 - (interactions_without_domain_event_id / total_interactions)")
    lines.append("# TYPE client_domain_timeline_parity_ratio gauge")
    lines.append(f"client_domain_timeline_parity_ratio {parity_ratio:.6f}")

    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain")


@router.post("/admin/client-domain/repair/projections")
async def post_repair_projections(
    limit: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("admin")),
) -> dict:
    repaired = await repair_missing_projections(db, limit=limit)
    await db.commit()
    return {"repaired_projections": repaired}


@router.post("/admin/client-domain/repair/events")
async def post_repair_events(
    limit: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("admin")),
) -> dict:
    repaired = await repair_missing_events_for_interactions(db, limit=limit)
    await db.commit()
    return {"repaired_events": repaired}
