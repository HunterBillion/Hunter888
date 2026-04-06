"""Cross-module recommendation engine: Arena ↔ Training.

Connects knowledge gaps from Arena quizzes with Training session configuration,
and vice versa — training L10 scores drive Arena quiz recommendations.

Block 5 (ТЗ_БЛОК_5_CROSS_MODULE): the "glue" between Arena and Training.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeAnswer, KnowledgeQuizSession, QuizSessionStatus
from app.models.training import SessionStatus, TrainingSession
from app.services.knowledge_quiz import get_category_progress, get_user_weak_areas

logger = logging.getLogger(__name__)

# Display names for legal categories (Russian)
CATEGORY_DISPLAY_NAMES: dict[str, str] = {
    "eligibility": "Условия подачи",
    "procedure": "Порядок процедуры",
    "property": "Имущество",
    "consequences": "Последствия",
    "costs": "Стоимость",
    "creditors": "Кредиторы",
    "documents": "Документы",
    "timeline": "Сроки",
    "court": "Судебные процессы",
    "rights": "Права должника",
}

# Mapping: Arena knowledge category → Training session focus
CATEGORY_TO_TRAINING_FOCUS: dict[str, dict] = {
    "eligibility": {
        "focus": "Условия подачи на банкротство",
        "trap_types": ["legal_threshold", "eligibility_confusion"],
        "scenario_boost": ["cold_base", "in_website"],
    },
    "procedure": {
        "focus": "Порядок процедуры банкротства",
        "trap_types": ["procedure_misunderstanding"],
        "scenario_boost": ["in_hotline", "in_website"],
    },
    "property": {
        "focus": "Защита имущества при банкротстве",
        "trap_types": ["property_fear", "asset_hiding"],
        "scenario_boost": ["rescue", "vip_debtor"],
    },
    "consequences": {
        "focus": "Последствия банкротства",
        "trap_types": ["consequences_fear", "credit_history"],
        "scenario_boost": ["cold_ad", "cold_referral"],
    },
    "costs": {
        "focus": "Стоимость процедуры",
        "trap_types": ["price_objection", "hidden_costs"],
        "scenario_boost": ["in_website", "upsell"],
    },
    "creditors": {
        "focus": "Работа с кредиторами",
        "trap_types": ["creditor_pressure", "collector_threats"],
        "scenario_boost": ["rescue", "cold_base"],
    },
    "documents": {
        "focus": "Необходимые документы",
        "trap_types": ["document_overwhelm"],
        "scenario_boost": ["in_hotline"],
    },
    "timeline": {
        "focus": "Сроки процедуры",
        "trap_types": ["timeline_impatience"],
        "scenario_boost": ["cold_referral"],
    },
    "court": {
        "focus": "Судебные процессы",
        "trap_types": ["court_fear", "judge_bias"],
        "scenario_boost": ["vip_debtor"],
    },
    "rights": {
        "focus": "Права должника",
        "trap_types": ["rights_ignorance"],
        "scenario_boost": ["rescue", "special_couple"],
    },
}


class CrossModuleRecommendationEngine:
    """Connects Arena knowledge gaps with Training session configuration."""

    async def get_training_recommendations_from_arena(
        self, user_id: uuid.UUID, db: AsyncSession
    ) -> list[dict]:
        """Analyze Arena results and recommend training focus areas.

        Returns list of dicts:
            source, category, accuracy, recommendation, priority,
            suggested_action, training_impact
        """
        recommendations = []

        category_progress = await get_category_progress(user_id, db)

        for cp in category_progress:
            total = cp.get("total_answers", 0)
            if total < 3:
                continue  # Not enough data

            accuracy = cp.get("mastery_pct", 0)

            if accuracy < 50:
                priority = "critical"
                action = "themed_quiz"
            elif accuracy < 70:
                priority = "high"
                action = "themed_quiz"
            elif accuracy < 80:
                priority = "medium"
                action = "free_dialog"
            else:
                continue  # Good enough

            cat = cp["category"]
            display = CATEGORY_DISPLAY_NAMES.get(cat, cat)
            training_impact = CATEGORY_TO_TRAINING_FOCUS.get(cat, {
                "focus": cat, "trap_types": [], "scenario_boost": [],
            })

            recommendations.append({
                "source": "arena",
                "category": cat,
                "accuracy": accuracy,
                "recommendation": (
                    f"Повторите тему «{display}» — accuracy {accuracy}%"
                ),
                "priority": priority,
                "suggested_action": action,
                "training_impact": training_impact,
            })

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2}
        recommendations.sort(key=lambda r: priority_order.get(r["priority"], 3))

        return recommendations[:5]

    async def get_arena_recommendations_from_training(
        self, user_id: uuid.UUID, db: AsyncSession
    ) -> list[dict]:
        """Analyze Training L10 (Legal Accuracy) scores and recommend Arena quizzes.

        Returns list of dicts:
            source, l10_score, l10_max, recommendation,
            suggested_categories, priority
        """
        # Get recent completed training sessions
        result = await db.execute(
            select(TrainingSession)
            .where(
                TrainingSession.user_id == user_id,
                TrainingSession.status == SessionStatus.completed,
            )
            .order_by(TrainingSession.started_at.desc())
            .limit(10)
        )
        sessions = result.scalars().all()

        if not sessions:
            return []

        # Extract L10 (legal accuracy) scores from score_breakdown
        l10_scores = []
        for s in sessions:
            bd = s.score_breakdown if hasattr(s, "score_breakdown") and s.score_breakdown else {}
            if isinstance(bd, dict):
                l10 = bd.get("legal", 0) or bd.get("legal_accuracy", 0) or 0
                if l10 > 0:
                    l10_scores.append(l10)

        if not l10_scores:
            return []

        avg_l10 = sum(l10_scores) / len(l10_scores)
        max_l10 = 5.0  # L10 max is typically 5.0

        recommendations = []

        if avg_l10 < max_l10 * 0.5:  # Below 50% of max
            # Determine weak categories from Arena data
            weak_areas = await get_user_weak_areas(user_id, db, limit=3)

            priority = "high" if avg_l10 < max_l10 * 0.3 else "medium"

            recommendations.append({
                "source": "training",
                "l10_score": round(avg_l10, 1),
                "l10_max": max_l10,
                "recommendation": (
                    f"Ваш показатель Legal Accuracy низкий "
                    f"({round(avg_l10, 1)}/{max_l10}). "
                    "Рекомендуем пройти тест знаний по ФЗ-127."
                ),
                "suggested_categories": (
                    weak_areas if weak_areas
                    else ["eligibility", "procedure"]
                ),
                "priority": priority,
            })

        return recommendations

    async def get_training_context_injection(
        self, user_id: uuid.UUID, db: AsyncSession
    ) -> str | None:
        """Build context injection string for training session system prompt.

        Returns a text block to append to the AI client's system prompt,
        or None if no Arena data warrants injection.
        """
        arena_recs = await self.get_training_recommendations_from_arena(user_id, db)

        if not arena_recs:
            return None

        # Only inject for critical/high priority
        high_recs = [r for r in arena_recs if r["priority"] in ("critical", "high")]
        if not high_recs:
            return None

        weak_topics = [
            r["training_impact"]["focus"]
            for r in high_recs[:3]
            if "training_impact" in r
        ]

        if not weak_topics:
            return None

        return (
            "\n\nДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ (из Арены знаний):\n"
            "У этого менеджера слабые знания по следующим темам ФЗ-127:\n"
            + "\n".join(f"- {topic}" for topic in weak_topics)
            + "\n\nВо время диалога ЧАЩЕ задавай вопросы по этим темам. "
            "Если менеджер ошибается — корректно поправляй."
        )

    async def get_all_recommendations(
        self, user_id: uuid.UUID, db: AsyncSession
    ) -> dict:
        """Get combined recommendations from both directions."""
        arena_to_training = await self.get_training_recommendations_from_arena(
            user_id, db,
        )
        training_to_arena = await self.get_arena_recommendations_from_training(
            user_id, db,
        )

        return {
            "arena_to_training": arena_to_training,
            "training_to_arena": training_to_arena,
            "total_recommendations": len(arena_to_training) + len(training_to_arena),
        }
