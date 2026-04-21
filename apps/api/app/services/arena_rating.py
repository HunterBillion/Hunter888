"""Glicko-2 rating wrapper for Arena Knowledge (127-FZ PvP).

Reuses the core Glicko-2 algorithm from services/glicko2.py but operates
on PvPRating rows with rating_type="knowledge_arena".

Supports:
- 1v1 (2-player) matches: simple win/loss
- FFA (3-4 player) matches: virtual pairwise comparisons with averaged deltas
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pvp import PvPRating, PvPRankTier, rank_from_rating
from app.services.glicko2 import (
    calculate_glicko2,
    apply_rd_decay,
    get_or_create_rating,
    DEFAULT_RATING,
    DEFAULT_RD,
    DEFAULT_VOL,
)

logger = logging.getLogger(__name__)

ARENA_RATING_TYPE = "knowledge_arena"

# S3-12: FFA inflation protection
MAX_FFA_RATING_GAP = 500            # Max gap for full gain
FFA_RD_WEIGHT_BASE = 350.0          # RD normalization base
REPEAT_OPPONENT_DECAY = [1.0, 0.50, 0.25, 0.10]  # gain multiplier for 1st/2nd/3rd/4th+ match
CHERRY_PICK_THRESHOLD = 3           # Flag if N+ opponents have RD > 300


async def get_arena_rating(user_id: uuid.UUID, db: AsyncSession) -> PvPRating:
    """Get or create Arena Knowledge rating (separate from training duels)."""
    return await get_or_create_rating(user_id, db, rating_type=ARENA_RATING_TYPE)


async def update_arena_rating_after_pvp(
    session_id: uuid.UUID,
    rankings: list[dict],  # [{user_id, rank, score, is_bot}]
    db: AsyncSession,
) -> dict[str, float]:
    """Update Glicko-2 ratings after a PvP knowledge match.

    For 2-player: simple win/loss.
    For 3-4 player: virtual pairwise comparisons with averaged deltas.

    Returns dict mapping user_id (str) -> rating delta.
    """
    # Filter out bots — no rating updates for AI opponents
    human_rankings = [r for r in rankings if not r.get("is_bot")]

    if len(human_rankings) < 2:
        return {}

    if len(human_rankings) == 2:
        rating_deltas = await _update_1v1(human_rankings, db)
    else:
        rating_deltas = await _update_ffa(human_rankings, session_id, db)

    await db.flush()
    logger.info(
        "Arena rating updated for session %s: %s",
        session_id,
        {uid: f"{d:+.1f}" for uid, d in rating_deltas.items()},
    )
    return rating_deltas


async def _update_1v1(rankings: list[dict], db: AsyncSession) -> dict[str, float]:
    """Simple 1v1 Glicko-2 update."""
    p1, p2 = rankings
    r1 = await get_arena_rating(uuid.UUID(p1["user_id"]), db)
    r2 = await get_arena_rating(uuid.UUID(p2["user_id"]), db)

    # Apply RD decay for inactivity
    r1.rd = apply_rd_decay(r1.rd, r1.last_played)
    r2.rd = apply_rd_decay(r2.rd, r2.last_played)

    # Determine outcome from rank (1 = best)
    if p1["rank"] < p2["rank"]:
        score1, score2 = 1.0, 0.0
    elif p1["rank"] > p2["rank"]:
        score1, score2 = 0.0, 1.0
    else:
        score1, score2 = 0.5, 0.5

    new_r1, new_rd1, new_v1 = calculate_glicko2(
        r1.rating, r1.rd, r1.volatility,
        r2.rating, r2.rd, score1,
    )
    new_r2, new_rd2, new_v2 = calculate_glicko2(
        r2.rating, r2.rd, r2.volatility,
        r1.rating, r1.rd, score2,
    )

    delta1 = new_r1 - r1.rating
    delta2 = new_r2 - r2.rating

    _apply_rating_update(r1, new_r1, new_rd1, new_v1, score1 == 1.0, score1 == 0.0)
    _apply_rating_update(r2, new_r2, new_rd2, new_v2, score2 == 1.0, score2 == 0.0)

    return {p1["user_id"]: delta1, p2["user_id"]: delta2}


async def _update_ffa(
    rankings: list[dict],
    session_id: uuid.UUID,
    db: AsyncSession,
) -> dict[str, float]:
    """3-4 player FFA: virtual pairwise comparisons with averaged deltas.

    S3-12 protections:
    a) RD-weighted gain: gain *= (1 - opponent_rd / 350)
    b) Rating gap cap: pairwise delta clamped to MAX_FFA_RATING_GAP effect
    c) Repeat opponent diminishing returns (via Redis counter, session-idempotent)
    d) Cherry-picking detection logged for anti-cheat
    """
    ratings: dict[str, PvPRating] = {}
    for p in rankings:
        r = await get_arena_rating(uuid.UUID(p["user_id"]), db)
        r.rd = apply_rd_decay(r.rd, r.last_played)
        ratings[p["user_id"]] = r

    n = len(rankings)
    deltas: dict[str, float] = {p["user_id"]: 0.0 for p in rankings}
    # FIX-3: Accumulate pairwise RD and volatility for proper Glicko-2 averaging
    rd_accum: dict[str, list[float]] = {p["user_id"]: [] for p in rankings}
    vol_accum: dict[str, list[float]] = {p["user_id"]: [] for p in rankings}

    for i, p1 in enumerate(rankings):
        for j, p2 in enumerate(rankings):
            if i >= j:
                continue

            r1 = ratings[p1["user_id"]]
            r2 = ratings[p2["user_id"]]

            if p1["rank"] < p2["rank"]:
                score = 1.0
            elif p1["rank"] > p2["rank"]:
                score = 0.0
            else:
                score = 0.5

            new_r1, new_rd1, new_v1 = calculate_glicko2(
                r1.rating, r1.rd, r1.volatility,
                r2.rating, r2.rd, score,
            )
            raw_delta_1 = (new_r1 - r1.rating) / (n - 1)
            rd_accum[p1["user_id"]].append(new_rd1)
            vol_accum[p1["user_id"]].append(new_v1)

            new_r2, new_rd2, new_v2 = calculate_glicko2(
                r2.rating, r2.rd, r2.volatility,
                r1.rating, r1.rd, 1.0 - score,
            )
            raw_delta_2 = (new_r2 - r2.rating) / (n - 1)
            rd_accum[p2["user_id"]].append(new_rd2)
            vol_accum[p2["user_id"]].append(new_v2)

            # S3-12a: RD-weighted gain — uncertain opponents give less gain
            rd_weight_1 = max(0.1, 1.0 - r2.rd / FFA_RD_WEIGHT_BASE)
            rd_weight_2 = max(0.1, 1.0 - r1.rd / FFA_RD_WEIGHT_BASE)

            # S3-12b: Rating gap attenuation — huge gaps reduce gain
            gap = abs(r1.rating - r2.rating)
            if gap > MAX_FFA_RATING_GAP:
                gap_factor = MAX_FFA_RATING_GAP / gap  # Linear attenuation
            else:
                gap_factor = 1.0

            # Apply only to gains (positive deltas), not losses
            if raw_delta_1 > 0:
                raw_delta_1 *= rd_weight_1 * gap_factor
            if raw_delta_2 > 0:
                raw_delta_2 *= rd_weight_2 * gap_factor

            deltas[p1["user_id"]] += raw_delta_1
            deltas[p2["user_id"]] += raw_delta_2

    # S3-12c: Repeat opponent diminishing returns (session-idempotent)
    repeat_factors = await _get_repeat_factors(rankings, session_id)

    # S3-12d: Cherry-picking detection
    _check_cherry_picking(rankings, ratings)

    # Apply averaged deltas with repeat factor + proper RD/vol from Glicko-2
    for uid, delta in deltas.items():
        r = ratings[uid]
        factor = repeat_factors.get(uid, 1.0)
        adjusted_delta = delta * factor if delta > 0 else delta
        new_rating = r.rating + adjusted_delta

        # FIX-3: Average RD and volatility from all pairwise Glicko-2 calculations
        # instead of crude r.rd * 0.95. This properly converges RD after FFA.
        pairwise_rds = rd_accum[uid]
        pairwise_vols = vol_accum[uid]
        new_rd = sum(pairwise_rds) / len(pairwise_rds) if pairwise_rds else r.rd
        new_vol = sum(pairwise_vols) / len(pairwise_vols) if pairwise_vols else r.volatility

        player_rank = next(p["rank"] for p in rankings if p["user_id"] == uid)
        is_win = player_rank == 1
        is_loss = player_rank == n

        _apply_rating_update(r, new_rating, new_rd, new_vol, is_win, is_loss)
        deltas[uid] = adjusted_delta  # Update with adjusted value

    return deltas


async def _get_repeat_factors(
    rankings: list[dict],
    session_id: uuid.UUID,
) -> dict[str, float]:
    """S3-12c: Check Redis for repeat opponent matches, return decay factors.

    FIX-1 (v13): Session-idempotent — uses SADD with session_id instead of
    bare INCR. If the same session is processed twice (retry/rollback),
    the counter stays the same because SADD is a set operation.
    """
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()

        factors: dict[str, float] = {}
        sid = str(session_id)

        for p in rankings:
            uid = p["user_id"]
            opponents = [q["user_id"] for q in rankings if q["user_id"] != uid]
            max_repeats = 0
            for opp_id in opponents:
                # Sorted key to avoid A-vs-B and B-vs-A duplication
                pair = ":".join(sorted([uid, opp_id]))
                key = f"ffa:repeat:{pair}"
                # SADD is idempotent: adding same session_id twice = no effect
                await r.sadd(key, sid)
                await r.expire(key, 86400)  # 24h window
                count = await r.scard(key)
                max_repeats = max(max_repeats, count)

            # Decay factor based on repeat count
            idx = min(max_repeats - 1, len(REPEAT_OPPONENT_DECAY) - 1)
            factors[uid] = REPEAT_OPPONENT_DECAY[idx] if max_repeats > 0 else 1.0

        return factors
    except Exception:
        # Redis down — no repeat tracking, full gain
        return {}


def _check_cherry_picking(
    rankings: list[dict],
    ratings: dict[str, PvPRating],
) -> None:
    """S3-12d: Log cherry-picking pattern for anti-cheat L1.

    Cherry-picking: a high-rated player consistently plays against
    opponents with high RD (uncertain/new players).
    """
    for p in rankings:
        uid = p["user_id"]
        player_r = ratings[uid]

        # Only flag strong players (rating > 1800)
        if player_r.rating < 1800:
            continue

        opponents = [
            ratings[q["user_id"]] for q in rankings
            if q["user_id"] != uid
        ]
        high_rd_opponents = sum(1 for opp in opponents if opp.rd > 300)

        if high_rd_opponents >= CHERRY_PICK_THRESHOLD:
            logger.warning(
                "ANTI-CHEAT L1: Cherry-picking suspected: user=%s (%.0f) "
                "played %d/%d opponents with RD>300",
                uid, player_r.rating, high_rd_opponents, len(opponents),
            )


def _apply_rating_update(
    rating: PvPRating,
    new_rating: float,
    new_rd: float,
    new_vol: float,
    is_win: bool,
    is_loss: bool,
) -> None:
    """Apply rating changes to PvPRating DB model."""
    rating.rating = round(new_rating, 1)
    rating.rd = round(new_rd, 1)
    rating.volatility = round(new_vol, 6)
    rating.rank_tier = rank_from_rating(rating.rating, rating.placement_done)
    rating.total_duels += 1
    rating.last_played = datetime.now(timezone.utc)

    if is_win:
        rating.wins += 1
        rating.current_streak = max(1, rating.current_streak + 1) if rating.current_streak >= 0 else 1
        rating.best_streak = max(rating.best_streak, rating.current_streak)
    elif is_loss:
        rating.losses += 1
        rating.current_streak = min(-1, rating.current_streak - 1) if rating.current_streak <= 0 else -1
    else:
        rating.draws += 1
        rating.current_streak = 0

    if rating.rating > rating.peak_rating:
        rating.peak_rating = rating.rating
        rating.peak_tier = rating.rank_tier

    # Placement tracking
    if not rating.placement_done:
        rating.placement_count += 1
        if rating.placement_count >= 10:
            rating.placement_done = True
