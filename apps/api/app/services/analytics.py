"""Analytics engine v5: weak spots, progress charts, skill radar, cross-session trends.

Diagnostic engine that:
1. Identifies WHERE the manager is weak (specific skill × specific archetype)
2. Tracks HOW they improve over time (weekly cohorts with trend detection)
3. Computes SKILL RADAR (6 canonical skills derived from 10 scoring layers)
4. Analyzes STORY ARCS (multi-call session progression)
5. Recommends WHAT to train next (adaptive difficulty + archetype rotation)
6. Detects PATTERNS the manager doesn't see (regression, plateau, fear avoidance)
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character
from app.models.scenario import Scenario
from app.models.training import Message, MessageRole, SessionStatus, TrainingSession

logger = logging.getLogger(__name__)


# ─── Data structures ────────────────────────────────────────────────────────


@dataclass
class WeakSpot:
    """A specific weakness identified from session history."""
    skill: str               # e.g. "objection_handling", "empathy" (radar skill)
    sub_skill: str | None    # e.g. "acknowledged", "clarified"
    avg_score: float
    max_possible: float
    pct: float               # avg_score / max_possible * 100
    trend: str               # "improving", "declining", "stagnant"
    trend_delta: float
    archetype: str | None    # if weakness is archetype-specific
    recommendation: str      # Russian advice


@dataclass
class ProgressPoint:
    """A single data point on the progress chart."""
    period_start: date
    period_end: date
    sessions_count: int
    avg_total: float
    avg_script: float
    avg_objection: float
    avg_communication: float
    avg_anti_patterns: float
    avg_result: float
    avg_human_factor: float
    avg_narrative: float
    avg_legal: float
    best_score: float
    worst_score: float
    # Skill radar averages for this period
    radar: dict[str, float] = field(default_factory=dict)


@dataclass
class ArchetypeScore:
    """Performance breakdown per character archetype."""
    archetype_slug: str
    archetype_name: str
    sessions_count: int
    avg_score: float
    best_score: float
    worst_score: float
    avg_script: float
    avg_objection: float
    avg_communication: float
    avg_anti_patterns: float
    avg_result: float
    avg_human_factor: float
    last_played: datetime | None
    mastery_level: str
    radar: dict[str, float] = field(default_factory=dict)


@dataclass
class ScenarioRecommendation:
    """A recommended next scenario with reasoning."""
    scenario_id: uuid.UUID
    scenario_title: str
    archetype_slug: str
    scenario_type: str
    difficulty: int
    reason: str
    priority: int


@dataclass
class StoryArcSummary:
    """Analytics for a multi-call story arc."""
    story_id: uuid.UUID
    story_name: str
    calls_completed: int
    calls_planned: int
    is_completed: bool
    avg_score: float
    score_trend: str           # "improving", "declining", "stagnant"
    skill_growth: dict[str, float]  # radar delta from first to last call
    best_call: int
    worst_call: int
    key_moments: list[dict]    # [{call, type, detail}]


@dataclass
class SkillRadarSnapshot:
    """Aggregated skill radar for a user over a time period."""
    empathy: float             # 0-100
    knowledge: float           # 0-100
    objection_handling: float  # 0-100
    stress_resistance: float   # 0-100
    closing: float             # 0-100
    qualification: float       # 0-100

    def to_dict(self) -> dict[str, float]:
        return {
            "empathy": self.empathy,
            "knowledge": self.knowledge,
            "objection_handling": self.objection_handling,
            "stress_resistance": self.stress_resistance,
            "closing": self.closing,
            "qualification": self.qualification,
        }


@dataclass
class AnalyticsSnapshot:
    """Full analytics picture for a user."""
    weak_spots: list[WeakSpot]
    progress: list[ProgressPoint]
    archetype_scores: list[ArchetypeScore]
    recommendations: list[ScenarioRecommendation]
    insights: list[str]
    skill_radar: SkillRadarSnapshot
    story_arcs: list[StoryArcSummary]
    meta: dict


# ─── Skill definitions (v5 rescaled) ─────────────────────────────────────────

SKILLS_V5 = {
    "script_adherence": {"max": 22.5, "label": "Следование скрипту", "weight": 0.225},
    "objection_handling": {"max": 18.75, "label": "Работа с возражениями", "weight": 0.1875},
    "communication": {"max": 15.0, "label": "Коммуникация", "weight": 0.15},
    "anti_patterns": {"max": 0.0, "label": "Антипаттерны", "weight": 0.1125},
    "result": {"max": 7.5, "label": "Результат", "weight": 0.075},
    "chain_traversal": {"max": 7.5, "label": "Цепочки возражений", "weight": 0.075},
    "trap_handling": {"max": 7.5, "label": "Ловушки", "weight": 0.075},
    "human_factor": {"max": 15.0, "label": "Человеческий фактор", "weight": 0.15},
    "narrative": {"max": 10.0, "label": "Нарратив", "weight": 0.10},
    "legal": {"max": 5.0, "label": "Юр. точность", "weight": 0.05},
}

# 6 canonical radar skills
RADAR_SKILLS = {
    "empathy": "Эмпатия",
    "knowledge": "Знания",
    "objection_handling": "Работа с возражениями",
    "stress_resistance": "Стрессоустойчивость",
    "closing": "Закрытие сделки",
    "qualification": "Квалификация клиента",
}

OBJECTION_SUB_SKILLS = ["heard", "acknowledged", "clarified", "argued", "checked"]

MASTERY_THRESHOLDS = {
    "untrained": 0,
    "beginner": 1,
    "intermediate": 3,
    "advanced": 7,
    "mastered": 15,
}


# ─── Core analytics functions ─────────────────────────────────────────────────


async def get_user_sessions(
    user_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 50,
    completed_only: bool = True,
) -> list[TrainingSession]:
    """Fetch user's training sessions with scores, ordered by date desc."""
    query = (
        select(TrainingSession)
        .where(TrainingSession.user_id == user_id)
        .order_by(TrainingSession.started_at.desc())
        .limit(limit)
    )
    if completed_only:
        query = query.where(TrainingSession.status == SessionStatus.completed)

    result = await db.execute(query)
    return list(result.scalars().all())


# ─── Skill Radar ─────────────────────────────────────────────────────────────


def compute_session_radar(session: TrainingSession) -> dict[str, float]:
    """Compute 6-skill radar from a single session's scoring_details.

    Uses the same formula as ScoreBreakdown.skill_radar but from stored data.
    """
    details = session.scoring_details or {}

    def _norm(val: float, mx: float) -> float:
        if mx <= 0:
            return 0.0
        return max(0.0, min(1.0, val / mx))

    # Pull sub-scores from details
    comm = details.get("communication", {})
    hf = details.get("human_factor", {})
    script = details.get("script_adherence", {})
    obj = details.get("objection_handling", {})

    empathy_l3 = comm.get("empathy_score", 0)
    empathy_l8_patience = hf.get("patience_score", 0)
    empathy_l8_empathy = hf.get("empathy_check_score", 0)
    empathy = (
        _norm(empathy_l3, 3.75) * 0.4
        + _norm(empathy_l8_patience, 5) * 0.3
        + _norm(empathy_l8_empathy, 5) * 0.3
    ) * 100

    l1 = session.score_script_adherence or 0
    l10 = session.score_legal or 0
    l7 = getattr(session, "_trap_score", 0)  # May not be stored separately
    # Use scoring_details for trap
    trap_details = details.get("trap_handling", {})
    l7 = trap_details.get("net_score", 0)

    knowledge = (
        _norm(l1, 22.5) * 0.3
        + _norm(l10 + 5, 10) * 0.4
        + _norm(l7 + 7.5, 15) * 0.3
    ) * 100

    l2 = session.score_objection_handling or 0
    l6_details = details.get("chain_traversal", {})
    l6 = l6_details.get("chain_score", 0) if isinstance(l6_details, dict) else 0
    objection_handling = (
        _norm(l2, 18.75) * 0.5
        + _norm(l6, 7.5) * 0.3
        + _norm(l7 + 7.5, 15) * 0.2
    ) * 100

    l4 = session.score_anti_patterns or 0
    composure = hf.get("composure_score", 0)
    pace = comm.get("pace_score", 0)
    stress_resistance = (
        _norm(l4 + 11.25, 11.25) * 0.4
        + _norm(composure, 5) * 0.3
        + _norm(pace, 3.75) * 0.3
    ) * 100

    l5 = session.score_result or 0
    l9 = session.score_narrative or 0
    check_score = obj.get("check_score", 0)
    closing = (
        _norm(l5, 7.5) * 0.5
        + _norm(l9, 10) * 0.3
        + _norm(check_score, 3.75) * 0.2
    ) * 100

    discovery = script.get("discovery_score", 0)
    control = comm.get("control_score", 0)
    listening = comm.get("listening_score", 0)
    qualification = (
        _norm(discovery, 10) * 0.4
        + _norm(control, 3.75) * 0.3
        + _norm(listening, 3.75) * 0.3
    ) * 100

    return {
        "empathy": round(min(100, max(0, empathy)), 1),
        "knowledge": round(min(100, max(0, knowledge)), 1),
        "objection_handling": round(min(100, max(0, objection_handling)), 1),
        "stress_resistance": round(min(100, max(0, stress_resistance)), 1),
        "closing": round(min(100, max(0, closing)), 1),
        "qualification": round(min(100, max(0, qualification)), 1),
    }


def aggregate_radar(sessions: list[TrainingSession]) -> SkillRadarSnapshot:
    """Compute average skill radar across multiple sessions."""
    if not sessions:
        return SkillRadarSnapshot(0, 0, 0, 0, 0, 0)

    totals: dict[str, float] = {k: 0.0 for k in RADAR_SKILLS}
    count = 0

    for s in sessions:
        radar = compute_session_radar(s)
        for k in totals:
            totals[k] += radar.get(k, 0)
        count += 1

    if count == 0:
        return SkillRadarSnapshot(0, 0, 0, 0, 0, 0)

    return SkillRadarSnapshot(
        empathy=round(totals["empathy"] / count, 1),
        knowledge=round(totals["knowledge"] / count, 1),
        objection_handling=round(totals["objection_handling"] / count, 1),
        stress_resistance=round(totals["stress_resistance"] / count, 1),
        closing=round(totals["closing"] / count, 1),
        qualification=round(totals["qualification"] / count, 1),
    )


# ─── Weak spot analysis ──────────────────────────────────────────────────────


async def analyze_weak_spots(
    user_id: uuid.UUID,
    db: AsyncSession,
    last_n: int = 15,
) -> list[WeakSpot]:
    """Identify weaknesses from last N sessions — now includes radar skills."""
    sessions = await get_user_sessions(user_id, db, limit=last_n)
    if not sessions:
        return []

    weak_spots: list[WeakSpot] = []

    # ── Radar-based weakness detection (primary for v5) ──
    radar = aggregate_radar(sessions)
    recent_radar = aggregate_radar(sessions[:5]) if len(sessions) >= 5 else radar
    older_radar = aggregate_radar(sessions[5:10]) if len(sessions) >= 10 else radar

    for skill_key, skill_label in RADAR_SKILLS.items():
        current_val = getattr(recent_radar, skill_key, 0)
        older_val = getattr(older_radar, skill_key, 0)
        delta = current_val - older_val

        trend = "stagnant"
        if delta > 5:
            trend = "improving"
        elif delta < -5:
            trend = "declining"

        # Flag as weak if below 50% or declining
        if current_val < 50 or (trend == "declining" and current_val < 70):
            weak_spots.append(WeakSpot(
                skill=skill_key,
                sub_skill=None,
                avg_score=current_val,
                max_possible=100.0,
                pct=current_val,
                trend=trend,
                trend_delta=round(delta, 1),
                archetype=None,
                recommendation=_get_radar_recommendation(skill_key, current_val, trend),
            ))

    # ── Sub-skill analysis from scoring_details ──
    objection_sub_scores = _analyze_objection_sub_skills(sessions)
    for sub_skill, data in objection_sub_scores.items():
        if data["hit_rate"] < 0.5:
            weak_spots.append(WeakSpot(
                skill="objection_handling",
                sub_skill=sub_skill,
                avg_score=data["hit_rate"] * 5.0,
                max_possible=5.0,
                pct=round(data["hit_rate"] * 100, 1),
                trend="stagnant",
                trend_delta=0.0,
                archetype=None,
                recommendation=_get_sub_skill_recommendation(sub_skill, data["hit_rate"]),
            ))

    # ── Archetype-specific weakness detection ──
    archetype_weak = await _detect_archetype_weaknesses(user_id, db, sessions)
    weak_spots.extend(archetype_weak)

    # Sort by severity
    weak_spots.sort(key=lambda w: (
        0 if w.trend == "declining" else 1,
        w.pct,
    ))

    return weak_spots[:10]


async def build_progress_chart(
    user_id: uuid.UUID,
    db: AsyncSession,
    weeks: int = 12,
) -> list[ProgressPoint]:
    """Build weekly progress data for charting — includes v5 layers."""
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(weeks=weeks)

    result = await db.execute(
        select(
            func.date_trunc("week", TrainingSession.started_at).label("week"),
            func.count(TrainingSession.id).label("cnt"),
            func.avg(TrainingSession.score_total).label("avg_total"),
            func.avg(TrainingSession.score_script_adherence).label("avg_script"),
            func.avg(TrainingSession.score_objection_handling).label("avg_objection"),
            func.avg(TrainingSession.score_communication).label("avg_communication"),
            func.avg(TrainingSession.score_anti_patterns).label("avg_anti"),
            func.avg(TrainingSession.score_result).label("avg_result"),
            func.avg(TrainingSession.score_human_factor).label("avg_hf"),
            func.avg(TrainingSession.score_narrative).label("avg_narr"),
            func.avg(TrainingSession.score_legal).label("avg_legal"),
            func.max(TrainingSession.score_total).label("best"),
            func.min(TrainingSession.score_total).label("worst"),
        )
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= start_date,
        )
        .group_by("week")
        .order_by("week")
    )
    rows = result.all()

    week_data = {}
    for row in rows:
        week_start = row[0]
        if isinstance(week_start, datetime):
            week_start = week_start.date()
        week_data[week_start] = row

    # Also compute per-week radar from sessions
    week_sessions: dict[date, list[TrainingSession]] = {}
    all_sessions = await get_user_sessions(user_id, db, limit=200, completed_only=True)
    for s in all_sessions:
        if s.started_at and s.started_at >= start_date:
            w = s.started_at.date()
            w = w - timedelta(days=w.weekday())  # Align to Monday
            week_sessions.setdefault(w, []).append(s)

    points: list[ProgressPoint] = []
    current = start_date.date()
    current = current - timedelta(days=current.weekday())

    while current <= now.date():
        week_end = current + timedelta(days=6)
        row = week_data.get(current)
        w_sessions = week_sessions.get(current, [])
        w_radar = aggregate_radar(w_sessions).to_dict() if w_sessions else {}

        if row:
            points.append(ProgressPoint(
                period_start=current,
                period_end=week_end,
                sessions_count=row[1] or 0,
                avg_total=round(float(row[2] or 0), 1),
                avg_script=round(float(row[3] or 0), 1),
                avg_objection=round(float(row[4] or 0), 1),
                avg_communication=round(float(row[5] or 0), 1),
                avg_anti_patterns=round(float(row[6] or 0), 1),
                avg_result=round(float(row[7] or 0), 1),
                avg_human_factor=round(float(row[8] or 0), 1),
                avg_narrative=round(float(row[9] or 0), 1),
                avg_legal=round(float(row[10] or 0), 1),
                best_score=round(float(row[11] or 0), 1),
                worst_score=round(float(row[12] or 0), 1),
                radar=w_radar,
            ))
        else:
            points.append(ProgressPoint(
                period_start=current,
                period_end=week_end,
                sessions_count=0,
                avg_total=0, avg_script=0, avg_objection=0,
                avg_communication=0, avg_anti_patterns=0, avg_result=0,
                avg_human_factor=0, avg_narrative=0, avg_legal=0,
                best_score=0, worst_score=0,
                radar=w_radar,
            ))

        current += timedelta(weeks=1)

    return points


async def get_archetype_scores(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[ArchetypeScore]:
    """Performance breakdown per archetype — now includes human_factor and radar."""
    result = await db.execute(
        select(
            Character.slug,
            Character.name,
            func.count(TrainingSession.id).label("cnt"),
            func.avg(TrainingSession.score_total).label("avg_total"),
            func.max(TrainingSession.score_total).label("best"),
            func.min(TrainingSession.score_total).label("worst"),
            func.avg(TrainingSession.score_script_adherence).label("avg_script"),
            func.avg(TrainingSession.score_objection_handling).label("avg_obj"),
            func.avg(TrainingSession.score_communication).label("avg_comm"),
            func.avg(TrainingSession.score_anti_patterns).label("avg_anti"),
            func.avg(TrainingSession.score_result).label("avg_result"),
            func.avg(TrainingSession.score_human_factor).label("avg_hf"),
            func.max(TrainingSession.started_at).label("last_played"),
        )
        .join(Scenario, Scenario.id == TrainingSession.scenario_id)
        .join(Character, Character.id == Scenario.character_id)
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.status == SessionStatus.completed,
        )
        .group_by(Character.slug, Character.name)
        .order_by(func.avg(TrainingSession.score_total).asc())
    )
    rows = result.all()

    all_chars_result = await db.execute(
        select(Character.slug, Character.name).where(Character.is_active == True)  # noqa: E712
    )
    all_chars = {r[0]: r[1] for r in all_chars_result.all()}

    # Also compute per-archetype radar
    archetype_sessions: dict[str, list[TrainingSession]] = {}
    all_user_sessions = await get_user_sessions(user_id, db, limit=200)
    for s in all_user_sessions:
        details = s.scoring_details or {}
        arch_slug = details.get("archetype_slug")
        if arch_slug:
            archetype_sessions.setdefault(arch_slug, []).append(s)

    trained = {}
    for row in rows:
        slug = row[0]
        cnt = row[2] or 0
        avg = float(row[3] or 0)
        a_sessions = archetype_sessions.get(slug, [])
        a_radar = aggregate_radar(a_sessions).to_dict() if a_sessions else {}

        trained[slug] = ArchetypeScore(
            archetype_slug=slug,
            archetype_name=row[1],
            sessions_count=cnt,
            avg_score=round(avg, 1),
            best_score=round(float(row[4] or 0), 1),
            worst_score=round(float(row[5] or 0), 1),
            avg_script=round(float(row[6] or 0), 1),
            avg_objection=round(float(row[7] or 0), 1),
            avg_communication=round(float(row[8] or 0), 1),
            avg_anti_patterns=round(float(row[9] or 0), 1),
            avg_result=round(float(row[10] or 0), 1),
            avg_human_factor=round(float(row[11] or 0), 1),
            last_played=row[12],
            mastery_level=_calculate_mastery(cnt, avg),
            radar=a_radar,
        )

    scores: list[ArchetypeScore] = []
    for slug, name in all_chars.items():
        if slug in trained:
            scores.append(trained[slug])
        else:
            scores.append(ArchetypeScore(
                archetype_slug=slug,
                archetype_name=name,
                sessions_count=0,
                avg_score=0, best_score=0, worst_score=0,
                avg_script=0, avg_objection=0, avg_communication=0,
                avg_anti_patterns=0, avg_result=0, avg_human_factor=0,
                last_played=None,
                mastery_level="untrained",
                radar={},
            ))

    scores.sort(key=lambda s: (
        1 if s.sessions_count == 0 else 2,
        s.avg_score,
    ))
    return scores


# ─── Story Arc Analytics ─────────────────────────────────────────────────────


async def get_story_arc_summaries(
    user_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 10,
) -> list[StoryArcSummary]:
    """Analyze multi-call story arcs for a user."""
    from app.models.roleplay import ClientStory

    try:
        stories_result = await db.execute(
            select(ClientStory)
            .where(ClientStory.user_id == user_id)
            .order_by(ClientStory.started_at.desc())
            .limit(limit)
        )
        stories = stories_result.scalars().all()
    except Exception:
        # Column may not exist yet if migration hasn't run
        await db.rollback()
        return []

    summaries: list[StoryArcSummary] = []

    for story in stories:
        # Get sessions for this story
        sessions_result = await db.execute(
            select(TrainingSession)
            .where(
                TrainingSession.client_story_id == story.id,
                TrainingSession.status == SessionStatus.completed,
            )
            .order_by(TrainingSession.call_number_in_story)
        )
        sessions = list(sessions_result.scalars().all())

        if not sessions:
            continue

        scores = [s.score_total or 0 for s in sessions]
        avg_score = sum(scores) / len(scores) if scores else 0

        # Score trend across calls
        if len(scores) >= 2:
            first_half = scores[:len(scores) // 2]
            second_half = scores[len(scores) // 2:]
            first_avg = sum(first_half) / len(first_half)
            second_avg = sum(second_half) / len(second_half)
            delta = second_avg - first_avg
            score_trend = "improving" if delta > 3 else ("declining" if delta < -3 else "stagnant")
        else:
            score_trend = "stagnant"

        # Skill growth: compare first and last call radar
        first_radar = compute_session_radar(sessions[0])
        last_radar = compute_session_radar(sessions[-1])
        skill_growth = {
            k: round(last_radar.get(k, 0) - first_radar.get(k, 0), 1)
            for k in RADAR_SKILLS
        }

        # Key moments from scoring details
        key_moments: list[dict] = []
        for s in sessions:
            details = s.scoring_details or {}
            legal = details.get("legal_accuracy", {})
            if legal.get("incorrect", 0) > 0:
                key_moments.append({
                    "call": s.call_number_in_story or 0,
                    "type": "legal_error",
                    "detail": f"Юридическая ошибка ({legal['incorrect']} шт.)",
                })
            hf = details.get("human_factor", {})
            if hf.get("fake_detected"):
                key_moments.append({
                    "call": s.call_number_in_story or 0,
                    "type": "fake_detected",
                    "detail": "Распознал фейковый переход клиента",
                })

        summaries.append(StoryArcSummary(
            story_id=story.id,
            story_name=story.story_name,
            calls_completed=len(sessions),
            calls_planned=story.total_calls_planned,
            is_completed=story.is_completed,
            avg_score=round(avg_score, 1),
            score_trend=score_trend,
            skill_growth=skill_growth,
            best_call=scores.index(max(scores)) + 1 if scores else 0,
            worst_call=scores.index(min(scores)) + 1 if scores else 0,
            key_moments=key_moments[:10],
        ))

    return summaries


# ─── Recommendations ─────────────────────────────────────────────────────────


async def generate_recommendations(
    user_id: uuid.UUID,
    db: AsyncSession,
    weak_spots: list[WeakSpot] | None = None,
    archetype_scores: list[ArchetypeScore] | None = None,
) -> list[ScenarioRecommendation]:
    """Generate smart scenario recommendations based on analytics.

    Algorithm:
    1. Untrained archetypes → highest priority (explore)
    2. Weakest archetype with score < 60 → train weakness
    3. Archetype not played in 7+ days → rotation
    4. Best archetype if all > 80 → push to mastery
    5. Random from pool if all covered → variety
    """
    if weak_spots is None:
        weak_spots = await analyze_weak_spots(user_id, db)
    if archetype_scores is None:
        archetype_scores = await get_archetype_scores(user_id, db)

    scenario_result = await db.execute(
        select(Scenario, Character.slug, Character.name)
        .join(Character, Character.id == Scenario.character_id)
        .where(Scenario.is_active == True, Character.is_active == True)  # noqa: E712
        .order_by(Scenario.difficulty)
    )
    scenarios = scenario_result.all()
    if not scenarios:
        return []

    recommendations: list[ScenarioRecommendation] = []
    used: set[uuid.UUID] = set()

    # Priority 1: Untrained
    for arch in archetype_scores:
        if arch.sessions_count == 0:
            sc = _find_scenario(scenarios, arch.archetype_slug, difficulty_max=5, exclude=used)
            if sc:
                used.add(sc[0].id)
                recommendations.append(ScenarioRecommendation(
                    scenario_id=sc[0].id, scenario_title=sc[0].title,
                    archetype_slug=sc[1], scenario_type=sc[0].scenario_type.value,
                    difficulty=sc[0].difficulty,
                    reason=f"Вы ещё не тренировались с архетипом «{sc[2]}». Начните с лёгкого сценария.",
                    priority=1,
                ))
            if len(recommendations) >= 2:
                break

    # Priority 2: Weakest (< 60)
    for arch in archetype_scores:
        if 0 < arch.sessions_count and arch.avg_score < 60:
            target_diff = min(10, arch.sessions_count + 3)
            sc = _find_scenario(scenarios, arch.archetype_slug, difficulty_max=target_diff, exclude=used)
            if sc:
                used.add(sc[0].id)
                skill_hint = ""
                for ws in weak_spots:
                    if ws.archetype == arch.archetype_slug:
                        skill_hint = f" Фокус: {RADAR_SKILLS.get(ws.skill, ws.skill)}."
                        break
                recommendations.append(ScenarioRecommendation(
                    scenario_id=sc[0].id, scenario_title=sc[0].title,
                    archetype_slug=sc[1], scenario_type=sc[0].scenario_type.value,
                    difficulty=sc[0].difficulty,
                    reason=f"Средний балл с «{arch.archetype_name}»: {arch.avg_score}. Нужна практика.{skill_hint}",
                    priority=2,
                ))
            if len(recommendations) >= 3:
                break

    # Priority 3: Rotation (7+ days)
    now = datetime.now(timezone.utc)
    for arch in archetype_scores:
        if arch.sessions_count > 0 and arch.last_played:
            days_ago = (now - arch.last_played).days
            if days_ago >= 7:
                sc = _find_scenario(scenarios, arch.archetype_slug, exclude=used)
                if sc:
                    used.add(sc[0].id)
                    recommendations.append(ScenarioRecommendation(
                        scenario_id=sc[0].id, scenario_title=sc[0].title,
                        archetype_slug=sc[1], scenario_type=sc[0].scenario_type.value,
                        difficulty=sc[0].difficulty,
                        reason=f"Вы не тренировались с «{arch.archetype_name}» {days_ago} дней.",
                        priority=3,
                    ))
                if len(recommendations) >= 4:
                    break

    # Priority 4: Push to mastery
    if len(recommendations) < 3:
        for arch in sorted(archetype_scores, key=lambda a: -a.avg_score):
            if arch.avg_score >= 80:
                sc = _find_scenario(scenarios, arch.archetype_slug, difficulty_min=7, exclude=used)
                if sc:
                    used.add(sc[0].id)
                    recommendations.append(ScenarioRecommendation(
                        scenario_id=sc[0].id, scenario_title=sc[0].title,
                        archetype_slug=sc[1], scenario_type=sc[0].scenario_type.value,
                        difficulty=sc[0].difficulty,
                        reason=f"Вы сильны с «{arch.archetype_name}» ({arch.avg_score}). Попробуйте сложнее.",
                        priority=4,
                    ))
                    break

    # Filler
    if len(recommendations) < 3:
        for sc_tuple in scenarios:
            sc, slug, name = sc_tuple
            if sc.id not in used and len(recommendations) < 3:
                used.add(sc.id)
                recommendations.append(ScenarioRecommendation(
                    scenario_id=sc.id, scenario_title=sc.title,
                    archetype_slug=slug, scenario_type=sc.scenario_type.value,
                    difficulty=sc.difficulty,
                    reason="Расширяйте опыт — попробуйте новый сценарий.",
                    priority=5,
                ))

    recommendations.sort(key=lambda r: r.priority)
    return recommendations[:5]


async def generate_insights(
    user_id: uuid.UUID,
    db: AsyncSession,
    sessions: list[TrainingSession] | None = None,
) -> list[str]:
    """Generate human-readable insights in Russian — v5 with radar and story data."""
    if sessions is None:
        sessions = await get_user_sessions(user_id, db, limit=30)

    if len(sessions) < 3:
        return ["Пройдите ещё несколько тренировок для получения аналитики."]

    insights: list[str] = []

    # ── Trend detection ──
    recent_5 = sessions[:5]
    older_5 = sessions[5:10] if len(sessions) >= 10 else sessions[len(sessions) // 2:]

    recent_avg = sum(s.score_total or 0 for s in recent_5) / len(recent_5)
    older_avg = sum(s.score_total or 0 for s in older_5) / len(older_5) if older_5 else recent_avg

    delta = recent_avg - older_avg
    if delta > 10:
        insights.append(f"Отличный прогресс! Ваш средний балл вырос на {delta:.0f} пунктов за последние сессии.")
    elif delta < -10:
        insights.append(f"Внимание: средний балл снизился на {abs(delta):.0f} пунктов. Возможно, стоит вернуться к более лёгким сценариям.")
    elif abs(delta) < 3 and len(sessions) >= 10:
        insights.append("Ваши баллы стабильны — для роста попробуйте более сложные сценарии или многозвонковые истории.")

    # ── Improvement streak ──
    streak = 0
    for i in range(len(sessions) - 1):
        if (sessions[i].score_total or 0) >= (sessions[i + 1].score_total or 0):
            streak += 1
        else:
            break
    if streak >= 3:
        insights.append(f"Серия улучшений: {streak} сессий подряд с ростом баллов!")

    # ── Radar-based insights ──
    radar = aggregate_radar(sessions[:10])
    radar_dict = radar.to_dict()
    best_skill = max(radar_dict, key=lambda k: radar_dict[k])
    worst_skill = min(radar_dict, key=lambda k: radar_dict[k])

    if radar_dict[best_skill] > 75:
        insights.append(f"Ваша сильная сторона — {RADAR_SKILLS[best_skill]} ({radar_dict[best_skill]:.0f}%).")
    if radar_dict[worst_skill] < 40:
        insights.append(f"Зона роста — {RADAR_SKILLS[worst_skill]} ({radar_dict[worst_skill]:.0f}%). Сфокусируйтесь на этом навыке.")

    # ── Human factor insights ──
    hf_scores = [s.score_human_factor or 0 for s in sessions[:10]]
    avg_hf = sum(hf_scores) / len(hf_scores) if hf_scores else 0
    if avg_hf < 7:
        insights.append("Работа с человеческим фактором ниже среднего. Больше терпения при агрессии, больше эмпатии при страхе клиента.")
    elif avg_hf > 12:
        insights.append("Отлично справляетесь с человеческим фактором — вы умеете сохранять спокойствие и проявлять эмпатию.")

    # ── Legal accuracy insights ──
    legal_scores = [s.score_legal or 0 for s in sessions[:10]]
    avg_legal = sum(legal_scores) / len(legal_scores) if legal_scores else 0
    if avg_legal < -2:
        insights.append("Юридическая точность требует внимания: повторите основные статьи 127-ФЗ перед тренировкой.")
    elif avg_legal > 2:
        insights.append("Высокая юридическая точность — вы хорошо знаете 127-ФЗ и цитируете статьи.")

    # ── Story arc insights ──
    story_sessions = [s for s in sessions if s.client_story_id is not None]
    if story_sessions:
        story_avg = sum(s.score_total or 0 for s in story_sessions) / len(story_sessions)
        single_sessions = [s for s in sessions if s.client_story_id is None]
        single_avg = sum(s.score_total or 0 for s in single_sessions) / len(single_sessions) if single_sessions else 0
        if story_avg > single_avg + 5:
            insights.append("Вы лучше работаете в многозвонковых историях — клиентская связь помогает вам продавать.")
        elif story_avg < single_avg - 5:
            insights.append("В многозвонковых историях баллы ниже. Работайте над поддержанием контекста между звонками.")

    # ── Session duration insight ──
    durations = [s.duration_seconds or 0 for s in sessions[:10] if s.duration_seconds]
    if durations:
        avg_dur = sum(durations) / len(durations)
        if avg_dur < 180:
            insights.append("Ваши сессии очень короткие (менее 3 мин). Углубляйте диалог — задавайте уточняющие вопросы.")
        elif avg_dur > 1200:
            insights.append("Сессии длятся дольше 20 минут. Цель — вывести на консультацию за 5-10 минут.")

    # ── Fear avoidance detection ──
    archetype_counts: dict[str, int] = {}
    for s in sessions:
        details = s.scoring_details or {}
        archetype = details.get("archetype_slug", "unknown")
        archetype_counts[archetype] = archetype_counts.get(archetype, 0) + 1

    total = sum(archetype_counts.values())
    if total >= 10:
        for arch, count in archetype_counts.items():
            if count / total > 0.5 and arch != "unknown":
                insights.append(f"Вы часто выбираете архетип «{arch}». Попробуйте другие — разнообразие развивает гибкость.")

    return insights[:8]


async def build_full_snapshot(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> AnalyticsSnapshot:
    """Build complete v5 analytics snapshot — all data in one call."""
    sessions = await get_user_sessions(user_id, db, limit=50)

    # Pre-compute session stats while objects are still attached to db session
    total = len(sessions)
    avg_score = sum(s.score_total or 0 for s in sessions) / total if total else 0
    days_active = len({s.started_at.date() for s in sessions if s.started_at})
    story_count = len({s.client_story_id for s in sessions if s.client_story_id})
    skill_radar = aggregate_radar(sessions[:20])

    weak_spots = await analyze_weak_spots(user_id, db)
    progress = await build_progress_chart(user_id, db)
    archetype_scores = await get_archetype_scores(user_id, db)
    recommendations = await generate_recommendations(
        user_id, db, weak_spots=weak_spots, archetype_scores=archetype_scores
    )
    insights = await generate_insights(user_id, db, sessions=sessions)
    story_arcs = await get_story_arc_summaries(user_id, db)

    return AnalyticsSnapshot(
        weak_spots=weak_spots,
        progress=progress,
        archetype_scores=archetype_scores,
        recommendations=recommendations,
        insights=insights,
        skill_radar=skill_radar,
        story_arcs=story_arcs,
        meta={
            "total_sessions": total,
            "avg_score": round(avg_score, 1),
            "days_active": days_active,
            "story_count": story_count,
            "analysis_window_sessions": min(total, 50),
            "scoring_version": "v5",
        },
    )


# ─── Helper functions ─────────────────────────────────────────────────────────


def _calculate_trend(values: list[float]) -> tuple[str, float]:
    """Calculate trend from a series of values (newest first)."""
    if len(values) < 4:
        return "stagnant", 0.0

    mid = len(values) // 2
    recent = values[:mid]
    older = values[mid:]

    recent_avg = sum(recent) / len(recent)
    older_avg = sum(older) / len(older)
    delta = recent_avg - older_avg

    if delta > 3:
        return "improving", delta
    elif delta < -3:
        return "declining", delta
    return "stagnant", delta


def _calculate_mastery(session_count: int, avg_score: float) -> str:
    """Determine mastery level."""
    if session_count == 0:
        return "untrained"
    if session_count >= 15 and avg_score >= 85:
        return "mastered"
    if session_count >= 7 and avg_score >= 70:
        return "advanced"
    if session_count >= 3 and avg_score >= 55:
        return "intermediate"
    return "beginner"


def _analyze_objection_sub_skills(sessions: list[TrainingSession]) -> dict:
    """Analyze hit rates for each objection-handling sub-skill."""
    results: dict = {}
    for sub in OBJECTION_SUB_SKILLS:
        hits = 0
        total = 0
        for s in sessions:
            details = s.scoring_details or {}
            obj_details = details.get("objection_handling", {})
            if obj_details.get("objections_found", 0) > 0:
                total += 1
                if obj_details.get(sub, False):
                    hits += 1
        results[sub] = {
            "hits": hits,
            "total": total,
            "hit_rate": hits / total if total > 0 else 1.0,
        }
    return results


async def _detect_archetype_weaknesses(
    user_id: uuid.UUID,
    db: AsyncSession,
    sessions: list[TrainingSession],
) -> list[WeakSpot]:
    """Find skills that are weak ONLY with specific archetypes — v5 with radar."""
    if not sessions:
        return []

    result = await db.execute(
        select(
            Character.slug,
            Character.name,
            func.avg(TrainingSession.score_script_adherence).label("avg_script"),
            func.avg(TrainingSession.score_objection_handling).label("avg_obj"),
            func.avg(TrainingSession.score_communication).label("avg_comm"),
            func.avg(TrainingSession.score_human_factor).label("avg_hf"),
            func.count(TrainingSession.id).label("cnt"),
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

    weak = []
    for row in rows:
        slug, name, avg_script, avg_obj, avg_comm, avg_hf, cnt = row
        if cnt < 2:
            continue

        # Check objection handling
        avg_obj_pct = (float(avg_obj or 0) / 18.75 * 100)
        if avg_obj_pct < 50:
            weak.append(WeakSpot(
                skill="objection_handling",
                sub_skill=None,
                avg_score=round(float(avg_obj or 0), 1),
                max_possible=18.75,
                pct=round(avg_obj_pct, 1),
                trend="stagnant", trend_delta=0.0,
                archetype=slug,
                recommendation=f"С «{name}» проседает работа с возражениями ({avg_obj_pct:.0f}%). Попробуйте «присоединение + аргумент + проверка».",
            ))

        # Check communication
        avg_comm_pct = (float(avg_comm or 0) / 15.0 * 100)
        if avg_comm_pct < 50:
            weak.append(WeakSpot(
                skill="empathy",
                sub_skill=None,
                avg_score=round(float(avg_comm or 0), 1),
                max_possible=15.0,
                pct=round(avg_comm_pct, 1),
                trend="stagnant", trend_delta=0.0,
                archetype=slug,
                recommendation=f"Коммуникация с «{name}» ниже среднего ({avg_comm_pct:.0f}%). Больше эмпатии и уточняющих вопросов.",
            ))

        # Check human factor
        avg_hf_pct = (float(avg_hf or 0) / 15.0 * 100) if avg_hf else 0
        if avg_hf_pct < 40:
            weak.append(WeakSpot(
                skill="stress_resistance",
                sub_skill=None,
                avg_score=round(float(avg_hf or 0), 1),
                max_possible=15.0,
                pct=round(avg_hf_pct, 1),
                trend="stagnant", trend_delta=0.0,
                archetype=slug,
                recommendation=f"С «{name}» страдает стрессоустойчивость ({avg_hf_pct:.0f}%). Больше терпения при агрессии.",
            ))

    return weak


def _get_radar_recommendation(skill: str, pct: float, trend: str) -> str:
    """Generate Russian recommendation for a radar skill weakness."""
    recs = {
        "empathy": {
            "low": "Фокус на эмпатию: используйте «я понимаю», «на вашем месте», «это важно». Проявляйте сочувствие при страхе клиента.",
            "declining": "Эмпатия снизилась. Больше внимания к эмоциональному состоянию клиента — не торопитесь с аргументами.",
        },
        "knowledge": {
            "low": "Изучите основные статьи 127-ФЗ: пороги (ст.213.3), процедуры (ст.213.2), имущество (ст.213.25). Цитируйте закон.",
            "declining": "Юридическая точность снизилась. Освежите знание 127-ФЗ перед тренировкой.",
        },
        "objection_handling": {
            "low": "Формула: выслушать → присоединиться → уточнить → аргументировать → проверить. Не пропускайте этапы.",
            "declining": "Работа с возражениями ухудшилась. Дайте клиенту высказаться, не перебивайте.",
        },
        "stress_resistance": {
            "low": "При агрессии — спокойствие. «Я понимаю ваше раздражение, давайте разберёмся». Без ответной агрессии.",
            "declining": "Стрессоустойчивость просела. Практикуйте сценарии с hostile/testing архетипами.",
        },
        "closing": {
            "low": "Не забывайте закрывать: предложите конкретное время, вышлите документы. Цель = запись на консультацию.",
            "declining": "Вы стали реже выводить на результат. Фокусируйтесь на конкретном CTA в каждом диалоге.",
        },
        "qualification": {
            "low": "Больше вопросов на квалификацию: сумма долга, количество кредиторов, наличие имущества. Это фундамент.",
            "declining": "Квалификация клиента ухудшилась. Вернитесь к базовому скрипту: кто, сколько должен, что есть.",
        },
    }

    skill_recs = recs.get(skill, {})
    if trend == "declining":
        return skill_recs.get("declining", skill_recs.get("low", "Работайте над этим навыком."))
    return skill_recs.get("low", "Работайте над этим навыком.")


def _get_sub_skill_recommendation(sub_skill: str, hit_rate: float) -> str:
    """Generate recommendation for a specific objection-handling sub-skill."""
    tips = {
        "heard": "Вы не всегда замечаете возражения клиента. Прислушивайтесь к «не уверен», «дорого», «нужно подумать».",
        "acknowledged": "Вы редко присоединяетесь к клиенту. Используйте: «Я вас понимаю», «Вы правы», «Хороший вопрос».",
        "clarified": "Вы не уточняете причину возражения. «Что именно вас смущает?», «Расскажите подробнее».",
        "argued": "Не подкрепляете аргументами. Используйте цифры: «В 85% случаев...», «Например...».",
        "checked": "Не проверяете, снято ли возражение. «Это отвечает на ваш вопрос?», «Как вам?».",
    }
    return tips.get(sub_skill, "Развивайте этот навык при работе с возражениями.")


def _find_scenario(
    scenarios: list,
    archetype_slug: str,
    difficulty_min: int = 1,
    difficulty_max: int = 10,
    exclude: set[uuid.UUID] | None = None,
) -> tuple | None:
    """Find a scenario by archetype slug and difficulty range."""
    exclude = exclude or set()
    for sc, slug, name in scenarios:
        if slug == archetype_slug and sc.id not in exclude:
            if difficulty_min <= sc.difficulty <= difficulty_max:
                return (sc, slug, name)
    for sc, slug, name in scenarios:
        if slug == archetype_slug and sc.id not in exclude:
            return (sc, slug, name)
    return None
