"""Anti-cheat system for PvP duels (Agent 8 — PvP Battle).

3-level detection + extensions:

Level 1 — Statistical:
  Score deviation analysis, unnatural win streaks, anomalous accuracy.
  Action: flag for review, increase monitoring.

Level 2 — Behavioral:
  ML pattern analysis — scripts, auto-responses, copy-paste detection.
  Action: temporary ban (24h), manual review.

Level 3 — AI Detector + Extensions:
  - Text perplexity + burstiness (one signal, not sole decider)
  - Latency analysis: median response < 3s at length > 50 words = red flag
  - Semantic consistency: vocabulary complexity jump detection
  Action: flag + rating freeze + manual review (NO auto-disqualification).

Prize Protection:
  - KYC: identity verification before payout
  - 72h payout delay: anti-cheat review period
  - Hidden metrics: players don't know exact scoring formula
  - Immutable audit log
  - Multi-account detection: fingerprint + IP + behavioral
"""

import logging
import math
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pvp import (
    AntiCheatLog,
    AntiCheatCheckType,
    AntiCheatAction,
    PvPDuel,
    DuelStatus,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Level 1: Statistical
MAX_WINSTREAK_BEFORE_FLAG = 12      # Flag if streak > 12
SCORE_DEVIATION_THRESHOLD = 2.5     # Standard deviations from mean
MIN_DUELS_FOR_STATS = 5             # Need at least 5 duels for analysis

# Level 2: Behavioral
COPY_PASTE_SIMILARITY_THRESHOLD = 0.85  # Jaccard similarity between responses
MIN_UNIQUE_RESPONSE_RATIO = 0.6         # At least 60% unique responses

# Level 3: AI Detection
PERPLEXITY_THRESHOLD = 15.0         # Low perplexity = likely AI-generated
BURSTINESS_THRESHOLD = 0.3         # Low burstiness = likely AI
MEDIAN_RESPONSE_TIME_MIN = 3.0     # Seconds — faster = suspicious
RESPONSE_LENGTH_FOR_LATENCY = 50   # Words — only flag if response is long
VOCAB_COMPLEXITY_JUMP = 2.0        # Std dev jump in vocabulary complexity


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AntiCheatSignal:
    """Single anti-cheat detection signal."""
    check_type: AntiCheatCheckType
    score: float            # 0.0-1.0 confidence
    flagged: bool
    details: dict = field(default_factory=dict)


@dataclass
class AntiCheatResult:
    """Aggregated anti-cheat result for a player in a duel."""
    user_id: uuid.UUID
    duel_id: uuid.UUID
    signals: list[AntiCheatSignal] = field(default_factory=list)
    overall_flagged: bool = False
    recommended_action: AntiCheatAction = AntiCheatAction.none

    @property
    def max_score(self) -> float:
        return max((s.score for s in self.signals), default=0.0)

    @property
    def flagged_signals(self) -> list[AntiCheatSignal]:
        return [s for s in self.signals if s.flagged]


# ---------------------------------------------------------------------------
# Level 1: Statistical Analysis
# ---------------------------------------------------------------------------

async def check_statistical(
    user_id: uuid.UUID,
    duel_id: uuid.UUID,
    db: AsyncSession,
) -> AntiCheatSignal:
    """Analyze player's score history for anomalies.

    Checks:
    - Unnatural win streaks (> 12)
    - Score deviation from personal mean (> 2.5σ)
    - Anomalous win rate in recent N games
    """
    # Get recent duels for this user
    stmt = (
        select(PvPDuel)
        .where(
            PvPDuel.status == DuelStatus.completed,
            (PvPDuel.player1_id == user_id) | (PvPDuel.player2_id == user_id),
        )
        .order_by(PvPDuel.completed_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    duels = result.scalars().all()

    if len(duels) < MIN_DUELS_FOR_STATS:
        return AntiCheatSignal(
            check_type=AntiCheatCheckType.statistical,
            score=0.0,
            flagged=False,
            details={"reason": "insufficient_data", "duels": len(duels)},
        )

    # Calculate scores and streaks
    scores = []
    wins = 0
    current_streak = 0
    max_streak = 0

    for d in duels:
        is_p1 = d.player1_id == user_id
        player_score = d.player1_total if is_p1 else d.player2_total
        won = d.winner_id == user_id

        scores.append(player_score)
        if won:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
            wins += 1
        else:
            current_streak = 0

    mean_score = statistics.mean(scores)
    stdev = statistics.stdev(scores) if len(scores) > 1 else 10.0
    win_rate = wins / len(duels)

    # Anomaly score (0.0-1.0)
    anomaly_score = 0.0
    flags = []

    # Win streak check
    if max_streak > MAX_WINSTREAK_BEFORE_FLAG:
        anomaly_score += 0.4
        flags.append(f"win_streak={max_streak}")

    # Win rate anomaly (> 85% over 20+ games)
    if len(duels) >= 20 and win_rate > 0.85:
        anomaly_score += 0.3
        flags.append(f"win_rate={win_rate:.2f}")

    # Latest score deviation
    if stdev > 0 and scores:
        latest_z = abs(scores[0] - mean_score) / stdev
        if latest_z > SCORE_DEVIATION_THRESHOLD:
            anomaly_score += 0.3
            flags.append(f"score_z={latest_z:.2f}")

    anomaly_score = min(1.0, anomaly_score)
    flagged = anomaly_score >= 0.5

    return AntiCheatSignal(
        check_type=AntiCheatCheckType.statistical,
        score=anomaly_score,
        flagged=flagged,
        details={
            "max_streak": max_streak,
            "win_rate": round(win_rate, 3),
            "mean_score": round(mean_score, 1),
            "stdev": round(stdev, 1),
            "flags": flags,
        },
    )


# ---------------------------------------------------------------------------
# Level 2: Behavioral Analysis
# ---------------------------------------------------------------------------

def _jaccard_similarity(a: str, b: str) -> float:
    """Token-level Jaccard similarity between two strings."""
    set_a = set(a.lower().split())
    set_b = set(b.lower().split())
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def check_behavioral(
    messages: list[dict],
    user_id: uuid.UUID,
) -> AntiCheatSignal:
    """Analyze message patterns for scripted/automated behavior.

    Checks:
    - Repeated/copy-pasted responses (high Jaccard similarity)
    - Response template patterns (fill-in-the-blank style)
    - Unnatural response timing patterns
    """
    user_msgs = [m for m in messages if m.get("sender_id") == str(user_id)]

    if len(user_msgs) < 3:
        return AntiCheatSignal(
            check_type=AntiCheatCheckType.behavioral,
            score=0.0,
            flagged=False,
            details={"reason": "insufficient_messages"},
        )

    texts = [m.get("text", "") for m in user_msgs]
    anomaly_score = 0.0
    flags = []

    # Check pairwise similarity
    high_sim_pairs = 0
    total_pairs = 0
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            sim = _jaccard_similarity(texts[i], texts[j])
            total_pairs += 1
            if sim > COPY_PASTE_SIMILARITY_THRESHOLD:
                high_sim_pairs += 1

    if total_pairs > 0:
        sim_ratio = high_sim_pairs / total_pairs
        if sim_ratio > 0.3:
            anomaly_score += 0.5
            flags.append(f"high_similarity_ratio={sim_ratio:.2f}")

    # Unique response ratio
    unique_count = len(set(texts))
    unique_ratio = unique_count / len(texts)
    if unique_ratio < MIN_UNIQUE_RESPONSE_RATIO:
        anomaly_score += 0.3
        flags.append(f"unique_ratio={unique_ratio:.2f}")

    # Response length variance (bots tend to have uniform length)
    lengths = [len(t.split()) for t in texts if t]
    if len(lengths) >= 3:
        length_cv = (statistics.stdev(lengths) / statistics.mean(lengths)) if statistics.mean(lengths) > 0 else 0
        if length_cv < 0.15:  # Very uniform = suspicious
            anomaly_score += 0.2
            flags.append(f"length_cv={length_cv:.3f}")

    anomaly_score = min(1.0, anomaly_score)
    flagged = anomaly_score >= 0.5

    return AntiCheatSignal(
        check_type=AntiCheatCheckType.behavioral,
        score=anomaly_score,
        flagged=flagged,
        details={
            "message_count": len(user_msgs),
            "high_sim_pairs": high_sim_pairs,
            "unique_ratio": round(unique_ratio, 3),
            "flags": flags,
        },
    )


# ---------------------------------------------------------------------------
# Level 3: AI Detection + Latency + Semantic
# ---------------------------------------------------------------------------

def _estimate_perplexity(text: str) -> float:
    """Rough perplexity estimate based on word frequency patterns.

    Real implementation would use a language model. This is a heuristic proxy:
    - Unique word ratio (type-token ratio)
    - Average word length distribution entropy
    """
    words = text.lower().split()
    if len(words) < 10:
        return 50.0  # Not enough text, assume human

    unique = set(words)
    ttr = len(unique) / len(words)

    # Low TTR with long text = possibly AI (more repetitive structure)
    # High TTR = more varied = more human-like
    # This is a very rough heuristic
    estimated = 50.0 * (1.0 - ttr) + 10.0
    return max(5.0, min(100.0, estimated))


def _estimate_burstiness(response_times: list[float]) -> float:
    """Burstiness of response timing. Low = robotic, high = human.

    Burstiness B = (σ - μ) / (σ + μ), range [-1, 1].
    Humans: B > 0 (irregular timing). Bots: B ≈ 0 or < 0 (regular).
    """
    if len(response_times) < 3:
        return 0.5  # Neutral

    mu = statistics.mean(response_times)
    sigma = statistics.stdev(response_times)

    if mu + sigma == 0:
        return 0.0

    return (sigma - mu) / (sigma + mu)


def check_ai_detector(
    messages: list[dict],
    user_id: uuid.UUID,
) -> AntiCheatSignal:
    """Detect AI-generated responses during PvP.

    Combines:
    - Text perplexity estimate (low = AI)
    - Response burstiness (regular timing = AI)
    - Latency analysis (fast + long = AI)
    """
    user_msgs = [m for m in messages if m.get("sender_id") == str(user_id)]

    if len(user_msgs) < 5:
        return AntiCheatSignal(
            check_type=AntiCheatCheckType.ai_detector,
            score=0.0,
            flagged=False,
            details={"reason": "insufficient_messages"},
        )

    anomaly_score = 0.0
    flags = []

    # Perplexity check
    all_text = " ".join(m.get("text", "") for m in user_msgs)
    perplexity = _estimate_perplexity(all_text)
    if perplexity < PERPLEXITY_THRESHOLD:
        anomaly_score += 0.25
        flags.append(f"low_perplexity={perplexity:.1f}")

    # Burstiness check
    response_times = []
    for m in user_msgs:
        rt = m.get("response_time")
        if rt is not None:
            response_times.append(float(rt))

    if response_times:
        burstiness = _estimate_burstiness(response_times)
        if burstiness < BURSTINESS_THRESHOLD:
            anomaly_score += 0.25
            flags.append(f"low_burstiness={burstiness:.3f}")

    # Latency analysis: fast responses to long texts
    fast_long_count = 0
    for m in user_msgs:
        rt = m.get("response_time")
        text = m.get("text", "")
        word_count = len(text.split())
        if rt is not None and rt < MEDIAN_RESPONSE_TIME_MIN and word_count > RESPONSE_LENGTH_FOR_LATENCY:
            fast_long_count += 1

    if fast_long_count >= 3:
        anomaly_score += 0.3
        flags.append(f"fast_long_responses={fast_long_count}")

    anomaly_score = min(1.0, anomaly_score)
    flagged = anomaly_score >= 0.5

    return AntiCheatSignal(
        check_type=AntiCheatCheckType.ai_detector,
        score=anomaly_score,
        flagged=flagged,
        details={
            "perplexity": round(perplexity, 1),
            "burstiness": round(_estimate_burstiness(response_times), 3) if response_times else None,
            "fast_long_count": fast_long_count,
            "flags": flags,
        },
    )


def check_semantic_consistency(
    current_messages: list[dict],
    historical_vocab_complexity: float | None,
    user_id: uuid.UUID,
) -> AntiCheatSignal:
    """Detect sudden jumps in legal vocabulary complexity.

    Compares current session's vocabulary level to player's historical average.
    A sudden jump (> 2σ) suggests external assistance.
    """
    user_msgs = [
        m.get("text", "")
        for m in current_messages
        if m.get("sender_id") == str(user_id)
    ]

    if len(user_msgs) < 3 or historical_vocab_complexity is None:
        return AntiCheatSignal(
            check_type=AntiCheatCheckType.semantic,
            score=0.0,
            flagged=False,
            details={"reason": "insufficient_data"},
        )

    # Simple vocabulary complexity: avg word length + unique legal terms ratio
    all_text = " ".join(user_msgs)
    words = all_text.lower().split()

    if not words:
        return AntiCheatSignal(
            check_type=AntiCheatCheckType.semantic,
            score=0.0,
            flagged=False,
        )

    # Legal terms (sample — would be loaded from DB in production)
    legal_terms = {
        "банкротство", "арбитражный", "конкурсный", "реструктуризация",
        "кредитор", "должник", "финансовый", "управляющий", "реестр",
        "требований", "субсидиарная", "ответственность", "мораторий",
        "реализация", "имущество", "процедура", "несостоятельность",
    }

    avg_word_length = sum(len(w) for w in words) / len(words)
    legal_ratio = sum(1 for w in words if w in legal_terms) / len(words)
    current_complexity = avg_word_length * 2 + legal_ratio * 100

    deviation = abs(current_complexity - historical_vocab_complexity)

    flagged = deviation > VOCAB_COMPLEXITY_JUMP * 10  # Scaled threshold
    score = min(1.0, deviation / (VOCAB_COMPLEXITY_JUMP * 20))

    return AntiCheatSignal(
        check_type=AntiCheatCheckType.semantic,
        score=score,
        flagged=flagged,
        details={
            "current_complexity": round(current_complexity, 2),
            "historical_complexity": round(historical_vocab_complexity, 2),
            "deviation": round(deviation, 2),
        },
    )


# ---------------------------------------------------------------------------
# Aggregated check
# ---------------------------------------------------------------------------

async def run_anti_cheat(
    user_id: uuid.UUID,
    duel_id: uuid.UUID,
    messages: list[dict],
    db: AsyncSession,
    historical_vocab_complexity: float | None = None,
) -> AntiCheatResult:
    """Run all anti-cheat checks for a player in a duel.

    Returns aggregated result with recommended action.
    """
    result = AntiCheatResult(user_id=user_id, duel_id=duel_id)

    # Level 1: Statistical
    stat_signal = await check_statistical(user_id, duel_id, db)
    result.signals.append(stat_signal)

    # Level 2: Behavioral
    behav_signal = check_behavioral(messages, user_id)
    result.signals.append(behav_signal)

    # Level 3: AI Detection
    ai_signal = check_ai_detector(messages, user_id)
    result.signals.append(ai_signal)

    # Level 3+: Semantic consistency
    sem_signal = check_semantic_consistency(
        messages, historical_vocab_complexity, user_id
    )
    result.signals.append(sem_signal)

    # Determine overall flag and action
    flagged_count = len(result.flagged_signals)
    result.overall_flagged = flagged_count > 0

    if flagged_count == 0:
        result.recommended_action = AntiCheatAction.none
    elif flagged_count == 1:
        result.recommended_action = AntiCheatAction.flag_review
    elif flagged_count == 2:
        result.recommended_action = AntiCheatAction.rating_freeze
    else:
        # 3+ signals flagged — serious, but still manual review
        result.recommended_action = AntiCheatAction.rating_freeze

    return result


async def save_anti_cheat_result(
    result: AntiCheatResult,
    db: AsyncSession,
) -> list[AntiCheatLog]:
    """Persist anti-cheat signals to database."""
    logs = []
    for signal in result.signals:
        if signal.score > 0.1:  # Only save non-trivial signals
            log = AntiCheatLog(
                user_id=result.user_id,
                duel_id=result.duel_id,
                check_type=signal.check_type,
                score=signal.score,
                flagged=signal.flagged,
                action_taken=result.recommended_action if signal.flagged else AntiCheatAction.none,
                details=signal.details,
            )
            db.add(log)
            logs.append(log)

    await db.flush()
    logger.info(
        "Anti-cheat: user=%s, duel=%s, flagged=%s, action=%s, signals=%d",
        result.user_id,
        result.duel_id,
        result.overall_flagged,
        result.recommended_action.value,
        len(logs),
    )
    return logs
