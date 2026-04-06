"""Seed Script + Checkpoint records from ScenarioTemplate stages.

Usage:
    python -m scripts.seed_scripts          # from apps/api/
    # or via make target:
    make seed-scripts

Creates a Script per scenario with Checkpoints derived from the scenario's
stage goals. This enables L1 (Script Adherence) scoring with checkpoint
tracking on the Results page.
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.database import async_session, engine, Base
from app.models.scenario import ScenarioTemplate, Scenario
from app.models.script import Script, Checkpoint

logger = logging.getLogger(__name__)


async def seed_scripts() -> None:
    """Create Script + Checkpoints from ScenarioTemplate stages, link to Scenario records."""
    async with async_session() as db:
        # Get all templates (have stages with goals)
        tmpl_result = await db.execute(select(ScenarioTemplate))
        templates = tmpl_result.scalars().all()

        # Get all scenarios (have script_id field)
        scen_result = await db.execute(select(Scenario))
        scenarios = scen_result.scalars().all()

        # Map template_id → scenarios for linking
        tmpl_to_scenarios: dict = {}
        for s in scenarios:
            if s.template_id:
                tmpl_to_scenarios.setdefault(s.template_id, []).append(s)

        created = 0
        skipped = 0

        for tmpl in templates:
            stages = tmpl.stages or []
            if not stages:
                logger.info("Template %s has no stages — skipping", tmpl.code)
                skipped += 1
                continue

            # Check if any linked scenario already has a script
            linked_scenarios = tmpl_to_scenarios.get(tmpl.id, [])
            if linked_scenarios and all(s.script_id for s in linked_scenarios):
                skipped += 1
                continue

            # Create Script from template stages
            script = Script(
                title=f"Скрипт: {tmpl.name}",
                description=f"Авто-генерация из stages сценария {tmpl.code}",
                version="1.0",
                is_active=True,
            )
            db.add(script)
            await db.flush()

            # Create Checkpoints from stages
            for stage in stages:
                order = stage.get("order", 0)
                name = stage.get("name", f"Этап {order}")
                description = stage.get("description", "")
                goals = stage.get("manager_goals", [])

                checkpoint = Checkpoint(
                    script_id=script.id,
                    title=name,
                    description=description,
                    order_index=order,
                    keywords=goals,
                    weight=1.0,
                )
                db.add(checkpoint)

            # Link script to all Scenario records that reference this template
            linked_count = 0
            for s in linked_scenarios:
                if not s.script_id:
                    s.script_id = script.id
                    linked_count += 1

            created += 1
            logger.info(
                "Created script '%s' with %d checkpoints (linked to %d scenarios)",
                script.title, len(stages), linked_count,
            )

        await db.commit()
        logger.info("Seed scripts: created=%d, skipped=%d", created, skipped)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_scripts()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
