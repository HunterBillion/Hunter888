"""TZ-1 client-domain ops CLI — bypasses HTTP/CSRF.

Runs directly inside the API container with the app's DB session and
commits its own transaction. Safe for ops to invoke without an admin JWT.

Usage (from /opt/hunter888/apps/api):
    # Print parity counts (read-only)
    python -m scripts.client_domain_ops parity

    # Backfill DomainEvent for legacy ClientInteraction rows that still
    # miss metadata.domain_event_id.
    python -m scripts.client_domain_ops repair-events [--limit 1000]

    # Fill in CrmTimelineProjectionState rows that reference an existing
    # DomainEvent but never got a projection record.
    python -m scripts.client_domain_ops repair-projections [--limit 1000]

    # Run everything (parity → repair events → repair projections → parity).
    python -m scripts.client_domain_ops full-sweep
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import async_session as AsyncSessionLocal  # noqa: E402
from app.services.client_domain_repair import (  # noqa: E402
    parity_report,
    repair_missing_events_for_interactions,
    repair_missing_projections,
)


def _print_report(title: str, report: dict) -> None:
    print(f"\n── {title} ──")
    print(json.dumps(report, indent=2, ensure_ascii=False))


async def _cmd_parity() -> int:
    async with AsyncSessionLocal() as db:
        report = await parity_report(db)
        _print_report("Parity report", report)
    return 0


async def _cmd_repair_events(limit: int) -> int:
    async with AsyncSessionLocal() as db:
        repaired = await repair_missing_events_for_interactions(db, limit=limit)
        await db.commit()
    print(f"repaired events: {repaired}")
    return 0


async def _cmd_repair_projections(limit: int) -> int:
    async with AsyncSessionLocal() as db:
        repaired = await repair_missing_projections(db, limit=limit)
        await db.commit()
    print(f"repaired projections: {repaired}")
    return 0


async def _cmd_full_sweep(limit: int) -> int:
    async with AsyncSessionLocal() as db:
        before = await parity_report(db)
        _print_report("Parity BEFORE", before)
    async with AsyncSessionLocal() as db:
        events_repaired = await repair_missing_events_for_interactions(db, limit=limit)
        await db.commit()
    async with AsyncSessionLocal() as db:
        projections_repaired = await repair_missing_projections(db, limit=limit)
        await db.commit()
    async with AsyncSessionLocal() as db:
        after = await parity_report(db)
        _print_report("Parity AFTER", after)
    print(
        f"\n== summary == events_repaired={events_repaired} "
        f"projections_repaired={projections_repaired}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("parity", help="Print parity counts")

    p_events = sub.add_parser("repair-events", help="Backfill missing DomainEvents")
    p_events.add_argument("--limit", type=int, default=1000)

    p_proj = sub.add_parser(
        "repair-projections", help="Backfill missing projection rows"
    )
    p_proj.add_argument("--limit", type=int, default=1000)

    p_full = sub.add_parser("full-sweep", help="Parity + repair both + parity again")
    p_full.add_argument("--limit", type=int, default=1000)

    args = parser.parse_args()

    if args.cmd == "parity":
        return asyncio.run(_cmd_parity())
    if args.cmd == "repair-events":
        return asyncio.run(_cmd_repair_events(args.limit))
    if args.cmd == "repair-projections":
        return asyncio.run(_cmd_repair_projections(args.limit))
    if args.cmd == "full-sweep":
        return asyncio.run(_cmd_full_sweep(args.limit))
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
