"""Reputation service — EMA-based reputation calculation, decay, tier management.

Cross-cutting service used by:
- gamification.py (badges, tier display, XP bonuses)
- scenario_engine.py (min_difficulty by tier, emotion weight shifting)
- game_director (client generation warmth)

Reputation formula:
- EMA (Exponential Moving Average) with α = 0.15
  new_ema = α × session_score + (1 - α) × old_ema
- Active impact: session score → reputation delta
  score < 30  → -3 (bad session penalty)
  30-60       → 0  (neutral)
  60-80       → +1 (good session bonus)
  80+         → +2 (excellent session bonus)
- Passive decay: -2/day after 7 days of inactivity

Score range: 0-100. Default start: 50 (Старший менеджер tier).
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reputation import (
    ManagerReputation,
    ReputationTier,
    TIER_BOUNDARIES,
    TIER_DISPLAY_NAMES,
    TIER_MIN_DIFFICULTY,
)

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

EMA_ALPHA = 0.15               # EMA smoothing factor
DECAY_RATE = 2.0               # points per day of inactivity
DECAY_GRACE_DAYS = 7           # days before decay starts
SCORE_MIN = 0.0
SCORE_MAX = 100.0
DEFAULT_SCORE = 50.0

# Active impact thresholds: session score → reputation delta
_ACTIVE_IMPACT = [
    (30, -3.0),   # score < 30 → bad session
    (60, 0.0),    # score 30-59 → neutral
    (80, 1.0),    # score 60-79 → good
    (101, 2.0),   # score 80+ → excellent
]

# Emotion weight shift: reputation_modifier = (reputation - 50) / 100
# Range: [-0.5, +0.5]
# Applied to initial_emotion_variants as multiplicative shift


# ─── Core functions ──────────────────────────────────────────────────────────

async def get_or_create_reputation(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> ManagerReputation:
    """Get existing reputation record or create a new one with defaults."""
    result = await db.execute(
        select(ManagerReputation)
        .where(ManagerReputation.user_id == user_id)
        .with_for_update()
    )
    rep = result.scalar_one_or_none()

    if rep is None:
        rep = ManagerReputation(
            user_id=user_id,
            score=DEFAULT_SCORE,
            tier=_score_to_tier(DEFAULT_SCORE),
            ema_state=DEFAULT_SCORE,
        )
        db.add(rep)
        await db.flush()
        logger.info("Created reputation for user %s: score=%.1f tier=%s",
                     user_id, rep.score, rep.tier.value)

    return rep


async def update_reputation_after_session(
    user_id: uuid.UUID,
    session_score: float,
    db: AsyncSession,
) -> ManagerReputation:
    """Update reputation after a completed training session.

    Applies:
    1. EMA update from session score
    2. Active impact (bonus/penalty based on session quality)
    3. Tier recalculation
    4. History entry

    Args:
        user_id: Manager's user ID
        session_score: Session score_total (0-100)
        db: Database session

    Returns:
        Updated ManagerReputation
    """
    rep = await get_or_create_reputation(user_id, db)
    now = datetime.now(timezone.utc)

    # ── Apply decay first (if applicable) ──
    rep = _apply_decay(rep, now)

    # ── EMA update ──
    old_ema = rep.ema_state
    new_ema = EMA_ALPHA * session_score + (1 - EMA_ALPHA) * old_ema
    rep.ema_state = _clamp(new_ema)

    # ── Active impact ──
    delta = _session_score_to_delta(session_score)
    new_score = _clamp(rep.ema_state + delta)

    # ── Update record ──
    old_score = rep.score
    rep.score = new_score
    rep.tier = _score_to_tier(new_score)
    rep.sessions_rated += 1
    rep.last_session_at = now

    # Track peak
    if new_score > rep.peak_score:
        rep.peak_score = new_score
        rep.peak_tier = rep.tier

    # ── History entry (keep last 50) ──
    entry = {
        "ts": now.isoformat(),
        "type": "session",
        "session_score": round(session_score, 1),
        "delta": round(new_score - old_score, 2),
        "old_score": round(old_score, 1),
        "new_score": round(new_score, 1),
        "ema": round(new_ema, 2),
    }
    history = list(rep.history or [])
    history.append(entry)
    if len(history) > 50:
        history = history[-50:]
    rep.history = history

    logger.info(
        "Reputation updated: user=%s session_score=%.1f delta=%.2f "
        "score=%.1f→%.1f tier=%s ema=%.2f",
        user_id, session_score, new_score - old_score,
        old_score, new_score, rep.tier.value, new_ema,
    )

    return rep


async def apply_decay_for_user(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> ManagerReputation | None:
    """Apply inactivity decay for a specific user. Called by scheduled tasks.

    Returns updated reputation or None if user not found.
    """
    rep = await get_or_create_reputation(user_id, db)
    now = datetime.now(timezone.utc)
    old_score = rep.score
    rep = _apply_decay(rep, now)

    if rep.score != old_score:
        logger.info("Decay applied: user=%s score=%.1f→%.1f",
                     user_id, old_score, rep.score)

    return rep


def calculate_emotion_weight_shift(reputation_score: float) -> float:
    """Calculate the emotion weight modifier based on reputation.

    Returns a modifier in range [-0.5, +0.5]:
    - reputation 0 → -0.5 (clients start much colder)
    - reputation 50 → 0.0 (neutral, no shift)
    - reputation 100 → +0.5 (clients start warmer)

    Usage in scenario_engine.generate_session_config:
        modifier = calculate_emotion_weight_shift(rep.score)
        shifted_weights = shift_emotion_weights(base_weights, modifier)
    """
    return (reputation_score - 50.0) / 100.0


def shift_emotion_weights(
    base_weights: dict[str, float],
    modifier: float,
) -> dict[str, float]:
    """Shift initial emotion variant weights based on reputation modifier.

    Positive modifier → increase weight of warmer emotions, decrease colder.
    Negative modifier → increase weight of colder emotions, decrease warmer.

    Emotion warmth ordering (cold → warm):
        hostile < cold < guarded < testing < callback < curious < considering < negotiating < deal

    Args:
        base_weights: Original emotion variant weights from ScenarioTemplate
        modifier: Reputation modifier from calculate_emotion_weight_shift() [-0.5, +0.5]

    Returns:
        New weights dict, normalized to sum = 1.0
    """
    if not base_weights or abs(modifier) < 0.01:
        return dict(base_weights) if base_weights else {}

    # Warmth index: higher = warmer emotion
    warmth = {
        "hostile": 0.0,
        "hangup": 0.0,
        "cold": 0.1,
        "guarded": 0.2,
        "testing": 0.3,
        "callback": 0.4,
        "curious": 0.6,
        "considering": 0.7,
        "negotiating": 0.8,
        "deal": 1.0,
    }

    shifted = {}
    for emotion, weight in base_weights.items():
        w_idx = warmth.get(emotion, 0.5)
        # Positive modifier → boost warm emotions (high warmth index)
        # Negative modifier → boost cold emotions (low warmth index)
        if modifier > 0:
            factor = 1.0 + modifier * w_idx * 2
        else:
            factor = 1.0 + abs(modifier) * (1.0 - w_idx) * 2
        shifted[emotion] = max(0.01, weight * factor)

    # Normalize to sum = 1.0
    total = sum(shifted.values())
    if total > 0:
        shifted = {k: v / total for k, v in shifted.items()}

    return shifted


def get_tier_min_difficulty(tier: ReputationTier) -> int:
    """Get minimum scenario difficulty for a reputation tier.

    Used by scenario_engine.select_scenario to filter by difficulty floor.
    """
    return TIER_MIN_DIFFICULTY.get(tier, 1)


def get_tier_display(tier: ReputationTier) -> dict:
    """Get display info for a tier (name, badge, boundaries)."""
    bounds = TIER_BOUNDARIES.get(tier, (0, 100))
    return {
        "tier": tier.value,
        "name": TIER_DISPLAY_NAMES.get(tier, tier.value),
        "min_score": bounds[0],
        "max_score": bounds[1],
    }


# ─── Internal helpers ────────────────────────────────────────────────────────

def _clamp(value: float) -> float:
    """Clamp value to [SCORE_MIN, SCORE_MAX]."""
    return max(SCORE_MIN, min(SCORE_MAX, value))


def _score_to_tier(score: float) -> ReputationTier:
    """Map reputation score to tier."""
    for tier, (low, high) in TIER_BOUNDARIES.items():
        if low <= score <= high:
            return tier
    return ReputationTier.hunter if score > 80 else ReputationTier.trainee


def _session_score_to_delta(session_score: float) -> float:
    """Map session score to reputation active impact delta."""
    for threshold, delta in _ACTIVE_IMPACT:
        if session_score < threshold:
            return delta
    return 0.0


def _apply_decay(rep: ManagerReputation, now: datetime) -> ManagerReputation:
    """Apply inactivity decay to reputation if applicable.

    Decay starts after DECAY_GRACE_DAYS (7) of no sessions.
    Rate: DECAY_RATE (2.0) points per day.
    Minimum score: 0.
    """
    if rep.last_session_at is None:
        return rep

    # Days since last session
    days_inactive = (now - rep.last_session_at).total_seconds() / 86400.0

    if days_inactive <= DECAY_GRACE_DAYS:
        return rep

    # Calculate decay from last decay application or grace period end
    if rep.last_decay_at and rep.last_decay_at > rep.last_session_at:
        decay_days = (now - rep.last_decay_at).total_seconds() / 86400.0
    else:
        decay_days = days_inactive - DECAY_GRACE_DAYS

    if decay_days <= 0:
        return rep

    decay_amount = decay_days * DECAY_RATE
    old_score = rep.score
    rep.score = _clamp(rep.score - decay_amount)
    rep.ema_state = _clamp(rep.ema_state - decay_amount * 0.5)  # EMA decays slower
    rep.tier = _score_to_tier(rep.score)
    rep.last_decay_at = now

    if decay_amount > 0.1:
        # Add decay entry to history
        history = list(rep.history or [])
        history.append({
            "ts": now.isoformat(),
            "type": "decay",
            "days_inactive": round(days_inactive, 1),
            "decay_amount": round(decay_amount, 1),
            "old_score": round(old_score, 1),
            "new_score": round(rep.score, 1),
        })
        if len(history) > 50:
            history = history[-50:]
        rep.history = history

    return rep
