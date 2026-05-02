"""Analytics events retention sweeper — periodic cron entrypoint.

Postgres has no built-in TTL on rows. The
:class:`app.models.analytics_event.AnalyticsEvent` table grows
unboundedly unless an external job deletes old rows. This script
implements the 90-day retention policy declared in alembic
``20260502_005_analytics_events.py``:

  * Dry run (preview):
        python -m scripts.cleanup_analytics --dry-run

  * Production weekly run (writes + commits):
        python -m scripts.cleanup_analytics

Idempotent — re-running on the same DB just deletes any newly-aged
rows. Safe to run hourly/daily/weekly; recommended cadence is once a
week (analytics tables don't need fine-grained pruning).

Cron snippet (Linux ``crontab -e``)::

    # Weekly analytics retention sweep, Sunday 03:00 server time.
    0 3 * * 0  cd /opt/hunter888 && docker compose -f docker-compose.yml \\
                -f docker-compose.prod.yml exec -T api \\
                python -m scripts.cleanup_analytics >> /var/log/hunter-analytics-cleanup.log 2>&1

The retention is **90 days** measured from ``created_at`` (server-side
ingestion timestamp). We deliberately do NOT key off ``occurred_at``
because that field can drift due to client clock skew — a phone with
a wrong date wouldn't be reaped on schedule.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.analytics_event import AnalyticsEvent  # noqa: E402

RETENTION_DAYS = 90


async def sweep(*, dry_run: bool) -> dict:
    """Delete (or count) analytics rows older than RETENTION_DAYS.

    Returns a result dict suitable for JSON-logging by cron wrappers.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    async with async_session() as session:
        # Count first — useful regardless of dry-run mode for ops
        # visibility ("how many rows would be deleted today?").
        count_stmt = select(func.count()).select_from(AnalyticsEvent).where(
            AnalyticsEvent.created_at < cutoff,
        )
        candidate_count = (await session.execute(count_stmt)).scalar_one()

        if dry_run or candidate_count == 0:
            return {
                "dry_run": dry_run,
                "cutoff": cutoff.isoformat(),
                "candidate_count": candidate_count,
                "deleted": 0,
            }

        result = await session.execute(
            delete(AnalyticsEvent).where(AnalyticsEvent.created_at < cutoff),
        )
        await session.commit()
        return {
            "dry_run": False,
            "cutoff": cutoff.isoformat(),
            "candidate_count": candidate_count,
            "deleted": result.rowcount or 0,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the row count that would be deleted; do not write.",
    )
    args = parser.parse_args()
    result = asyncio.run(sweep(dry_run=args.dry_run))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
