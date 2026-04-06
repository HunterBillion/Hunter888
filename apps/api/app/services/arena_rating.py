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
        rating_deltas = await _update_ffa(human_rankings, db)

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


async def _update_ffa(rankings: list[dict], db: AsyncSession) -> dict[str, float]:
    """3-4 player FFA: virtual pairwise comparisons with averaged deltas."""
    ratings: dict[str, PvPRating] = {}
    for p in rankings:
        r = await get_arena_rating(uuid.UUID(p["user_id"]), db)
        r.rd = apply_rd_decay(r.rd, r.last_played)
        ratings[p["user_id"]] = r

    n = len(rankings)
    deltas: dict[str, float] = {p["user_id"]: 0.0 for p in rankings}

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

            new_r1, _, _ = calculate_glicko2(
                r1.rating, r1.rd, r1.volatility,
                r2.rating, r2.rd, score,
            )
            deltas[p1["user_id"]] += (new_r1 - r1.rating) / (n - 1)

            new_r2, _, _ = calculate_glicko2(
                r2.rating, r2.rd, r2.volatility,
                r1.rating, r1.rd, 1.0 - score,
            )
            deltas[p2["user_id"]] += (new_r2 - r2.rating) / (n - 1)

    # Apply averaged deltas
    for uid, delta in deltas.items():
        r = ratings[uid]
        new_rating = r.rating + delta
        new_rd = max(30.0, r.rd * 0.95)

        player_rank = next(p["rank"] for p in rankings if p["user_id"] == uid)
        is_win = player_rank == 1
        is_loss = player_rank == n

        _apply_rating_update(r, new_rating, new_rd, r.volatility, is_win, is_loss)

    return deltas


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
