"""Behavioral Intelligence — Progress/Regression Detector.

Analyzes manager's performance trends to detect:
- Improvement (score growth over time)
- Decline/regression (score drop, skill degradation)
- Stagnation (no change despite practice)
- Fatigue (declining performance within a day)

Generates alerts for ROP when a manager needs attention.
Provides predictions for skill growth.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.behavior import (
    BehaviorSnapshot, EmotionProfile, ProgressTrend,
    TrendDirection, AlertSeverity,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

DECLINE_THRESHOLD = -5.0  # Score drop > 5 = declining
IMPROVE_THRESHOLD = 3.0   # Score growth > 3 = improving
STAGNATION_SESSIONS = 10  # No change after 10 sessions = stagnating

ALERT_DECLINE_DAYS = 3    # 3+ days declining = warning
ALERT_CRITICAL_DAYS = 5   # 5+ days declining = critical


# ═══════════════════════════════════════════════════════════════════════════════
# Trend detection
# ═══════════════════════════════════════════════════════════════════════════════


async def detect_trends(
    user_id: uuid.UUID,
    db: AsyncSession,
    period_days: int = 7,
) -> ProgressTrend | None:
    """Detect progress/regression trends for a user.

    Compares recent period vs previous period of same length.
    Creates ProgressTrend record with alerts if needed.
    """
    now = datetime.now(timezone.utc)
    period_end = now
    period_start = now - timedelta(days=period_days)
    prev_start = period_start - timedelta(days=period_days)

    # Get snapshots for current and previous periods
    current_snapshots = await _get_snapshots(user_id, period_start, period_end, db)
    prev_snapshots = await _get_snapshots(user_id, prev_start, period_start, db)

    if not current_snapshots:
        return None  # No data for current period

    # Calculate averages
    current_avg = _average_metrics(current_snapshots)
    prev_avg = _average_metrics(prev_snapshots) if prev_snapshots else current_avg

    # Determine overall direction
    score_delta = current_avg["confidence"] - prev_avg["confidence"]

    if score_delta > IMPROVE_THRESHOLD:
        direction = TrendDirection.improving
    elif score_delta < DECLINE_THRESHOLD:
        direction = TrendDirection.declining
    elif len(current_snapshots) > STAGNATION_SESSIONS and abs(score_delta) < 1.0:
        direction = TrendDirection.stagnating
    else:
        direction = TrendDirection.stable

    # Per-skill trends
    skill_trends = {}
    for metric in ["confidence", "stress_resistance", "adaptability"]:
        delta = current_avg[metric] - prev_avg[metric]
        if delta > IMPROVE_THRESHOLD:
            skill_trends[metric] = {"direction": "improving", "delta": round(delta, 1)}
        elif delta < DECLINE_THRESHOLD:
            skill_trends[metric] = {"direction": "declining", "delta": round(delta, 1)}
        else:
            skill_trends[metric] = {"direction": "stable", "delta": round(delta, 1)}

    # Generate alerts
    alert_severity, alert_message = _generate_alert(
        direction, score_delta, current_avg, current_snapshots, user_id
    )

    # Simple prediction
    predicted_score_7d = None
    if len(current_snapshots) >= 3:
        # Linear extrapolation
        daily_rate = score_delta / max(period_days, 1)
        predicted_score_7d = round(current_avg["confidence"] + daily_rate * 7, 1)
        predicted_score_7d = max(0, min(100, predicted_score_7d))

    # Create trend record
    trend = ProgressTrend(
        user_id=user_id,
        period_start=period_start,
        period_end=period_end,
        period_type="weekly" if period_days >= 7 else "daily",
        direction=direction,
        score_delta=round(score_delta, 1),
        skill_trends=skill_trends,
        confidence_trend=skill_trends.get("confidence", {}).get("direction"),
        stress_trend=skill_trends.get("stress_resistance", {}).get("direction"),
        adaptability_trend=skill_trends.get("adaptability", {}).get("direction"),
        alert_severity=alert_severity,
        alert_message=alert_message,
        sessions_count=len(current_snapshots),
        predicted_score_in_7d=predicted_score_7d,
    )
    db.add(trend)
    await db.flush()

    if alert_severity:
        logger.info(
            "ProgressTrend alert: user=%s direction=%s severity=%s delta=%.1f",
            user_id, direction.value, alert_severity.value, score_delta,
        )

    return trend


async def get_user_trend_history(
    user_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 12,
) -> list[ProgressTrend]:
    """Get recent trend records for a user."""
    result = await db.execute(
        select(ProgressTrend)
        .where(ProgressTrend.user_id == user_id)
        .order_by(ProgressTrend.period_end.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_team_alerts(
    team_user_ids: list[uuid.UUID],
    db: AsyncSession,
    unseen_only: bool = True,
) -> list[ProgressTrend]:
    """Get alerts for ROP — team members with declining trends."""
    stmt = (
        select(ProgressTrend)
        .where(
            ProgressTrend.user_id.in_(team_user_ids),
            ProgressTrend.alert_severity.isnot(None),
        )
        .order_by(ProgressTrend.created_at.desc())
        .limit(50)
    )
    if unseen_only:
        stmt = stmt.where(ProgressTrend.alert_seen_by_rop.is_(False))
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════════


async def _get_snapshots(
    user_id: uuid.UUID,
    start: datetime,
    end: datetime,
    db: AsyncSession,
) -> list[BehaviorSnapshot]:
    result = await db.execute(
        select(BehaviorSnapshot)
        .where(
            BehaviorSnapshot.user_id == user_id,
            BehaviorSnapshot.created_at >= start,
            BehaviorSnapshot.created_at < end,
        )
        .order_by(BehaviorSnapshot.created_at)
    )
    return list(result.scalars().all())


def _average_metrics(snapshots: list[BehaviorSnapshot]) -> dict:
    """Average key metrics across snapshots."""
    n = len(snapshots)
    if n == 0:
        return {"confidence": 50, "stress_resistance": 50, "adaptability": 50}
    return {
        "confidence": sum(s.confidence_score for s in snapshots) / n,
        "stress_resistance": sum(100 - s.stress_level for s in snapshots) / n,
        "adaptability": sum(s.adaptability_score for s in snapshots) / n,
    }


def _generate_alert(
    direction: TrendDirection,
    score_delta: float,
    current_avg: dict,
    snapshots: list[BehaviorSnapshot],
    user_id: uuid.UUID,
) -> tuple[AlertSeverity | None, str | None]:
    """Generate alert if trend warrants ROP attention."""
    if direction == TrendDirection.declining:
        if score_delta < -15:
            return (
                AlertSeverity.critical,
                f"Менеджер показывает резкое снижение уверенности (−{abs(score_delta):.0f} за период). "
                f"Текущий уровень: {current_avg['confidence']:.0f}/100. Рекомендуется личная беседа.",
            )
        elif score_delta < -8:
            return (
                AlertSeverity.warning,
                f"Наблюдается снижение показателей (−{abs(score_delta):.0f}). "
                f"Уверенность: {current_avg['confidence']:.0f}/100. "
                f"Рекомендуется дополнительная тренировка.",
            )
        return (
            AlertSeverity.info,
            f"Небольшое снижение показателей (−{abs(score_delta):.0f}). Мониторинг продолжается.",
        )

    if direction == TrendDirection.stagnating and current_avg["confidence"] < 50:
        return (
            AlertSeverity.warning,
            f"Менеджер стагнирует на низком уровне ({current_avg['confidence']:.0f}/100 за {len(snapshots)} сессий). "
            f"Рекомендуется смена подхода к обучению.",
        )

    return None, None
