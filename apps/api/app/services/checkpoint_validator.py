"""
Checkpoint validation service (DOC_04 §27).

Validates checkpoint conditions, manages user checkpoint progress,
and gates level-up on required checkpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.checkpoint import CheckpointDefinition, UserCheckpoint
from app.models.progress import ManagerProgress


@dataclass
class CheckpointStatus:
    code: str
    name: str
    description: str
    is_required: bool
    is_completed: bool
    progress: dict | None  # {"current": N, "target": M}
    xp_reward: int
    category: str


@dataclass
class LevelUpEligibility:
    xp_sufficient: bool
    checkpoints_met: bool
    missing_checkpoints: list[str]  # codes of missing required checkpoints
    message: str


class CheckpointValidator:
    """Validates checkpoint conditions and manages level-up gates."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_all_for_level(self, user_id: UUID, level: int) -> list[CheckpointStatus]:
        """Get status of all checkpoints for a specific level."""
        # Get checkpoint definitions for this level
        defs_result = await self.db.execute(
            select(CheckpointDefinition)
            .where(CheckpointDefinition.level == level)
            .order_by(CheckpointDefinition.order_num)
        )
        definitions = defs_result.scalars().all()

        # Get user progress
        user_cps_result = await self.db.execute(
            select(UserCheckpoint)
            .where(
                UserCheckpoint.user_id == user_id,
                UserCheckpoint.checkpoint_id.in_([d.id for d in definitions]),
            )
        )
        user_cps = {ucp.checkpoint_id: ucp for ucp in user_cps_result.scalars().all()}

        statuses = []
        for d in definitions:
            ucp = user_cps.get(d.id)
            statuses.append(CheckpointStatus(
                code=d.code,
                name=d.name,
                description=d.description,
                is_required=d.is_required,
                is_completed=ucp.is_completed if ucp else False,
                progress=ucp.progress if ucp else None,
                xp_reward=d.xp_reward,
                category=d.category,
            ))

        return statuses

    async def can_level_up(self, user_id: UUID, current_level: int) -> LevelUpEligibility:
        """Check if user can advance to next level (XP + checkpoints)."""
        from scripts.seed_levels import LEVEL_XP_THRESHOLDS

        # Get manager progress
        result = await self.db.execute(
            select(ManagerProgress).where(ManagerProgress.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            return LevelUpEligibility(
                xp_sufficient=False, checkpoints_met=False,
                missing_checkpoints=[], message="Профиль не найден",
            )

        next_level = current_level + 1
        xp_needed = LEVEL_XP_THRESHOLDS.get(next_level, 999999)
        xp_sufficient = profile.total_xp >= xp_needed

        # Check required checkpoints for current level
        statuses = await self.check_all_for_level(user_id, current_level)
        missing = [s.code for s in statuses if s.is_required and not s.is_completed]
        checkpoints_met = len(missing) == 0

        if xp_sufficient and checkpoints_met:
            message = f"Готов к уровню {next_level}!"
        elif not xp_sufficient:
            message = f"Нужно ещё {xp_needed - profile.total_xp} XP"
        else:
            message = f"Выполните обязательные чекпоинты: {len(missing)} осталось"

        return LevelUpEligibility(
            xp_sufficient=xp_sufficient,
            checkpoints_met=checkpoints_met,
            missing_checkpoints=missing,
            message=message,
        )

    async def complete_checkpoint(
        self, user_id: UUID, checkpoint_code: str
    ) -> tuple[bool, int]:
        """Mark a checkpoint as completed and award XP. Returns (newly_completed, xp_awarded)."""
        # Find definition
        def_result = await self.db.execute(
            select(CheckpointDefinition).where(CheckpointDefinition.code == checkpoint_code)
        )
        cp_def = def_result.scalar_one_or_none()
        if not cp_def:
            return False, 0

        # Find or create user checkpoint
        ucp_result = await self.db.execute(
            select(UserCheckpoint).where(
                UserCheckpoint.user_id == user_id,
                UserCheckpoint.checkpoint_id == cp_def.id,
            )
        )
        ucp = ucp_result.scalar_one_or_none()

        if ucp and ucp.is_completed:
            return False, 0  # Already completed

        if not ucp:
            ucp = UserCheckpoint(
                user_id=user_id,
                checkpoint_id=cp_def.id,
                is_completed=True,
                completed_at=datetime.now(timezone.utc),
                xp_awarded=True,
            )
            self.db.add(ucp)
        else:
            ucp.is_completed = True
            ucp.completed_at = datetime.now(timezone.utc)
            ucp.xp_awarded = True

        return True, cp_def.xp_reward

    async def grandfather_existing_user(self, user_id: UUID, current_level: int) -> int:
        """Auto-complete all required checkpoints for levels below current (DOC_04 §30 Conflict 2)."""
        if current_level <= 1:
            return 0

        # Get all required checkpoints for levels 1..(current_level-1)
        defs_result = await self.db.execute(
            select(CheckpointDefinition).where(
                CheckpointDefinition.level < current_level,
                CheckpointDefinition.is_required == True,  # noqa: E712
            )
        )
        definitions = defs_result.scalars().all()

        # Use INSERT ON CONFLICT DO NOTHING to avoid TOCTOU race and unique violation
        now = datetime.now(timezone.utc)
        completed = 0
        for cp_def in definitions:
            stmt = (
                pg_insert(UserCheckpoint.__table__)
                .values(
                    user_id=user_id,
                    checkpoint_id=cp_def.id,
                    is_completed=True,
                    completed_at=now,
                    xp_awarded=False,  # Don't double-award XP
                )
                .on_conflict_do_nothing(constraint="uq_user_checkpoint")
            )
            result = await self.db.execute(stmt)
            if result.rowcount:
                completed += 1

        return completed
