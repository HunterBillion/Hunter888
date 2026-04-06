"""Team-level analytics for ROP Dashboard v2.

Provides:
- Team heatmap (skills × managers matrix)
- Weak links detection (managers needing attention)
- Manager benchmark (within team comparison)
- ROI calculation (training hours ↔ score improvement)
- Platform benchmark (team vs all users)
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import ManagerProgress, SessionHistory
from app.models.training import SessionStatus, TrainingSession
from app.models.user import Team, User, UserRole

logger = logging.getLogger(__name__)

SKILL_NAMES = ["empathy", "knowledge", "objection_handling", "stress_resistance", "closing", "qualification"]

SKILL_DISPLAY_NAMES = {
    "empathy": "Эмпатия",
    "knowledge": "Знания",
    "objection_handling": "Работа с возражениями",
    "stress_resistance": "Стрессоустойчивость",
    "closing": "Закрытие сделки",
    "qualification": "Квалификация",
}


async def _get_team_members(team_id: uuid.UUID, db: AsyncSession) -> list[User]:
    """Get all active members of a team."""
    result = await db.execute(
        select(User).where(
            User.team_id == team_id,
            User.is_active == True,  # noqa: E712
        )
    )
    return list(result.scalars().all())


async def _get_member_skills(user_id: uuid.UUID, db: AsyncSession) -> dict[str, float]:
    """Get 6 skills for a user from ManagerProgress."""
    result = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user_id)
    )
    progress = result.scalar_one_or_none()
    if not progress:
        return {s: 50.0 for s in SKILL_NAMES}

    return {
        "empathy": float(progress.skill_empathy),
        "knowledge": float(progress.skill_knowledge),
        "objection_handling": float(progress.skill_objection_handling),
        "stress_resistance": float(progress.skill_stress_resistance),
        "closing": float(progress.skill_closing),
        "qualification": float(progress.skill_qualification),
    }


async def _get_member_sessions_this_week(user_id: uuid.UUID, db: AsyncSession) -> int:
    """Count completed sessions in last 7 days."""
    since = datetime.now(timezone.utc) - timedelta(days=7)
    result = await db.execute(
        select(func.count(TrainingSession.id)).where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= since,
        )
    )
    return result.scalar() or 0


async def _get_member_avg_score_recent(user_id: uuid.UUID, db: AsyncSession, days: int = 14) -> float:
    """Average score over recent N days."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(func.avg(TrainingSession.score_total)).where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= since,
        )
    )
    val = result.scalar()
    return float(val) if val else 0.0


async def _get_score_trend(user_id: uuid.UUID, db: AsyncSession) -> str:
    """Determine score trend: improving / declining / stable."""
    now = datetime.now(timezone.utc)
    week1_start = now - timedelta(days=14)
    week1_end = now - timedelta(days=7)
    week2_start = now - timedelta(days=7)

    # Week 1 avg (older)
    r1 = await db.execute(
        select(func.avg(TrainingSession.score_total)).where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= week1_start,
            TrainingSession.started_at < week1_end,
        )
    )
    avg1 = r1.scalar()

    # Week 2 avg (recent)
    r2 = await db.execute(
        select(func.avg(TrainingSession.score_total)).where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= week2_start,
        )
    )
    avg2 = r2.scalar()

    if avg1 is None or avg2 is None:
        return "stable"

    diff = float(avg2) - float(avg1)
    if diff > 5:
        return "improving"
    elif diff < -5:
        return "declining"
    return "stable"


async def _get_last_session_time(user_id: uuid.UUID, db: AsyncSession) -> datetime | None:
    result = await db.execute(
        select(TrainingSession.started_at).where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
        ).order_by(TrainingSession.started_at.desc()).limit(1)
    )
    row = result.first()
    return row[0] if row else None


# ═══════════════════════════════════════════════════════════════════════════
# TEAM HEATMAP
# ═══════════════════════════════════════════════════════════════════════════

async def get_team_heatmap(team_id: uuid.UUID, db: AsyncSession) -> dict:
    """Build skill heatmap for team: rows=managers, cols=6 skills."""
    members = await _get_team_members(team_id, db)

    team_result = await db.execute(select(Team).where(Team.id == team_id))
    team = team_result.scalar_one_or_none()
    team_name = team.name if team else "Team"

    rows = []
    skill_sums: dict[str, float] = {s: 0.0 for s in SKILL_NAMES}
    count = 0

    for member in members:
        skills = await _get_member_skills(member.id, db)
        trend = await _get_score_trend(member.id, db)
        sessions_week = await _get_member_sessions_this_week(member.id, db)

        cells = []
        for skill_name in SKILL_NAMES:
            score = skills.get(skill_name, 50.0)
            skill_sums[skill_name] += score
            cells.append({
                "skill": skill_name,
                "score": round(score, 1),
                "trend": trend,
            })

        avg_score = sum(skills.values()) / len(skills) if skills else 50.0

        rows.append({
            "user_id": str(member.id),
            "full_name": member.full_name,
            "avatar_url": getattr(member, "avatar_url", None),
            "skills": cells,
            "avg_score": round(avg_score, 1),
            "sessions_this_week": sessions_week,
        })
        count += 1

    team_avg = {s: round(v / max(count, 1), 1) for s, v in skill_sums.items()}

    return {
        "team_name": team_name,
        "skill_names": SKILL_NAMES,
        "rows": rows,
        "team_avg": team_avg,
    }


# ═══════════════════════════════════════════════════════════════════════════
# WEAK LINKS
# ═══════════════════════════════════════════════════════════════════════════

async def get_weak_links(team_id: uuid.UUID, db: AsyncSession) -> dict:
    """Identify managers needing attention."""
    members = await _get_team_members(team_id, db)

    needs_attention = []

    for member in members:
        if member.role != UserRole.manager:
            continue

        reasons = []
        trend = await _get_score_trend(member.id, db)
        avg_score = await _get_member_avg_score_recent(member.id, db, days=14)
        sessions_week = await _get_member_sessions_this_week(member.id, db)
        last_session = await _get_last_session_time(member.id, db)

        if trend == "declining":
            reasons.append("Результаты снижаются последние 2 недели")
        if avg_score > 0 and avg_score < 50:
            reasons.append(f"Средний балл ниже 50 ({avg_score:.0f})")
        if sessions_week == 0:
            reasons.append("Нет тренировок на этой неделе")
        if last_session and (datetime.now(timezone.utc) - last_session).days > 7:
            reasons.append(f"Неактивен {(datetime.now(timezone.utc) - last_session).days} дней")

        if reasons:
            needs_attention.append({
                "user_id": str(member.id),
                "full_name": member.full_name,
                "avatar_url": getattr(member, "avatar_url", None),
                "reasons": reasons,
                "avg_score": round(avg_score, 1),
                "trend": trend,
                "sessions_this_week": sessions_week,
                "last_session_at": last_session.isoformat() if last_session else None,
            })

    return {
        "needs_attention": needs_attention,
        "total_team": len(members),
        "attention_count": len(needs_attention),
    }


# ═══════════════════════════════════════════════════════════════════════════
# MANAGER BENCHMARK
# ═══════════════════════════════════════════════════════════════════════════

async def compare_managers(team_id: uuid.UUID, db: AsyncSession) -> dict:
    """Compare each manager's skills against team average."""
    members = await _get_team_members(team_id, db)

    team_result = await db.execute(select(Team).where(Team.id == team_id))
    team = team_result.scalar_one_or_none()
    team_name = team.name if team else "Team"

    # Collect all member skills
    member_data = []
    for member in members:
        skills = await _get_member_skills(member.id, db)
        sessions = await _get_member_sessions_this_week(member.id, db)
        member_data.append({
            "user": member,
            "skills": skills,
            "sessions": sessions,
        })

    # Calculate team averages
    n = len(member_data)
    team_avg: dict[str, float] = {s: 0.0 for s in SKILL_NAMES}
    for md in member_data:
        for s in SKILL_NAMES:
            team_avg[s] += md["skills"].get(s, 50.0)
    team_avg = {s: v / max(n, 1) for s, v in team_avg.items()}

    team_avg_score = sum(team_avg.values()) / len(team_avg) if team_avg else 50.0

    # Build entries with percentile
    entries = []
    for md in member_data:
        skill_scores = md["skills"]
        overall = sum(skill_scores.values()) / len(skill_scores) if skill_scores else 50.0

        benchmark_skills = []
        for s in SKILL_NAMES:
            score = skill_scores.get(s, 50.0)
            tavg = team_avg[s]
            # Percentile: how many team members score lower
            lower_count = sum(1 for other in member_data if other["skills"].get(s, 50.0) < score)
            percentile = int(lower_count / max(n, 1) * 100)
            benchmark_skills.append({
                "skill": s,
                "score": round(score, 1),
                "team_avg": round(tavg, 1),
                "diff": round(score - tavg, 1),
                "percentile": percentile,
            })

        entries.append({
            "user_id": str(md["user"].id),
            "full_name": md["user"].full_name,
            "avatar_url": getattr(md["user"], "avatar_url", None),
            "overall_score": round(overall, 1),
            "overall_rank": 0,  # Set below
            "skills": benchmark_skills,
            "sessions_count": md["sessions"],
        })

    # Set ranks
    entries.sort(key=lambda e: e["overall_score"], reverse=True)
    for i, e in enumerate(entries):
        e["overall_rank"] = i + 1

    return {
        "team_name": team_name,
        "entries": entries,
        "team_avg_score": round(team_avg_score, 1),
    }


# ═══════════════════════════════════════════════════════════════════════════
# ROI TRAINING
# ═══════════════════════════════════════════════════════════════════════════

async def get_team_roi(team_id: uuid.UUID, db: AsyncSession, weeks: int = 8) -> dict:
    """Calculate ROI: correlation between training hours and score improvement."""
    members = await _get_team_members(team_id, db)
    member_ids = [m.id for m in members]

    if not member_ids:
        return {"data_points": [], "correlation": 0.0, "summary": "Нет данных"}

    data_points = []
    hours_list = []
    delta_list = []

    now = datetime.now(timezone.utc)

    for w in range(weeks):
        week_end = now - timedelta(weeks=w)
        week_start = week_end - timedelta(days=7)
        prev_week_start = week_start - timedelta(days=7)

        # Training hours this week
        duration_result = await db.execute(
            select(func.sum(TrainingSession.duration_seconds)).where(
                TrainingSession.user_id.in_(member_ids),
                TrainingSession.status == SessionStatus.completed,
                TrainingSession.started_at >= week_start,
                TrainingSession.started_at < week_end,
            )
        )
        total_seconds = duration_result.scalar() or 0
        hours = round(total_seconds / 3600, 1)

        # Session count
        count_result = await db.execute(
            select(func.count(TrainingSession.id)).where(
                TrainingSession.user_id.in_(member_ids),
                TrainingSession.status == SessionStatus.completed,
                TrainingSession.started_at >= week_start,
                TrainingSession.started_at < week_end,
            )
        )
        sessions = count_result.scalar() or 0

        # Score delta (this week avg - previous week avg)
        curr_avg_r = await db.execute(
            select(func.avg(TrainingSession.score_total)).where(
                TrainingSession.user_id.in_(member_ids),
                TrainingSession.status == SessionStatus.completed,
                TrainingSession.started_at >= week_start,
                TrainingSession.started_at < week_end,
            )
        )
        prev_avg_r = await db.execute(
            select(func.avg(TrainingSession.score_total)).where(
                TrainingSession.user_id.in_(member_ids),
                TrainingSession.status == SessionStatus.completed,
                TrainingSession.started_at >= prev_week_start,
                TrainingSession.started_at < week_start,
            )
        )
        curr_avg = curr_avg_r.scalar()
        prev_avg = prev_avg_r.scalar()
        delta = float(curr_avg or 0) - float(prev_avg or 0) if curr_avg and prev_avg else 0.0

        iso_week = week_start.isocalendar()
        period = f"{iso_week[0]}-W{iso_week[1]:02d}"

        data_points.append({
            "period": period,
            "training_hours": hours,
            "sessions_count": sessions,
            "avg_score_delta": round(delta, 1),
            "skill_improvement": {},
        })
        hours_list.append(hours)
        delta_list.append(delta)

    data_points.reverse()

    # Pearson correlation
    correlation = _pearson(hours_list, delta_list)

    if correlation > 0.5:
        summary = f"Сильная корреляция ({correlation:.2f}): больше тренировок → лучше результат"
    elif correlation > 0.2:
        summary = f"Умеренная корреляция ({correlation:.2f}): тренировки помогают"
    else:
        summary = f"Слабая корреляция ({correlation:.2f}): нужно улучшить качество тренировок"

    return {
        "data_points": data_points,
        "correlation": round(correlation, 3),
        "summary": summary,
    }


def _pearson(x: list[float], y: list[float]) -> float:
    """Pearson correlation coefficient."""
    n = len(x)
    if n < 3:
        return 0.0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
    std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
    if std_x == 0 or std_y == 0:
        return 0.0
    return cov / (std_x * std_y)


# ═══════════════════════════════════════════════════════════════════════════
# PLATFORM BENCHMARK
# ═══════════════════════════════════════════════════════════════════════════

async def get_platform_benchmark(db: AsyncSession) -> dict[str, float]:
    """Get platform-wide averages for all skills."""
    result = await db.execute(
        select(
            func.avg(ManagerProgress.skill_empathy),
            func.avg(ManagerProgress.skill_knowledge),
            func.avg(ManagerProgress.skill_objection_handling),
            func.avg(ManagerProgress.skill_stress_resistance),
            func.avg(ManagerProgress.skill_closing),
            func.avg(ManagerProgress.skill_qualification),
        )
    )
    row = result.one()
    return {
        "empathy": float(row[0] or 50),
        "knowledge": float(row[1] or 50),
        "objection_handling": float(row[2] or 50),
        "stress_resistance": float(row[3] or 50),
        "closing": float(row[4] or 50),
        "qualification": float(row[5] or 50),
    }


async def get_team_vs_platform(team_id: uuid.UUID, db: AsyncSession) -> dict:
    """Compare team skills against platform average with percentiles."""
    team_result = await db.execute(select(Team).where(Team.id == team_id))
    team = team_result.scalar_one_or_none()
    team_name = team.name if team else "Team"

    # Team averages
    team_avg_result = await db.execute(
        select(
            func.avg(ManagerProgress.skill_empathy),
            func.avg(ManagerProgress.skill_knowledge),
            func.avg(ManagerProgress.skill_objection_handling),
            func.avg(ManagerProgress.skill_stress_resistance),
            func.avg(ManagerProgress.skill_closing),
            func.avg(ManagerProgress.skill_qualification),
        ).join(User, User.id == ManagerProgress.user_id).where(User.team_id == team_id)
    )
    team_row = team_avg_result.one()

    platform_avg = await get_platform_benchmark(db)

    team_skills = {
        "empathy": float(team_row[0] or 50),
        "knowledge": float(team_row[1] or 50),
        "objection_handling": float(team_row[2] or 50),
        "stress_resistance": float(team_row[3] or 50),
        "closing": float(team_row[4] or 50),
        "qualification": float(team_row[5] or 50),
    }

    # Calculate percentile: how many teams have lower avg
    all_teams_result = await db.execute(
        select(User.team_id).where(User.team_id.isnot(None)).distinct()
    )
    all_team_ids = [r[0] for r in all_teams_result.all()]

    skills_data = []
    for s in SKILL_NAMES:
        skill_col = getattr(ManagerProgress, f"skill_{s}")
        # Count teams with lower average for this skill
        lower_count = 0
        for tid in all_team_ids:
            if tid == team_id:
                continue
            r = await db.execute(
                select(func.avg(skill_col)).join(
                    User, User.id == ManagerProgress.user_id
                ).where(User.team_id == tid)
            )
            other_avg = r.scalar()
            if other_avg and float(other_avg) < team_skills[s]:
                lower_count += 1

        percentile = int(lower_count / max(len(all_team_ids), 1) * 100)

        skills_data.append({
            "skill": s,
            "team_avg": round(team_skills[s], 1),
            "platform_avg": round(platform_avg[s], 1),
            "percentile": percentile,
        })

    # Sessions per week
    since = datetime.now(timezone.utc) - timedelta(days=7)
    member_ids = [m.id for m in await _get_team_members(team_id, db)]

    team_sessions_r = await db.execute(
        select(func.count(TrainingSession.id)).where(
            TrainingSession.user_id.in_(member_ids) if member_ids else False,
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= since,
        )
    ) if member_ids else None
    team_sessions = (team_sessions_r.scalar() or 0) if team_sessions_r else 0

    platform_sessions_r = await db.execute(
        select(func.count(TrainingSession.id)).where(
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= since,
        )
    )
    total_platform_sessions = platform_sessions_r.scalar() or 0
    total_teams = max(len(all_team_ids), 1)

    team_avg_score = sum(team_skills.values()) / len(team_skills)
    platform_avg_score = sum(platform_avg.values()) / len(platform_avg)

    return {
        "team_name": team_name,
        "skills": skills_data,
        "team_sessions_per_week": round(team_sessions / max(len(member_ids), 1), 1) if member_ids else 0,
        "platform_sessions_per_week": round(total_platform_sessions / total_teams, 1),
        "team_avg_score": round(team_avg_score, 1),
        "platform_avg_score": round(platform_avg_score, 1),
    }


# ═══════════════════════════════════════════════════════════════════════════
# TEAM TRENDS (weekly avg score over time)
# ═══════════════════════════════════════════════════════════════════════════

async def get_team_trends(
    team_id: uuid.UUID,
    db: AsyncSession,
    period: str = "month",
) -> dict:
    """Weekly trend data for team: avg score, session count, active managers.

    Args:
        period: "week" (4 weeks), "month" (12 weeks), "all" (26 weeks)
    """
    weeks_map = {"week": 4, "month": 12, "all": 26}
    num_weeks = weeks_map.get(period, 12)

    members = await _get_team_members(team_id, db)
    member_ids = [m.id for m in members]

    if not member_ids:
        return {"weeks": [], "period": period}

    now = datetime.now(timezone.utc)
    weeks_data = []

    for w in range(num_weeks):
        week_end = now - timedelta(weeks=w)
        week_start = week_end - timedelta(days=7)

        result = await db.execute(
            select(
                func.count(TrainingSession.id),
                func.avg(TrainingSession.score_total),
                func.count(func.distinct(TrainingSession.user_id)),
            ).where(
                TrainingSession.user_id.in_(member_ids),
                TrainingSession.status == SessionStatus.completed,
                TrainingSession.started_at >= week_start,
                TrainingSession.started_at < week_end,
            )
        )
        row = result.one()

        weeks_data.append({
            "week": week_start.strftime("%Y-%m-%d"),
            "sessions_count": row[0] or 0,
            "avg_score": round(float(row[1] or 0), 1),
            "active_managers": row[2] or 0,
        })

    weeks_data.reverse()

    return {"weeks": weeks_data, "period": period}


# ═══════════════════════════════════════════════════════════════════════════
# DAILY ACTIVITY (sessions per day)
# ═══════════════════════════════════════════════════════════════════════════

async def get_daily_activity(
    team_id: uuid.UUID,
    db: AsyncSession,
    days: int = 14,
) -> dict:
    """Daily session counts for team over the last N days."""
    members = await _get_team_members(team_id, db)
    member_ids = [m.id for m in members]

    if not member_ids:
        return {"days": [], "total_sessions": 0}

    now = datetime.now(timezone.utc)
    days_data = []
    total = 0

    for d in range(days):
        day_end = now - timedelta(days=d)
        day_start = day_end - timedelta(days=1)

        result = await db.execute(
            select(
                func.count(TrainingSession.id),
                func.count(func.distinct(TrainingSession.user_id)),
            ).where(
                TrainingSession.user_id.in_(member_ids),
                TrainingSession.status == SessionStatus.completed,
                TrainingSession.started_at >= day_start,
                TrainingSession.started_at < day_end,
            )
        )
        row = result.one()
        sessions = row[0] or 0
        total += sessions

        days_data.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "sessions": sessions,
            "managers_active": row[1] or 0,
        })

    days_data.reverse()

    return {"days": days_data, "total_sessions": total}
