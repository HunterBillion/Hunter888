"""Glicko-2 rating algorithm implementation (Agent 8 — PvP Battle).

Reference: Mark Glickman, "Example of the Glicko-2 System" (2013).
http://www.glicko.net/glicko/glicko2.pdf

Parameters:
- τ (tau): system constant controlling volatility change. Typical: 0.3-1.2.
  We use 0.5 (moderate: not too volatile, not too rigid).
- Default rating: 1500 (Glicko-2 scale: μ = (r-1500)/173.7178)
- Default RD: 350
- Default volatility: 0.06
- RD decay: +15/week inactive, cap at 250
- Placement: first 10 duels, RD decreases at 2× rate
"""

import logging
import math
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pvp import PvPRating, PvPRankTier, rank_from_rating

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TAU = 0.5           # System constant (volatility control)
EPSILON = 0.000001  # Convergence tolerance
SCALE = 173.7178    # Glicko-2 scaling factor (400 / ln(10))
DEFAULT_RATING = 1500.0
DEFAULT_RD = 350.0
DEFAULT_VOL = 0.06
MAX_RD = 350.0
MIN_RD = 30.0
PLACEMENT_MATCHES = 10
RD_DECAY_PER_WEEK = 15.0
RD_DECAY_CAP = 250.0

# PvE gives 50% of rating change
PVE_RATING_MULTIPLIER = 0.5


# ---------------------------------------------------------------------------
# Glicko-2 math (pure functions)
# ---------------------------------------------------------------------------

def _to_glicko2(rating: float, rd: float) -> tuple[float, float]:
    """Convert Glicko-1 scale to Glicko-2 scale."""
    mu = (rating - DEFAULT_RATING) / SCALE
    phi = rd / SCALE
    return mu, phi


def _from_glicko2(mu: float, phi: float) -> tuple[float, float]:
    """Convert Glicko-2 scale back to Glicko-1 scale."""
    rating = mu * SCALE + DEFAULT_RATING
    rd = phi * SCALE
    return rating, rd


def _g(phi: float) -> float:
    """Glicko-2 g function: reduces impact of uncertain opponents."""
    return 1.0 / math.sqrt(1.0 + 3.0 * phi ** 2 / (math.pi ** 2))


def _E(mu: float, mu_j: float, phi_j: float) -> float:
    """Expected score (win probability)."""
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def _compute_variance(mu: float, opponents: list[tuple[float, float]]) -> float:
    """Compute estimated variance of player's rating (v)."""
    v_inv = 0.0
    for mu_j, phi_j in opponents:
        g_val = _g(phi_j)
        e_val = _E(mu, mu_j, phi_j)
        v_inv += g_val ** 2 * e_val * (1.0 - e_val)
    if v_inv == 0.0:
        return 1e6  # Very large variance (no opponents)
    return 1.0 / v_inv


def _compute_delta(
    mu: float,
    opponents: list[tuple[float, float]],
    scores: list[float],
    v: float,
) -> float:
    """Compute estimated improvement (δ)."""
    total = 0.0
    for (mu_j, phi_j), s in zip(opponents, scores):
        total += _g(phi_j) * (s - _E(mu, mu_j, phi_j))
    return v * total


def _new_volatility(
    sigma: float, phi: float, v: float, delta: float
) -> float:
    """Illinois algorithm for new volatility (σ')."""
    a = math.log(sigma ** 2)
    tau2 = TAU ** 2

    def f(x: float) -> float:
        ex = math.exp(x)
        d2 = delta ** 2
        phi2 = phi ** 2
        num1 = ex * (d2 - phi2 - v - ex)
        den1 = 2.0 * (phi2 + v + ex) ** 2
        return num1 / den1 - (x - a) / tau2

    # Set initial boundaries
    A = a
    if delta ** 2 > phi ** 2 + v:
        B = math.log(delta ** 2 - phi ** 2 - v)
    else:
        k = 1
        while f(a - k * TAU) < 0:
            k += 1
        B = a - k * TAU

    # Illinois algorithm (bisection variant)
    fA = f(A)
    fB = f(B)

    iterations = 0
    while abs(B - A) > EPSILON and iterations < 100:
        C = A + (A - B) * fA / (fB - fA)
        fC = f(C)

        if fC * fB <= 0:
            A = B
            fA = fB
        else:
            fA /= 2.0

        B = C
        fB = fC
        iterations += 1

    return math.exp(A / 2.0)


def calculate_glicko2(
    rating: float,
    rd: float,
    volatility: float,
    opponent_rating: float,
    opponent_rd: float,
    score: float,  # 1.0 = win, 0.5 = draw, 0.0 = loss
    is_pve: bool = False,
    is_placement: bool = False,
) -> tuple[float, float, float]:
    """Calculate new Glicko-2 rating after a single game.

    Args:
        rating: current rating (Glicko-1 scale)
        rd: current rating deviation
        volatility: current volatility (σ)
        opponent_rating: opponent's rating
        opponent_rd: opponent's RD
        score: game outcome (1.0/0.5/0.0)
        is_pve: if True, rating change × 0.5
        is_placement: if True, RD decreases at 2× rate

    Returns:
        (new_rating, new_rd, new_volatility)
    """
    # Step 1: Convert to Glicko-2 scale
    mu, phi = _to_glicko2(rating, rd)
    mu_j, phi_j = _to_glicko2(opponent_rating, opponent_rd)

    opponents = [(mu_j, phi_j)]
    scores = [score]

    # Step 2: Compute variance
    v = _compute_variance(mu, opponents)

    # Step 3: Compute delta
    delta = _compute_delta(mu, opponents, scores, v)

    # Step 4: New volatility
    sigma_new = _new_volatility(volatility, phi, v, delta)

    # Step 5: Pre-rating period phi*
    phi_star = math.sqrt(phi ** 2 + sigma_new ** 2)

    # Step 6: New phi and mu
    phi_new = 1.0 / math.sqrt(1.0 / phi_star ** 2 + 1.0 / v)
    mu_new = mu + phi_new ** 2 * sum(
        _g(phi_j) * (s - _E(mu, mu_j, phi_j))
        for (mu_j, phi_j), s in zip(opponents, scores)
    )

    # Placement acceleration: RD drops faster
    if is_placement:
        phi_new *= 0.5  # 2× faster convergence

    # Convert back
    new_rating, new_rd = _from_glicko2(mu_new, phi_new)

    # PvE multiplier: only 50% rating change
    if is_pve:
        rating_delta = (new_rating - rating) * PVE_RATING_MULTIPLIER
        new_rating = rating + rating_delta

    # Clamp
    new_rating = max(0.0, min(3000.0, new_rating))
    new_rd = max(MIN_RD, min(MAX_RD, new_rd))

    return new_rating, new_rd, sigma_new


def apply_rd_decay(rd: float, last_played: datetime | None) -> float:
    """Apply RD decay for inactive players. +15/week, cap at 250."""
    if last_played is None:
        return rd

    now = datetime.now(timezone.utc)
    weeks_inactive = (now - last_played).total_seconds() / (7 * 24 * 3600)

    if weeks_inactive < 1.0:
        return rd

    new_rd = rd + RD_DECAY_PER_WEEK * weeks_inactive
    return min(new_rd, RD_DECAY_CAP)


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

async def get_or_create_rating(
    user_id: uuid.UUID, db: AsyncSession
) -> PvPRating:
    """Get existing rating or create a new one with defaults.

    Race-safe: if two concurrent requests try to create the same rating,
    the second one catches the IntegrityError (UNIQUE on user_id) and
    re-fetches the row that the first request created.
    """
    from sqlalchemy.exc import IntegrityError

    result = await db.execute(
        select(PvPRating).where(PvPRating.user_id == user_id)
    )
    rating = result.scalar_one_or_none()

    if rating is None:
        rating = PvPRating(
            user_id=user_id,
            rating=DEFAULT_RATING,
            rd=DEFAULT_RD,
            volatility=DEFAULT_VOL,
            rank_tier=PvPRankTier.unranked,
        )
        db.add(rating)
        try:
            await db.flush()
            logger.info("Created PvP rating for user %s", user_id)
        except IntegrityError:
            # Another request created the rating first — rollback and re-fetch
            await db.rollback()
            result = await db.execute(
                select(PvPRating).where(PvPRating.user_id == user_id)
            )
            rating = result.scalar_one()
            logger.debug("PvP rating already existed for user %s (concurrent create)", user_id)

    return rating


async def update_rating_after_duel(
    user_id: uuid.UUID,
    opponent_id: uuid.UUID,
    score: float,
    is_pve: bool,
    db: AsyncSession,
) -> tuple[PvPRating, float]:
    """Update user's Glicko-2 rating after a duel.

    Returns:
        (updated_rating, rating_delta)
    """
    user_rating = await get_or_create_rating(user_id, db)
    opp_rating = await get_or_create_rating(opponent_id, db)

    # Apply RD decay before calculation
    user_rating.rd = apply_rd_decay(user_rating.rd, user_rating.last_played)

    old_rating = user_rating.rating
    is_placement = not user_rating.placement_done

    new_r, new_rd, new_vol = calculate_glicko2(
        rating=user_rating.rating,
        rd=user_rating.rd,
        volatility=user_rating.volatility,
        opponent_rating=opp_rating.rating,
        opponent_rd=opp_rating.rd,
        score=score,
        is_pve=is_pve,
        is_placement=is_placement,
    )

    rating_delta = new_r - old_rating

    # Update fields
    user_rating.rating = new_r
    user_rating.rd = new_rd
    user_rating.volatility = new_vol
    user_rating.last_played = datetime.now(timezone.utc)
    user_rating.last_rd_decay = datetime.now(timezone.utc)
    user_rating.total_duels += 1

    # Win/loss/draw
    if score == 1.0:
        user_rating.wins += 1
        user_rating.current_streak = max(1, user_rating.current_streak + 1)
    elif score == 0.0:
        user_rating.losses += 1
        user_rating.current_streak = min(-1, user_rating.current_streak - 1)
    else:
        user_rating.draws += 1
        user_rating.current_streak = 0

    user_rating.best_streak = max(user_rating.best_streak, user_rating.current_streak)

    # Placement tracking
    if not user_rating.placement_done:
        user_rating.placement_count += 1
        if user_rating.placement_count >= PLACEMENT_MATCHES:
            user_rating.placement_done = True
            logger.info(
                "User %s completed placement: rating=%.0f", user_id, new_r
            )

    # Peak tracking
    if new_r > user_rating.peak_rating:
        user_rating.peak_rating = new_r

    # Rank tier
    user_rating.rank_tier = rank_from_rating(new_r, user_rating.placement_done)
    if user_rating.rank_tier.value > user_rating.peak_tier.value:
        user_rating.peak_tier = user_rating.rank_tier

    db.add(user_rating)
    await db.flush()

    logger.info(
        "PvP rating update: user=%s, %.0f → %.0f (Δ%+.0f), RD=%.0f, tier=%s",
        user_id, old_rating, new_r, rating_delta, new_rd, user_rating.rank_tier.value,
    )

    return user_rating, rating_delta


async def apply_season_reset(db: AsyncSession, season_id: uuid.UUID) -> int:
    """Soft reset all ratings for new season.

    Formula: r_new = r * 0.75 + 1500 * 0.25, RD = 150.
    Returns number of ratings reset.
    """
    result = await db.execute(select(PvPRating))
    ratings = result.scalars().all()
    count = 0

    for r in ratings:
        r.rating = r.rating * 0.75 + DEFAULT_RATING * 0.25
        r.rd = 150.0
        r.placement_done = True  # Keep placement status across seasons
        r.current_streak = 0
        r.season_id = season_id
        r.rank_tier = rank_from_rating(r.rating, r.placement_done)
        db.add(r)
        count += 1

    await db.flush()
    logger.info("Season reset applied to %d ratings", count)
    return count
