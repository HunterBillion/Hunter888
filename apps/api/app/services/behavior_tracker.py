"""Behavioral Intelligence — Message-level signal extraction.

Analyzes manager's messages during training and quiz sessions to extract:
- Response patterns (timing, length, consistency)
- Confidence indicators (assertive vs hedging language)
- Stress signals (acceleration, shortening, emotional volatility)
- Adaptability (reaction to client emotion changes)
- Legal terminology usage (growth indicator)

Hooks:
- Called after each training session completes (ws/training.py)
- Called after each quiz session completes (ws/knowledge.py)
"""

import logging
import math
import re
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.behavior import BehaviorSnapshot

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants — behavioral signal thresholds
# ═══════════════════════════════════════════════════════════════════════════════

# Hedging phrases (indicate low confidence)
HESITATION_PHRASES = [
    "может быть", "наверное", "не уверен", "не знаю", "думаю что",
    "мне кажется", "возможно", "скорее всего", "не совсем", "как бы",
    "ну это", "типа", "в общем", "короче", "ээ", "хм",
    "я не специалист", "не могу точно", "затрудняюсь", "сложно сказать",
]

# Assertive phrases (indicate high confidence)
ASSERTIVE_PHRASES = [
    "согласно закону", "по статье", "в соответствии", "гарантирую",
    "однозначно", "безусловно", "абсолютно", "на 100%", "точно",
    "уверен", "подтверждаю", "мы решим", "я помогу", "давайте разберём",
    "это важно", "обратите внимание", "ключевой момент",
]

# Legal terminology (indicates knowledge growth)
LEGAL_TERMS = [
    "банкротство", "должник", "кредитор", "арбитражный", "финансовый управляющий",
    "реструктуризация", "реализация имущества", "конкурсная масса",
    "мораторий", "исполнительное производство", "127-фз", "127 фз",
    "федеральный закон", "статья", "ст.", "пункт", "п.",
    "требования кредиторов", "реестр", "очередь", "залоговый",
    "мировое соглашение", "алименты", "субсидиарная ответственность",
    "неплатёжеспособность", "недостаточность имущества", "ефрсб", "коммерсантъ",
]


# ═══════════════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class MessageSignal:
    """Behavioral signals extracted from a single manager message."""
    sequence: int
    text: str
    length: int
    response_time_ms: int | None
    confidence: float  # 0-1
    hesitation_phrases_found: list[str]
    assertive_phrases_found: list[str]
    legal_terms_found: list[str]
    legal_term_density: float  # 0-1


@dataclass
class SessionBehaviorAnalysis:
    """Aggregated behavioral analysis for a session."""
    user_id: uuid.UUID
    session_id: uuid.UUID
    session_type: str

    # Response patterns
    avg_response_time_ms: int | None = None
    min_response_time_ms: int | None = None
    max_response_time_ms: int | None = None
    response_time_stddev: float | None = None
    response_acceleration: float | None = None

    # Message patterns
    avg_message_length: int | None = None
    min_message_length: int | None = None
    max_message_length: int | None = None
    total_messages: int = 0

    # Scores
    confidence_score: float = 50.0
    stress_level: float = 30.0
    adaptability_score: float = 50.0
    hesitation_count: int = 0
    legal_term_density: float = 0.0

    # Detailed signals
    signals: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════════
# Signal extraction (per message)
# ═══════════════════════════════════════════════════════════════════════════════


def extract_message_signal(
    text: str,
    sequence: int,
    response_time_ms: int | None = None,
) -> MessageSignal:
    """Extract behavioral signals from a single manager message."""
    text_lower = text.lower().strip()
    words = text_lower.split()
    word_count = len(words)

    # Hesitation detection
    hesitations = [p for p in HESITATION_PHRASES if p in text_lower]

    # Assertiveness detection
    assertives = [p for p in ASSERTIVE_PHRASES if p in text_lower]

    # Legal terminology
    legal_found = [t for t in LEGAL_TERMS if t in text_lower]
    legal_density = len(legal_found) / max(word_count, 1)

    # Confidence score (0-1)
    # Base: 0.5, boosted by assertive, reduced by hesitation
    confidence = 0.5
    if assertives:
        confidence += min(0.3, len(assertives) * 0.1)
    if hesitations:
        confidence -= min(0.4, len(hesitations) * 0.15)
    if legal_found:
        confidence += min(0.2, len(legal_found) * 0.05)
    # Long, detailed answers = more confident
    if word_count > 30:
        confidence += 0.1
    elif word_count < 5:
        confidence -= 0.15
    confidence = max(0.0, min(1.0, confidence))

    return MessageSignal(
        sequence=sequence,
        text=text[:200],  # Truncate for storage
        length=len(text),
        response_time_ms=response_time_ms,
        confidence=confidence,
        hesitation_phrases_found=hesitations,
        assertive_phrases_found=assertives,
        legal_terms_found=legal_found,
        legal_term_density=legal_density,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Session-level analysis
# ═══════════════════════════════════════════════════════════════════════════════


def analyze_session_behavior(
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    session_type: str,
    messages: list[dict],
    emotion_transitions: list[dict] | None = None,
) -> SessionBehaviorAnalysis:
    """Analyze all manager messages from a session.

    Args:
        messages: [{"role": "user", "content": "...", "response_time_ms": int, "sequence": int}]
        emotion_transitions: [{"from": "cold", "to": "guarded", "trigger": "empathy"}, ...]
    """
    # Filter to manager messages only
    manager_msgs = [m for m in messages if m.get("role") == "user"]
    if not manager_msgs:
        return SessionBehaviorAnalysis(user_id=user_id, session_id=session_id, session_type=session_type)

    # Extract signals per message
    signals = []
    for msg in manager_msgs:
        sig = extract_message_signal(
            text=msg.get("content", ""),
            sequence=msg.get("sequence", 0),
            response_time_ms=msg.get("response_time_ms"),
        )
        signals.append(sig)

    # ── Response time analysis ────────────────────────────────────────────
    response_times = [s.response_time_ms for s in signals if s.response_time_ms and s.response_time_ms > 0]
    avg_rt = int(sum(response_times) / len(response_times)) if response_times else None
    min_rt = min(response_times) if response_times else None
    max_rt = max(response_times) if response_times else None
    stddev_rt = None
    acceleration = None
    if len(response_times) >= 3:
        mean = sum(response_times) / len(response_times)
        stddev_rt = math.sqrt(sum((t - mean) ** 2 for t in response_times) / len(response_times))
        # Acceleration: compare first half vs second half avg
        mid = len(response_times) // 2
        first_half = sum(response_times[:mid]) / mid
        second_half = sum(response_times[mid:]) / (len(response_times) - mid)
        acceleration = (second_half - first_half) / max(first_half, 1)  # positive = slowing down

    # ── Message length analysis ───────────────────────────────────────────
    lengths = [s.length for s in signals]
    avg_len = int(sum(lengths) / len(lengths)) if lengths else None
    min_len = min(lengths) if lengths else None
    max_len = max(lengths) if lengths else None

    # ── Confidence aggregation ────────────────────────────────────────────
    confidences = [s.confidence for s in signals]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5

    # ── Hesitation count ──────────────────────────────────────────────────
    total_hesitations = sum(len(s.hesitation_phrases_found) for s in signals)

    # ── Legal term density ────────────────────────────────────────────────
    all_legal = set()
    for s in signals:
        all_legal.update(s.legal_terms_found)
    legal_density = len(all_legal) / max(len(signals), 1)

    # ── Stress level (0-100) ──────────────────────────────────────────────
    stress = 30.0  # Base
    # High variance in response time = stress
    if stddev_rt and avg_rt:
        cv = stddev_rt / max(avg_rt, 1)  # Coefficient of variation
        if cv > 0.8:
            stress += 20
        elif cv > 0.5:
            stress += 10
    # Decreasing message length = stress
    if len(lengths) >= 4:
        first_q = sum(lengths[:len(lengths) // 4]) / max(len(lengths) // 4, 1)
        last_q = sum(lengths[-len(lengths) // 4:]) / max(len(lengths) // 4, 1)
        if last_q < first_q * 0.6:
            stress += 15
    # Many hesitations = stress
    if total_hesitations > len(signals) * 0.3:
        stress += 15
    # Acceleration (positive = slowing = fatigue, negative = speeding = stress)
    if acceleration is not None and acceleration < -0.3:
        stress += 10  # Rushing = stress
    stress = min(100.0, max(0.0, stress))

    # ── Adaptability (0-100) ──────────────────────────────────────────────
    adaptability = 50.0
    if emotion_transitions:
        # How well did manager react to negative emotions?
        negative_transitions = [
            t for t in emotion_transitions
            if t.get("to") in ("hostile", "hangup", "testing")
        ]
        positive_after_negative = 0
        for nt in negative_transitions:
            # Check if manager's next message had good confidence
            seq = nt.get("sequence", 0)
            next_sigs = [s for s in signals if s.sequence > seq]
            if next_sigs and next_sigs[0].confidence > 0.5:
                positive_after_negative += 1
        if negative_transitions:
            reaction_rate = positive_after_negative / len(negative_transitions)
            adaptability = 30 + reaction_rate * 70
    adaptability = min(100.0, max(0.0, adaptability))

    # ── Build detailed signals ────────────────────────────────────────────
    detailed = {
        "message_lengths": lengths,
        "response_times_ms": response_times,
        "confidence_per_message": [round(s.confidence, 2) for s in signals],
        "legal_terms_used": list(all_legal),
        "hesitation_phrases": [
            {"msg": s.sequence, "phrase": p}
            for s in signals for p in s.hesitation_phrases_found
        ],
    }

    return SessionBehaviorAnalysis(
        user_id=user_id,
        session_id=session_id,
        session_type=session_type,
        avg_response_time_ms=avg_rt,
        min_response_time_ms=min_rt,
        max_response_time_ms=max_rt,
        response_time_stddev=stddev_rt,
        response_acceleration=acceleration,
        avg_message_length=avg_len,
        min_message_length=min_len,
        max_message_length=max_len,
        total_messages=len(signals),
        confidence_score=round(avg_confidence * 100, 1),
        stress_level=round(stress, 1),
        adaptability_score=round(adaptability, 1),
        hesitation_count=total_hesitations,
        legal_term_density=round(legal_density, 3),
        signals=detailed,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Persistence
# ═══════════════════════════════════════════════════════════════════════════════


async def save_behavior_snapshot(
    analysis: SessionBehaviorAnalysis,
    db: AsyncSession,
) -> BehaviorSnapshot:
    """Persist session behavioral analysis to database."""
    snapshot = BehaviorSnapshot(
        user_id=analysis.user_id,
        session_id=analysis.session_id,
        session_type=analysis.session_type,
        avg_response_time_ms=analysis.avg_response_time_ms,
        min_response_time_ms=analysis.min_response_time_ms,
        max_response_time_ms=analysis.max_response_time_ms,
        response_time_stddev=analysis.response_time_stddev,
        avg_message_length=analysis.avg_message_length,
        min_message_length=analysis.min_message_length,
        max_message_length=analysis.max_message_length,
        total_messages=analysis.total_messages,
        confidence_score=analysis.confidence_score,
        hesitation_count=analysis.hesitation_count,
        legal_term_density=analysis.legal_term_density,
        stress_level=analysis.stress_level,
        response_acceleration=analysis.response_acceleration,
        adaptability_score=analysis.adaptability_score,
        signals=analysis.signals,
    )
    db.add(snapshot)
    await db.flush()
    logger.info(
        "BehaviorSnapshot saved: user=%s session=%s confidence=%.0f stress=%.0f adapt=%.0f",
        analysis.user_id, analysis.session_id,
        analysis.confidence_score, analysis.stress_level, analysis.adaptability_score,
    )
    return snapshot


async def get_user_behavior_history(
    user_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 20,
) -> list[BehaviorSnapshot]:
    """Get recent behavior snapshots for a user."""
    result = await db.execute(
        select(BehaviorSnapshot)
        .where(BehaviorSnapshot.user_id == user_id)
        .order_by(BehaviorSnapshot.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
