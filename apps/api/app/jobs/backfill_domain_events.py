"""Backfill DomainEvents for legacy ClientInteraction rows (TZ-1 §9.1).

This is the scheduler-friendly wrapper around
``services.client_domain_repair.repair_missing_events_for_interactions``.
It runs a single bounded pass, exposes a ``dry_run`` mode for ops
validation, and is safe to call from cron or an admin trigger — the
underlying repair uses deterministic idempotency keys
(``repair:client_interaction:<id>``) so re-runs are no-ops.

CLI entry point lives at ``scripts/client_domain_ops.py`` — this module
is the importable surface for background workers.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import ClientInteraction
from app.services.client_domain_repair import (
    parity_report,
    repair_missing_events_for_interactions,
    repair_missing_projections,
)

logger = logging.getLogger(__name__)


async def count_legacy_interactions(db: AsyncSession) -> int:
    """How many ClientInteraction rows still miss ``metadata.domain_event_id``."""
    stmt = select(func.count()).select_from(ClientInteraction).where(
        (ClientInteraction.metadata_.is_(None))
        | (~ClientInteraction.metadata_.has_key("domain_event_id"))  # noqa: W504
    )
    return int((await db.execute(stmt)).scalar_one())


async def run_backfill(
    db: AsyncSession,
    *,
    batch_size: int = 500,
    max_batches: int = 10,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run up to ``max_batches`` passes of the repair helper.

    ``dry_run=True`` returns the current parity + backlog counts without
    writing anything. Use this from ops before a scheduled run.
    """
    backlog_before = await count_legacy_interactions(db)
    if dry_run:
        return {
            "dry_run": True,
            "interactions_without_domain_event_id": backlog_before,
            "parity_before": await parity_report(db),
        }

    total_events_repaired = 0
    total_projections_filled = 0
    for batch in range(1, max_batches + 1):
        repaired = await repair_missing_events_for_interactions(db, limit=batch_size)
        total_events_repaired += repaired
        logger.info(
            "backfill_domain_events.batch_done",
            extra={"batch": batch, "repaired": repaired, "running_total": total_events_repaired},
        )
        if repaired == 0:
            break
    # Fill any projection gaps caused by the fresh events.
    total_projections_filled = await repair_missing_projections(db, limit=batch_size)
    await db.commit()

    return {
        "dry_run": False,
        "batches_run": batch,
        "events_repaired": total_events_repaired,
        "projections_filled": total_projections_filled,
        "parity_after": await parity_report(db),
    }
