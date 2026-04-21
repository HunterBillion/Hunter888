"""Wiki Lint Service — Karpathy-inspired wiki health checks.

Performs automated quality analysis on a manager's wiki:
1. Contradictions: patterns that conflict (e.g., weakness says "avoids price" but strength says "confident pricing")
2. Stale pages: pages not updated in 20+ sessions while related pages changed
3. Orphan pages: pages with no source sessions (except system pages)
4. Missing concepts: techniques referenced in patterns but lacking their own page
5. Confidence scoring: pages with low confidence (few source sessions)
6. Cross-reference suggestions: pages that should link to each other

Results are saved as a WikiPage (lint report) and logged in WikiUpdateLog.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.manager_wiki import (
    ManagerPattern,
    ManagerTechnique,
    ManagerWiki,
    WikiAction,
    WikiPage,
    WikiPageType,
    WikiUpdateLog,
)

logger = logging.getLogger(__name__)


async def run_lint_pass(manager_id: uuid.UUID, db: AsyncSession) -> dict:
    """Run a full lint pass on a manager's wiki. Returns structured report."""

    # Load wiki
    wiki_result = await db.execute(
        select(ManagerWiki).where(ManagerWiki.manager_id == manager_id)
    )
    wiki = wiki_result.scalar_one_or_none()
    if not wiki:
        return {"status": "no_wiki", "issues": []}

    # Create log entry
    log = WikiUpdateLog(
        wiki_id=wiki.id,
        action=WikiAction.lint_pass.value,
        description="Automated wiki health check (Karpathy lint pattern)",
        started_at=datetime.now(timezone.utc),
        status="in_progress",
    )
    db.add(log)
    await db.flush()

    issues: list[dict] = []
    suggestions: list[dict] = []

    # ── 1. Load all wiki data ──
    pages_result = await db.execute(
        select(WikiPage).where(WikiPage.wiki_id == wiki.id)
    )
    pages = list(pages_result.scalars().all())
    page_map = {p.page_path: p for p in pages}

    patterns_result = await db.execute(
        select(ManagerPattern).where(ManagerPattern.manager_id == manager_id)
    )
    patterns = list(patterns_result.scalars().all())

    techniques_result = await db.execute(
        select(ManagerTechnique).where(ManagerTechnique.manager_id == manager_id)
    )
    techniques = list(techniques_result.scalars().all())

    # ── 2. Contradiction detection ──
    weakness_codes = {
        p.pattern_code: p.description
        for p in patterns
        if p.category == "weakness"
    }
    strength_codes = {
        p.pattern_code: p.description
        for p in patterns
        if p.category == "strength"
    }
    # Check for semantically opposing patterns
    _OPPOSITION_PAIRS = [
        ("price", "pricing"),
        ("avoid", "confident"),
        ("rush", "patient"),
        ("skip", "thorough"),
        ("ignore", "attentive"),
        ("fear", "brave"),
        ("passive", "active"),
        ("weak", "strong"),
    ]
    for w_code, w_desc in weakness_codes.items():
        w_words = set((w_code + " " + (w_desc or "")).lower().split())
        for s_code, s_desc in strength_codes.items():
            s_words = set((s_code + " " + (s_desc or "")).lower().split())
            # Check keyword overlap suggesting contradiction
            for neg, pos in _OPPOSITION_PAIRS:
                if neg in w_words and pos in s_words:
                    issues.append({
                        "type": "contradiction",
                        "severity": "high",
                        "title": f"Противоречие: паттерн '{w_code}' vs '{s_code}'",
                        "detail": f"Слабость описывает: {w_desc[:100]}. Сила описывает: {s_desc[:100]}. Ключевые слова '{neg}'/'{pos}' конфликтуют.",
                        "affected_pages": [f"patterns/{w_code}", f"patterns/{s_code}"],
                        "recommendation": "Проверьте, актуальны ли оба паттерна. Возможно, один устарел.",
                    })
            # Also check direct code overlap (e.g., "avoid_price" weakness vs "handle_price" strength)
            common = w_words & s_words - {"the", "a", "и", "в", "на", "по", "не", "с"}
            if len(common) >= 2:
                issues.append({
                    "type": "contradiction",
                    "severity": "medium",
                    "title": f"Возможное противоречие: '{w_code}' и '{s_code}' пересекаются",
                    "detail": f"Общие ключевые слова: {', '.join(sorted(common)[:5])}",
                    "affected_pages": [f"patterns/{w_code}", f"patterns/{s_code}"],
                    "recommendation": "Уточните формулировки паттернов.",
                })

    # ── 3. Stale pages ──
    if wiki.sessions_ingested > 20:
        for page in pages:
            if page.page_type == WikiPageType.log.value:
                continue
            source_count = len(page.source_sessions or [])
            # Page hasn't been updated by recent sessions
            if source_count > 0 and source_count < wiki.sessions_ingested * 0.3:
                sessions_behind = wiki.sessions_ingested - source_count
                if sessions_behind > 15:
                    issues.append({
                        "type": "stale",
                        "severity": "low",
                        "title": f"Устаревшая страница: {page.page_path}",
                        "detail": f"Обновлена {source_count} сессиями из {wiki.sessions_ingested}. Отставание: {sessions_behind} сессий.",
                        "affected_pages": [page.page_path],
                        "recommendation": "Запустите 'Reanalyze' для обновления.",
                    })

    # ── 4. Orphan pages ──
    for page in pages:
        if page.page_type in (WikiPageType.log.value, WikiPageType.overview.value):
            continue  # System pages are OK without sources
        if page.page_path.startswith("synthesis/"):
            continue  # Synthesis pages are auto-generated
        if page.page_path == "index":
            continue
        if not page.source_sessions or len(page.source_sessions) == 0:
            issues.append({
                "type": "orphan",
                "severity": "low",
                "title": f"Осиротевшая страница: {page.page_path}",
                "detail": "Страница не связана ни с одной тренировочной сессией.",
                "affected_pages": [page.page_path],
                "recommendation": "Удалите или привяжите к сессиям через manual edit.",
            })

    # ── 5. Missing concepts ──
    technique_codes = {t.technique_code for t in techniques}
    for pattern in patterns:
        if pattern.mitigation_technique:
            # Check if the mitigation technique exists as a tracked technique
            mit_code = pattern.mitigation_technique.strip()
            if mit_code and mit_code not in technique_codes:
                suggestions.append({
                    "type": "missing_concept",
                    "severity": "medium",
                    "title": f"Техника '{mit_code}' упоминается, но не отслеживается",
                    "detail": f"Паттерн '{pattern.pattern_code}' рекомендует технику '{mit_code}', но она не существует как отдельная техника.",
                    "recommendation": "Добавьте эту технику или исправьте рекомендацию паттерна.",
                })

    # ── 6. Confidence scoring ──
    for page in pages:
        if page.page_type in (WikiPageType.log.value,):
            continue
        source_count = len(page.source_sessions or [])
        if source_count == 0:
            confidence = "none"
        elif source_count <= 2:
            confidence = "low"
        elif source_count <= 5:
            confidence = "medium"
        else:
            confidence = "high"

        if confidence in ("none", "low") and not page.page_path.startswith("synthesis/"):
            suggestions.append({
                "type": "low_confidence",
                "severity": "low" if confidence == "low" else "medium",
                "title": f"Низкая уверенность: {page.page_path}",
                "detail": f"Основана на {source_count} сессии(ях). Нужно больше данных для надёжных выводов.",
                "recommendation": "Проведите больше тренировок для подтверждения.",
            })

    # ── 7. Cross-reference suggestions ──
    for pattern in patterns:
        if not pattern.confirmed_at:
            continue  # Only suggest cross-refs for confirmed patterns
        desc_lower = (pattern.description or "").lower()
        for tech in techniques:
            tech_words = set((tech.technique_name or "").lower().split())
            if tech_words & set(desc_lower.split()) and len(tech_words & set(desc_lower.split())) >= 2:
                suggestions.append({
                    "type": "cross_reference",
                    "severity": "info",
                    "title": f"Связь: паттерн '{pattern.pattern_code}' ↔ техника '{tech.technique_code}'",
                    "detail": f"Паттерн '{pattern.pattern_code}' и техника '{tech.technique_name}' семантически связаны.",
                    "recommendation": "Добавьте перекрёстную ссылку для навигации.",
                })

    # ── 8. Unconfirmed patterns (seen < 3 times) ──
    unconfirmed = [p for p in patterns if not p.confirmed_at and p.sessions_in_pattern >= 2]
    for p in unconfirmed:
        suggestions.append({
            "type": "pending_confirmation",
            "severity": "info",
            "title": f"Паттерн '{p.pattern_code}' близок к подтверждению",
            "detail": f"Обнаружен {p.sessions_in_pattern} раз(а). Нужно 3 для подтверждения.",
            "recommendation": "Ещё 1-2 тренировки для подтверждения.",
        })

    # ── Build report ──
    report = {
        "manager_id": str(manager_id),
        "wiki_id": str(wiki.id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_issues": len(issues),
            "total_suggestions": len(suggestions),
            "contradictions": len([i for i in issues if i["type"] == "contradiction"]),
            "stale_pages": len([i for i in issues if i["type"] == "stale"]),
            "orphan_pages": len([i for i in issues if i["type"] == "orphan"]),
            "low_confidence": len([s for s in suggestions if s["type"] == "low_confidence"]),
            "cross_references": len([s for s in suggestions if s["type"] == "cross_reference"]),
            "missing_concepts": len([s for s in suggestions if s["type"] == "missing_concept"]),
        },
        "health_score": _calculate_health_score(issues, suggestions, len(pages), len(patterns)),
        "issues": issues,
        "suggestions": suggestions,
    }

    # ── Save report as wiki page ──
    report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_content = _build_report_markdown(report)

    # Upsert lint report page
    existing = await db.execute(
        select(WikiPage).where(
            WikiPage.wiki_id == wiki.id,
            WikiPage.page_path == "lint/latest",
        )
    )
    lint_page = existing.scalar_one_or_none()
    if lint_page:
        lint_page.content = report_content
        lint_page.version += 1
        lint_page.updated_at = datetime.now(timezone.utc)
    else:
        lint_page = WikiPage(
            wiki_id=wiki.id,
            page_path="lint/latest",
            content=report_content,
            page_type="benchmark",  # closest existing type
            tags=["lint", "health-check", "automated"],
        )
        db.add(lint_page)

    # Also save dated archive
    archive_existing = await db.execute(
        select(WikiPage).where(
            WikiPage.wiki_id == wiki.id,
            WikiPage.page_path == f"lint/{report_date}",
        )
    )
    if not archive_existing.scalar_one_or_none():
        archive_page = WikiPage(
            wiki_id=wiki.id,
            page_path=f"lint/{report_date}",
            content=report_content,
            page_type="benchmark",
            tags=["lint", "archive", report_date],
        )
        db.add(archive_page)

    # Finalize log
    log.pages_modified = 1
    log.pages_created = 0 if lint_page.id else 1
    log.status = "completed"
    log.completed_at = datetime.now(timezone.utc)
    log.description = (
        f"Lint pass: {report['summary']['total_issues']} issues, "
        f"{report['summary']['total_suggestions']} suggestions, "
        f"health score: {report['health_score']}%"
    )

    await db.commit()
    logger.info(
        "Wiki lint pass for manager %s: %d issues, %d suggestions, health=%d%%",
        manager_id, len(issues), len(suggestions), report["health_score"],
    )
    return report


def _calculate_health_score(
    issues: list[dict],
    suggestions: list[dict],
    total_pages: int,
    total_patterns: int,
) -> int:
    """Calculate wiki health score 0-100."""
    score = 100
    for issue in issues:
        if issue["severity"] == "high":
            score -= 15
        elif issue["severity"] == "medium":
            score -= 8
        elif issue["severity"] == "low":
            score -= 3

    for sug in suggestions:
        if sug["type"] == "missing_concept":
            score -= 5
        elif sug["type"] == "low_confidence" and sug["severity"] == "medium":
            score -= 3

    # Bonus for breadth
    if total_pages >= 5:
        score += 5
    if total_patterns >= 3:
        score += 5

    return max(0, min(100, score))


def _build_report_markdown(report: dict) -> str:
    """Build human-readable markdown from lint report."""
    lines = [
        f"# Wiki Health Report",
        f"",
        f"**Дата:** {report['timestamp'][:10]}",
        f"**Health Score:** {report['health_score']}%",
        f"",
        f"## Сводка",
        f"- Проблем: **{report['summary']['total_issues']}**",
        f"  - Противоречий: {report['summary']['contradictions']}",
        f"  - Устаревших страниц: {report['summary']['stale_pages']}",
        f"  - Осиротевших страниц: {report['summary']['orphan_pages']}",
        f"- Предложений: **{report['summary']['total_suggestions']}**",
        f"  - Низкая уверенность: {report['summary']['low_confidence']}",
        f"  - Перекрёстные ссылки: {report['summary']['cross_references']}",
        f"  - Недостающие концепции: {report['summary']['missing_concepts']}",
        f"",
    ]

    if report["issues"]:
        lines.append("## Проблемы")
        lines.append("")
        for i, issue in enumerate(report["issues"], 1):
            severity_icon = {"high": "!!!", "medium": "!!", "low": "!"}.get(issue["severity"], "")
            lines.append(f"### {i}. [{severity_icon}] {issue['title']}")
            lines.append(f"{issue['detail']}")
            lines.append(f"**Рекомендация:** {issue['recommendation']}")
            lines.append("")

    if report["suggestions"]:
        lines.append("## Предложения")
        lines.append("")
        for i, sug in enumerate(report["suggestions"], 1):
            lines.append(f"### {i}. {sug['title']}")
            lines.append(f"{sug['detail']}")
            lines.append(f"**Рекомендация:** {sug['recommendation']}")
            lines.append("")

    return "\n".join(lines)
