"""PDF report generator for ROP team dashboard.

Generates a compact team report with:
- Header with ROP name and period
- Team summary stats
- Manager table (sessions, avg score, streak)
- Simplified skill heatmap
- Top-3 leaderboard
"""

import io
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import ManagerProgress
from app.models.training import SessionStatus, TrainingSession
from app.models.user import Team, User, UserRole

logger = logging.getLogger(__name__)

SKILL_LABELS = {
    "empathy": "Эмп",
    "knowledge": "Зн",
    "objection_handling": "Возр",
    "stress_resistance": "Стр",
    "closing": "Закр",
    "qualification": "Кв",
}

SKILL_NAMES = list(SKILL_LABELS.keys())

# Cyrillic-capable TTF (installed via fonts-dejavu-core in production Dockerfile;
# present on most dev macs at /Library/.../DejaVuSans.ttf or via Homebrew).
# Built-in fpdf core fonts (Helvetica/Times) only support Latin-1 — they raise
# UnicodeEncodeError on Cyrillic team names, which is the FIND-008 export 500.
DEJAVU_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/DejaVuSans.ttf",
    "/opt/homebrew/share/fonts/DejaVuSans.ttf",
]
DEJAVU_BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/DejaVuSans-Bold.ttf",
    "/opt/homebrew/share/fonts/DejaVuSans-Bold.ttf",
]


def _first_existing(paths: list[str]) -> str | None:
    for p in paths:
        if os.path.exists(p):
            return p
    return None


async def generate_team_report_pdf(
    team_id: uuid.UUID,
    rop_name: str,
    period: str,
    db: AsyncSession,
) -> bytes:
    """Generate PDF report and return as bytes."""
    from fpdf import FPDF

    now = datetime.now(timezone.utc)
    if period == "week":
        since = now - timedelta(days=7)
        period_label = f"{since.strftime('%d.%m.%Y')} — {now.strftime('%d.%m.%Y')}"
    else:
        since = now - timedelta(days=30)
        period_label = f"{since.strftime('%d.%m.%Y')} — {now.strftime('%d.%m.%Y')}"

    # Get team info
    team_r = await db.execute(select(Team).where(Team.id == team_id))
    team = team_r.scalar_one_or_none()
    team_name = team.name if team else "Команда"

    # Get members
    members_r = await db.execute(
        select(User).where(
            User.team_id == team_id,
            User.is_active == True,  # noqa: E712
            User.role == UserRole.manager,
        ).order_by(User.full_name)
    )
    members = list(members_r.scalars().all())
    member_ids = [m.id for m in members]

    # Get stats per member
    member_data = []
    for m in members:
        stats_r = await db.execute(
            select(
                func.count(TrainingSession.id),
                func.avg(TrainingSession.score_total),
            ).where(
                TrainingSession.user_id == m.id,
                TrainingSession.status == SessionStatus.completed,
                TrainingSession.started_at >= since,
            )
        )
        row = stats_r.one()

        # Get skills
        progress_r = await db.execute(
            select(ManagerProgress).where(ManagerProgress.user_id == m.id)
        )
        progress = progress_r.scalar_one_or_none()
        skills = progress.skills_dict() if progress else {s: 50 for s in SKILL_NAMES}
        streak = progress.current_deal_streak if progress else 0

        member_data.append({
            "name": m.full_name,
            "sessions": row[0] or 0,
            "avg_score": round(float(row[1] or 0), 1),
            "streak": streak,
            "skills": skills,
        })

    # Sort by avg_score desc
    member_data.sort(key=lambda x: x["avg_score"], reverse=True)

    # Team totals
    total_sessions = sum(m["sessions"] for m in member_data)
    scored = [m for m in member_data if m["sessions"] > 0]
    team_avg = round(sum(m["avg_score"] for m in scored) / len(scored), 1) if scored else 0

    # ── Build PDF ──
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Register Cyrillic-capable font if the system has DejaVu installed.
    # Falls back to Helvetica (Latin-1 only) if not — the team report
    # then transliterates Cyrillic team names to ASCII to avoid 500.
    dejavu_regular = _first_existing(DEJAVU_CANDIDATES)
    dejavu_bold = _first_existing(DEJAVU_BOLD_CANDIDATES)
    if dejavu_regular and dejavu_bold:
        pdf.add_font("DejaVu", "", dejavu_regular)
        pdf.add_font("DejaVu", "B", dejavu_bold)
        font_family = "DejaVu"

        def _safe(s: str) -> str:
            return s
    else:
        font_family = "Helvetica"
        logger.warning(
            "DejaVu TTF not found; PDF report will transliterate Cyrillic. "
            "Install fonts-dejavu-core in the runtime image."
        )
        # Latin-1 fallback: best-effort transliteration so we still produce
        # a readable (Latin) report instead of a 500.
        try:
            from unicodedata import normalize
            def _safe(s: str) -> str:
                return normalize("NFKD", s).encode("ascii", "ignore").decode("ascii") or "?"
        except Exception:  # pragma: no cover
            def _safe(s: str) -> str:
                return s.encode("ascii", "replace").decode("ascii")

    pdf.set_font(font_family, "B", 16)
    pdf.cell(0, 10, _safe(f"Отчёт команды: {team_name}"), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font(font_family, "", 10)
    pdf.cell(0, 6, _safe(f"РОП: {rop_name}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, _safe(f"Период: {period_label}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Summary stats
    pdf.set_font(font_family, "B", 12)
    pdf.cell(0, 8, _safe("Сводка"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(font_family, "", 10)
    pdf.cell(0, 6, _safe(f"Всего сессий: {total_sessions}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, _safe(f"Средний балл команды: {team_avg}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, _safe(f"Активных охотников: {len(scored)}/{len(members)}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Manager table
    pdf.set_font(font_family, "B", 12)
    pdf.cell(0, 8, _safe("Результаты охотников"), new_x="LMARGIN", new_y="NEXT")

    # Table header
    pdf.set_font(font_family, "B", 9)
    col_widths = [60, 25, 30, 20]
    headers = ["Охотник", "Сессии", "Ср. балл", "Серия"]
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 7, _safe(h), border=1)
    pdf.ln()

    # Table rows
    pdf.set_font(font_family, "", 9)
    for md in member_data:
        pdf.cell(col_widths[0], 6, _safe((md["name"] or "—")[:30]), border=1)
        pdf.cell(col_widths[1], 6, str(md["sessions"]), border=1, align="C")
        pdf.cell(col_widths[2], 6, str(md["avg_score"]), border=1, align="C")
        pdf.cell(col_widths[3], 6, str(md["streak"]), border=1, align="C")
        pdf.ln()

    pdf.ln(4)

    # Skill heatmap (simplified)
    pdf.set_font(font_family, "B", 12)
    pdf.cell(0, 8, _safe("Карта навыков"), new_x="LMARGIN", new_y="NEXT")

    # Header row
    pdf.set_font(font_family, "B", 8)
    name_w = 50
    skill_w = 22
    pdf.cell(name_w, 6, _safe("Охотник"), border=1)
    for s in SKILL_NAMES:
        pdf.cell(skill_w, 6, _safe(SKILL_LABELS[s]), border=1, align="C")
    pdf.ln()

    # Data rows
    pdf.set_font(font_family, "", 8)
    for md in member_data:
        pdf.cell(name_w, 6, _safe((md["name"] or "—")[:25]), border=1)
        for s in SKILL_NAMES:
            val = int(md["skills"].get(s, 50))
            # Color coding: red < 40, yellow 40-70, green > 70
            if val >= 70:
                pdf.set_fill_color(200, 255, 200)
            elif val >= 40:
                pdf.set_fill_color(255, 255, 200)
            else:
                pdf.set_fill_color(255, 200, 200)
            pdf.cell(skill_w, 6, str(val), border=1, align="C", fill=True)
        pdf.ln()

    pdf.ln(4)

    # Top-3 leaderboard
    pdf.set_font(font_family, "B", 12)
    pdf.cell(0, 8, _safe("Топ-3"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(font_family, "", 10)
    # No medal emojis — DejaVuSans doesn't ship those glyphs.
    for i, md in enumerate(member_data[:3]):
        line = f"{i + 1}. {md['name']} — {md['avg_score']} баллов"
        pdf.cell(0, 6, _safe(line), new_x="LMARGIN", new_y="NEXT")

    # Output
    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()
