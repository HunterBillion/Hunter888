"""ROP alert generation service.

Generates alerts on-the-fly based on team state (no persistent storage).
Cached for 30s via dashboard endpoint.

Alert types:
- inactive: Manager hasn't trained in 3+ days
- record: Manager scored 90+ recently
- overdue: Assignment past deadline
- skill_drop: Skill dropped 15+ in last week
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import ManagerProgress, WeeklyReport
from app.models.training import SessionStatus, TrainingSession
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

INACTIVE_DAYS = 3
RECORD_THRESHOLD = 90
SKILL_DROP_THRESHOLD = 15


async def get_active_alerts(team_id: uuid.UUID, db: AsyncSession) -> dict:
    """Generate alerts based on current team state."""
    # Get team members
    members_result = await db.execute(
        select(User).where(
            User.team_id == team_id,
            User.is_active == True,  # noqa: E712
            User.role == UserRole.manager,
        )
    )
    members = list(members_result.scalars().all())

    if not members:
        return {"alerts": [], "total": 0}

    member_ids = [m.id for m in members]
    now = datetime.now(timezone.utc)
    alerts = []

    # ── 1. Inactive alerts: no sessions in 3+ days ──
    for member in members:
        last_session_r = await db.execute(
            select(TrainingSession.started_at).where(
                TrainingSession.user_id == member.id,
                TrainingSession.status == SessionStatus.completed,
            ).order_by(TrainingSession.started_at.desc()).limit(1)
        )
        last_row = last_session_r.first()
        if last_row:
            days_inactive = (now - last_row[0]).days
            if days_inactive >= INACTIVE_DAYS:
                alerts.append({
                    "type": "inactive",
                    "manager_id": str(member.id),
                    "manager_name": member.full_name,
                    "message": f"Не тренировался {days_inactive} дней",
                    "severity": "warning" if days_inactive < 7 else "critical",
                    "created_at": now.isoformat(),
                    "value": days_inactive,
                })
        else:
            # Never trained
            alerts.append({
                "type": "inactive",
                "manager_id": str(member.id),
                "manager_name": member.full_name,
                "message": "Ещё не проходил тренировок",
                "severity": "info",
                "created_at": now.isoformat(),
                "value": 0,
            })

    # ── 2. Record alerts: score 90+ in last 7 days ──
    week_ago = now - timedelta(days=7)
    records_r = await db.execute(
        select(
            TrainingSession.user_id,
            func.max(TrainingSession.score_total).label("best"),
        ).where(
            TrainingSession.user_id.in_(member_ids),
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= week_ago,
        ).group_by(TrainingSession.user_id)
        .having(func.max(TrainingSession.score_total) >= RECORD_THRESHOLD)
    )
    for row in records_r.all():
        member = next((m for m in members if m.id == row[0]), None)
        if member:
            alerts.append({
                "type": "record",
                "manager_id": str(member.id),
                "manager_name": member.full_name,
                "message": f"Рекорд: {round(float(row[1]), 1)} баллов",
                "severity": "success",
                "created_at": now.isoformat(),
                "value": round(float(row[1]), 1),
            })

    # ── 3. Skill drop alerts: skill dropped 15+ in last week ──
    for member in members:
        # Compare current skills with last week's snapshot
        progress_r = await db.execute(
            select(ManagerProgress).where(ManagerProgress.user_id == member.id)
        )
        progress = progress_r.scalar_one_or_none()
        if not progress:
            continue

        # Get last weekly report for comparison
        report_r = await db.execute(
            select(WeeklyReport).where(
                WeeklyReport.user_id == member.id,
            ).order_by(WeeklyReport.week_end.desc()).limit(1)
        )
        report = report_r.scalar_one_or_none()
        if not report or not report.skills_snapshot:
            continue

        current_skills = progress.skills_dict()
        for skill_name, current_val in current_skills.items():
            old_val = report.skills_snapshot.get(skill_name, current_val)
            drop = old_val - current_val
            if drop >= SKILL_DROP_THRESHOLD:
                from app.services.team_analytics import SKILL_DISPLAY_NAMES
                skill_label = SKILL_DISPLAY_NAMES.get(skill_name, skill_name)
                alerts.append({
                    "type": "skill_drop",
                    "manager_id": str(member.id),
                    "manager_name": member.full_name,
                    "message": f"{skill_label}: -{int(drop)} за неделю",
                    "severity": "warning",
                    "created_at": now.isoformat(),
                    "value": -int(drop),
                })

    # Sort: critical first, then warning, then success, then info
    severity_order = {"critical": 0, "warning": 1, "success": 2, "info": 3}
    alerts.sort(key=lambda a: severity_order.get(a["severity"], 4))

    return {"alerts": alerts, "total": len(alerts)}
