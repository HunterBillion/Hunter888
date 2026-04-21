"""S3-02: XP Daily Soft Cap with tiered diminishing returns.

Prevents XP farming while still rewarding dedicated players.

Tiers (per calendar day, UTC):
  0 – 1500 XP  → 100% awarded
  1500 – 3000  → 50% awarded
  3000+        → 25% awarded

Exceptions (bypass cap entirely):
  - achievement XP (rare/epic/legendary reward moments)
  - team_challenge_win bonus
  - level_up bonuses

Redis key: xp:daily:{user_id}:{YYYY-MM-DD}
TTL: 25 hours (auto-expire after the day ends, with buffer for timezones)

Usage:
    from app.services.xp_daily_cap import apply_daily_cap, get_daily_xp_status
    effective_xp = await apply_daily_cap(user_id, raw_xp, source="training_session")
"""

import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Lua script for atomic XP cap calculation (eliminates TOCTOU race) ──────
_XP_CAP_LUA = """
local key = KEYS[1]
local raw_xp = tonumber(ARGV[1])
local tier1 = tonumber(ARGV[2])
local tier2 = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])

local already = tonumber(redis.call('GET', key) or '0')
local eff = 0
local rem = raw_xp
local cur = already

if cur < tier1 then
  local room = tier1 - cur
  local use = math.min(rem, room)
  eff = eff + use
  rem = rem - use
  cur = cur + use
end

if rem > 0 and cur < tier2 then
  local room = tier2 - cur
  local use = math.min(rem, room)
  eff = eff + math.floor(use * 0.5)
  rem = rem - use
  cur = cur + use
end

if rem > 0 then
  eff = eff + math.floor(rem * 0.25)
end

if raw_xp > 0 and eff < 1 then
  eff = 1
end

redis.call('INCRBY', key, raw_xp)
redis.call('EXPIRE', key, ttl)
return eff
"""

# ── Tier configuration ──────────────────────────────────────────────────────

TIER_1_LIMIT = 1500   # 100% up to this
TIER_2_LIMIT = 3000   # 50% between TIER_1 and TIER_2
TIER_2_RATE = 0.50
TIER_3_RATE = 0.25    # 25% above TIER_2
TTL_SECONDS = 25 * 3600  # 25 hours

# Sources that bypass the cap entirely
EXEMPT_SOURCES = frozenset({
    "achievement",
    "team_challenge_win",
    "level_up_bonus",
    "admin_grant",
})


def _redis_key(user_id: uuid.UUID, date_str: str) -> str:
    return f"xp:daily:{user_id}:{date_str}"


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def compute_effective_xp(raw_xp: int, already_earned: int) -> int:
    """Pure function: compute effective XP after tiered diminishing returns.

    Args:
        raw_xp: XP to be awarded this action.
        already_earned: XP already earned today (before this action).

    Returns:
        Effective XP after cap tiers.
    """
    if raw_xp <= 0:
        return 0

    effective = 0
    remaining = raw_xp
    cursor = already_earned

    # Tier 1: 100% up to TIER_1_LIMIT
    if cursor < TIER_1_LIMIT:
        tier1_room = TIER_1_LIMIT - cursor
        tier1_use = min(remaining, tier1_room)
        effective += tier1_use
        remaining -= tier1_use
        cursor += tier1_use

    # Tier 2: 50% between TIER_1 and TIER_2
    if remaining > 0 and cursor < TIER_2_LIMIT:
        tier2_room = TIER_2_LIMIT - cursor
        tier2_use = min(remaining, tier2_room)
        effective += int(tier2_use * TIER_2_RATE)
        remaining -= tier2_use
        cursor += tier2_use

    # Tier 3: 25% above TIER_2
    if remaining > 0:
        effective += int(remaining * TIER_3_RATE)

    return max(1, effective) if raw_xp > 0 else 0


async def apply_daily_cap(
    user_id: uuid.UUID,
    raw_xp: int,
    source: str = "training_session",
) -> int:
    """Apply daily soft cap and return effective XP.

    Updates Redis counter atomically. Exempt sources bypass the cap.

    Args:
        user_id: User UUID.
        raw_xp: Raw XP to be awarded.
        source: XP source identifier.

    Returns:
        Effective XP after cap application.
    """
    if raw_xp <= 0:
        return 0

    # Exempt sources bypass cap
    if source in EXEMPT_SOURCES:
        # Still track for display purposes but don't reduce
        try:
            from app.core.redis_pool import get_redis
            r = get_redis()
            key = _redis_key(user_id, _today_str())
            await r.incrby(key, raw_xp)
            await r.expire(key, TTL_SECONDS)
        except Exception as e:
            logger.warning("Redis tracking for exempt XP failed: %s", e)
        return raw_xp

    # Get current daily total from Redis
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        key = _redis_key(user_id, _today_str())

        # Atomic Lua script: read current total, compute tiered XP, increment — no TOCTOU race
        effective = await r.eval(
            _XP_CAP_LUA,
            1,  # number of keys
            key,  # KEYS[1]
            str(raw_xp),  # ARGV[1]
            str(TIER_1_LIMIT),  # ARGV[2]
            str(TIER_2_LIMIT),  # ARGV[3]
            str(TTL_SECONDS),  # ARGV[4]
        )
        effective = int(effective)

        if effective < raw_xp:
            logger.info(
                "XP daily cap applied: user=%s raw=%d effective=%d",
                user_id, raw_xp, effective,
            )

        return effective

    except Exception as e:
        # Redis down → graceful degradation: apply cap anyway (no data = full award)
        logger.warning("Redis unavailable for XP cap, awarding full XP: %s", e)
        return raw_xp


async def get_daily_xp_status(user_id: uuid.UUID) -> dict:
    """Get current daily XP status for dashboard display.

    Returns:
        {
            "earned_today": int,
            "tier1_limit": int,
            "tier2_limit": int,
            "current_rate": float,  # current multiplier (1.0, 0.5, or 0.25)
            "next_tier_at": int | None,  # XP until next tier change
        }
    """
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        key = _redis_key(user_id, _today_str())
        earned = await r.get(key)
        earned = int(earned) if earned else 0
    except Exception:
        earned = 0

    if earned < TIER_1_LIMIT:
        current_rate = 1.0
        next_tier_at = TIER_1_LIMIT - earned
    elif earned < TIER_2_LIMIT:
        current_rate = TIER_2_RATE
        next_tier_at = TIER_2_LIMIT - earned
    else:
        current_rate = TIER_3_RATE
        next_tier_at = None

    return {
        "earned_today": earned,
        "tier1_limit": TIER_1_LIMIT,
        "tier2_limit": TIER_2_LIMIT,
        "current_rate": current_rate,
        "next_tier_at": next_tier_at,
    }
