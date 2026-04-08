"""Wiki synthesis service — daily and weekly LLM-powered summaries.

Daily synthesis: summarizes today's sessions for each manager.
Weekly synthesis: broader trends, cross-session analysis, updated recommendations.

Both use the LLM via generate_response() and update wiki pages + audit log.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.manager_wiki import (
    ManagerWiki,
    WikiAction,
    WikiPage,
    WikiPageType,
    WikiUpdateLog,
)
from app.models.training import Message, SessionStatus, TrainingSession

logger = logging.getLogger(__name__)


def _parse_json_safe(text: str) -> dict | None:
    """Extract JSON from LLM response, handling markdown code fences."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
        cleaned = cleaned[first_newline + 1:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse synthesis LLM response as JSON")
        return None


async def _get_recent_sessions_summary(
    manager_id: uuid.UUID,
    since: datetime,
    db: AsyncSession,
) -> list[dict]:
    """Get summaries of sessions completed since a given time."""
    result = await db.execute(
        select(TrainingSession)
        .where(
            TrainingSession.user_id == manager_id,
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= since,
        )
        .order_by(TrainingSession.started_at)
    )
    sessions = result.scalars().all()

    summaries = []
    for s in sessions:
        params = s.custom_params or {}
        summaries.append({
            "id": str(s.id),
            "archetype": params.get("archetype", "unknown"),
            "scenario": params.get("scenario_type", "unknown"),
            "score": s.score_total,
            "duration_sec": s.duration_seconds,
            "started_at": s.started_at.isoformat() if s.started_at else None,
        })
    return summaries


async def _get_existing_pages_content(
    wiki_id: uuid.UUID,
    db: AsyncSession,
    max_chars: int = 3000,
) -> str:
    """Get brief content of existing wiki pages for LLM context."""
    result = await db.execute(
        select(WikiPage.page_path, WikiPage.content)
        .where(WikiPage.wiki_id == wiki_id)
        .order_by(WikiPage.page_path)
    )
    pages = result.all()
    if not pages:
        return "Wiki is empty."

    parts = []
    total = 0
    for p in pages:
        preview = (p.content or "")[:400]
        chunk = f"--- {p.page_path} ---\n{preview}\n"
        if total + len(chunk) > max_chars:
            break
        parts.append(chunk)
        total += len(chunk)
    return "\n".join(parts)


async def _upsert_synthesis_page(
    wiki_id: uuid.UUID,
    page_path: str,
    content: str,
    page_type: WikiPageType,
    db: AsyncSession,
) -> tuple[bool, WikiPage]:
    """Create or update a synthesis wiki page."""
    result = await db.execute(
        select(WikiPage).where(
            WikiPage.wiki_id == wiki_id,
            WikiPage.page_path == page_path,
        )
    )
    page = result.scalar_one_or_none()
    if page:
        page.content = content
        page.version += 1
        page.updated_at = datetime.now(timezone.utc)
        return False, page
    else:
        page = WikiPage(
            wiki_id=wiki_id,
            page_path=page_path,
            content=content,
            page_type=page_type,
            source_sessions=[],
        )
        db.add(page)
        return True, page


# ---------------------------------------------------------------------------
# Daily synthesis
# ---------------------------------------------------------------------------


async def _daily_synthesis_for_manager(
    wiki: ManagerWiki,
    db: AsyncSession,
) -> dict:
    """Run daily synthesis for one manager."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    sessions = await _get_recent_sessions_summary(wiki.manager_id, since, db)
    if not sessions:
        return {"manager_id": str(wiki.manager_id), "status": "skipped", "reason": "no_sessions_today"}

    existing_content = await _get_existing_pages_content(wiki.id, db)

    prompt = (
        "Ты — AI-аналитик менеджера по банкротству.\n"
        "Создай КРАТКОЕ дневное резюме на основе сессий за последние 24 часа.\n\n"
        f"СЕССИИ ЗА СЕГОДНЯ ({len(sessions)} шт.):\n"
        f"{json.dumps(sessions, ensure_ascii=False, indent=2)}\n\n"
        f"ТЕКУЩИЕ СТРАНИЦЫ WIKI (контекст):\n{existing_content}\n\n"
        "Ответь СТРОГО JSON:\n"
        "{\n"
        '  "daily_summary": "2-4 предложения: что менеджер делал сегодня, основные наблюдения",\n'
        '  "score_trend": "improving|stable|declining",\n'
        '  "key_insight": "одно самое важное наблюдение за день",\n'
        '  "recommendation": "рекомендация на завтра"\n'
        "}"
    )

    # Create log
    log = WikiUpdateLog(
        wiki_id=wiki.id,
        action=WikiAction.daily_synthesis,
        status="running",
    )
    db.add(log)
    await db.flush()

    pages_created = 0
    pages_modified = 0

    try:
        from app.services.llm import generate_response

        resp = await generate_response(
            system_prompt="Ты аналитик обучения. Отвечай только валидным JSON.",
            messages=[{"role": "user", "content": prompt}],
            emotion_state="cold",
            user_id=f"wiki:daily:{wiki.manager_id}",
        )
        analysis = _parse_json_safe(resp.content)
        log.tokens_used = resp.latency_ms or 0

        if not analysis:
            log.status = "error"
            log.error_msg = "Failed to parse LLM JSON"
            log.completed_at = now
            await db.commit()
            return {"manager_id": str(wiki.manager_id), "status": "parse_error"}

        # Upsert daily summary page
        date_str = now.strftime("%Y-%m-%d")
        content = (
            f"## Дневное резюме — {date_str}\n\n"
            f"**Сессий:** {len(sessions)}\n"
            f"**Тренд:** {analysis.get('score_trend', 'stable')}\n\n"
            f"### Итоги дня\n{analysis.get('daily_summary', '')}\n\n"
            f"### Ключевой инсайт\n{analysis.get('key_insight', '')}\n\n"
            f"### Рекомендация на завтра\n{analysis.get('recommendation', '')}\n"
        )

        is_new, _ = await _upsert_synthesis_page(
            wiki.id, f"synthesis/daily/{date_str}", content, WikiPageType.insight, db
        )
        if is_new:
            pages_created += 1
        else:
            pages_modified += 1

        # Also update latest daily pointer
        is_new2, _ = await _upsert_synthesis_page(
            wiki.id, "synthesis/daily_latest", content, WikiPageType.insight, db
        )
        if is_new2:
            pages_created += 1
        else:
            pages_modified += 1

        log.pages_created = pages_created
        log.pages_modified = pages_modified
        log.status = "completed"
        log.completed_at = datetime.now(timezone.utc)
        log.description = f"Daily synthesis: {len(sessions)} sessions, trend={analysis.get('score_trend', 'unknown')}"

        wiki.last_daily_synthesis_at = now
        await db.commit()

        return {
            "manager_id": str(wiki.manager_id),
            "status": "completed",
            "sessions_analyzed": len(sessions),
            "pages_created": pages_created,
            "pages_modified": pages_modified,
        }

    except Exception as e:
        logger.warning("Daily synthesis failed for manager %s: %s", wiki.manager_id, e)
        log.status = "error"
        log.error_msg = str(e)[:500]
        log.completed_at = datetime.now(timezone.utc)
        await db.commit()
        return {"manager_id": str(wiki.manager_id), "status": "error", "error": str(e)[:200]}


async def run_daily_synthesis(
    db: AsyncSession,
    manager_id: uuid.UUID | None = None,
) -> dict:
    """Run daily synthesis for one or all managers."""
    if manager_id:
        wiki_r = await db.execute(
            select(ManagerWiki).where(ManagerWiki.manager_id == manager_id)
        )
        wiki = wiki_r.scalar_one_or_none()
        if not wiki:
            return {"status": "error", "reason": "wiki_not_found"}
        result = await _daily_synthesis_for_manager(wiki, db)
        return {"status": "completed", "results": [result]}

    # All active wikis
    wikis_r = await db.execute(
        select(ManagerWiki)
    )
    wikis = wikis_r.scalars().all()

    results = []
    for wiki in wikis:
        r = await _daily_synthesis_for_manager(wiki, db)
        results.append(r)

    return {
        "status": "completed",
        "total_wikis": len(wikis),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Weekly synthesis
# ---------------------------------------------------------------------------


async def _weekly_synthesis_for_manager(
    wiki: ManagerWiki,
    db: AsyncSession,
) -> dict:
    """Run weekly synthesis for one manager."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=7)

    sessions = await _get_recent_sessions_summary(wiki.manager_id, since, db)
    if not sessions:
        return {"manager_id": str(wiki.manager_id), "status": "skipped", "reason": "no_sessions_this_week"}

    existing_content = await _get_existing_pages_content(wiki.id, db, max_chars=4000)

    prompt = (
        "Ты — AI-аналитик менеджера по банкротству.\n"
        "Создай НЕДЕЛЬНОЕ резюме с анализом трендов за 7 дней.\n\n"
        f"СЕССИИ ЗА НЕДЕЛЮ ({len(sessions)} шт.):\n"
        f"{json.dumps(sessions, ensure_ascii=False, indent=2)}\n\n"
        f"ТЕКУЩИЕ СТРАНИЦЫ WIKI:\n{existing_content}\n\n"
        "Ответь СТРОГО JSON:\n"
        "{\n"
        '  "weekly_summary": "4-6 предложений: обзор недели, прогресс, проблемные зоны",\n'
        '  "score_trend": "improving|stable|declining",\n'
        '  "strongest_area": "в чём менеджер лучше всего на этой неделе",\n'
        '  "weakest_area": "главная зона для улучшения",\n'
        '  "progress_vs_last_week": "улучшение/стагнация/ухудшение + пояснение",\n'
        '  "top_3_recommendations": ["рек1", "рек2", "рек3"],\n'
        '  "archetype_mastery": "над какими архетипами стоит поработать"\n'
        "}"
    )

    log = WikiUpdateLog(
        wiki_id=wiki.id,
        action=WikiAction.weekly_synthesis,
        status="running",
    )
    db.add(log)
    await db.flush()

    pages_created = 0
    pages_modified = 0

    try:
        from app.services.llm import generate_response

        resp = await generate_response(
            system_prompt="Ты аналитик обучения. Отвечай только валидным JSON.",
            messages=[{"role": "user", "content": prompt}],
            emotion_state="cold",
            user_id=f"wiki:weekly:{wiki.manager_id}",
        )
        analysis = _parse_json_safe(resp.content)
        log.tokens_used = resp.latency_ms or 0

        if not analysis:
            log.status = "error"
            log.error_msg = "Failed to parse LLM JSON"
            log.completed_at = now
            await db.commit()
            return {"manager_id": str(wiki.manager_id), "status": "parse_error"}

        # Build weekly page
        week_str = now.strftime("%Y-W%V")
        recs = analysis.get("top_3_recommendations", [])
        recs_md = "\n".join(f"- {r}" for r in recs) if recs else "Нет рекомендаций"

        content = (
            f"## Недельное резюме — {week_str}\n\n"
            f"**Сессий за неделю:** {len(sessions)}\n"
            f"**Тренд:** {analysis.get('score_trend', 'stable')}\n\n"
            f"### Обзор недели\n{analysis.get('weekly_summary', '')}\n\n"
            f"### Сильная сторона\n{analysis.get('strongest_area', '')}\n\n"
            f"### Зона роста\n{analysis.get('weakest_area', '')}\n\n"
            f"### Прогресс\n{analysis.get('progress_vs_last_week', '')}\n\n"
            f"### Рекомендации\n{recs_md}\n\n"
            f"### Архетипы для работы\n{analysis.get('archetype_mastery', '')}\n"
        )

        is_new, _ = await _upsert_synthesis_page(
            wiki.id, f"synthesis/weekly/{week_str}", content, WikiPageType.insight, db
        )
        if is_new:
            pages_created += 1
        else:
            pages_modified += 1

        # Update latest weekly pointer
        is_new2, _ = await _upsert_synthesis_page(
            wiki.id, "synthesis/weekly_latest", content, WikiPageType.insight, db
        )
        if is_new2:
            pages_created += 1
        else:
            pages_modified += 1

        log.pages_created = pages_created
        log.pages_modified = pages_modified
        log.status = "completed"
        log.completed_at = datetime.now(timezone.utc)
        log.description = f"Weekly synthesis: {len(sessions)} sessions, trend={analysis.get('score_trend', 'unknown')}"

        wiki.last_weekly_synthesis_at = now
        await db.commit()

        return {
            "manager_id": str(wiki.manager_id),
            "status": "completed",
            "sessions_analyzed": len(sessions),
            "pages_created": pages_created,
            "pages_modified": pages_modified,
        }

    except Exception as e:
        logger.warning("Weekly synthesis failed for manager %s: %s", wiki.manager_id, e)
        log.status = "error"
        log.error_msg = str(e)[:500]
        log.completed_at = datetime.now(timezone.utc)
        await db.commit()
        return {"manager_id": str(wiki.manager_id), "status": "error", "error": str(e)[:200]}


async def run_weekly_synthesis(
    db: AsyncSession,
    manager_id: uuid.UUID | None = None,
) -> dict:
    """Run weekly synthesis for one or all managers."""
    if manager_id:
        wiki_r = await db.execute(
            select(ManagerWiki).where(ManagerWiki.manager_id == manager_id)
        )
        wiki = wiki_r.scalar_one_or_none()
        if not wiki:
            return {"status": "error", "reason": "wiki_not_found"}
        result = await _weekly_synthesis_for_manager(wiki, db)
        return {"status": "completed", "results": [result]}

    wikis_r = await db.execute(
        select(ManagerWiki)
    )
    wikis = wikis_r.scalars().all()

    results = []
    for wiki in wikis:
        r = await _weekly_synthesis_for_manager(wiki, db)
        results.append(r)

    return {
        "status": "completed",
        "total_wikis": len(wikis),
        "results": results,
    }
