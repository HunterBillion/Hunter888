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


def _format_transcript(messages: list[Message], max_chars: int = 6000) -> str:
    """Format message list into a readable transcript.

    Uses smart truncation: keeps the first 40% and last 40% of the conversation,
    cutting the middle. This preserves the opening (rapport, needs discovery) and
    the closing (objection handling, deal closure) — the two most analytically
    valuable parts of a sales call.
    """
    parts = []
    for msg in messages:
        role_label = "Менеджер" if msg.role.value == "user" else "Клиент"
        parts.append(f"{role_label}: {msg.content}")
    transcript = "\n".join(parts)
    if len(transcript) <= max_chars:
        return transcript
    # Smart truncation: keep start + end, cut middle
    head_budget = int(max_chars * 0.4)
    tail_budget = int(max_chars * 0.4)
    head = transcript[:head_budget]
    tail = transcript[-tail_budget:]
    omitted = len(transcript) - head_budget - tail_budget
    return (
        head
        + f"\n\n[...пропущено ~{omitted} символов середины диалога...]\n\n"
        + tail
    )


def _parse_json_safe(text: str) -> dict | None:
    """Extract JSON from LLM response, handling markdown code fences.

    NOTE: Shared implementation. wiki_synthesis_service.py imports this.
    """
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
        cleaned = cleaned[first_newline + 1 :]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse LLM response as JSON: %s", cleaned[:100])
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
    is_new = False
    if page:
        page.content = content
        page.version += 1
        page.updated_at = datetime.now(timezone.utc)
        sources = list(page.source_sessions or [])
        sid = str(session_id)
        if sid not in sources:
            sources.append(sid)
        page.source_sessions = sources
    else:
        page = WikiPage(
            wiki_id=wiki_id,
            page_path=page_path,
            content=content,
            page_type=page_type,
            source_sessions=[str(session_id)],
        )
        db.add(page)
        is_new = True

    # Phase 2: Generate embedding for semantic wiki search
    try:
        from app.services.rag_wiki import generate_wiki_embedding
        await generate_wiki_embedding(page, db)
    except Exception:
        pass  # Non-critical — page still usable without embedding

    return is_new, page


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
        '  "best_practices": [],\n'
        '  "weakness_update": "обновление матрицы слабостей или null",\n'
        '  "recommendation": "рекомендация для следующей тренировки"\n'
        "}\n\n"
        "ВАЖНО: Если общий балл >= 85, ОБЯЗАТЕЛЬНО заполни best_practices:\n"
        '[{"phrase": "точная фраза менеджера", "context": "что сказал клиент до", "effect": "реакция клиента после", "skill": "empathy|objection_handling|closing|..."}]\n'
        "Извлекай фразы, которые вызвали положительную реакцию клиента."
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
        log.tokens_used = (llm_response.input_tokens or 0) + (llm_response.output_tokens or 0)

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

    # Best practices (Phase 2: extracted when score >= 85)
    best_practices = analysis.get("best_practices", [])
    if best_practices and isinstance(best_practices, list):
        bp_content = "## Best Practices\n\n"
        for bp in best_practices:
            if not isinstance(bp, dict):
                continue
            bp_content += f"**Фраза:** {bp.get('phrase', '')}\n"
            bp_content += f"- Контекст: {bp.get('context', '')}\n"
            bp_content += f"- Эффект: {bp.get('effect', '')}\n"
            bp_content += f"- Навык: {bp.get('skill', '')}\n\n"
        if len(best_practices) > 0:
            is_new, _ = await _upsert_wiki_page(
                wiki.id,
                "practices/best_phrases",
                bp_content,
                WikiPageType.insight,
                session_id,
                db,
            )
            if is_new:
                pages_created += 1
            else:
                pages_modified += 1

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
        # Rotate: keep only the last 50 session entries to prevent unbounded growth
        _LOG_MAX_ENTRIES = 50
        _entries = existing_log_page.content.split("\n\n### Сессия ")
        if len(_entries) > _LOG_MAX_ENTRIES + 1:  # +1 for the header before first entry
            _header = _entries[0]  # "## Журнал сессий" header
            _kept = _entries[-_LOG_MAX_ENTRIES:]
            existing_log_page.content = _header + "\n\n### Сессия " + "\n\n### Сессия ".join(_kept)
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

    # 6b. Rebuild index page (auto-generated table of contents)
    await _rebuild_index_page(wiki, db)

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


# ---------------------------------------------------------------------------
# Auto-generated index page
# ---------------------------------------------------------------------------


async def _rebuild_index_page(wiki: ManagerWiki, db: AsyncSession) -> None:
    """Rebuild the wiki index page — a table of contents for the AI Coach.

    Inspired by Karpathy's LLM Wiki pattern: the index gives the AI a fast
    map of available knowledge before deciding what to load.
    """
    pages_result = await db.execute(
        select(WikiPage)
        .where(WikiPage.wiki_id == wiki.id)
        .order_by(WikiPage.page_type, WikiPage.page_path)
    )
    all_pages = list(pages_result.scalars().all())

    # Group by type
    by_type: dict[str, list] = {}
    for p in all_pages:
        if p.page_path.startswith("lint/") or p.page_path == "index":
            continue
        ptype = p.page_type or "other"
        by_type.setdefault(ptype, []).append(p)

    # Build cross-reference map (pages sharing source sessions)
    cross_refs: dict[str, list[str]] = {}
    for p in all_pages:
        if not p.source_sessions:
            continue
        sessions_set = set(p.source_sessions)
        for q in all_pages:
            if q.id == p.id or not q.source_sessions:
                continue
            if sessions_set & set(q.source_sessions):
                cross_refs.setdefault(p.page_path, [])
                if q.page_path not in cross_refs[p.page_path]:
                    cross_refs[p.page_path].append(q.page_path)

    # Build markdown
    lines = [
        "# Wiki Index",
        "",
        f"**Всего страниц:** {len(all_pages)}  ",
        f"**Последнее обновление:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    type_labels = {
        "overview": "Обзор",
        "pattern": "Паттерны",
        "insight": "Инсайты и лучшие практики",
        "recommendation": "Рекомендации",
        "benchmark": "Бенчмарки и отчёты",
        "log": "Журналы",
    }

    for ptype, pages_list in sorted(by_type.items()):
        label = type_labels.get(ptype, ptype.capitalize())
        lines.append(f"## {label} ({len(pages_list)})")
        lines.append("")
        for p in pages_list:
            updated = p.updated_at.strftime("%d.%m") if p.updated_at else "?"
            sources = len(p.source_sessions or [])
            refs = cross_refs.get(p.page_path, [])
            ref_str = f" | ссылки: {', '.join(refs[:3])}" if refs else ""
            lines.append(f"- **{p.page_path}** (v{p.version}, {updated}, {sources} сессий{ref_str})")
        lines.append("")

    if cross_refs:
        lines.append("## Перекрёстные ссылки")
        lines.append("")
        for page_path, refs in sorted(cross_refs.items()):
            if len(refs) > 0:
                lines.append(f"- {page_path} → {', '.join(refs[:5])}")
        lines.append("")

    content = "\n".join(lines)

    # Upsert
    existing = await db.execute(
        select(WikiPage).where(
            WikiPage.wiki_id == wiki.id,
            WikiPage.page_path == "index",
        )
    )
    index_page = existing.scalar_one_or_none()
    if index_page:
        index_page.content = content
        index_page.version += 1
        index_page.updated_at = datetime.now(timezone.utc)
    else:
        index_page = WikiPage(
            wiki_id=wiki.id,
            page_path="index",
            content=content,
            page_type=WikiPageType.overview.value,
            tags=["index", "auto-generated"],
        )
        db.add(index_page)
