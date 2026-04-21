"""Wiki export service — generates PDF and CSV exports of manager wiki data.

Used by: GET /api/wiki/{manager_id}/export?format=pdf|csv
"""

import csv
import io
import logging
import pathlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.manager_wiki import (
    ManagerPattern,
    ManagerTechnique,
    ManagerWiki,
    WikiPage,
)

logger = logging.getLogger(__name__)

# DejaVu Sans TTF supports Cyrillic, Latin, Greek — no transliteration needed
_FONT_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "data"
_DEJAVU_SANS = str(_FONT_DIR / "DejaVuSans.ttf")


async def _load_wiki_data(wiki_id: uuid.UUID, db: AsyncSession) -> dict:
    """Load all wiki data for export."""
    # Pages
    pages_r = await db.execute(
        select(WikiPage)
        .where(WikiPage.wiki_id == wiki_id)
        .order_by(WikiPage.page_path)
    )
    pages = pages_r.scalars().all()

    # Wiki metadata
    wiki_r = await db.execute(
        select(ManagerWiki).where(ManagerWiki.id == wiki_id)
    )
    wiki = wiki_r.scalar_one()

    # Patterns
    patterns_r = await db.execute(
        select(ManagerPattern)
        .where(ManagerPattern.manager_id == wiki.manager_id)
        .order_by(ManagerPattern.discovered_at.desc())
    )
    patterns = patterns_r.scalars().all()

    # Techniques
    techniques_r = await db.execute(
        select(ManagerTechnique)
        .where(ManagerTechnique.manager_id == wiki.manager_id)
        .order_by(ManagerTechnique.success_rate.desc())
    )
    techniques = techniques_r.scalars().all()

    return {
        "wiki": wiki,
        "pages": pages,
        "patterns": patterns,
        "techniques": techniques,
    }


async def export_wiki_pdf(
    wiki_id: uuid.UUID,
    manager_name: str,
    db: AsyncSession,
) -> bytes:
    """Generate PDF report of manager's wiki. Returns bytes."""
    from fpdf import FPDF

    data = await _load_wiki_data(wiki_id, db)
    wiki = data["wiki"]
    pages = data["pages"]
    patterns = data["patterns"]
    techniques = data["techniques"]

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Register DejaVu Sans — supports Cyrillic, Latin, Greek natively
    # No more transliteration — Russian text renders correctly
    pdf.add_font("DejaVu", "", _DEJAVU_SANS, uni=True)
    pdf.add_font("DejaVu", "B", _DEJAVU_SANS, uni=True)

    pdf.add_page()

    # Title
    pdf.set_font("DejaVu", "B", 16)
    pdf.cell(0, 10, f"Wiki Отчёт: {manager_name}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 10)
    pdf.cell(
        0, 6,
        f"Создан: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.cell(0, 6, f"Сессий проанализировано: {wiki.sessions_ingested}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Паттернов обнаружено: {wiki.patterns_discovered}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Страниц Wiki: {wiki.pages_count}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # --- Pages ---
    if pages:
        pdf.set_font("DejaVu", "B", 14)
        pdf.cell(0, 10, "Страницы Wiki", new_x="LMARGIN", new_y="NEXT")

        for page in pages:
            pdf.set_font("DejaVu", "B", 11)
            pdf.cell(
                0, 8,
                f"{page.page_path} (v{page.version})",
                new_x="LMARGIN", new_y="NEXT",
            )
            pdf.set_font("DejaVu", "", 9)
            content = page.content or ""
            if len(content) > 2000:
                content = content[:2000] + "\n[...сокращено]"
            content = content.replace("##", "").replace("**", "").replace("*", "")
            pdf.multi_cell(0, 5, content)
            pdf.ln(4)

    # --- Patterns ---
    if patterns:
        pdf.add_page()
        pdf.set_font("DejaVu", "B", 14)
        pdf.cell(0, 10, "Поведенческие паттерны", new_x="LMARGIN", new_y="NEXT")

        pdf.set_font("DejaVu", "B", 9)
        col_w = [40, 25, 80, 20, 25]
        headers = ["Код", "Категория", "Описание", "Сессий", "Подтв."]
        for i, h in enumerate(headers):
            pdf.cell(col_w[i], 7, h, border=1)
        pdf.ln()

        pdf.set_font("DejaVu", "", 8)
        for p in patterns:
            pdf.cell(col_w[0], 6, (p.pattern_code or "")[:20], border=1)
            pdf.cell(col_w[1], 6, str(p.category) if p.category else "", border=1)
            pdf.cell(col_w[2], 6, (p.description or "")[:50], border=1)
            pdf.cell(col_w[3], 6, str(p.sessions_in_pattern), border=1, align="C")
            pdf.cell(col_w[4], 6, "Да" if p.confirmed_at else "Нет", border=1, align="C")
            pdf.ln()

    # --- Techniques ---
    if techniques:
        pdf.ln(6)
        pdf.set_font("DejaVu", "B", 14)
        pdf.cell(0, 10, "Эффективные техники", new_x="LMARGIN", new_y="NEXT")

        pdf.set_font("DejaVu", "B", 9)
        col_w = [40, 60, 25, 25, 25]
        headers = ["Код", "Название", "Успех%", "Попыток", "Успешно"]
        for i, h in enumerate(headers):
            pdf.cell(col_w[i], 7, h, border=1)
        pdf.ln()

        pdf.set_font("DejaVu", "", 8)
        for t in techniques:
            pdf.cell(col_w[0], 6, (t.technique_code or "")[:20], border=1)
            pdf.cell(col_w[1], 6, (t.technique_name or "")[:30], border=1)
            pdf.cell(col_w[2], 6, f"{round(t.success_rate * 100)}%", border=1, align="C")
            pdf.cell(col_w[3], 6, str(t.attempt_count), border=1, align="C")
            pdf.cell(col_w[4], 6, str(t.success_count), border=1, align="C")
            pdf.ln()

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


async def export_wiki_csv(
    wiki_id: uuid.UUID,
    manager_name: str,
    db: AsyncSession,
) -> bytes:
    """Generate CSV export of manager's wiki. Returns bytes."""
    data = await _load_wiki_data(wiki_id, db)
    pages = data["pages"]
    patterns = data["patterns"]
    techniques = data["techniques"]

    output = io.StringIO()
    writer = csv.writer(output)

    # Section: Pages
    writer.writerow(["=== WIKI PAGES ==="])
    writer.writerow(["Page Path", "Type", "Version", "Tags", "Updated At", "Content (first 500 chars)"])
    for p in pages:
        content_preview = (p.content or "")[:500].replace("\n", " ")
        writer.writerow([
            p.page_path,
            str(p.page_type) if p.page_type else "",
            p.version,
            ", ".join(p.tags or []),
            p.updated_at.isoformat() if p.updated_at else "",
            content_preview,
        ])

    writer.writerow([])

    # Section: Patterns
    writer.writerow(["=== PATTERNS ==="])
    writer.writerow(["Code", "Category", "Description", "Sessions", "Impact", "Confirmed", "Mitigation"])
    for p in patterns:
        writer.writerow([
            p.pattern_code,
            str(p.category) if p.category else "",
            p.description or "",
            p.sessions_in_pattern,
            p.impact_on_score_delta or "",
            "Yes" if p.confirmed_at else "No",
            p.mitigation_technique or "",
        ])

    writer.writerow([])

    # Section: Techniques
    writer.writerow(["=== TECHNIQUES ==="])
    writer.writerow(["Code", "Name", "Description", "Success Rate", "Attempts", "Successes", "Archetype", "How To Apply"])
    for t in techniques:
        writer.writerow([
            t.technique_code,
            t.technique_name or "",
            t.description or "",
            f"{round(t.success_rate * 100)}%",
            t.attempt_count,
            t.success_count,
            t.applicable_to_archetype or "",
            t.how_to_apply or "",
        ])

    return output.getvalue().encode("utf-8-sig")  # BOM for Excel compatibility
