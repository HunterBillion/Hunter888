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

from sqlalchemy import func, literal_column, select, case
from sqlalchemy.ext.asyncio import AsyncSession


def _trunc(interval: str, col):
    """date_trunc with literal interval to avoid asyncpg GROUP BY mismatch."""
    return func.date_trunc(literal_column(f"'{interval}'"), col)

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


# ═══════════════════════════════════════════════════════════════════════════
# BATCH HELPERS — S2-07b: eliminate N+1 queries in team analytics
# ═══════════════════════════════════════════════════════════════════════════


def _progress_to_skills(progress: ManagerProgress) -> dict[str, float]:
    """Extract 6 skills from ManagerProgress row. Safe for None values."""
    return {
        "empathy": float(progress.skill_empathy or 50),
        "knowledge": float(progress.skill_knowledge or 50),
        "objection_handling": float(progress.skill_objection_handling or 50),
        "stress_resistance": float(progress.skill_stress_resistance or 50),
        "closing": float(progress.skill_closing or 50),
        "qualification": float(progress.skill_qualification or 50),
    }


async def _batch_member_skills(
    member_ids: list[uuid.UUID], db: AsyncSession,
) -> dict[uuid.UUID, dict[str, float]]:
    """Batch-load skills for all members in one query."""
    default = {s: 50.0 for s in SKILL_NAMES}
    if not member_ids:
        return {}
    result = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id.in_(member_ids))
    )
    by_user = {p.user_id: _progress_to_skills(p) for p in result.scalars().all()}
    return {uid: by_user.get(uid, dict(default)) for uid in member_ids}


async def _batch_session_stats(
    member_ids: list[uuid.UUID], db: AsyncSession, days: int = 7,
) -> dict[uuid.UUID, dict]:
    """Batch-load session count + avg score for all members in one query.

    Returns {user_id: {"count": int, "avg_score": float}}.
    """
    if not member_ids:
        return {}
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            TrainingSession.user_id,
            func.count(TrainingSession.id).label("cnt"),
            func.avg(TrainingSession.score_total).label("avg"),
        ).where(
            TrainingSession.user_id.in_(member_ids),
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= since,
        ).group_by(TrainingSession.user_id)
    )
    stats = {
        row.user_id: {"count": row.cnt, "avg_score": float(row.avg or 0)}
        for row in result.all()
    }
    for uid in member_ids:
        if uid not in stats:
            stats[uid] = {"count": 0, "avg_score": 0.0}
    return stats


async def _batch_score_trends(
    member_ids: list[uuid.UUID], db: AsyncSession,
) -> dict[uuid.UUID, str]:
    """Batch-load score trends for all members in TWO queries (not 2×N)."""
    if not member_ids:
        return {}
    now = datetime.now(timezone.utc)
    week1_start = now - timedelta(days=14)
    week1_end = now - timedelta(days=7)

    # Week 1 (older) averages — one query for all members
    r1 = await db.execute(
        select(
            TrainingSession.user_id,
            func.avg(TrainingSession.score_total).label("avg"),
        ).where(
            TrainingSession.user_id.in_(member_ids),
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= week1_start,
            TrainingSession.started_at < week1_end,
        ).group_by(TrainingSession.user_id)
    )
    avg1 = {row.user_id: float(row.avg) for row in r1.all() if row.avg is not None}

    # Week 2 (recent) averages — one query for all members
    r2 = await db.execute(
        select(
            TrainingSession.user_id,
            func.avg(TrainingSession.score_total).label("avg"),
        ).where(
            TrainingSession.user_id.in_(member_ids),
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= week1_end,
        ).group_by(TrainingSession.user_id)
    )
    avg2 = {row.user_id: float(row.avg) for row in r2.all() if row.avg is not None}

    trends = {}
    for uid in member_ids:
        a1, a2 = avg1.get(uid), avg2.get(uid)
        if a1 is None or a2 is None:
            trends[uid] = "stable"
        else:
            diff = a2 - a1
            trends[uid] = "improving" if diff > 5 else ("declining" if diff < -5 else "stable")
    return trends


async def _batch_last_session(
    member_ids: list[uuid.UUID], db: AsyncSession,
) -> dict[uuid.UUID, datetime | None]:
    """Batch-load last session time for all members in one query."""
    if not member_ids:
        return {}
    result = await db.execute(
        select(
            TrainingSession.user_id,
            func.max(TrainingSession.started_at).label("last_at"),
        ).where(
            TrainingSession.user_id.in_(member_ids),
            TrainingSession.status == SessionStatus.completed,
        ).group_by(TrainingSession.user_id)
    )
    by_user = {row.user_id: row.last_at for row in result.all()}
    return {uid: by_user.get(uid) for uid in member_ids}


# Legacy single-user helpers (kept for backward compatibility)

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

    r1 = await db.execute(
        select(func.avg(TrainingSession.score_total)).where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= week1_start,
            TrainingSession.started_at < week1_end,
        )
    )
    avg1 = r1.scalar()

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
    """Build skill heatmap for team: rows=managers, cols=6 skills.

    S2-07b: Uses batch queries — 4 total instead of 3×N.
    """
    members = await _get_team_members(team_id, db)

    team_result = await db.execute(select(Team).where(Team.id == team_id))
    team = team_result.scalar_one_or_none()
    team_name = team.name if team else "Team"

    member_ids = [m.id for m in members]

    # 3 batch queries instead of 3×N individual queries
    all_skills = await _batch_member_skills(member_ids, db)
    all_trends = await _batch_score_trends(member_ids, db)
    all_stats = await _batch_session_stats(member_ids, db, days=7)

    rows = []
    skill_sums: dict[str, float] = {s: 0.0 for s in SKILL_NAMES}
    count = 0

    for member in members:
        skills = all_skills.get(member.id, {s: 50.0 for s in SKILL_NAMES})
        trend = all_trends.get(member.id, "stable")
        sessions_week = all_stats.get(member.id, {}).get("count", 0)

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
    """Identify managers needing attention.

    S2-07b: Uses batch queries — 4 total instead of 5×N.
    """
    members = await _get_team_members(team_id, db)
    manager_members = [m for m in members if m.role == UserRole.manager]
    member_ids = [m.id for m in manager_members]

    # 4 batch queries instead of 5×N individual queries
    all_trends = await _batch_score_trends(member_ids, db)
    all_stats_14d = await _batch_session_stats(member_ids, db, days=14)
    all_stats_7d = await _batch_session_stats(member_ids, db, days=7)
    all_last = await _batch_last_session(member_ids, db)

    needs_attention = []
    now = datetime.now(timezone.utc)

    for member in manager_members:
        reasons = []
        trend = all_trends.get(member.id, "stable")
        avg_score = all_stats_14d.get(member.id, {}).get("avg_score", 0.0)
        sessions_week = all_stats_7d.get(member.id, {}).get("count", 0)
        last_session = all_last.get(member.id)

        if trend == "declining":
            reasons.append("Результаты снижаются последние 2 недели")
        if avg_score > 0 and avg_score < 50:
            reasons.append(f"Средний балл ниже 50 ({avg_score:.0f})")
        if sessions_week == 0:
            reasons.append("Нет тренировок на этой неделе")
        if last_session and (now - last_session).days > 7:
            reasons.append(f"Неактивен {(now - last_session).days} дней")

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
    """Compare each manager's skills against team average.

    S2-07b: Uses batch queries — 2 total instead of 2×N.
    """
    members = await _get_team_members(team_id, db)

    team_result = await db.execute(select(Team).where(Team.id == team_id))
    team = team_result.scalar_one_or_none()
    team_name = team.name if team else "Team"

    member_ids = [m.id for m in members]
    all_skills = await _batch_member_skills(member_ids, db)
    all_stats = await _batch_session_stats(member_ids, db, days=7)

    # Collect all member skills
    member_data = []
    for member in members:
        skills = all_skills.get(member.id, {s: 50.0 for s in SKILL_NAMES})
        sessions = all_stats.get(member.id, {}).get("count", 0)
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
    """Calculate ROI: correlation between training hours and score improvement.

    S2-07b: Single aggregated query instead of 4×N_weeks.
    """
    members = await _get_team_members(team_id, db)
    member_ids = [m.id for m in members]

    if not member_ids:
        return {"data_points": [], "correlation": 0.0, "summary": "Нет данных"}

    now = datetime.now(timezone.utc)
    since = now - timedelta(weeks=weeks + 1)  # +1 for delta calculation

    # ONE query: weekly aggregates for all weeks at once
    from sqlalchemy import text as sa_text
    weekly_result = await db.execute(
        select(
            _trunc("week", TrainingSession.started_at).label("week_start"),
            func.count(TrainingSession.id).label("sessions"),
            func.sum(TrainingSession.duration_seconds).label("total_seconds"),
            func.avg(TrainingSession.score_total).label("avg_score"),
        ).where(
            TrainingSession.user_id.in_(member_ids),
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= since,
        ).group_by(
            _trunc("week", TrainingSession.started_at)
        ).order_by(
            _trunc("week", TrainingSession.started_at)
        )
    )
    weekly_rows = weekly_result.all()

    # Build lookup by week
    week_data = {}
    for row in weekly_rows:
        week_key = row.week_start
        week_data[week_key] = {
            "sessions": row.sessions or 0,
            "hours": round((row.total_seconds or 0) / 3600, 1),
            "avg_score": float(row.avg_score) if row.avg_score else None,
        }

    data_points = []
    hours_list = []
    delta_list = []

    for w in range(weeks):
        week_end = now - timedelta(weeks=w)
        week_start = week_end - timedelta(days=7)
        prev_week_start = week_start - timedelta(days=7)

        # Find matching week in aggregated data (date_trunc rounds to Monday)
        wk = None
        prev_wk = None
        for key, val in week_data.items():
            if key and abs((key - week_start).total_seconds()) < 86400 * 2:
                wk = val
            if key and abs((key - prev_week_start).total_seconds()) < 86400 * 2:
                prev_wk = val

        hours = wk["hours"] if wk else 0.0
        sessions = wk["sessions"] if wk else 0
        curr_avg = wk["avg_score"] if wk else None
        prev_avg = prev_wk["avg_score"] if prev_wk else None
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

    # S2-07b: Calculate percentiles in ONE query instead of 6 × N_teams
    # Get per-team skill averages for ALL teams in a single query
    all_team_avgs_result = await db.execute(
        select(
            User.team_id,
            func.avg(ManagerProgress.skill_empathy).label("empathy"),
            func.avg(ManagerProgress.skill_knowledge).label("knowledge"),
            func.avg(ManagerProgress.skill_objection_handling).label("objection_handling"),
            func.avg(ManagerProgress.skill_stress_resistance).label("stress_resistance"),
            func.avg(ManagerProgress.skill_closing).label("closing"),
            func.avg(ManagerProgress.skill_qualification).label("qualification"),
        )
        .join(User, User.id == ManagerProgress.user_id)
        .where(User.team_id.isnot(None))
        .group_by(User.team_id)
    )
    all_team_avgs = all_team_avgs_result.all()
    total_teams = max(len(all_team_avgs), 1)

    skills_data = []
    for s in SKILL_NAMES:
        # Count teams with lower average for this skill
        lower_count = sum(
            1 for row in all_team_avgs
            if row.team_id != team_id
            and getattr(row, s) is not None
            and float(getattr(row, s)) < team_skills[s]
        )
        percentile = int(lower_count / total_teams * 100)

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
    total_teams = max(len(all_team_avgs), 1)

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

    # S2-07b: Single GROUP BY query instead of N_weeks separate queries
    now = datetime.now(timezone.utc)
    since = now - timedelta(weeks=num_weeks)

    result = await db.execute(
        select(
            _trunc("week", TrainingSession.started_at).label("week_start"),
            func.count(TrainingSession.id).label("sessions"),
            func.avg(TrainingSession.score_total).label("avg_score"),
            func.count(func.distinct(TrainingSession.user_id)).label("active"),
        ).where(
            TrainingSession.user_id.in_(member_ids),
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= since,
        ).group_by(
            _trunc("week", TrainingSession.started_at)
        ).order_by(
            _trunc("week", TrainingSession.started_at)
        )
    )
    rows = result.all()

    # Build lookup, then fill in any missing weeks with zeros
    by_week = {}
    for row in rows:
        if row.week_start:
            by_week[row.week_start.strftime("%Y-%m-%d")] = {
                "sessions_count": row.sessions or 0,
                "avg_score": round(float(row.avg_score or 0), 1),
                "active_managers": row.active or 0,
            }

    weeks_data = []
    for w in range(num_weeks):
        week_end = now - timedelta(weeks=w)
        week_start = week_end - timedelta(days=7)
        key = week_start.strftime("%Y-%m-%d")
        # Match by closest week (date_trunc may differ by a day)
        matched = by_week.get(key)
        if not matched:
            # Try adjacent days for date_trunc alignment
            for offset in range(-2, 3):
                alt_key = (week_start + timedelta(days=offset)).strftime("%Y-%m-%d")
                if alt_key in by_week:
                    matched = by_week[alt_key]
                    break

        weeks_data.append({
            "week": key,
            "sessions_count": matched["sessions_count"] if matched else 0,
            "avg_score": matched["avg_score"] if matched else 0.0,
            "active_managers": matched["active_managers"] if matched else 0,
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

    # S2-07b: Single GROUP BY query instead of N_days separate queries
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    result = await db.execute(
        select(
            _trunc("day", TrainingSession.started_at).label("day"),
            func.count(TrainingSession.id).label("sessions"),
            func.count(func.distinct(TrainingSession.user_id)).label("active"),
        ).where(
            TrainingSession.user_id.in_(member_ids),
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= since,
        ).group_by(
            _trunc("day", TrainingSession.started_at)
        ).order_by(
            _trunc("day", TrainingSession.started_at)
        )
    )
    by_day = {}
    for row in result.all():
        if row.day:
            by_day[row.day.strftime("%Y-%m-%d")] = {
                "sessions": row.sessions or 0,
                "managers_active": row.active or 0,
            }

    days_data = []
    total = 0

    for d in range(days):
        day_end = now - timedelta(days=d)
        day_start = day_end - timedelta(days=1)
        key = day_start.strftime("%Y-%m-%d")
        matched = by_day.get(key, {"sessions": 0, "managers_active": 0})
        total += matched["sessions"]
        days_data.append({"date": key, **matched})

    days_data.reverse()

    return {"days": days_data, "total_sessions": total}
