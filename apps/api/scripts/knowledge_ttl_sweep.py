"""TZ-4 §8.3 knowledge TTL sweeper — daily cron entrypoint.

Runs :func:`app.services.knowledge_review_policy.expire_overdue` once
inside the API container's DB session and commits. Designed to be
invoked from cron / systemd timer / `docker compose exec`:

    # Operator one-shot (read-only check first):
    python -m scripts.knowledge_ttl_sweep --dry-run

    # Production daily run (writes + commits):
    python -m scripts.knowledge_ttl_sweep

The sweeper is **idempotent** — re-running on the same DB does
nothing because :func:`expire_overdue` only matches rows still in
``knowledge_status='actual'``. Once flipped to ``needs_review`` they
fall out of the candidate set, so a stuck cron firing every minute
is safe (just wasteful).

Per §8.3.1 the sweeper writes ``knowledge_status='needs_review'`` and
**never** ``'outdated'``. The architectural guard lives in the service
module; this script is a thin dispatcher.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import async_session  # noqa: E402
from app.services.knowledge_review_policy import expire_overdue  # noqa: E402


def _format_result(result, *, dry_run: bool) -> str:
    return json.dumps(
        {
            "dry_run": dry_run,
            "swept_at": result.swept_at.isoformat(),
            "total_expired": result.total_expired,
            "flipped_to_needs_review": result.flipped_to_needs_review,
            "skipped_already_flipped": result.skipped_already_flipped,
        },
        indent=2,
    )


async def _run(*, dry_run: bool, batch_size: int) -> None:
    async with async_session() as db:
        result = await expire_overdue(db, batch_size=batch_size)
        if dry_run:
            await db.rollback()
            print(_format_result(result, dry_run=True))
            print(
                "[dry-run] Rolled back. Re-run without --dry-run to commit.",
                file=sys.stderr,
            )
            return
        await db.commit()
        print(_format_result(result, dry_run=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the sweep but ROLLBACK the transaction at the end. "
        "Useful for inspecting how many items would flip.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Maximum number of chunks processed per invocation. "
        "Multiple runs catch up if the candidate set is larger.",
    )
    args = parser.parse_args(argv)
    asyncio.run(_run(dry_run=args.dry_run, batch_size=args.batch_size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
