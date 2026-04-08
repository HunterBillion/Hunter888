"""Post-session wiki ingest — extracts knowledge from completed training sessions.

Karpathy LLM Wiki pattern: after each training session, the LLM analyzes the
transcript, discovers patterns/techniques, and updates the manager's personal wiki.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.manager_wiki import (
    ManagerPattern,
    ManagerTechnique,
    ManagerWiki,
    PatternCategory,
    WikiAction,
    WikiPage,
    WikiPageType,
    WikiUpdateLog,
)
from app.models.training import Message, TrainingSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_transcript(messages: list[Message], max_chars: int = 3000) -> str:
    """Format message list into a readable transcript, truncated to max_chars."""
    parts = []
    for msg in messages:
        role_label = "Менеджер" if msg.role.value == "user" else "Клиент"
        parts.append(f"{role_label}: {msg.content}")
    transcript = "\n".join(parts)
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "\n[...транскрипт сокращён]"
    return transcript


def _parse_json_safe(text: str) -> dict | None:
    """Extract JSON from LLM response, handling markdown code fences."""
    if not text:
        return None
    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
        cleaned = cleaned[first_newline + 1 :]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse wiki ingest LLM response as JSON")
        return None


async def _get_existing_pages_summary(
    wiki_id: uuid.UUID, db: AsyncSession
) -> str:
    """Build a brief summary of existing wiki pages for LLM context."""
    result = await db.execute(
        select(WikiPage.page_path, WikiPage.page_type)
        .where(WikiPage.wiki_id == wiki_id)
        .order_by(WikiPage.page_path)
    )
    pages = result.all()
    if not pages:
        return "Wiki пуста — это первая сессия."
    lines = [f"- {p.page_path} ({p.page_type})" for p in pages]
    return "\n".join(lines)


async def _get_or_create_wiki(
    manager_id: uuid.UUID, db: AsyncSession
) -> ManagerWiki:
    """Get existing wiki for manager or create a new one."""
    result = await db.execute(
        select(ManagerWiki).where(ManagerWiki.manager_id == manager_id)
    )
    wiki = result.scalar_one_or_none()
    if wiki:
        return wiki
    wiki = ManagerWiki(manager_id=manager_id)
    db.add(wiki)
    await db.flush()
    return wiki


async def _upsert_wiki_page(
    wiki_id: uuid.UUID,
    page_path: str,
    content: str,
    page_type: WikiPageType,
    session_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[bool, WikiPage]:
    """Create or update a wiki page. Returns (is_new, page)."""
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
        # Append session to source list
        sources = list(page.source_sessions or [])
        sid = str(session_id)
        if sid not in sources:
            sources.append(sid)
        page.source_sessions = sources
        return False, page
    else:
        page = WikiPage(
            wiki_id=wiki_id,
            page_path=page_path,
            content=content,
            page_type=page_type,
            source_sessions=[str(session_id)],
        )
        db.add(page)
        return True, page


async def _upsert_pattern(
    manager_id: uuid.UUID,
    pattern_code: str,
    category: PatternCategory,
    description: str,
    db: AsyncSession,
) -> ManagerPattern:
    """Create or update a manager pattern."""
    result = await db.execute(
        select(ManagerPattern).where(
            ManagerPattern.manager_id == manager_id,
            ManagerPattern.pattern_code == pattern_code,
        )
    )
    pattern = result.scalar_one_or_none()
    if pattern:
        pattern.sessions_in_pattern += 1
        pattern.description = description
        # Confirm after 3 sightings
        if pattern.sessions_in_pattern >= 3 and not pattern.confirmed_at:
            pattern.confirmed_at = datetime.now(timezone.utc)
        return pattern
    pattern = ManagerPattern(
        manager_id=manager_id,
        pattern_code=pattern_code,
        category=category,
        description=description,
        sessions_in_pattern=1,
    )
    db.add(pattern)
    return pattern


async def _upsert_technique(
    manager_id: uuid.UUID,
    technique_code: str,
    technique_name: str,
    description: str,
    db: AsyncSession,
) -> ManagerTechnique:
    """Create or update a manager technique."""
    result = await db.execute(
        select(ManagerTechnique).where(
            ManagerTechnique.manager_id == manager_id,
            ManagerTechnique.technique_code == technique_code,
        )
    )
    tech = result.scalar_one_or_none()
    if tech:
        tech.attempt_count += 1
        tech.success_count += 1
        tech.success_rate = tech.success_count / max(tech.attempt_count, 1)
        tech.description = description
        return tech
    tech = ManagerTechnique(
        manager_id=manager_id,
        technique_code=technique_code,
        technique_name=technique_name,
        description=description,
        attempt_count=1,
        success_count=1,
        success_rate=1.0,
    )
    db.add(tech)
    return tech


# ---------------------------------------------------------------------------
# Main ingest function
# ---------------------------------------------------------------------------


async def ingest_session(session_id: uuid.UUID, db: AsyncSession) -> dict:
    """Called after training session completes. Analyzes transcript and updates wiki.

    Returns:
        dict with status and counts of updates made.
    """
    # 1. Load session
    session = await db.get(TrainingSession, session_id)
    if not session:
        logger.warning("Wiki ingest: session %s not found", session_id)
        return {"status": "error", "reason": "session_not_found"}

    # 2. Load messages
    msg_result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.sequence_number)
    )
    messages = msg_result.scalars().all()
    if not messages:
        logger.info("Wiki ingest: no messages for session %s, skipping", session_id)
        return {"status": "skipped", "reason": "no_messages"}

    # 3. Get or create wiki
    wiki = await _get_or_create_wiki(session.user_id, db)

    # 4. Build context
    transcript = _format_transcript(messages)
    existing_pages_summary = await _get_existing_pages_summary(wiki.id, db)

    custom_params = session.custom_params or {}
    metadata = {
        "session_id": str(session_id),
        "archetype": custom_params.get("archetype", "unknown"),
        "scenario": custom_params.get("scenario_type", "unknown"),
        "score_total": session.score_total,
        "duration_seconds": session.duration_seconds,
    }

    # 5. Call LLM to analyze session
    analysis_prompt = (
        "Ты - AI-аналитик менеджера по продажам банкротства. "
        "Проанализируй тренировочную сессию и обнови wiki менеджера.\n\n"
        f"ТРАНСКРИПТ:\n{transcript}\n\n"
        f"МЕТАДАННЫЕ:\n{json.dumps(metadata, ensure_ascii=False)}\n\n"
        f"ТЕКУЩИЕ СТРАНИЦЫ WIKI:\n{existing_pages_summary}\n\n"
        "Ответь СТРОГО в формате JSON (без markdown, без пояснений):\n"
        "{\n"
        '  "session_summary": "1-2 предложения о сессии",\n'
        '  "patterns_found": [{"code": "код_паттерна", "category": "weakness|strength|quirk|misconception", "description": "описание"}],\n'
        '  "techniques_used": [{"code": "код_техники", "name": "название", "description": "описание"}],\n'
        '  "weakness_update": "обновление матрицы слабостей или null",\n'
        '  "recommendation": "рекомендация для следующей тренировки"\n'
        "}"
    )

    # Create log entry
    log = WikiUpdateLog(
        wiki_id=wiki.id,
        action=WikiAction.ingest_session,
        triggered_by_session_id=session_id,
        status="running",
    )
    db.add(log)
    await db.flush()

    analysis = None
    pages_created = 0
    pages_modified = 0
    patterns_found = []

    try:
        from app.services.llm import generate_response

        llm_response = await generate_response(
            system_prompt="Ты аналитик обучения менеджеров. Отвечай только валидным JSON.",
            messages=[{"role": "user", "content": analysis_prompt}],
            emotion_state="cold",
            user_id=f"wiki:{session.user_id}",
            task_type="structured",
            prefer_provider="local",
        )
        analysis = _parse_json_safe(llm_response.content)
        log.tokens_used = llm_response.latency_ms or 0  # approximate tracking

    except Exception as e:
        logger.warning(
            "Wiki ingest LLM call failed for session %s: %s", session_id, e
        )
        log.status = "error"
        log.error_msg = str(e)[:500]
        log.completed_at = datetime.now(timezone.utc)
        wiki.sessions_ingested += 1
        wiki.last_ingest_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "llm_error", "error": str(e)[:200]}

    if not analysis:
        log.status = "error"
        log.error_msg = "Failed to parse LLM JSON response"
        log.completed_at = datetime.now(timezone.utc)
        wiki.sessions_ingested += 1
        wiki.last_ingest_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "parse_error"}

    # 6. Update wiki pages from analysis

    # Overview page
    summary = analysis.get("session_summary", "")
    if summary:
        overview_content = (
            f"## Обзор менеджера\n\n"
            f"Сессий пройдено: {wiki.sessions_ingested + 1}\n"
            f"Паттернов обнаружено: {wiki.patterns_discovered}\n\n"
            f"### Последняя сессия\n{summary}\n"
            f"Балл: {session.score_total or 'N/A'}"
        )
        is_new, _ = await _upsert_wiki_page(
            wiki.id, "overview", overview_content, WikiPageType.overview, session_id, db
        )
        if is_new:
            pages_created += 1
        else:
            pages_modified += 1

    # Patterns — discover and notify ROP
    for p in analysis.get("patterns_found", []):
        if not isinstance(p, dict) or not p.get("code"):
            continue
        cat_str = p.get("category", "weakness")
        try:
            cat = PatternCategory(cat_str)
        except ValueError:
            cat = PatternCategory.weakness
        pattern_obj = await _upsert_pattern(
            session.user_id, p["code"], cat, p.get("description", ""), db
        )
        patterns_found.append(p)

        # Notify ROP about new/confirmed patterns (fire-and-forget)
        try:
            from app.services.wiki_notifications import notify_rop_about_pattern
            from app.models.user import User as _User
            mgr = await db.get(_User, session.user_id)
            mgr_name = mgr.full_name if mgr else "Unknown"
            await notify_rop_about_pattern(
                manager_id=session.user_id,
                manager_name=mgr_name,
                pattern_code=p["code"],
                category=cat_str,
                description=p.get("description", ""),
                sessions_count=pattern_obj.sessions_in_pattern,
                db=db,
            )
        except Exception as notif_err:
            logger.debug("Pattern notification failed (non-blocking): %s", notif_err)

    # Weakness matrix page
    weakness_update = analysis.get("weakness_update")
    if weakness_update and weakness_update != "null":
        is_new, _ = await _upsert_wiki_page(
            wiki.id,
            "patterns/WEAKNESS_MATRIX",
            f"## Матрица слабостей\n\n{weakness_update}",
            WikiPageType.pattern,
            session_id,
            db,
        )
        if is_new:
            pages_created += 1
        else:
            pages_modified += 1

    # Techniques
    for t in analysis.get("techniques_used", []):
        if not isinstance(t, dict) or not t.get("code"):
            continue
        await _upsert_technique(
            session.user_id,
            t["code"],
            t.get("name", t["code"]),
            t.get("description", ""),
            db,
        )

    # Recommendation page
    recommendation = analysis.get("recommendation")
    if recommendation:
        is_new, _ = await _upsert_wiki_page(
            wiki.id,
            "recommendations/next_scenarios",
            f"## Рекомендации\n\n{recommendation}",
            WikiPageType.recommendation,
            session_id,
            db,
        )
        if is_new:
            pages_created += 1
        else:
            pages_modified += 1

    # Session log page (append-only)
    session_log_content = (
        f"### Сессия {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n"
        f"- Архетип: {metadata['archetype']}\n"
        f"- Балл: {session.score_total or 'N/A'}\n"
        f"- Резюме: {summary}\n"
    )
    result = await db.execute(
        select(WikiPage).where(
            WikiPage.wiki_id == wiki.id,
            WikiPage.page_path == "log/sessions",
        )
    )
    existing_log_page = result.scalar_one_or_none()
    if existing_log_page:
        existing_log_page.content = (
            existing_log_page.content + "\n\n" + session_log_content
        )
        existing_log_page.version += 1
        existing_log_page.updated_at = datetime.now(timezone.utc)
        pages_modified += 1
    else:
        log_page = WikiPage(
            wiki_id=wiki.id,
            page_path="log/sessions",
            content=f"## Журнал сессий\n\n{session_log_content}",
            page_type=WikiPageType.log,
            source_sessions=[str(session_id)],
        )
        db.add(log_page)
        pages_created += 1

    # 7. Finalize log entry
    log.pages_created = pages_created
    log.pages_modified = pages_modified
    log.patterns_discovered = patterns_found
    log.status = "completed"
    log.completed_at = datetime.now(timezone.utc)

    # 8. Update wiki metadata
    wiki.sessions_ingested += 1
    wiki.last_ingest_at = datetime.now(timezone.utc)
    wiki.pages_count = wiki.pages_count + pages_created
    wiki.patterns_discovered = wiki.patterns_discovered + len(patterns_found)

    await db.commit()

    logger.info(
        "Wiki ingest completed: session=%s pages_created=%d pages_modified=%d patterns=%d",
        session_id,
        pages_created,
        pages_modified,
        len(patterns_found),
    )

    return {
        "status": "ingested",
        "pages_created": pages_created,
        "pages_modified": pages_modified,
        "patterns_found": len(patterns_found),
    }
