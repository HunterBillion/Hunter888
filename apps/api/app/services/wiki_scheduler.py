"""Wiki background scheduler — auto-ingest + daily/weekly synthesis.

Runs as an asyncio background task, similar to ReminderScheduler.
Registered in main.py lifespan.

Schedule:
- Every 12h: auto-ingest any un-ingested completed sessions
- Every 24h (at ~03:00 UTC): daily synthesis for all active wikis
- Every 7 days (Monday ~04:00 UTC): weekly synthesis for all active wikis
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import async_session
from app.models.manager_wiki import ManagerWiki, WikiAction, WikiUpdateLog
from app.models.training import SessionStatus, TrainingSession

logger = logging.getLogger(__name__)

# Intervals
INGEST_INTERVAL_HOURS = 12
DAILY_SYNTHESIS_HOUR = 3  # UTC hour for daily synthesis
WEEKLY_SYNTHESIS_DAY = 0  # Monday (0=Mon)
WEEKLY_SYNTHESIS_HOUR = 4  # UTC hour for weekly synthesis
CHECK_INTERVAL_MIN = 30  # How often we check if it's time to run


class WikiScheduler:
    """Background scheduler for wiki auto-ingest and synthesis."""

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_ingest_run: datetime | None = None
        self._last_daily_run: datetime | None = None
        self._last_weekly_run: datetime | None = None
        self._stats = {
            "total_ingests": 0,
            "total_daily_syntheses": 0,
            "total_weekly_syntheses": 0,
            "errors": 0,
        }

    def start(self) -> None:
        """Start the background scheduler."""
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("WikiScheduler started (ingest every %dh, daily at %02d:00 UTC)",
                     INGEST_INTERVAL_HOURS, DAILY_SYNTHESIS_HOUR)

    def stop(self) -> None:
        """Stop the background scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("WikiScheduler stopped")

    def get_status(self) -> dict:
        """Return current scheduler status."""
        return {
            "running": self._running,
            "last_ingest_run": self._last_ingest_run.isoformat() if self._last_ingest_run else None,
            "last_daily_run": self._last_daily_run.isoformat() if self._last_daily_run else None,
            "last_weekly_run": self._last_weekly_run.isoformat() if self._last_weekly_run else None,
            "stats": self._stats,
            "config": {
                "ingest_interval_hours": INGEST_INTERVAL_HOURS,
                "daily_synthesis_hour_utc": DAILY_SYNTHESIS_HOUR,
                "weekly_synthesis_day": "Monday",
                "weekly_synthesis_hour_utc": WEEKLY_SYNTHESIS_HOUR,
                "check_interval_min": CHECK_INTERVAL_MIN,
            },
        }

    async def _run_loop(self) -> None:
        """Main background loop."""
        # Wait 60s after startup before first check
        await asyncio.sleep(60)

        while self._running:
            try:
                now = datetime.now(timezone.utc)

                # Check: auto-ingest every 12h
                if self._should_run_ingest(now):
                    await self._run_auto_ingest()
                    self._last_ingest_run = now

                # Check: daily synthesis
                if self._should_run_daily(now):
                    await self._run_daily_synthesis()
                    self._last_daily_run = now

                # Check: weekly synthesis
                if self._should_run_weekly(now):
                    await self._run_weekly_synthesis()
                    self._last_weekly_run = now

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("WikiScheduler loop error: %s", e, exc_info=True)
                self._stats["errors"] += 1

            # Sleep until next check
            await asyncio.sleep(CHECK_INTERVAL_MIN * 60)

    def _should_run_ingest(self, now: datetime) -> bool:
        if not self._last_ingest_run:
            return True  # First run
        return (now - self._last_ingest_run) >= timedelta(hours=INGEST_INTERVAL_HOURS)

    def _should_run_daily(self, now: datetime) -> bool:
        if not self._last_daily_run:
            # Only run if it's around the right hour
            return now.hour == DAILY_SYNTHESIS_HOUR
        # Already ran today?
        if self._last_daily_run.date() == now.date():
            return False
        return now.hour >= DAILY_SYNTHESIS_HOUR

    def _should_run_weekly(self, now: datetime) -> bool:
        if not self._last_weekly_run:
            return now.weekday() == WEEKLY_SYNTHESIS_DAY and now.hour == WEEKLY_SYNTHESIS_HOUR
        # Already ran this week?
        days_since = (now - self._last_weekly_run).days
        if days_since < 6:
            return False
        return now.weekday() == WEEKLY_SYNTHESIS_DAY and now.hour >= WEEKLY_SYNTHESIS_HOUR

    async def _run_auto_ingest(self) -> None:
        """Auto-ingest un-ingested sessions for all managers."""
        logger.info("WikiScheduler: starting auto-ingest cycle")
        try:
            async with async_session() as db:
                # Get all active wikis
                wikis_r = await db.execute(
                    select(ManagerWiki)
                )
                wikis = wikis_r.scalars().all()

                total_ingested = 0
                for wiki in wikis:
                    try:
                        count = await self._ingest_for_manager(wiki.manager_id, wiki, db)
                        total_ingested += count
                    except Exception as e:
                        logger.warning("Auto-ingest failed for manager %s: %s", wiki.manager_id, e)

                self._stats["total_ingests"] += total_ingested
                logger.info("WikiScheduler: auto-ingest complete, %d sessions ingested", total_ingested)

        except Exception as e:
            logger.error("WikiScheduler: auto-ingest cycle failed: %s", e)
            self._stats["errors"] += 1

    async def _ingest_for_manager(
        self,
        manager_id,
        wiki: ManagerWiki,
        db,
    ) -> int:
        """Ingest un-ingested sessions for a specific manager. Returns count."""
        # Get already ingested session IDs
        log_r = await db.execute(
            select(WikiUpdateLog.triggered_by_session_id).where(
                WikiUpdateLog.wiki_id == wiki.id,
                WikiUpdateLog.action == WikiAction.ingest_session,
                WikiUpdateLog.status == "completed",
            )
        )
        ingested_ids = {row[0] for row in log_r.all() if row[0]}

        # Get completed sessions not yet ingested
        sessions_r = await db.execute(
            select(TrainingSession.id).where(
                TrainingSession.user_id == manager_id,
                TrainingSession.status == SessionStatus.completed,
            ).order_by(TrainingSession.started_at)
        )
        all_ids = [row[0] for row in sessions_r.all()]
        to_ingest = [sid for sid in all_ids if sid not in ingested_ids]

        if not to_ingest:
            return 0

        from app.services.wiki_ingest_service import ingest_session

        count = 0
        for sid in to_ingest[:10]:  # Cap per manager per cycle
            try:
                result = await ingest_session(sid, db)
                if result.get("status") == "ingested":
                    count += 1
            except Exception as e:
                logger.warning("Auto-ingest session %s failed: %s", sid, e)
        return count

    async def _run_daily_synthesis(self) -> None:
        """Run daily synthesis for all active wikis."""
        logger.info("WikiScheduler: starting daily synthesis")
        try:
            async with async_session() as db:
                from app.services.wiki_synthesis_service import run_daily_synthesis
                result = await run_daily_synthesis(db)
                completed = len([r for r in result.get("results", []) if r.get("status") == "completed"])
                self._stats["total_daily_syntheses"] += completed
                logger.info("WikiScheduler: daily synthesis complete, %d wikis processed", completed)
        except Exception as e:
            logger.error("WikiScheduler: daily synthesis failed: %s", e)
            self._stats["errors"] += 1

    async def _run_weekly_synthesis(self) -> None:
        """Run weekly synthesis for all active wikis."""
        logger.info("WikiScheduler: starting weekly synthesis")
        try:
            async with async_session() as db:
                from app.services.wiki_synthesis_service import run_weekly_synthesis
                result = await run_weekly_synthesis(db)
                completed = len([r for r in result.get("results", []) if r.get("status") == "completed"])
                self._stats["total_weekly_syntheses"] += completed
                logger.info("WikiScheduler: weekly synthesis complete, %d wikis processed", completed)
        except Exception as e:
            logger.error("WikiScheduler: weekly synthesis failed: %s", e)
            self._stats["errors"] += 1


# Singleton instance
wiki_scheduler = WikiScheduler()
