"""AI Coach 2.0 — Unified interactive coaching service (Task 2.5).

Personal mentor that:
1. Uses Unified RAG (Legal + Wiki + Personality)
2. References specific sessions ("8 апреля с клиентом-скептиком...")
3. Suggests scenarios based on weakness patterns
4. Can trigger quiz on weak legal topics
5. Proactively reaches out after sessions with personalized tips
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from sqlalchemy import func, select, desc
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

    # 1. Gather deep manager context (stats + last 5 sessions + patterns + techniques)
    profile_ctx = await _get_manager_context(user_id, db)
    recent_sessions_ctx = await _get_recent_sessions(user_id, db)

    # 2. Unified RAG: Legal + Wiki + Personality + Methodology in parallel.
    #
    # SEC/AUDIT-2026-05-02 (P0 #1 from 9-layer audit + prod-deploy report):
    # the previous call omitted ``team_id``. ``rag_unified.retrieve_all_context``
    # silently SKIPS the methodology branch when ``team_id is None`` (line 264
    # of rag_unified.py — by design, since methodology is per-team-only per
    # TZ-8 §1, no global fallback). Net effect: every methodology playbook
    # ROP uploaded was *invisible* to the coach. Resolve the caller's team
    # from the User row and forward it.
    rag_ctx = ""
    try:
        from app.models.user import User as _User
        from app.services.rag_unified import retrieve_all_context

        _team_id = (
            await db.execute(select(_User.team_id).where(_User.id == user_id))
        ).scalar_one_or_none()

        rag_result = await retrieve_all_context(
            query=message,
            user_id=user_id,
            db=db,
            context_type="coach",
            team_id=_team_id,
        )
        rag_ctx = rag_result.to_prompt()
    except Exception:
        logger.debug("Unified RAG failed for coach, continuing without")

    # 3. Build system prompt — mentor, not chatbot
    system_prompt = f"""Ты — персональный AI-наставник менеджера по продажам банкротства (127-ФЗ).
Ты НЕ чат-бот. Ты наставник, который ЗНАЕТ историю менеджера и даёт конкретные советы.

ПРОФИЛЬ МЕНЕДЖЕРА:
{profile_ctx}

ПОСЛЕДНИЕ СЕССИИ:
{recent_sessions_ctx}

{rag_ctx or ""}

ПРАВИЛА НАСТАВНИКА:
- Ссылайся на КОНКРЕТНЫЕ сессии менеджера: "В сессии от [дата] с [архетип]..."
- Если менеджер спрашивает про слабости — используй wiki-паттерны и покажи прогресс
- Предлагай КОНКРЕТНЫЙ сценарий: "Попробуй сценарий '[название]' с архетипом [тип], сложность [N]"
- Если вопрос про закон — используй юридический контекст, цитируй статьи
- Если менеджер может потренировать слабое место — предложи: "Хочешь мини-квиз на эту тему?"
- Будь мотивирующим но честным. Хвали конкретные улучшения
- Максимум 200 слов. Отвечай на русском
- Не повторяй общие фразы. Каждый ответ — персонализированный"""

    # 4. Generate response
    result = await generate_response(
        system_prompt=system_prompt,
        messages=[{"role": "user", "content": message}],
        task_type="coach",
        user_id=str(user_id),
    )

    # 4a. Citation enforcement: check whether the coach answer cites articles
    # from the retrieved legal RAG set. If the model hallucinated an article
    # not in the retrieved context, annotate the answer with a warning so the
    # manager knows to double-check. Fail-open: if rag_legal results are empty
    # (e.g. wiki-only question), no check runs.
    try:
        if rag_result and hasattr(rag_result, "legal_context") and rag_result.legal_context:
            from app.services.rag_grounding import check_citations, annotate_answer
            # Reconstruct a minimal RAGResult list from the legal_context text
            # by parsing article references. The true list lives upstream of
            # this function; we reconstruct a compat shim.
            from app.services.rag_grounding import extract_article_numbers
            allowed = extract_article_numbers(rag_result.legal_context)
            if allowed:
                from app.services.rag_legal import RAGResult
                _mock_retrieved = [RAGResult(
                    chunk_id=uuid.uuid4(),
                    category="law",
                    fact_text=rag_result.legal_context[:200],
                    law_article=f"ст. {n} 127-ФЗ",
                    relevance_score=0.8,
                ) for n in allowed]
                check = check_citations(result.content, _mock_retrieved)
                if check.status == "hallucinated":
                    logger.warning(
                        "Coach hallucinated citations for user=%s: cited=%s allowed=%s",
                        user_id, check.cited_articles, check.allowed_articles,
                    )
                    result.content = annotate_answer(result.content, check)
    except Exception as _e:
        logger.debug("Citation check failed (non-blocking): %s", _e)

    # 4b. Knowledge compounding: save novel cross-page insights back to wiki
    try:
        if rag_ctx and rag_result and hasattr(rag_result, "wiki_pages") and len(rag_result.wiki_pages or []) >= 2:
            from app.services.rag_wiki import compound_knowledge
            import asyncio
            _source_pages = [p.get("page_path", "") for p in (rag_result.wiki_pages or [])]
            asyncio.create_task(compound_knowledge(
                manager_id=user_id,
                query=message,
                synthesis=result.content,
                source_pages=_source_pages,
                db=db,
            ))
    except Exception:
        pass  # compounding is non-critical fire-and-forget

    # 5. Detect action suggestions
    action = None
    action_data = None
    text_lower = result.content.lower()
    if any(kw in text_lower for kw in ["потренируй", "тренировк", "попробуй сценарий", "рекомендую сценарий"]):
        action = "start_training"
    elif any(kw in text_lower for kw in ["квиз", "проверь знания", "тест", "мини-квиз"]):
        action = "start_quiz"
    elif any(kw in text_lower for kw in ["повтор", "replay", "пересмотр"]):
        action = "show_replay"

    return CoachResponse(
        text=result.content,
        action=action,
        action_data=action_data,
    )


async def get_proactive_tip(user_id: uuid.UUID, db: AsyncSession) -> str | None:
    """Generate proactive tip after session. Returns personalized tip or None."""

    # Check last completed session
    last_session = await db.execute(
        select(TrainingSession)
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
        )
        .order_by(desc(TrainingSession.ended_at))
        .limit(1)
    )
    session = last_session.scalar_one_or_none()

    if not session:
        return "Привет! Ты ещё не проходил тренировки. Давай начнём с простого сценария — cold_ad, сложность 4?"

    # Recent stats (last 5 sessions)
    recent = await db.execute(
        select(
            func.count().label("cnt"),
            func.avg(TrainingSession.score_total).label("avg"),
        )
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
        )
        .order_by(desc(TrainingSession.ended_at))
        .limit(5)
    )
    row = recent.one_or_none()
    count = row.cnt if row else 0
    avg_score = row.avg if row else 0

    # Personalized tips based on last session score
    score = session.score_total or 0
    date_str = session.ended_at.strftime("%d.%m") if session.ended_at else "недавно"

    if score >= 85:
        return f"Отличная сессия {date_str} — {int(score)} баллов! Ты готов к более сложным сценариям. Попробуй crisis или special?"

    if score >= 60:
        # Check for specific weakness
        patterns = await db.execute(
            select(ManagerPattern.pattern_code, ManagerPattern.description)
            .where(
                ManagerPattern.manager_id == user_id,
                ManagerPattern.category == "weakness",
            )
            .order_by(ManagerPattern.sessions_in_pattern.desc())
            .limit(1)
        )
        weakness = patterns.first()
        if weakness:
            return (
                f"Сессия {date_str}: {int(score)} баллов — неплохо! "
                f"Но я заметил паттерн: {weakness.description}. "
                f"Хочешь поработать над этим? Могу подобрать сценарий."
            )
        return f"Сессия {date_str}: {int(score)} баллов. Средний уровень за последние сессии — {int(avg_score or 0)}. Давай поднимем до 80+?"

    # Low score — encouraging but honest
    if count >= 3 and avg_score and avg_score < 50:
        return (
            f"Сессия {date_str}: {int(score)} баллов. Средний за последние — {int(avg_score)}. "
            f"Не расстраивайся — давай разберём что именно не работает? Напиши мне."
        )

    return f"Сессия {date_str}: {int(score)} баллов. Каждая тренировка делает тебя лучше. Хочешь разбор?"


async def _get_recent_sessions(user_id: uuid.UUID, db: AsyncSession) -> str:
    """Get last 5 sessions with dates, scores, and scenarios for Coach context."""
    result = await db.execute(
        select(
            TrainingSession.started_at,
            TrainingSession.score_total,
            TrainingSession.custom_params,
            TrainingSession.feedback_text,
        )
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
        )
        .order_by(desc(TrainingSession.ended_at))
        .limit(5)
    )
    sessions = result.all()

    if not sessions:
        return "Менеджер ещё не проходил тренировки."

    lines = []
    for s in sessions:
        date_str = s.started_at.strftime("%d.%m.%Y") if s.started_at else "?"
        score = int(s.score_total or 0)
        # Extract archetype from custom_params if available
        archetype = ""
        if s.custom_params and isinstance(s.custom_params, dict):
            archetype = s.custom_params.get("archetype_code", s.custom_params.get("archetype", ""))
        feedback_short = ""
        if s.feedback_text:
            feedback_short = s.feedback_text[:100] + "..." if len(s.feedback_text) > 100 else s.feedback_text
        line = f"- {date_str}: {score}/100"
        if archetype:
            line += f" (архетип: {archetype})"
        if feedback_short:
            line += f" — {feedback_short}"
        lines.append(line)

    return "\n".join(lines)


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

    # Patterns (weaknesses and strengths)
    patterns = await db.execute(
        select(ManagerPattern.pattern_code, ManagerPattern.category, ManagerPattern.description)
        .where(ManagerPattern.manager_id == user_id)
        .order_by(ManagerPattern.sessions_in_pattern.desc())
        .limit(5)
    )
    for p in patterns:
        lines.append(f"- Паттерн [{p.category}]: {p.description}")

    # Techniques with success rates
    techniques = await db.execute(
        select(ManagerTechnique.technique_name, ManagerTechnique.success_rate)
        .where(ManagerTechnique.manager_id == user_id)
        .order_by(ManagerTechnique.success_rate.desc())
        .limit(3)
    )
    for t in techniques:
        lines.append(f"- Техника: {t.technique_name} (успешность {int(t.success_rate * 100)}%)")

    return "\n".join(lines) if lines else "Нет данных — менеджер новый."
