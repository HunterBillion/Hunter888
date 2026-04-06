"""PvP Matchmaker with Redis queue (Agent 8 — PvP Battle).

Matchmaking algorithm:
1. Player joins queue via WebSocket
2. Matchmaker searches for opponent: |r1-r2| < 200 + (RD1+RD2)/2
3. Range expands over time: +5 per second waited
4. If no match in 90s → offer PvE duel (AI bot, 50% rating points)
5. On match → create PvPDuel, notify both players via WS

Difficulty assignment:
- Both < 1600: Easy (×1.0)
- 1600-2200: Medium (×1.3)
- > 2200: Hard (×1.6)

Redis keys:
- pvp:queue — sorted set (score = rating, member = user_id)
- pvp:queue:{user_id} — hash with queue metadata
- pvp:duel:{duel_id}:state — duel state for WS reconnect
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.redis_pool import get_redis as _redis
from app.models.pvp import (
    DuelDifficulty,
    DuelStatus,
    MatchQueueStatus,
    PvPDuel,
    PvPMatchQueue,
)
from app.services.glicko2 import get_or_create_rating

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Redis connection (uses centralized pool from app.core.redis_pool)
# ---------------------------------------------------------------------------

QUEUE_KEY = "pvp:queue"
QUEUE_META_KEY = "pvp:queue:{user_id}"
DUEL_STATE_KEY = "pvp:duel:{duel_id}:state"
RECONNECT_KEY = "pvp:reconnect:{user_id}"
INVITATION_KEY = "pvp:invitation:{challenger_id}"
INVITATION_MATCHED_KEY = "pvp:invitation:matched:{challenger_id}"

MATCH_TIMEOUT_SECONDS = 90          # After this, offer PvE
RANGE_EXPANSION_RATE = 5.0          # Points per second
BASE_MATCH_RANGE = 200.0
DUEL_STATE_TTL = 3600               # 1 hour TTL for duel state in Redis
RECONNECT_GRACE_SECONDS = 60        # Grace period for reconnection


# ---------------------------------------------------------------------------
# Difficulty assignment
# ---------------------------------------------------------------------------

def determine_difficulty(rating1: float, rating2: float) -> DuelDifficulty:
    """Assign difficulty based on average rating of both players."""
    avg = (rating1 + rating2) / 2
    if avg < 1600:
        return DuelDifficulty.easy
    elif avg < 2200:
        return DuelDifficulty.medium
    else:
        return DuelDifficulty.hard


# ---------------------------------------------------------------------------
# Queue operations
# ---------------------------------------------------------------------------

async def join_queue(
    user_id: uuid.UUID,
    db: AsyncSession,
    *,
    create_invitation: bool = False,
) -> dict:
    """Add player to matchmaking queue.

    Returns:
        {"status": "queued", "rating": float, "rd": float, "position": int}
    """
    r = _redis()

    # Acquire lock to prevent race condition (two concurrent joins for same user)
    lock_key = f"pvp:queue:lock:{user_id}"
    acquired = await r.set(lock_key, "1", nx=True, ex=10)
    if not acquired:
        return {"status": "already_queued", "rating": 0, "position": 0}

    try:
        # Check if already in queue
        existing = await r.zscore(QUEUE_KEY, str(user_id))
        if existing is not None:
            return {
                "status": "already_queued",
                "rating": existing,
                "position": await r.zcard(QUEUE_KEY),
            }

        # Get player rating
        rating = await get_or_create_rating(user_id, db)

        # Add to sorted set (score = rating for range queries)
        await r.zadd(QUEUE_KEY, {str(user_id): rating.rating})
    finally:
        await r.delete(lock_key)

    # Store metadata
    meta_key = QUEUE_META_KEY.format(user_id=user_id)
    await r.hset(meta_key, mapping={
        "rating": str(rating.rating),
        "rd": str(rating.rd),
        "queued_at": str(time.time()),
        "status": MatchQueueStatus.waiting.value,
    })
    await r.expire(meta_key, MATCH_TIMEOUT_SECONDS + 30)

    # Also persist in DB
    queue_entry = PvPMatchQueue(
        user_id=user_id,
        rating=rating.rating,
        rd=rating.rd,
        status=MatchQueueStatus.waiting,
    )
    db.add(queue_entry)
    await db.flush()

    position = await r.zcard(QUEUE_KEY)

    if create_invitation:
        inv_key = INVITATION_KEY.format(challenger_id=user_id)
        await r.set(inv_key, "1", ex=MATCH_TIMEOUT_SECONDS)

    logger.info(
        "Player %s joined PvP queue (rating=%.0f, rd=%.0f, pos=%d)",
        user_id, rating.rating, rating.rd, position,
    )

    return {
        "status": "queued",
        "rating": rating.rating,
        "rd": rating.rd,
        "position": position,
        "invitation_enabled": create_invitation,
    }


async def leave_queue(user_id: uuid.UUID) -> bool:
    """Remove player from matchmaking queue."""
    r = _redis()
    removed = await r.zrem(QUEUE_KEY, str(user_id))
    meta_key = QUEUE_META_KEY.format(user_id=user_id)
    await r.delete(meta_key)
    inv_key = INVITATION_KEY.format(challenger_id=user_id)
    await r.delete(inv_key)

    if removed:
        logger.info("Player %s left PvP queue", user_id)
    return bool(removed)


async def accept_invitation(
    challenger_id: uuid.UUID,
    acceptor_id: uuid.UUID,
    db: AsyncSession,
) -> dict | None:
    """Accept PvP invitation: create duel, store for challenger's find_match.

    Returns match dict or None if invitation expired/invalid.
    """
    r = _redis()

    if challenger_id == acceptor_id:
        return None

    inv_key = INVITATION_KEY.format(challenger_id=challenger_id)
    if not await r.exists(inv_key):
        return None

    # Challenger must still be in queue
    if await r.zscore(QUEUE_KEY, str(challenger_id)) is None:
        await r.delete(inv_key)
        return None

    # Acceptor must not be in queue
    if await r.zscore(QUEUE_KEY, str(acceptor_id)) is not None:
        return None

    # Get ratings
    challenger_rating = await get_or_create_rating(challenger_id, db)
    acceptor_rating = await get_or_create_rating(acceptor_id, db)
    difficulty = determine_difficulty(challenger_rating.rating, acceptor_rating.rating)

    duel = PvPDuel(
        player1_id=challenger_id,
        player2_id=acceptor_id,
        status=DuelStatus.pending,
        difficulty=difficulty,
    )
    db.add(duel)
    await db.flush()

    # Remove challenger from queue and delete invitation
    await r.zrem(QUEUE_KEY, str(challenger_id))
    await r.delete(inv_key)
    await r.delete(QUEUE_META_KEY.format(user_id=challenger_id))

    # Store for challenger's find_match to pick up
    matched_key = INVITATION_MATCHED_KEY.format(challenger_id=challenger_id)
    await r.hset(matched_key, mapping={
        "duel_id": str(duel.id),
        "opponent_id": str(acceptor_id),
        "player1_id": str(challenger_id),
        "player2_id": str(acceptor_id),
        "player1_rating": str(challenger_rating.rating),
        "player2_rating": str(acceptor_rating.rating),
        "difficulty": difficulty.value,
    })
    await r.expire(matched_key, 30)

    logger.info(
        "PvP invitation accepted: %s vs %s, duel=%s",
        challenger_id, acceptor_id, duel.id,
    )

    return {
        "opponent_id": acceptor_id,
        "duel_id": duel.id,
        "player1_id": challenger_id,
        "player2_id": acceptor_id,
        "player1_rating": challenger_rating.rating,
        "player2_rating": acceptor_rating.rating,
        "difficulty": difficulty.value,
    }


async def find_match(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> dict | None:
    """Try to find a suitable opponent for the player.

    First checks if someone accepted an invitation.
    Then searches queue by rating range.

    Returns:
        {"opponent_id": UUID, "duel_id": UUID, "difficulty": str} if matched,
        None if no match found yet.
    """
    r = _redis()

    # Check if invitation was accepted
    matched_key = INVITATION_MATCHED_KEY.format(challenger_id=user_id)
    matched = await r.hgetall(matched_key)
    if matched:
        await r.delete(matched_key)
        return {
            "opponent_id": uuid.UUID(matched["opponent_id"]),
            "duel_id": uuid.UUID(matched["duel_id"]),
            "player1_id": uuid.UUID(matched["player1_id"]),
            "player2_id": uuid.UUID(matched["player2_id"]),
            "player1_rating": float(matched["player1_rating"]),
            "player2_rating": float(matched["player2_rating"]),
            "difficulty": matched["difficulty"],
        }

    # Get player's data
    meta_key = QUEUE_META_KEY.format(user_id=user_id)
    meta = await r.hgetall(meta_key)

    if not meta:
        return None

    player_rating = float(meta["rating"])
    player_rd = float(meta["rd"])
    queued_at = float(meta["queued_at"])
    seconds_waited = time.time() - queued_at

    # Calculate match range (expands over time)
    expanded_range = BASE_MATCH_RANGE + seconds_waited * RANGE_EXPANSION_RATE
    match_range = expanded_range + player_rd / 2

    # Search for opponents in range
    min_rating = player_rating - match_range
    max_rating = player_rating + match_range

    # Get candidates from sorted set
    candidates = await r.zrangebyscore(
        QUEUE_KEY, min_rating, max_rating, withscores=True
    )

    for candidate_id_str, candidate_rating in candidates:
        candidate_id = uuid.UUID(candidate_id_str)

        # Skip self
        if candidate_id == user_id:
            continue

        # Check candidate's RD for refined match range
        c_meta_key = QUEUE_META_KEY.format(user_id=candidate_id)
        c_meta = await r.hgetall(c_meta_key)
        if not c_meta or c_meta.get("status") != MatchQueueStatus.waiting.value:
            continue

        c_rd = float(c_meta.get("rd", 350))
        refined_range = BASE_MATCH_RANGE + (player_rd + c_rd) / 2

        # Check if within refined range
        if abs(player_rating - candidate_rating) <= refined_range + seconds_waited * RANGE_EXPANSION_RATE:
            # MATCH FOUND — create duel
            difficulty = determine_difficulty(player_rating, candidate_rating)

            duel = PvPDuel(
                player1_id=user_id,
                player2_id=candidate_id,
                status=DuelStatus.pending,
                difficulty=difficulty,
            )

            # BUG-6 fix: execute Redis pipeline BEFORE db.flush() to prevent
            # race where duel exists in DB but Redis state is not yet ready.
            # duel.id is available pre-flush because PvPDuel uses default=uuid.uuid4.
            duel_state_key = DUEL_STATE_KEY.format(duel_id=duel.id)
            pipe = r.pipeline(transaction=True)
            pipe.zrem(QUEUE_KEY, str(user_id), candidate_id_str)
            for uid in [str(user_id), candidate_id_str]:
                mk = QUEUE_META_KEY.format(user_id=uid)
                pipe.hset(mk, "status", MatchQueueStatus.matched.value)
            pipe.hset(duel_state_key, mapping={
                "player1_id": str(user_id),
                "player2_id": str(candidate_id),
                "status": DuelStatus.pending.value,
                "difficulty": difficulty.value,
                "round": "1",
                "created_at": str(time.time()),
            })
            pipe.expire(duel_state_key, DUEL_STATE_TTL)
            await pipe.execute()

            # Now persist to DB — Redis state is already ready for reconnecting clients
            db.add(duel)
            await db.flush()

            logger.info(
                "PvP match: %s (%.0f) vs %s (%.0f), difficulty=%s, duel=%s",
                user_id, player_rating,
                candidate_id, candidate_rating,
                difficulty.value, duel.id,
            )

            return {
                "opponent_id": candidate_id,
                "duel_id": duel.id,
                "player1_id": user_id,
                "player2_id": candidate_id,
                "player1_rating": player_rating,
                "player2_rating": candidate_rating,
                "difficulty": difficulty.value,
            }

    # No match found
    if seconds_waited >= MATCH_TIMEOUT_SECONDS:
        logger.info(
            "PvP match timeout for %s after %.0fs, offering PvE",
            user_id, seconds_waited,
        )
        return None  # Caller should offer PvE

    return None


async def create_pve_duel(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> PvPDuel:
    """Create a PvE duel against AI bot when no PvP match found.

    Bot rating calibrated to player's rating ± small random offset.
    PvE duels give 50% rating points.
    """
    rating = await get_or_create_rating(user_id, db)

    # Bot uses a sentinel UUID
    bot_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    difficulty = determine_difficulty(rating.rating, rating.rating)

    duel = PvPDuel(
        player1_id=user_id,
        player2_id=bot_id,
        status=DuelStatus.pending,
        difficulty=difficulty,
        is_pve=True,
    )
    db.add(duel)
    await db.flush()

    # Remove from queue
    await leave_queue(user_id)

    # Store duel state
    r = _redis()
    duel_state_key = DUEL_STATE_KEY.format(duel_id=duel.id)
    await r.hset(duel_state_key, mapping={
        "player1_id": str(user_id),
        "player2_id": str(bot_id),
        "status": DuelStatus.pending.value,
        "difficulty": difficulty.value,
        "is_pve": "true",
        "round": "1",
        "created_at": str(time.time()),
    })
    await r.expire(duel_state_key, DUEL_STATE_TTL)

    logger.info("PvE duel created: user=%s, duel=%s", user_id, duel.id)
    return duel


# ---------------------------------------------------------------------------
# Duel state management (Redis)
# ---------------------------------------------------------------------------

async def get_duel_state(duel_id: uuid.UUID) -> dict | None:
    """Get current duel state from Redis."""
    r = _redis()
    key = DUEL_STATE_KEY.format(duel_id=duel_id)
    state = await r.hgetall(key)
    return state if state else None


async def update_duel_state(duel_id: uuid.UUID, updates: dict) -> None:
    """Update duel state in Redis."""
    r = _redis()
    key = DUEL_STATE_KEY.format(duel_id=duel_id)
    await r.hset(key, mapping={k: str(v) for k, v in updates.items()})


async def set_reconnect_grace(user_id: uuid.UUID, duel_id: uuid.UUID) -> None:
    """Set reconnect grace period for a disconnected player."""
    r = _redis()
    key = RECONNECT_KEY.format(user_id=user_id)
    await r.hset(key, mapping={
        "duel_id": str(duel_id),
        "disconnected_at": str(time.time()),
    })
    await r.expire(key, RECONNECT_GRACE_SECONDS)


async def check_reconnect(user_id: uuid.UUID) -> dict | None:
    """Check if player has an active reconnect window."""
    r = _redis()
    key = RECONNECT_KEY.format(user_id=user_id)
    data = await r.hgetall(key)

    if not data:
        return None

    disconnected_at = float(data.get("disconnected_at", 0))
    elapsed = time.time() - disconnected_at

    if elapsed > RECONNECT_GRACE_SECONDS:
        await r.delete(key)
        return None

    return {
        "duel_id": uuid.UUID(data["duel_id"]),
        "seconds_remaining": int(RECONNECT_GRACE_SECONDS - elapsed),
    }


async def clear_reconnect_grace(user_id: uuid.UUID) -> None:
    """Clear reconnect grace once a player is back online."""
    r = _redis()
    key = RECONNECT_KEY.format(user_id=user_id)
    await r.delete(key)


async def cleanup_duel_state(duel_id: uuid.UUID) -> None:
    """Remove duel state from Redis after completion."""
    r = _redis()
    key = DUEL_STATE_KEY.format(duel_id=duel_id)
    await r.delete(key)


# ---------------------------------------------------------------------------
# Promotion / Demotion Logic (DOC_13)
# ---------------------------------------------------------------------------

TIER_BOUNDARIES: dict[str, tuple[int, int]] = {
    "iron": (0, 999),
    "bronze": (1000, 1399),
    "silver": (1400, 1699),
    "gold": (1700, 1999),
    "platinum": (2000, 2299),
    "diamond": (2300, 2599),
    "master": (2600, 2899),
    "grandmaster": (2900, 9999),
}

TIER_ORDER = ["iron", "bronze", "silver", "gold", "platinum", "diamond", "master", "grandmaster"]
DEMOTION_SHIELD_THRESHOLD = 5  # losses at tier floor before demotion


def get_tier_for_rating(rating: float) -> str:
    """Return tier name for a given rating value."""
    for tier in reversed(TIER_ORDER):
        lo, hi = TIER_BOUNDARIES[tier]
        if rating >= lo:
            return tier
    return "iron"


def get_tier_index(tier: str) -> int:
    """Return numeric index for tier ordering."""
    base = tier.split("_")[0] if "_" in tier else tier
    try:
        return TIER_ORDER.index(base)
    except ValueError:
        return 0


async def check_tier_change(
    user_id: uuid.UUID,
    old_rating: float,
    new_rating: float,
    duel_id: uuid.UUID | None,
    db: AsyncSession,
) -> dict | None:
    """Check if a rating change triggers promotion series or demotion.

    Called after update_rating_after_duel().

    Returns:
        dict with tier change info, or None if no change.
    """
    from app.models.pvp import PromotionSeries, PvPRating
    from datetime import timedelta

    old_tier = get_tier_for_rating(old_rating)
    new_tier = get_tier_for_rating(new_rating)
    old_idx = get_tier_index(old_tier)
    new_idx = get_tier_index(new_tier)

    # --- Check active promotion series first ---
    active_series = (await db.execute(
        select(PromotionSeries).where(
            PromotionSeries.user_id == user_id,
            PromotionSeries.result == None,  # noqa: E711
            PromotionSeries.expires_at > datetime.now(timezone.utc),
        )
    )).scalar_one_or_none()

    if active_series:
        # Player is in a promotion series — update it
        is_win = new_rating > old_rating
        if is_win:
            active_series.wins += 1
        else:
            active_series.losses += 1
        active_series.matches_played += 1

        if duel_id:
            duel_ids = list(active_series.duel_ids or [])
            duel_ids.append(str(duel_id))
            active_series.duel_ids = duel_ids

        # Check if series resolved
        if active_series.wins >= 2:
            # Promoted!
            active_series.result = "promoted"
            active_series.completed_at = datetime.now(timezone.utc)

            # Update rank tier
            rating_obj = (await db.execute(
                select(PvPRating).where(
                    PvPRating.user_id == user_id,
                    PvPRating.rating_type == "training_duel",
                )
            )).scalar_one_or_none()
            if rating_obj:
                from app.models.pvp import rank_from_rating
                rating_obj.rank_tier = rank_from_rating(new_rating, rating_obj.placement_done)
                rating_obj.demotion_shield_losses = 0
                db.add(rating_obj)

            db.add(active_series)
            await db.flush()

            logger.info(
                "Promotion series WON: user=%s %s -> %s",
                user_id, active_series.from_tier, active_series.to_tier,
            )
            return {
                "promotion_completed": True,
                "new_tier": active_series.to_tier,
                "series_wins": active_series.wins,
                "series_losses": active_series.losses,
            }

        elif active_series.losses >= 2:
            # Series failed
            active_series.result = "failed"
            active_series.completed_at = datetime.now(timezone.utc)
            db.add(active_series)
            await db.flush()

            logger.info(
                "Promotion series FAILED: user=%s %s -> %s",
                user_id, active_series.from_tier, active_series.to_tier,
            )
            return {
                "promotion_failed": True,
                "target_tier": active_series.to_tier,
                "series_wins": active_series.wins,
                "series_losses": active_series.losses,
            }

        # Series still in progress
        db.add(active_series)
        await db.flush()
        return {
            "promotion_in_progress": True,
            "target_tier": active_series.to_tier,
            "series_wins": active_series.wins,
            "series_losses": active_series.losses,
            "matches_needed": 3,
        }

    # --- No active series ---
    if new_idx > old_idx:
        # Crossed into higher tier — start promotion series
        series = PromotionSeries(
            user_id=user_id,
            rating_type="training_duel",
            from_tier=old_tier,
            to_tier=new_tier,
            matches_played=1,
            wins=1,  # current win counts
            losses=0,
            duel_ids=[str(duel_id)] if duel_id else [],
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.add(series)
        await db.flush()

        logger.info(
            "Promotion series STARTED: user=%s %s -> %s",
            user_id, old_tier, new_tier,
        )
        return {
            "promotion_started": True,
            "target_tier": new_tier,
            "series_wins": 1,
            "series_losses": 0,
            "matches_needed": 3,
        }

    elif new_idx < old_idx:
        # Rating dropped below tier floor — demotion warning
        rating_obj = (await db.execute(
            select(PvPRating).where(
                PvPRating.user_id == user_id,
                PvPRating.rating_type == "training_duel",
            )
        )).scalar_one_or_none()

        if rating_obj:
            rating_obj.demotion_shield_losses += 1
            if rating_obj.demotion_shield_losses >= DEMOTION_SHIELD_THRESHOLD:
                # Actually demote
                from app.models.pvp import rank_from_rating
                rating_obj.rank_tier = rank_from_rating(new_rating, rating_obj.placement_done)
                rating_obj.demotion_shield_losses = 0
                rating_obj.demotion_warning_issued = False
                db.add(rating_obj)
                await db.flush()

                logger.info("Player DEMOTED: user=%s -> %s", user_id, new_tier)
                return {
                    "demoted": True,
                    "new_tier": new_tier,
                    "losses_until_demotion": 0,
                }
            else:
                rating_obj.demotion_warning_issued = True
                db.add(rating_obj)
                await db.flush()

                remaining = DEMOTION_SHIELD_THRESHOLD - rating_obj.demotion_shield_losses
                logger.info(
                    "Demotion WARNING: user=%s, %d losses until demotion",
                    user_id, remaining,
                )
                return {
                    "demotion_warning": True,
                    "losses_until_demotion": remaining,
                }

    return None


async def is_in_queue(user_id: uuid.UUID) -> bool:
    """Check if player is currently in the matchmaking queue."""
    r = _redis()
    return await r.zscore(QUEUE_KEY, str(user_id)) is not None


async def get_queue_size() -> int:
    """Get current number of players in queue."""
    r = _redis()
    return await r.zcard(QUEUE_KEY)


# ---------------------------------------------------------------------------
# Mode-aware queue operations (DOC_09: Rapid Fire, Gauntlet, Team 2v2)
# ---------------------------------------------------------------------------

MODE_QUEUE_KEY = "pvp:queue:{mode}"
MODE_QUEUE_META_KEY = "pvp:queue:{mode}:{user_id}"
GAUNTLET_COOLDOWN_KEY = "pvp:gauntlet:cooldown:{user_id}"
GAUNTLET_COOLDOWN_SECONDS = 6 * 3600  # 6 hours


async def join_mode_queue(
    user_id: uuid.UUID,
    mode: str,
    db: AsyncSession,
) -> dict:
    """Add player to a mode-specific matchmaking queue.

    For rapid/gauntlet: instant PvE (no matchmaking needed).
    For team2v2: separate queue, needs 2+ players.
    """
    r = _redis()
    queue_key = MODE_QUEUE_KEY.format(mode=mode)

    if mode in ("rapid", "gauntlet"):
        # PvE modes — no queuing, immediate start
        return {"status": "ready", "mode": mode}

    # team2v2: add to team queue
    existing = await r.zscore(queue_key, str(user_id))
    if existing is not None:
        return {"status": "already_queued", "mode": mode}

    rating = await get_or_create_rating(user_id, db)
    await r.zadd(queue_key, {str(user_id): rating.rating})

    meta_key = MODE_QUEUE_META_KEY.format(mode=mode, user_id=user_id)
    await r.hset(meta_key, mapping={
        "rating": str(rating.rating),
        "rd": str(rating.rd),
        "queued_at": str(time.time()),
        "status": MatchQueueStatus.waiting.value,
    })
    await r.expire(meta_key, MATCH_TIMEOUT_SECONDS + 30)

    position = await r.zcard(queue_key)
    logger.info("Player %s joined %s queue (pos=%d)", user_id, mode, position)

    return {"status": "queued", "mode": mode, "position": position}


async def leave_mode_queue(user_id: uuid.UUID, mode: str) -> bool:
    """Remove player from a mode-specific queue."""
    r = _redis()
    queue_key = MODE_QUEUE_KEY.format(mode=mode)
    removed = await r.zrem(queue_key, str(user_id))
    meta_key = MODE_QUEUE_META_KEY.format(mode=mode, user_id=user_id)
    await r.delete(meta_key)
    return bool(removed)


async def check_gauntlet_cooldown(user_id: uuid.UUID) -> dict:
    """Check if player is on gauntlet cooldown. Returns {on_cooldown, seconds_remaining}."""
    r = _redis()
    key = GAUNTLET_COOLDOWN_KEY.format(user_id=user_id)
    ttl = await r.ttl(key)
    if ttl and ttl > 0:
        return {"on_cooldown": True, "seconds_remaining": ttl}
    return {"on_cooldown": False, "seconds_remaining": 0}


async def set_gauntlet_cooldown(user_id: uuid.UUID) -> None:
    """Set gauntlet cooldown for a player (6 hours)."""
    r = _redis()
    key = GAUNTLET_COOLDOWN_KEY.format(user_id=user_id)
    await r.set(key, "1", ex=GAUNTLET_COOLDOWN_SECONDS)


async def get_mode_queue_size(mode: str) -> int:
    """Get number of players in a mode-specific queue."""
    r = _redis()
    queue_key = MODE_QUEUE_KEY.format(mode=mode)
    return await r.zcard(queue_key)
