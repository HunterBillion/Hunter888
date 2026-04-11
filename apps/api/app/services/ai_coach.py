"""AI Coach 2.0 — Unified interactive coaching service.

Phase 2: Merges daily_advice, recommendation_engine, and weekly_report
into a single conversational AI coach with RAG over:
  1. Legal knowledge (rag_legal)
  2. Manager's personal wiki (rag_wiki)
  3. Manager's session history
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.training import TrainingSession, SessionStatus
from app.models.manager_wiki import ManagerPattern, ManagerTechnique, ManagerWiki

logger = logging.getLogger(__name__)


@dataclass
class CoachResponse:
    text: str
    action: str | None = None  # "start_training", "start_quiz", "show_replay"
    action_data: dict | None = None


async def coach_chat(
    user_id: uuid.UUID,
    message: str,
    db: AsyncSession,
) -> CoachResponse:
    """Main AI Coach chat endpoint. Coach knows everything about the manager."""
    from app.services.llm import generate_response

    # 1. Gather manager context
    profile_ctx = await _get_manager_context(user_id, db)

    # 2. Unified RAG: Legal + Wiki + Personality in parallel
    rag_ctx = ""
    try:
        from app.services.rag_unified import retrieve_all_context
        rag_result = await retrieve_all_context(
            query=message,
            user_id=user_id,
            db=db,
            context_type="coach",
        )
        rag_ctx = rag_result.to_prompt()
    except Exception:
        logger.debug("Unified RAG failed for coach, continuing without")

    # 3. Build system prompt
    system_prompt = f"""Ты — персональный AI-тренер менеджера по продажам банкротства (127-ФЗ).

ПРОФИЛЬ МЕНЕДЖЕРА:
{profile_ctx}

{rag_ctx or "Нет дополнительного контекста."}

ПРАВИЛА:
- Отвечай конкретно, ссылаясь на данные менеджера
- Если менеджер спрашивает про свои слабости — используй wiki-паттерны
- Если спрашивает про закон — используй юридический контекст
- Предлагай конкретные тренировки (сценарий + архетип + сложность)
- Будь мотивирующим но честным
- Максимум 150 слов
- Отвечай на русском"""

    # 4. Generate response
    result = await generate_response(
        system_prompt=system_prompt,
        messages=[{"role": "user", "content": message}],
        task_type="coach",
        user_id=str(user_id),
    )

    # 5. Detect action suggestions
    action = None
    action_data = None
    text_lower = result.content.lower()
    if any(kw in text_lower for kw in ["потренируй", "тренировк", "попробуй сценарий"]):
        action = "start_training"
    elif any(kw in text_lower for kw in ["квиз", "проверь знания", "тест"]):
        action = "start_quiz"

    return CoachResponse(
        text=result.content,
        action=action,
        action_data=action_data,
    )


async def get_proactive_tip(user_id: uuid.UUID, db: AsyncSession) -> str | None:
    """Check if coach should proactively reach out. Returns tip or None."""
    # Check recent sessions
    recent = await db.execute(
        select(func.count(), func.avg(TrainingSession.score_total))
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
        )
    )
    row = recent.one_or_none()
    if not row or row[0] == 0:
        return "Привет! Ты ещё не проходил тренировки. Давай начнём с простого сценария?"

    count, avg_score = row
    if count >= 3 and avg_score and avg_score < 50:
        return f"Заметил, что средний балл за последние сессии — {int(avg_score)}. Давай разберём, что можно улучшить?"

    # Check for confirmed weakness patterns
    patterns = await db.execute(
        select(ManagerPattern.pattern_code, ManagerPattern.description)
        .where(
            ManagerPattern.manager_id == user_id,
            ManagerPattern.category == "weakness",
            ManagerPattern.confirmed_at.isnot(None),
        )
        .limit(1)
    )
    weakness = patterns.first()
    if weakness:
        return f"У тебя подтверждённый паттерн: {weakness.description}. Хочешь поработать над этим?"

    return None


async def _get_manager_context(user_id: uuid.UUID, db: AsyncSession) -> str:
    """Build manager profile context for coach prompt."""
    lines = []

    # Sessions stats
    stats = await db.execute(
        select(
            func.count().label("total"),
            func.avg(TrainingSession.score_total).label("avg_score"),
            func.max(TrainingSession.score_total).label("best_score"),
        )
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
        )
    )
    row = stats.one_or_none()
    if row and row.total:
        lines.append(f"- Сессий: {row.total}, средний балл: {int(row.avg_score or 0)}, лучший: {int(row.best_score or 0)}")

    # Patterns
    patterns = await db.execute(
        select(ManagerPattern.pattern_code, ManagerPattern.category, ManagerPattern.description)
        .where(ManagerPattern.manager_id == user_id)
        .order_by(ManagerPattern.sessions_in_pattern.desc())
        .limit(5)
    )
    for p in patterns:
        lines.append(f"- Паттерн [{p.category}]: {p.description}")

    # Techniques
    techniques = await db.execute(
        select(ManagerTechnique.technique_name, ManagerTechnique.success_rate)
        .where(ManagerTechnique.manager_id == user_id)
        .order_by(ManagerTechnique.success_rate.desc())
        .limit(3)
    )
    for t in techniques:
        lines.append(f"- Техника: {t.technique_name} (успешность {int(t.success_rate * 100)}%)")

    return "\n".join(lines) if lines else "Нет данных — менеджер новый."
