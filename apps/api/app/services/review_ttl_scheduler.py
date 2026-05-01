"""TZ-8 PR-E — TTL auto-flip ``actual → needs_review`` for governance.

Closes the auto-stale arm of the four-state lifecycle for the
two user-curated RAG sources that carry a TTL field:

  * :class:`MethodologyChunk` — per-team playbooks. ROP can set
    ``review_due_at`` when authoring; this scheduler flips
    ``actual → needs_review`` once that timestamp passes, so the
    chunk disappears from RAG until a reviewer re-acknowledges
    it.
  * :class:`WikiPage` — per-manager auto-wiki + manual edits.
    Same TTL field added in PR-A; same auto-flip path here.

``LegalKnowledgeChunk`` already has its own governance hook in
:mod:`app.services.knowledge_governance` (TZ-4 §8.3.1) and is
**out of scope** for this scheduler — its review queue is admin-
only, not per-team.

The contract from TZ-4 §8.3.1, repeated here so a future PR can't
"helpfully" generalise it:

  *Auto-flip is one-directional.* The scheduler only ever flips
  ``actual → needs_review``. Promoting back to ``actual`` (re-
  acknowledge) or moving to ``outdated`` (manually retire) is a
  human-initiated PATCH ``/status`` call. If the scheduler did
  the second hop too, a day-of-cutover bug would silently delete
  the entire knowledge base by flipping every overdue row to
  ``outdated`` in one pass. The two-step gate prevents that.

How it runs
-----------

A single asyncio task is started by ``app.main`` lifespan when
``settings.review_ttl_scheduler_enabled`` is ``True`` (default
``False`` so existing deploys are unchanged). The task:

  1. Aligns to the top of the next hour so multi-worker fleets
     don't pile concurrent UPDATEs at offset moments.
  2. Calls :func:`run_review_ttl_pass` which scans the two
     tables and bulk-updates the rows past their TTL.
  3. Sleeps another hour. Cooperative cancel-aware.

For ad-hoc / cron-style triggers (e.g. a one-shot management
command), :func:`run_review_ttl_pass` is the public seam — it
takes a session and returns a structured summary. ``run_forever``
is the long-running variant.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_status import KnowledgeStatus
from app.models.manager_wiki import WikiPage
from app.models.methodology import MethodologyChunk

logger = logging.getLogger(__name__)


# ── Public seam: run-once ──────────────────────────────────────────────


class ReviewTtlPassResult(TypedDict):
    """Summary of one auto-flip pass for telemetry / management
    command output."""

    methodology_flipped: int
    wiki_flipped: int
    ran_at: datetime


async def run_review_ttl_pass(db: AsyncSession) -> ReviewTtlPassResult:
    """Scan and flip overdue rows once.

    Two bulk UPDATE statements (one per table) so a thousand-row
    pass is one round-trip, not one-row-per-flush. Both are scoped
    to ``knowledge_status='actual' AND review_due_at <= now()``;
    rows already in ``needs_review`` / ``disputed`` / ``outdated``
    are skipped (the SQL filter), as are rows without a TTL
    (``review_due_at IS NULL``).

    Idempotent: re-running within the hour is a no-op for any row
    a previous run already flipped, since it's no longer
    ``actual``. Safe to invoke from a cron + lifespan in parallel.

    Returns the count per table and the timestamp the run started
    (so a follow-up audit row can pin causality).
    """
    now = datetime.now(timezone.utc)

    # Methodology chunks
    meth_result = await db.execute(
        update(MethodologyChunk)
        .where(MethodologyChunk.knowledge_status == KnowledgeStatus.actual.value)
        .where(MethodologyChunk.review_due_at.isnot(None))
        .where(MethodologyChunk.review_due_at <= now)
        .values(
            knowledge_status=KnowledgeStatus.needs_review.value,
            updated_at=now,
        )
    )
    meth_count = meth_result.rowcount or 0

    # Wiki pages — same TTL contract introduced in PR-A.
    wiki_result = await db.execute(
        update(WikiPage)
        .where(WikiPage.knowledge_status == KnowledgeStatus.actual.value)
        .where(WikiPage.review_due_at.isnot(None))
        .where(WikiPage.review_due_at <= now)
        .values(
            knowledge_status=KnowledgeStatus.needs_review.value,
            updated_at=now,
        )
    )
    wiki_count = wiki_result.rowcount or 0

    await db.commit()

    if meth_count or wiki_count:
        logger.info(
            "review_ttl_scheduler: flipped methodology=%d wiki=%d at %s",
            meth_count, wiki_count, now.isoformat(),
        )

    return ReviewTtlPassResult(
        methodology_flipped=int(meth_count),
        wiki_flipped=int(wiki_count),
        ran_at=now,
    )


# ── Long-running scheduler ─────────────────────────────────────────────


_HOUR_SECONDS = 3600


def _seconds_until_top_of_next_hour(*, _now: datetime | None = None) -> float:
    """Aligns multi-worker fleets so the scan happens once per hour.

    Without alignment, two workers that started 30 seconds apart
    would each fire their hourly UPDATE 30 seconds offset — twice
    the contention on the row locks for no benefit. Computing the
    delay-to-top-of-the-hour at first run forces every worker to
    converge.
    """
    now = _now or datetime.now(timezone.utc)
    # next_top = round ``now`` up to the next exact hour.
    floor_hour = now.replace(minute=0, second=0, microsecond=0)
    next_top = floor_hour + timedelta(hours=1)
    delta = (next_top - now).total_seconds()
    return max(0.0, delta)


class ReviewTtlScheduler:
    """Long-running worker that calls :func:`run_review_ttl_pass` on
    an hourly schedule.

    Runs forever until ``stop()`` is called or the surrounding
    asyncio task is cancelled. Cancellation-aware: if cancelled
    mid-scan, the in-flight transaction's ``commit`` either
    completes or rolls back. The bulk UPDATE is idempotent so a
    partial rollback just means the next tick repeats the work.
    """

    def __init__(
        self,
        *,
        tick_seconds: int = _HOUR_SECONDS,
        align_to_hour: bool = True,
    ) -> None:
        self.tick_seconds = tick_seconds
        self.align_to_hour = align_to_hour
        self._stopped = asyncio.Event()
        self.last_result: ReviewTtlPassResult | None = None
        self.runs_count = 0

    def stop(self) -> None:
        self._stopped.set()

    async def _run_one(self) -> None:
        from app.database import async_session

        try:
            async with async_session() as db:
                self.last_result = await run_review_ttl_pass(db)
        except Exception:
            logger.warning(
                "review_ttl_scheduler: tick failed (will retry next hour)",
                exc_info=True,
            )
        else:
            self.runs_count += 1

    async def run_forever(self) -> None:
        """Sleep-tick-repeat loop. First wake aligns to the top of
        the next hour (when ``align_to_hour=True``), then every
        ``tick_seconds`` after that."""
        logger.info(
            "review_ttl_scheduler: started (tick_seconds=%d, align=%s)",
            self.tick_seconds, self.align_to_hour,
        )
        try:
            if self.align_to_hour:
                # First alignment — wait until top of the next hour so
                # multi-worker fleets converge.
                initial = _seconds_until_top_of_next_hour()
                try:
                    await asyncio.wait_for(
                        self._stopped.wait(), timeout=initial
                    )
                    return  # stop() called during the alignment wait
                except asyncio.TimeoutError:
                    pass  # alignment elapsed normally, fall through

            while not self._stopped.is_set():
                await self._run_one()
                try:
                    await asyncio.wait_for(
                        self._stopped.wait(), timeout=self.tick_seconds
                    )
                    return  # stop() during sleep
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            raise
        finally:
            logger.info(
                "review_ttl_scheduler: stopped (runs=%d, last_result=%s)",
                self.runs_count, self.last_result,
            )


__all__ = [
    "ReviewTtlScheduler",
    "ReviewTtlPassResult",
    "run_review_ttl_pass",
    "_seconds_until_top_of_next_hour",
]
