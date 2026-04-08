"""Wiki export service — generates PDF and CSV exports of manager wiki data.

Used by: GET /api/wiki/{manager_id}/export?format=pdf|csv
"""

import csv
import io
import logging
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

# Simple Cyrillic → Latin transliteration for PDF (fpdf2 Helvetica is Latin-only)
_CYR_TO_LAT = {
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "Yo",
    "Ж": "Zh", "З": "Z", "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M",
    "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
    "Ф": "F", "Х": "Kh", "Ц": "Ts", "Ч": "Ch", "Ш": "Sh", "Щ": "Sch",
    "Ъ": "", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "Yu", "Я": "Ya",
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _to_latin(text: str) -> str:
    """Convert Cyrillic text to Latin transliteration for PDF compatibility."""
    return "".join(_CYR_TO_LAT.get(c, c) for c in text)


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
    pdf.add_page()

    # Title — all text must be transliterated for Helvetica (Latin-only)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _to_latin(f"Wiki Report: {manager_name}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0, 6,
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.cell(0, 6, f"Sessions ingested: {wiki.sessions_ingested}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Patterns discovered: {wiki.patterns_discovered}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Pages: {wiki.pages_count}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # --- Pages ---
    if pages:
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, "Wiki Pages", new_x="LMARGIN", new_y="NEXT")

        for page in pages:
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(
                0, 8,
                f"{page.page_path} (v{page.version})",
                new_x="LMARGIN", new_y="NEXT",
            )
            pdf.set_font("Helvetica", "", 9)
            content = page.content or ""
            if len(content) > 2000:
                content = content[:2000] + "\n[...truncated]"
            content = content.replace("##", "").replace("**", "").replace("*", "")
            pdf.multi_cell(0, 5, _to_latin(content))
            pdf.ln(4)

    # --- Patterns ---
    if patterns:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, "Behavioral Patterns", new_x="LMARGIN", new_y="NEXT")

        pdf.set_font("Helvetica", "B", 9)
        col_w = [40, 25, 80, 20, 25]
        headers = ["Code", "Category", "Description", "Sessions", "Confirmed"]
        for i, h in enumerate(headers):
            pdf.cell(col_w[i], 7, h, border=1)
        pdf.ln()

        pdf.set_font("Helvetica", "", 8)
        for p in patterns:
            pdf.cell(col_w[0], 6, _to_latin(p.pattern_code[:20]), border=1)
            pdf.cell(col_w[1], 6, str(p.category) if p.category else "", border=1)
            desc = _to_latin((p.description or "")[:50])
            pdf.cell(col_w[2], 6, desc, border=1)
            pdf.cell(col_w[3], 6, str(p.sessions_in_pattern), border=1, align="C")
            pdf.cell(col_w[4], 6, "Yes" if p.confirmed_at else "No", border=1, align="C")
            pdf.ln()

    # --- Techniques ---
    if techniques:
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, "Effective Techniques", new_x="LMARGIN", new_y="NEXT")

        pdf.set_font("Helvetica", "B", 9)
        col_w = [40, 60, 25, 25, 25]
        headers = ["Code", "Name", "Success%", "Attempts", "Successes"]
        for i, h in enumerate(headers):
            pdf.cell(col_w[i], 7, h, border=1)
        pdf.ln()

        pdf.set_font("Helvetica", "", 8)
        for t in techniques:
            pdf.cell(col_w[0], 6, _to_latin(t.technique_code[:20]), border=1)
            pdf.cell(col_w[1], 6, _to_latin((t.technique_name or "")[:30]), border=1)
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
