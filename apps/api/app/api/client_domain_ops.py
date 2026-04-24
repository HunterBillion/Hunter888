"""Admin-only operational endpoints for the unified client domain (TZ-1).

* ``GET  /admin/client-domain/parity`` — current counts used to gate cutover.
* ``POST /admin/client-domain/repair/projections`` — fill missing projections.
* ``POST /admin/client-domain/repair/events`` — backfill events for legacy
  interactions.

Restricted to ``admin``. Use sparingly during rollout; the numbers should
trend to zero once dual-write covers every producer.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.database import get_db
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
