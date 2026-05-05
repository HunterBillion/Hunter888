"""PvP duel reaper — closes duels stuck in non-terminal state.

A duel can get stuck in ``pending`` / ``round_1`` / ``swap`` / ``round_2``
/ ``judging`` if the API worker that owned it dies (deploy, OOM, SIGKILL).
The in-process ``_disconnect_tasks`` dict in ``ws.pvp`` is not persisted —
so on restart, no task ever fires the 60s grace cancel for the orphaned
participants. Without this reaper, stuck rows live forever.

Production audit on 2026-05-05 found 4/11 historical duels in this state
(see PR-1 motivation in CLAUDE.md §4). The reaper closes any row whose
``created_at`` is older than ``_STUCK_AGE_SECONDS`` and whose status is
non-terminal, stamping ``terminal_outcome=pvp_abandoned`` and
``terminal_reason=reaper_stuck_state`` via the completion policy.

Tick cadence is intentionally short (5 min default) — leftover stuck
rows hurt observability metrics and confuse the leaderboard. There is no
contention with the live disconnect-cancel path because that path
checks ``duel.status in (completed, cancelled)`` before acting and the
reaper's UPDATE flips status to cancelled in the same transaction it
stamps terminal columns.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

logger = logging.getLogger(__name__)


_STUCK_AGE_SECONDS = 30 * 60  # 30 min — well past round limit (10m) + grace (1m)
_TICK_SECONDS = 5 * 60        # 5 min cadence


class PvPDuelReaper:
    """Long-running worker that closes orphaned non-terminal duels."""

    def __init__(
        self,
        *,
        tick_seconds: int = _TICK_SECONDS,
        stuck_age_seconds: int = _STUCK_AGE_SECONDS,
    ) -> None:
        self.tick_seconds = tick_seconds
        self.stuck_age_seconds = stuck_age_seconds
        self._stopped = asyncio.Event()
        self.runs_count = 0
        self.reaped_total = 0
        self.last_reaped: int = 0

    def stop(self) -> None:
        self._stopped.set()

    async def _run_one(self) -> int:
        """Single sweep. Returns the number of duels reaped this tick."""
        from app.database import async_session
        from app.models.pvp import DuelStatus, PvPDuel
        from app.services.completion_policy import (
            TerminalOutcome,
            TerminalReason,
            finalize_pvp_duel,
        )

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.stuck_age_seconds)
        non_terminal = (
            DuelStatus.pending,
            DuelStatus.round_1,
            DuelStatus.swap,
            DuelStatus.round_2,
            DuelStatus.judging,
        )

        reaped = 0
        try:
            async with async_session() as db:
                # Review fix #2: with_for_update(skip_locked=True) so two
                # API replicas (rolling deploy 1→2) don't both try to
                # finalize the same row. The second replica gets an empty
                # batch and waits for next tick instead of contending.
                # SQLite (test) does not support row-locking, so the
                # `with_for_update()` call is a no-op there but kept for
                # the production Postgres path. ``skip_locked`` is the
                # same pattern matchmaker.py uses for queue safety.
                try:
                    stmt = select(PvPDuel).where(
                        PvPDuel.status.in_(non_terminal),
                        PvPDuel.created_at < cutoff,
                    ).limit(100).with_for_update(skip_locked=True)
                    rows = (await db.execute(stmt)).scalars().all()
                except Exception:
                    # SQLite-in-tests can't compile FOR UPDATE; fall back
                    # to a plain select. Production Postgres always supports
                    # row locks, so this catch only fires under unit tests.
                    stmt = select(PvPDuel).where(
                        PvPDuel.status.in_(non_terminal),
                        PvPDuel.created_at < cutoff,
                    ).limit(100)
                    rows = (await db.execute(stmt)).scalars().all()
                for duel in rows:
                    # Re-verify status under the held row lock — defensive
                    # if a concurrent transaction snuck a state transition
                    # past the WHERE clause (shouldn't happen with
                    # skip_locked, but cheap insurance).
                    if duel.status not in non_terminal:
                        continue
                    duel.status = DuelStatus.cancelled
                    now = datetime.now(timezone.utc)
                    if not duel.completed_at:
                        duel.completed_at = now
                    if duel.created_at and not duel.duration_seconds:
                        # SQLite (test) returns naive datetimes; Postgres
                        # TIMESTAMPTZ returns aware. Normalize before subtract
                        # so the test path doesn't TypeError on a real bug we'd
                        # see only in CI.
                        created = duel.created_at
                        completed = duel.completed_at
                        if created.tzinfo is None:
                            created = created.replace(tzinfo=timezone.utc)
                        if completed.tzinfo is None:
                            completed = completed.replace(tzinfo=timezone.utc)
                        duel.duration_seconds = max(
                            0,
                            int((completed - created).total_seconds()),
                        )
                    try:
                        await finalize_pvp_duel(
                            db,
                            duel=duel,
                            outcome=TerminalOutcome.pvp_abandoned,
                            reason=TerminalReason.reaper_stuck_state,
                        )
                    except Exception:
                        logger.warning(
                            "pvp_duel_reaper: finalize stamp failed for %s",
                            duel.id, exc_info=True,
                        )
                    db.add(duel)
                    reaped += 1
                if reaped:
                    await db.commit()
                    logger.info(
                        "pvp_duel_reaper: reaped %d stuck duel(s)", reaped
                    )
        except Exception:
            logger.warning(
                "pvp_duel_reaper: tick failed (will retry next pass)",
                exc_info=True,
            )
        self.last_reaped = reaped
        self.reaped_total += reaped
        return reaped

    async def run_forever(self) -> None:
        logger.info(
            "pvp_duel_reaper: started (tick=%ds, stuck_age=%ds)",
            self.tick_seconds, self.stuck_age_seconds,
        )
        try:
            while not self._stopped.is_set():
                await self._run_one()
                self.runs_count += 1
                try:
                    await asyncio.wait_for(
                        self._stopped.wait(), timeout=self.tick_seconds
                    )
                    return
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            raise
        finally:
            logger.info(
                "pvp_duel_reaper: stopped (runs=%d, reaped_total=%d)",
                self.runs_count, self.reaped_total,
            )


__all__ = ["PvPDuelReaper"]
