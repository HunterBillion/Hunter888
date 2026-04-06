"""
Catch-up manager for stuck checkpoints (DOC_04 §26).

Three-stage system:
- Stage 1 (7 days no progress): personalized hint
- Stage 2 (14 days no progress): reduce requirement by 1 step
- Never auto-complete
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.checkpoint import CheckpointDefinition, UserCheckpoint


# Reduction rules per condition parameter
REDUCTION_RULES: dict[str, dict[str, Any]] = {
    "count": {"delta": -1, "min": 1},
    "min_score": {"delta": -5, "min": 40},
    "min_value": {"delta": -5, "min": 40},
    "min_difficulty": {"delta": -1, "min": 1},
    "min_pct": {"delta": -5, "min": 40},
}


class CatchUpManager:
    """Manages catch-up mechanics for stuck checkpoints."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_and_apply(self, user_id) -> list[dict]:
        """Check all incomplete checkpoints for catch-up eligibility."""
        now = datetime.utcnow()
        actions: list[dict] = []

        # Find incomplete user checkpoints with stale progress
        result = await self.db.execute(
            select(UserCheckpoint, CheckpointDefinition)
            .join(CheckpointDefinition, UserCheckpoint.checkpoint_id == CheckpointDefinition.id)
            .where(
                UserCheckpoint.user_id == user_id,
                UserCheckpoint.is_completed == False,  # noqa: E712
            )
        )

        for ucp, cp_def in result.all():
            if not ucp.updated_at and not ucp.created_at:
                continue

            last_activity = ucp.updated_at or ucp.created_at
            days_stuck = (now - last_activity).days

            if days_stuck >= 14 and not ucp.is_softened:
                # Stage 2: reduce requirement
                softened = self._soften_condition(cp_def.condition)
                if softened:
                    ucp.progress = ucp.progress or {}
                    ucp.progress["softened_condition"] = softened
                    ucp.is_softened = True
                    actions.append({
                        "code": cp_def.code,
                        "stage": 2,
                        "action": "softened",
                        "original": cp_def.condition,
                        "softened": softened,
                    })

            elif days_stuck >= 7:
                # Stage 1: generate hint
                hint = self._generate_hint(cp_def)
                actions.append({
                    "code": cp_def.code,
                    "stage": 1,
                    "action": "hint",
                    "hint": hint,
                })

        return actions

    def _soften_condition(self, condition: dict) -> dict | None:
        """Apply reduction rules to condition parameters."""
        softened = dict(condition)
        changed = False

        for param, rule in REDUCTION_RULES.items():
            if param in softened:
                new_val = softened[param] + rule["delta"]
                if new_val >= rule["min"]:
                    softened[param] = new_val
                    changed = True

        return softened if changed else None

    def _generate_hint(self, cp_def: CheckpointDefinition) -> str:
        """Generate a personalized hint for a stuck checkpoint."""
        cond = cp_def.condition
        cond_type = cond.get("type", "")

        hints = {
            "score_threshold": f"Попробуйте сессию с лёгким архетипом (grateful, passive) на сложности 3-4",
            "deal_at_difficulty": f"Начните с архетипа pragmatic или referred — у них высокий шанс deal",
            "skill_threshold": f"Сфокусируйтесь на сессиях с архетипами, прокачивающими нужный навык",
            "deal_with_archetype": f"Используйте конструктор с нужным архетипом на сложности на 1-2 ниже вашего уровня",
            "trap_dodge_streak": f"Выбирайте сложность 3-4 и внимательно слушайте вопросы-ловушки клиента",
            "all_skills_threshold": f"Ищите навык с самым низким значением и играйте архетипы, которые его прокачивают",
            "consecutive_sessions_score": f"Играйте знакомых архетипов на комфортной сложности — стабильность важнее рекордов",
            "deal_streak": f"Выбирайте лёгких клиентов (T1) для создания серии, потом повышайте",
        }

        return hints.get(cond_type, f"Продолжайте тренировки — прогресс чекпоинта '{cp_def.name}' обновляется автоматически")
