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

    # Use built-in Helvetica (no external font files needed)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"Team Report: {team_name}", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"ROP: {rop_name}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Period: {period_label}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Summary stats
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Total sessions: {total_sessions}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Team avg score: {team_avg}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Active managers: {len(scored)}/{len(members)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Manager table
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Manager Performance", new_x="LMARGIN", new_y="NEXT")

    # Table header
    pdf.set_font("Helvetica", "B", 9)
    col_widths = [60, 25, 30, 20]
    headers = ["Manager", "Sessions", "Avg Score", "Streak"]
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 7, h, border=1)
    pdf.ln()

    # Table rows
    pdf.set_font("Helvetica", "", 9)
    for md in member_data:
        pdf.cell(col_widths[0], 6, md["name"][:30], border=1)
        pdf.cell(col_widths[1], 6, str(md["sessions"]), border=1, align="C")
        pdf.cell(col_widths[2], 6, str(md["avg_score"]), border=1, align="C")
        pdf.cell(col_widths[3], 6, str(md["streak"]), border=1, align="C")
        pdf.ln()

    pdf.ln(4)

    # Skill heatmap (simplified)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Skill Heatmap", new_x="LMARGIN", new_y="NEXT")

    # Header row
    pdf.set_font("Helvetica", "B", 8)
    name_w = 50
    skill_w = 22
    pdf.cell(name_w, 6, "Manager", border=1)
    for s in SKILL_NAMES:
        pdf.cell(skill_w, 6, SKILL_LABELS[s], border=1, align="C")
    pdf.ln()

    # Data rows
    pdf.set_font("Helvetica", "", 8)
    for md in member_data:
        pdf.cell(name_w, 6, md["name"][:25], border=1)
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
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Top 3", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    medals = ["1st", "2nd", "3rd"]
    for i, md in enumerate(member_data[:3]):
        pdf.cell(0, 6, f"{medals[i]}: {md['name']} - {md['avg_score']} pts", new_x="LMARGIN", new_y="NEXT")

    # Output
    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()
