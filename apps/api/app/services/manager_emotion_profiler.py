"""Behavioral Intelligence — Manager Emotion Profiler.

Builds a persistent emotional profile of each manager based on:
- Cross-session behavioral snapshots (confidence, stress, adaptability)
- Performance under different client emotions (hostile, empathetic, etc.)
- OCEAN Big Five personality inference from behavioral patterns
- Archetype-specific performance breakdown

Updated after each training session via update_emotion_profile().
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.behavior import BehaviorSnapshot, EmotionProfile

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# OCEAN inference constants
# ═══════════════════════════════════════════════════════════════════════════════

# Exponential moving average alpha for profile updates
# Lower = smoother (less reactive), higher = more reactive
PROFILE_EMA_ALPHA = 0.25


# ═══════════════════════════════════════════════════════════════════════════════
# Profile update
# ═══════════════════════════════════════════════════════════════════════════════


async def get_or_create_profile(user_id: uuid.UUID, db: AsyncSession) -> EmotionProfile:
    """Get existing profile or create default one."""
    result = await db.execute(
        select(EmotionProfile).where(EmotionProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = EmotionProfile(user_id=user_id)
        db.add(profile)
        await db.flush()
    return profile


async def update_emotion_profile(
    user_id: uuid.UUID,
    db: AsyncSession,
    session_snapshot: BehaviorSnapshot | None = None,
    session_score: float | None = None,
    archetype: str | None = None,
    emotion_peak: str | None = None,
) -> EmotionProfile:
    """Update the manager's emotion profile after a session.

    Uses exponential moving average to smooth scores across sessions.
    """
    profile = await get_or_create_profile(user_id, db)
    alpha = PROFILE_EMA_ALPHA

    # If we have a fresh snapshot, update composite scores
    if session_snapshot:
        profile.overall_confidence = _ema(
            profile.overall_confidence, session_snapshot.confidence_score, alpha
        )
        profile.overall_stress_resistance = _ema(
            profile.overall_stress_resistance, 100 - session_snapshot.stress_level, alpha
        )
        profile.overall_adaptability = _ema(
            profile.overall_adaptability, session_snapshot.adaptability_score, alpha
        )

        # Infer OCEAN traits from behavioral signals
        _update_ocean(profile, session_snapshot)

        profile.sessions_analyzed += 1

    # Update archetype-specific scores
    if archetype and session_score is not None:
        scores = profile.archetype_scores or {}
        old = scores.get(archetype, 50.0)
        scores[archetype] = round(_ema(old, session_score, alpha), 1)
        profile.archetype_scores = scores

    # Update performance under emotion types
    if emotion_peak and session_score is not None:
        if emotion_peak in ("hostile", "hangup"):
            profile.performance_under_hostility = _ema(
                profile.performance_under_hostility or 50.0, session_score, alpha
            )
        elif emotion_peak == "testing":
            profile.performance_under_stress = _ema(
                profile.performance_under_stress or 50.0, session_score, alpha
            )
        elif emotion_peak in ("considering", "negotiating", "deal"):
            profile.performance_with_empathy = _ema(
                profile.performance_with_empathy or 50.0, session_score, alpha
            )

    profile.last_updated = datetime.now(timezone.utc)
    await db.flush()

    logger.info(
        "EmotionProfile updated: user=%s confidence=%.0f stress_resistance=%.0f adaptability=%.0f sessions=%d",
        user_id, profile.overall_confidence, profile.overall_stress_resistance,
        profile.overall_adaptability, profile.sessions_analyzed,
    )
    return profile


def _update_ocean(profile: EmotionProfile, snapshot: BehaviorSnapshot) -> None:
    """Infer OCEAN Big Five traits from behavioral snapshot."""
    alpha = PROFILE_EMA_ALPHA

    # Openness: varied message lengths + legal terms = tries different approaches
    openness_signal = 50.0
    if snapshot.signals:
        lengths = snapshot.signals.get("message_lengths", [])
        if lengths and len(lengths) >= 3:
            # High variance in lengths = openness
            mean_len = sum(lengths) / len(lengths)
            variance = sum((ln - mean_len) ** 2 for ln in lengths) / len(lengths)
            cv = (variance ** 0.5) / max(mean_len, 1)
            openness_signal = min(100, 50 + cv * 50)
    if snapshot.legal_term_density > 0.1:
        openness_signal += 10
    profile.openness = _ema(profile.openness, min(100, openness_signal), alpha)

    # Conscientiousness: consistent timing + longer messages = thorough
    consc_signal = 50.0
    if snapshot.response_time_stddev and snapshot.avg_response_time_ms:
        cv = snapshot.response_time_stddev / max(snapshot.avg_response_time_ms, 1)
        consc_signal = max(20, 80 - cv * 40)  # Low variance = high conscientiousness
    if snapshot.avg_message_length and snapshot.avg_message_length > 100:
        consc_signal += 10
    profile.conscientiousness = _ema(profile.conscientiousness, min(100, consc_signal), alpha)

    # Extraversion: fast responses + long messages + many messages
    extraversion_signal = 50.0
    if snapshot.avg_response_time_ms and snapshot.avg_response_time_ms < 5000:
        extraversion_signal += 15
    if snapshot.avg_message_length and snapshot.avg_message_length > 80:
        extraversion_signal += 10
    if snapshot.total_messages > 15:
        extraversion_signal += 10
    profile.extraversion = _ema(profile.extraversion, min(100, extraversion_signal), alpha)

    # Agreeableness: high confidence + low stress + adaptability
    agree_signal = (snapshot.confidence_score * 0.3 +
                    (100 - snapshot.stress_level) * 0.3 +
                    snapshot.adaptability_score * 0.4)
    profile.agreeableness = _ema(profile.agreeableness, min(100, agree_signal), alpha)

    # Neuroticism: high stress + many hesitations + low confidence
    neuro_signal = (snapshot.stress_level * 0.4 +
                    (100 - snapshot.confidence_score) * 0.3 +
                    min(100, snapshot.hesitation_count * 10) * 0.3)
    profile.neuroticism = _ema(profile.neuroticism, min(100, neuro_signal), alpha)


def _ema(old_value: float, new_value: float, alpha: float) -> float:
    """Exponential moving average."""
    return round(old_value * (1 - alpha) + new_value * alpha, 1)


# ═══════════════════════════════════════════════════════════════════════════════
# 3.5: OCEAN profile retrieval + archetype recommendations
# ═══════════════════════════════════════════════════════════════════════════════

# Map OCEAN weaknesses to recommended training archetypes
_OCEAN_ARCHETYPE_RECOMMENDATIONS: dict[str, dict] = {
    "low_openness": {
        "archetypes": ["manipulator", "emotional"],
        "reason": "Низкая открытость — тренируйте работу с нестандартными клиентами",
        "tip": "Попробуйте разные подходы: эмпатия вместо логики, или наоборот",
    },
    "low_conscientiousness": {
        "archetypes": ["analytical", "skeptic"],
        "reason": "Низкая добросовестность — тренируйте точность и последовательность",
        "tip": "Уделяйте внимание деталям: цифрам, срокам, юридическим формулировкам",
    },
    "low_extraversion": {
        "archetypes": ["passive", "depressed"],
        "reason": "Низкая экстраверсия — тренируйте активное ведение диалога",
        "tip": "Задавайте больше открытых вопросов, берите инициативу",
    },
    "low_agreeableness": {
        "archetypes": ["hostile", "aggressive"],
        "reason": "Низкая доброжелательность — тренируйте работу с конфликтными клиентами",
        "tip": "Фокусируйтесь на де-эскалации и поиске компромиссов",
    },
    "high_neuroticism": {
        "archetypes": ["hostile", "manipulator", "aggressive"],
        "reason": "Высокий нейротизм — тренируйте стрессоустойчивость",
        "tip": "Практикуйте спокойные ответы на провокации",
    },
}


async def get_ocean_profile(
    user_id: uuid.UUID, db: AsyncSession
) -> dict:
    """Get OCEAN profile with trait analysis and archetype recommendations."""
    profile = await get_or_create_profile(user_id, db)

    traits = {
        "openness": {"value": round(profile.openness, 1), "label": "Открытость"},
        "conscientiousness": {"value": round(profile.conscientiousness, 1), "label": "Добросовестность"},
        "extraversion": {"value": round(profile.extraversion, 1), "label": "Экстраверсия"},
        "agreeableness": {"value": round(profile.agreeableness, 1), "label": "Доброжелательность"},
        "neuroticism": {"value": round(profile.neuroticism, 1), "label": "Нейротизм"},
    }

    # Classify each trait
    for key, data in traits.items():
        v = data["value"]
        if key == "neuroticism":
            data["level"] = "high" if v > 65 else "medium" if v > 35 else "low"
        else:
            data["level"] = "high" if v > 65 else "medium" if v > 35 else "low"

    # Generate recommendations based on weak spots
    recommendations = []
    if traits["openness"]["value"] < 40:
        recommendations.append(_OCEAN_ARCHETYPE_RECOMMENDATIONS["low_openness"])
    if traits["conscientiousness"]["value"] < 40:
        recommendations.append(_OCEAN_ARCHETYPE_RECOMMENDATIONS["low_conscientiousness"])
    if traits["extraversion"]["value"] < 40:
        recommendations.append(_OCEAN_ARCHETYPE_RECOMMENDATIONS["low_extraversion"])
    if traits["agreeableness"]["value"] < 40:
        recommendations.append(_OCEAN_ARCHETYPE_RECOMMENDATIONS["low_agreeableness"])
    if traits["neuroticism"]["value"] > 65:
        recommendations.append(_OCEAN_ARCHETYPE_RECOMMENDATIONS["high_neuroticism"])

    # Archetype performance breakdown
    archetype_scores = profile.archetype_scores or {}

    return {
        "traits": traits,
        "sessions_analyzed": profile.sessions_analyzed,
        "overall_confidence": round(profile.overall_confidence, 1),
        "overall_stress_resistance": round(profile.overall_stress_resistance, 1),
        "overall_adaptability": round(profile.overall_adaptability, 1),
        "archetype_scores": archetype_scores,
        "recommendations": recommendations[:3],
        "performance": {
            "under_hostility": round(profile.performance_under_hostility or 50, 1),
            "under_stress": round(profile.performance_under_stress or 50, 1),
            "with_empathy": round(profile.performance_with_empathy or 50, 1),
        },
    }
