"""
Сервис генерации еженедельных отчётов (ТЗ v5, Мастер ТЗ).

Собирает метрики за неделю, вычисляет тренды, ранжирует менеджеров,
формирует рекомендации и сохраняет в weekly_reports.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from statistics import mean

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import (
    ManagerProgress,
    SessionHistory,
    EarnedAchievement as Achievement,
    WeeklyReport,
    SKILL_NAMES,
)
from app.models.user import User
from app.services.manager_progress import ManagerProgressService
from scripts.seed_levels import get_level_name

logger = logging.getLogger(__name__)


def _week_bounds(ref: datetime | None = None) -> tuple[datetime, datetime]:
    """Понедельник 00:00 и воскресенье 23:59:59 для данной даты."""
    now = ref or datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return monday, sunday


def _score_trend(current_avg: float, prev_avg: float | None) -> str:
    """Определить тренд баллов: growing / stable / declining."""
    if prev_avg is None:
        return "new"
    diff = current_avg - prev_avg
    if diff > 3:
        return "growing"
    elif diff < -3:
        return "declining"
    return "stable"


def _build_recommendations(
    weak_points: list[dict],
    win_rate: float,
    sessions_count: int,
) -> list[str]:
    """Генерирует рекомендации на основе слабых мест и статистики."""
    recs: list[str] = []

    if sessions_count < 3:
        recs.append("Проведите минимум 3 тренировки в неделю для стабильного роста навыков")

    for wp in weak_points[:3]:
        skill = wp.get("skill", "")
        skill_labels = {
            "empathy": "эмпатию",
            "knowledge": "знание продукта",
            "objection_handling": "работу с возражениями",
            "stress_resistance": "стрессоустойчивость",
            "closing": "закрытие сделок",
            "qualification": "квалификацию клиента",
        }
        label = skill_labels.get(skill, skill)
        recs.append(f"Сфокусируйтесь на навыке «{label}» — он отстаёт от среднего")

    if win_rate < 30:
        recs.append("Попробуйте снизить сложность, чтобы закрепить базовые техники")
    elif win_rate > 70:
        recs.append("Отличный win rate! Попробуйте повысить сложность для развития")

    if not recs:
        recs.append("Продолжайте в том же темпе — вы на верном пути!")

    return recs


async def generate_weekly_report(
    db: AsyncSession,
    user_id: uuid.UUID,
    week_start: datetime | None = None,
) -> WeeklyReport:
    """
    Генерирует и сохраняет еженедельный отчёт.

    Если отчёт за данную неделю уже существует — обновляет его.
    """
    monday, sunday = _week_bounds(week_start)

    # ── Проверить дубликат ──
    existing = await db.execute(
        select(WeeklyReport).where(
            and_(
                WeeklyReport.user_id == user_id,
                WeeklyReport.week_start == monday,
            )
        )
    )
    report = existing.scalar_one_or_none()

    # ── Сессии за неделю ──
    result = await db.execute(
        select(SessionHistory)
        .where(
            and_(
                SessionHistory.user_id == user_id,
                SessionHistory.created_at >= monday,
                SessionHistory.created_at <= sunday,
            )
        )
        .order_by(SessionHistory.created_at)
    )
    sessions = list(result.scalars().all())

    sessions_count = len(sessions)
    total_time = sum(s.duration_seconds for s in sessions) // 60 if sessions else 0

    # ── Scores ──
    scores = [s.score_total for s in sessions] if sessions else []
    avg_score = round(mean(scores), 2) if scores else None
    best = max(scores) if scores else None
    worst = min(scores) if scores else None

    # ── Outcomes ──
    outcomes: dict[str, int] = {}
    for s in sessions:
        outcomes[s.outcome] = outcomes.get(s.outcome, 0) + 1
    deals = outcomes.get("deal", 0)
    win_rate = round(100 * deals / sessions_count, 2) if sessions_count > 0 else None

    # ── XP ──
    xp_earned = sum(s.xp_earned for s in sessions) if sessions else 0

    # ── Profile (level, skills) ──
    svc = ManagerProgressService(db)
    profile = await svc.get_or_create_profile(user_id)

    current_skills = profile.skills_dict()
    level_now = profile.current_level

    # ── Previous week report (for trend + rank change) ──
    prev_monday = monday - timedelta(days=7)
    prev_result = await db.execute(
        select(WeeklyReport).where(
            and_(
                WeeklyReport.user_id == user_id,
                WeeklyReport.week_start == prev_monday,
            )
        )
    )
    prev_report = prev_result.scalar_one_or_none()

    prev_avg = float(prev_report.average_score) if prev_report and prev_report.average_score else None
    trend = _score_trend(avg_score or 0, prev_avg)

    # Skills change
    prev_skills = prev_report.skills_snapshot if prev_report else {}
    skills_change: dict[str, int] = {}
    for sk in SKILL_NAMES:
        cur = current_skills.get(sk, 0)
        prev = prev_skills.get(sk, 0)
        skills_change[sk] = cur - prev

    level_start = prev_report.level_at_end if prev_report else level_now

    # ── Achievements ──
    ach_result = await db.execute(
        select(Achievement).where(
            and_(
                Achievement.user_id == user_id,
                Achievement.unlocked_at >= monday,
                Achievement.unlocked_at <= sunday,
            )
        )
    )
    week_achievements = [
        {"code": a.achievement_code, "name": a.achievement_name, "xp": a.xp_bonus}
        for a in ach_result.scalars().all()
    ]

    # ── Weak points ──
    weak_points = profile.weak_points or []

    # ── Recommendations ──
    recommendations = _build_recommendations(
        weak_points, win_rate or 0, sessions_count
    )

    # ── Ranking (по average_score среди всех менеджеров за эту неделю) ──
    rank_query = await db.execute(
        select(
            SessionHistory.user_id,
            func.avg(SessionHistory.score_total).label("avg_score"),
        )
        .where(
            and_(
                SessionHistory.created_at >= monday,
                SessionHistory.created_at <= sunday,
            )
        )
        .group_by(SessionHistory.user_id)
        .order_by(func.avg(SessionHistory.score_total).desc())
    )
    rankings = rank_query.all()
    weekly_rank = None
    for i, row in enumerate(rankings, 1):
        if row.user_id == user_id:
            weekly_rank = i
            break

    prev_rank = prev_report.weekly_rank if prev_report else None
    rank_change = (prev_rank - weekly_rank) if prev_rank and weekly_rank else None

    # ── Report text ──
    level_name = get_level_name(level_now)
    report_text = (
        f"За неделю {monday.strftime('%d.%m')}–{sunday.strftime('%d.%m')} "
        f"вы провели {sessions_count} тренировок ({total_time} мин). "
    )
    if avg_score:
        report_text += f"Средний балл: {avg_score:.0f}. "
    if trend == "growing":
        report_text += "Результаты растут — отличная динамика! "
    elif trend == "declining":
        report_text += "Результаты снизились — не сдавайтесь, проработайте слабые места. "
    if win_rate and win_rate > 0:
        report_text += f"Win rate: {win_rate:.0f}%. "
    if weekly_rank:
        report_text += f"Ваше место в рейтинге: #{weekly_rank}. "
    report_text += f"Уровень: {level_name} ({level_now})."

    # ── Save / Update ──
    if report is None:
        report = WeeklyReport(
            id=uuid.uuid4(),
            user_id=user_id,
            week_start=monday,
            week_end=sunday,
            level_at_start=level_start,
            level_at_end=level_now,
        )
        db.add(report)

    report.sessions_completed = sessions_count
    report.total_time_minutes = total_time
    report.average_score = avg_score
    report.best_score = best
    report.worst_score = worst
    report.score_trend = trend
    report.outcomes = outcomes
    report.win_rate = win_rate
    report.skills_snapshot = current_skills
    report.skills_change = skills_change
    report.xp_earned = xp_earned
    report.level_at_end = level_now
    report.new_achievements = week_achievements
    report.weak_points = weak_points
    report.recommendations = recommendations
    report.weekly_rank = weekly_rank
    report.rank_change = rank_change
    report.report_text = report_text

    await db.flush()

    logger.info(
        "Weekly report generated: user=%s week=%s sessions=%d avg=%.1f",
        user_id,
        monday.strftime("%Y-%m-%d"),
        sessions_count,
        avg_score or 0,
    )

    return report


async def generate_all_weekly_reports(db: AsyncSession) -> int:
    """
    Генерирует отчёты для ВСЕХ активных пользователей за текущую неделю.
    Предназначен для вызова из cron/scheduled task.
    """
    result = await db.execute(
        select(User.id).where(User.is_active.is_(True))
    )
    user_ids = [row[0] for row in result.all()]

    count = 0
    for uid in user_ids:
        try:
            await generate_weekly_report(db, uid)
            count += 1
        except Exception:
            logger.exception("Failed to generate weekly report for user %s", uid)

    await db.commit()
    logger.info("Generated %d weekly reports out of %d users", count, len(user_ids))
    return count
