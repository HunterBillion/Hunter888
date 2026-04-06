"""Weekly report generation for managers and team digests for ROP.

Generated every Monday at 09:00 by the scheduler.
Stored in WeeklyReport model for historical access.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import ManagerProgress, WeeklyReport
from app.models.training import SessionStatus, TrainingSession
from app.models.user import Team, User, UserRole

logger = logging.getLogger(__name__)


async def generate_weekly_report(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> WeeklyReport:
    """Generate a weekly report for a single user.

    Covers the last 7 days (Monday to Sunday).
    """
    now = datetime.now(timezone.utc)
    # Find the start of the reporting week (last Monday)
    days_since_monday = now.weekday()  # 0=Mon
    week_end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = week_end - timedelta(days=days_since_monday)
    prev_week_start = week_start - timedelta(days=7)

    # Check if report already exists for this week
    existing = await db.execute(
        select(WeeklyReport).where(
            WeeklyReport.user_id == user_id,
            WeeklyReport.week_start == week_start,
        )
    )
    if existing.scalar_one_or_none():
        logger.info("Weekly report already exists for user=%s week=%s", user_id, week_start)
        return existing.scalar_one_or_none()

    # Sessions this week
    sessions_result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= week_start,
            TrainingSession.started_at < week_end,
        )
    )
    sessions = sessions_result.scalars().all()

    sessions_completed = len(sessions)
    total_time_minutes = sum((s.duration_seconds or 0) for s in sessions) // 60
    scores = [s.score_total for s in sessions if s.score_total is not None]
    avg_score = sum(scores) / len(scores) if scores else None
    best_score = max(scores) if scores else None
    worst_score = min(scores) if scores else None

    # Previous week avg for trend
    prev_result = await db.execute(
        select(func.avg(TrainingSession.score_total)).where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= prev_week_start,
            TrainingSession.started_at < week_start,
        )
    )
    prev_avg = prev_result.scalar()

    if avg_score is not None and prev_avg is not None:
        diff = avg_score - float(prev_avg)
        score_trend = "improving" if diff > 3 else ("declining" if diff < -3 else "stable")
    else:
        score_trend = "stable"

    # Skills snapshot
    progress_r = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user_id)
    )
    progress = progress_r.scalar_one_or_none()

    skills_snapshot = {}
    skills_change = {}
    if progress:
        skills_snapshot = {
            "empathy": progress.skill_empathy,
            "knowledge": progress.skill_knowledge,
            "objection_handling": progress.skill_objection_handling,
            "stress_resistance": progress.skill_stress_resistance,
            "closing": progress.skill_closing,
            "qualification": progress.skill_qualification,
        }

        # Skills change vs previous report
        prev_report_r = await db.execute(
            select(WeeklyReport).where(
                WeeklyReport.user_id == user_id,
                WeeklyReport.week_start == prev_week_start,
            )
        )
        prev_report = prev_report_r.scalar_one_or_none()
        if prev_report and prev_report.skills_snapshot:
            for skill, val in skills_snapshot.items():
                prev_val = prev_report.skills_snapshot.get(skill, val)
                skills_change[skill] = val - prev_val

    # XP earned this week
    xp_earned = sum((s.xp_earned or 0) for s in sessions) if hasattr(sessions[0], 'xp_earned') and sessions else 0
    if xp_earned == 0 and sessions:
        from app.services.gamification import calculate_session_xp
        xp_earned = sum(calculate_session_xp(s.score_total, 0) for s in sessions)

    # Weak points
    weak_points = []
    if skills_snapshot:
        avg_skill = sum(skills_snapshot.values()) / len(skills_snapshot) if skills_snapshot else 50
        for skill, val in skills_snapshot.items():
            if val < avg_skill - 10:
                weak_points.append({"skill": skill, "score": val, "gap": round(avg_skill - val, 1)})

    # Recommendations
    recommendations = []
    for wp in weak_points[:3]:
        recommendations.append(f"Сфокусируйтесь на навыке '{wp['skill']}' — отставание {wp['gap']} от среднего")

    # Weekly rank in team
    weekly_rank = None
    rank_change = None
    user_r = await db.execute(select(User).where(User.id == user_id))
    user_obj = user_r.scalar_one_or_none()
    if user_obj and user_obj.team_id:
        team_members_r = await db.execute(
            select(User.id).where(
                User.team_id == user_obj.team_id,
                User.is_active == True,  # noqa: E712
            )
        )
        team_member_ids = [r[0] for r in team_members_r.all()]

        # Rank by avg score this week
        scores_by_member = []
        for mid in team_member_ids:
            r = await db.execute(
                select(func.avg(TrainingSession.score_total)).where(
                    TrainingSession.user_id == mid,
                    TrainingSession.status == SessionStatus.completed,
                    TrainingSession.started_at >= week_start,
                    TrainingSession.started_at < week_end,
                )
            )
            member_avg = r.scalar()
            scores_by_member.append((mid, float(member_avg or 0)))

        scores_by_member.sort(key=lambda x: x[1], reverse=True)
        for i, (mid, _) in enumerate(scores_by_member):
            if mid == user_id:
                weekly_rank = i + 1
                break

        # Rank change from previous week
        if prev_report and prev_report.weekly_rank and weekly_rank:
            rank_change = prev_report.weekly_rank - weekly_rank  # Positive = moved up

    # Report text
    report_text = _generate_report_text(
        sessions_completed, avg_score, score_trend, weak_points, skills_change
    )

    # Create report
    report = WeeklyReport(
        user_id=user_id,
        week_start=week_start,
        week_end=week_end,
        sessions_completed=sessions_completed,
        total_time_minutes=total_time_minutes,
        average_score=round(avg_score, 1) if avg_score else None,
        best_score=int(best_score) if best_score else None,
        worst_score=int(worst_score) if worst_score else None,
        score_trend=score_trend,
        skills_snapshot=skills_snapshot,
        skills_change=skills_change,
        weak_points=weak_points,
        recommendations=recommendations,
        report_text=report_text,
        weekly_rank=weekly_rank,
        rank_change=rank_change,
        xp_earned=xp_earned,
        level_at_start=progress.current_level if progress else 1,
        level_at_end=progress.current_level if progress else 1,
        new_achievements=[],
    )
    db.add(report)
    await db.flush()

    logger.info("Generated weekly report for user=%s: %d sessions, avg=%.1f",
                user_id, sessions_completed, avg_score or 0)
    return report


def _generate_report_text(
    sessions: int,
    avg_score: float | None,
    trend: str,
    weak_points: list,
    skills_change: dict,
) -> str:
    """Generate human-readable report summary in Russian."""
    parts = []

    if sessions == 0:
        return "На этой неделе вы не проходили тренировки. Рекомендуем выделить хотя бы 2-3 сессии."

    parts.append(f"За эту неделю вы завершили {sessions} тренировок.")

    if avg_score:
        parts.append(f"Средний балл: {avg_score:.0f}.")

    if trend == "improving":
        parts.append("Результаты улучшаются — отличная динамика!")
    elif trend == "declining":
        parts.append("Результаты снижаются — рекомендуем увеличить частоту тренировок.")

    # Top improved skill
    if skills_change:
        improved = [(s, d) for s, d in skills_change.items() if d > 0]
        if improved:
            best = max(improved, key=lambda x: x[1])
            parts.append(f"Лучший прогресс: {best[0]} (+{best[1]}).")

    if weak_points:
        parts.append(f"Слабые навыки: {', '.join(wp['skill'] for wp in weak_points[:2])}.")

    return " ".join(parts)


async def generate_all_weekly_reports(db: AsyncSession) -> int:
    """Generate weekly reports for all active users. Called by scheduler."""
    result = await db.execute(
        select(User.id).where(User.is_active == True)  # noqa: E712
    )
    user_ids = [r[0] for r in result.all()]

    count = 0
    for uid in user_ids:
        try:
            await generate_weekly_report(uid, db)
            count += 1
        except Exception as e:
            logger.error("Failed to generate weekly report for user=%s: %s", uid, e)

    await db.commit()
    logger.info("Generated %d weekly reports out of %d users", count, len(user_ids))
    return count


async def get_team_weekly_digest(team_id: uuid.UUID, db: AsyncSession) -> dict:
    """Aggregated weekly digest for ROP."""
    team_r = await db.execute(select(Team).where(Team.id == team_id))
    team = team_r.scalar_one_or_none()
    team_name = team.name if team else "Team"

    now = datetime.now(timezone.utc)
    days_since_monday = now.weekday()
    week_end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = week_end - timedelta(days=days_since_monday)

    # Get all team members' reports for this week
    members_r = await db.execute(
        select(User).where(
            User.team_id == team_id,
            User.is_active == True,  # noqa: E712
            User.role == UserRole.manager,
        )
    )
    members = members_r.scalars().all()

    total_sessions = 0
    all_scores = []
    digest_members = []
    top_improvements = []
    degrading = []

    for member in members:
        report_r = await db.execute(
            select(WeeklyReport).where(
                WeeklyReport.user_id == member.id,
                WeeklyReport.week_start == week_start,
            )
        )
        report = report_r.scalar_one_or_none()

        sessions = report.sessions_completed if report else 0
        avg_score = float(report.average_score) if report and report.average_score else 0
        trend = report.score_trend if report else "stable"
        total_sessions += sessions
        if avg_score > 0:
            all_scores.append(avg_score)

        # Skills change summary
        change_summary = ""
        if report and report.skills_change:
            improved = [f"{s}(+{d})" for s, d in report.skills_change.items() if d > 2]
            declined = [f"{s}({d})" for s, d in report.skills_change.items() if d < -2]
            if improved:
                change_summary = "Рост: " + ", ".join(improved[:2])
            elif declined:
                change_summary = "Спад: " + ", ".join(declined[:2])

        digest_members.append({
            "user_id": str(member.id),
            "full_name": member.full_name,
            "sessions_completed": sessions,
            "avg_score": round(avg_score, 1),
            "score_trend": trend,
            "skills_change_summary": change_summary,
        })

        if trend == "improving":
            top_improvements.append(f"{member.full_name} (avg {avg_score:.0f})")
        elif trend == "declining":
            degrading.append(f"{member.full_name} (avg {avg_score:.0f})")

    avg_team_score = sum(all_scores) / len(all_scores) if all_scores else 0

    return {
        "team_name": team_name,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "total_sessions": total_sessions,
        "avg_team_score": round(avg_team_score, 1),
        "top_improvements": top_improvements[:3],
        "degrading_members": degrading,
        "members": digest_members,
    }
