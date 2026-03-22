"""Adaptive difficulty engine: keeps manager in the "zone of proximal development".

Algorithm:
1. Calculate user's rolling average from last N sessions
2. Determine target difficulty based on performance band
3. Select least-trained archetype for variety
4. Apply rotation logic (avoid repeating same archetype)
5. Return 3 recommended scenarios with reasoning

Performance bands:
  avg >= 85 → push UP (difficulty + 1..2)
  avg 60-84 → stay CURRENT (optimal zone)
  avg < 60  → ease DOWN (difficulty - 1..2)

Archetype rotation:
  - Untrained archetypes get highest priority
  - Least-played archetypes get secondary priority
  - Archetypes not played in 5+ days get rotation boost
  - Avoid recommending same archetype twice in a row
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character
from app.models.scenario import Scenario
from app.models.training import SessionStatus, TrainingSession

logger = logging.getLogger(__name__)


@dataclass
class DifficultyProfile:
    """User's current difficulty profile."""

    current_level: int  # 1-10
    target_level: int  # recommended next
    avg_score: float
    sessions_analyzed: int
    trend: str  # "up", "down", "stable"
    band: str  # "push", "optimal", "ease"


@dataclass
class RecommendedScenario:
    """A scenario recommendation with context."""

    scenario_id: uuid.UUID
    title: str
    description: str
    scenario_type: str
    difficulty: int
    archetype_slug: str
    archetype_name: str
    reason: str
    priority: int  # 1 = highest
    tags: list[str]  # e.g. ["untrained", "rotation", "challenge"]


# ── Performance bands ────────────────────────────────────────────────────────

PUSH_THRESHOLD = 85   # avg >= 85 → increase difficulty
EASE_THRESHOLD = 60   # avg < 60 → decrease difficulty
ANALYSIS_WINDOW = 10  # last N sessions to analyze


async def get_difficulty_profile(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> DifficultyProfile:
    """Calculate user's current difficulty level and target."""
    # Get last N completed sessions with scores
    result = await db.execute(
        select(TrainingSession.score_total, Scenario.difficulty)
        .join(Scenario, Scenario.id == TrainingSession.scenario_id)
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.score_total.isnot(None),
        )
        .order_by(TrainingSession.started_at.desc())
        .limit(ANALYSIS_WINDOW)
    )
    rows = result.all()

    if not rows:
        return DifficultyProfile(
            current_level=3,
            target_level=3,
            avg_score=0,
            sessions_analyzed=0,
            trend="stable",
            band="optimal",
        )

    scores = [float(r[0]) for r in rows]
    difficulties = [int(r[1]) for r in rows]

    avg_score = sum(scores) / len(scores)
    avg_difficulty = sum(difficulties) / len(difficulties)
    current_level = max(1, min(10, round(avg_difficulty)))

    # Determine band
    if avg_score >= PUSH_THRESHOLD:
        band = "push"
        target_level = min(10, current_level + 1)
        if avg_score >= 92:
            target_level = min(10, current_level + 2)
    elif avg_score < EASE_THRESHOLD:
        band = "ease"
        target_level = max(1, current_level - 1)
        if avg_score < 40:
            target_level = max(1, current_level - 2)
    else:
        band = "optimal"
        target_level = current_level

    # Trend detection (first half vs second half)
    trend = "stable"
    if len(scores) >= 4:
        mid = len(scores) // 2
        recent = sum(scores[:mid]) / mid
        older = sum(scores[mid:]) / (len(scores) - mid)
        delta = recent - older
        if delta > 5:
            trend = "up"
        elif delta < -5:
            trend = "down"

    return DifficultyProfile(
        current_level=current_level,
        target_level=target_level,
        avg_score=round(avg_score, 1),
        sessions_analyzed=len(rows),
        trend=trend,
        band=band,
    )


async def get_archetype_usage(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> dict[str, dict]:
    """Get per-archetype usage stats for rotation logic."""
    result = await db.execute(
        select(
            Character.slug,
            Character.name,
            func.count(TrainingSession.id).label("cnt"),
            func.max(TrainingSession.started_at).label("last_played"),
            func.avg(TrainingSession.score_total).label("avg_score"),
        )
        .join(Scenario, Scenario.id == TrainingSession.scenario_id)
        .join(Character, Character.id == Scenario.character_id)
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
        )
        .group_by(Character.slug, Character.name)
    )
    rows = result.all()

    usage = {}
    for slug, name, cnt, last, avg in rows:
        days_since = 999
        if last:
            days_since = (datetime.now(timezone.utc) - last).days

        usage[slug] = {
            "name": name,
            "count": cnt or 0,
            "last_played": last,
            "days_since": days_since,
            "avg_score": round(float(avg or 0), 1),
        }

    return usage


async def get_recommended_scenarios(
    user_id: uuid.UUID,
    db: AsyncSession,
    count: int = 3,
) -> list[RecommendedScenario]:
    """Generate smart scenario recommendations.

    Priority system:
    1. UNTRAINED archetype at target difficulty (explore new)
    2. WEAKEST archetype below 60 at current difficulty (train weakness)
    3. ROTATION: archetype not played in 5+ days (prevent skill decay)
    4. CHALLENGE: push difficulty if in "push" band (growth)
    5. VARIETY: random from pool (exploration)

    Each recommendation gets a Russian-language reason explaining WHY.
    """
    profile = await get_difficulty_profile(user_id, db)
    usage = await get_archetype_usage(user_id, db)

    # Get all active scenarios with characters
    scenario_result = await db.execute(
        select(Scenario, Character)
        .join(Character, Character.id == Scenario.character_id)
        .where(Scenario.is_active == True, Character.is_active == True)  # noqa: E712
        .order_by(Scenario.difficulty)
    )
    all_scenarios = scenario_result.all()

    if not all_scenarios:
        return []

    # Get all active character slugs
    all_chars = {char.slug: char.name for _, char in all_scenarios}

    # Find untrained archetypes
    untrained = [slug for slug in all_chars if slug not in usage]

    # Find weak archetypes (played but avg < 60)
    weak = [
        slug for slug, data in usage.items()
        if data["count"] >= 2 and data["avg_score"] < 60
    ]

    # Find stale archetypes (not played in 5+ days)
    stale = [
        slug for slug, data in usage.items()
        if data["days_since"] >= 5 and data["count"] > 0
    ]

    # Get last played archetype to avoid repeating
    last_result = await db.execute(
        select(Character.slug)
        .join(Scenario, Scenario.id == TrainingSession.scenario_id)
        .join(Character, Character.id == Scenario.character_id)
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
        )
        .order_by(TrainingSession.started_at.desc())
        .limit(1)
    )
    last_row = last_result.one_or_none()
    last_archetype = last_row[0] if last_row else None

    recommendations: list[RecommendedScenario] = []
    used_ids: set[uuid.UUID] = set()

    def _find(slug: str, diff_min: int, diff_max: int) -> tuple | None:
        for sc, ch in all_scenarios:
            if ch.slug == slug and sc.id not in used_ids:
                if diff_min <= sc.difficulty <= diff_max:
                    return sc, ch
        # Fallback: any difficulty
        for sc, ch in all_scenarios:
            if ch.slug == slug and sc.id not in used_ids:
                return sc, ch
        return None

    def _add(sc, ch, reason: str, priority: int, tags: list[str]):
        used_ids.add(sc.id)
        recommendations.append(RecommendedScenario(
            scenario_id=sc.id,
            title=sc.title,
            description=sc.description,
            scenario_type=sc.scenario_type.value,
            difficulty=sc.difficulty,
            archetype_slug=ch.slug,
            archetype_name=ch.name,
            reason=reason,
            priority=priority,
            tags=tags,
        ))

    target = profile.target_level

    # ── Priority 1: Untrained archetypes ──
    for slug in untrained:
        if slug == last_archetype:
            continue
        match = _find(slug, max(1, target - 2), target)
        if match:
            sc, ch = match
            _add(sc, ch,
                 f"Вы ещё не пробовали архетип «{ch.name}». Начните с него для расширения опыта.",
                 1, ["untrained", "explore"])
        if len(recommendations) >= 1:
            break

    # ── Priority 2: Weakest archetype ──
    for slug in sorted(weak, key=lambda s: usage[s]["avg_score"]):
        if slug == last_archetype:
            continue
        match = _find(slug, max(1, target - 1), target + 1)
        if match:
            sc, ch = match
            avg = usage[slug]["avg_score"]
            _add(sc, ch,
                 f"Архетип «{ch.name}» — ваша зона роста (avg {avg:.0f}). Практика закрепит навык.",
                 2, ["weakness", "practice"])
        if len(recommendations) >= 2:
            break

    # ── Priority 3: Rotation (stale) ──
    for slug in sorted(stale, key=lambda s: usage[s]["days_since"], reverse=True):
        if slug == last_archetype or len(recommendations) >= 2:
            continue
        match = _find(slug, max(1, target - 1), target + 1)
        if match:
            sc, ch = match
            days = usage[slug]["days_since"]
            _add(sc, ch,
                 f"Вы не тренировались с «{ch.name}» {days} дней. Навыки теряются без практики.",
                 3, ["rotation", "refresh"])

    # ── Priority 4: Challenge (push band) ──
    if profile.band == "push" and len(recommendations) < count:
        # Find hardest scenario user hasn't mastered
        for sc, ch in reversed(all_scenarios):
            if sc.id not in used_ids and ch.slug != last_archetype:
                if sc.difficulty >= target:
                    _add(sc, ch,
                         f"Вы показываете отличные результаты ({profile.avg_score:.0f}). Попробуйте сложнее!",
                         4, ["challenge", "growth"])
                    break

    # ── Priority 5: Fill to count ──
    for sc, ch in all_scenarios:
        if len(recommendations) >= count:
            break
        if sc.id not in used_ids and ch.slug != last_archetype:
            if abs(sc.difficulty - target) <= 2:
                _add(sc, ch,
                     "Для разнообразия — попробуйте этот сценарий.",
                     5, ["variety"])

    recommendations.sort(key=lambda r: r.priority)
    return recommendations[:count]
