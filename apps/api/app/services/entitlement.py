"""Entitlement Service — S3-03: subscription and feature access control.

Plans:
  Scout (Free)  → 3 sessions/day, 2 PvP, 5 RAG, basic analytics
  Ranger (Basic) → 10 sessions/day, 10 PvP, 50 RAG, extended analytics
  Hunter (Pro)   → Unlimited sessions/PvP, 500 RAG, full analytics + export
  Master (Enterprise) → Unlimited everything, dedicated LLM, custom tournaments

Role-based exemptions:
  Existing seed accounts (admin, rop, methodologist) get automatic Master access
  regardless of subscription status. This ensures pilot users always have full access.

Feature gate checks are O(1) — plan limits are hardcoded dicts, subscription
is fetched once per request and cached in the dependency injection chain.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Plan definitions
# ═══════════════════════════════════════════════════════════════════════════

class PlanType(str, Enum):
    scout = "scout"
    ranger = "ranger"
    hunter = "hunter"
    master = "master"


class LLMPriority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    dedicated = "dedicated"


@dataclass(frozen=True)
class PlanLimits:
    sessions_per_day: int         # -1 = unlimited
    pvp_matches_per_day: int      # -1 = unlimited
    rag_queries_per_day: int      # -1 = unlimited
    ai_coach: bool
    wiki_full_access: bool
    export_reports: bool
    voice_cloning: bool
    team_management: bool
    team_challenge: bool
    priority_matchmaking: bool
    llm_priority: LLMPriority
    tournaments: str              # "leaderboard", "all", "custom"
    analytics: str                # "basic", "extended", "full", "full_api"


PLAN_LIMITS: dict[PlanType, PlanLimits] = {
    PlanType.scout: PlanLimits(
        sessions_per_day=3,
        pvp_matches_per_day=2,
        rag_queries_per_day=5,
        ai_coach=False,
        wiki_full_access=False,
        export_reports=False,
        voice_cloning=False,
        team_management=False,
        team_challenge=False,
        priority_matchmaking=False,
        llm_priority=LLMPriority.low,
        tournaments="leaderboard",
        analytics="basic",
    ),
    PlanType.ranger: PlanLimits(
        sessions_per_day=10,
        pvp_matches_per_day=10,
        rag_queries_per_day=50,
        ai_coach=True,
        wiki_full_access=True,
        export_reports=False,
        voice_cloning=False,
        team_management=False,
        team_challenge=False,
        priority_matchmaking=False,
        llm_priority=LLMPriority.normal,
        tournaments="all",
        analytics="extended",
    ),
    PlanType.hunter: PlanLimits(
        sessions_per_day=-1,
        pvp_matches_per_day=-1,
        rag_queries_per_day=500,
        ai_coach=True,
        wiki_full_access=True,
        export_reports=True,
        voice_cloning=False,
        team_management=True,
        team_challenge=True,
        priority_matchmaking=True,
        llm_priority=LLMPriority.high,
        tournaments="all",
        analytics="full",
    ),
    PlanType.master: PlanLimits(
        sessions_per_day=-1,
        pvp_matches_per_day=-1,
        rag_queries_per_day=-1,
        ai_coach=True,
        wiki_full_access=True,
        export_reports=True,
        voice_cloning=True,
        team_management=True,
        team_challenge=True,
        priority_matchmaking=True,
        llm_priority=LLMPriority.dedicated,
        tournaments="custom",
        analytics="full_api",
    ),
}

FREE_TRIAL_DAYS = 14

# Seed account emails — always get Master access regardless of subscription
SEED_ACCOUNT_EMAILS = frozenset({
    "admin@trainer.local",
    "rop1@trainer.local",
    "rop2@trainer.local",
    "method@trainer.local",
    "manager1@trainer.local",
    "manager2@trainer.local",
    "manager3@trainer.local",
    "manager4@trainer.local",
})

# Roles that automatically get elevated access (admin/rop/methodologist → Master)
ELEVATED_ROLES = frozenset({"admin", "rop", "methodologist"})


# ═══════════════════════════════════════════════════════════════════════════
# Entitlement status
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class EntitlementStatus:
    plan: PlanType
    is_trial: bool
    trial_days_remaining: int
    limits: PlanLimits
    sessions_used_today: int
    pvp_used_today: int
    rag_used_today: int
    is_seed_account: bool
    subscription_expires: datetime | None


def _resolve_plan_for_user(user, subscription) -> tuple[PlanType, bool]:
    """Determine effective plan for a user.

    Priority:
    1. Seed account email → Master (always)
    2. Elevated role (admin/rop/methodologist) → Master
    3. Active subscription → subscription plan
    4. Default → Scout
    """
    # 1. Seed account override
    if user.email in SEED_ACCOUNT_EMAILS:
        return PlanType.master, True

    # 2. Role-based elevation
    role_val = user.role.value if hasattr(user.role, 'value') else str(user.role)
    if role_val in ELEVATED_ROLES:
        return PlanType.master, False

    # 3. Active subscription
    if subscription:
        now = datetime.now(timezone.utc)
        if subscription.expires_at is None or subscription.expires_at > now:
            try:
                return PlanType(subscription.plan_type), False
            except ValueError:
                logger.warning("Unknown plan_type: %s for user %s", subscription.plan_type, user.id)

    # 4. Default
    return PlanType.scout, False


ENTITLEMENT_CACHE_TTL = 300  # 5 minutes — spec 6.3


async def _get_cached_plan(user_id: uuid.UUID) -> PlanType | None:
    """Try to get plan_type from Redis cache. Returns None on miss or error."""
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        val = await r.get(f"entitlement:{user_id}")
        if val:
            return PlanType(val.decode() if isinstance(val, bytes) else val)
    except Exception:
        logger.debug("Failed to read entitlement cache for user %s", user_id, exc_info=True)
    return None


async def _set_cached_plan(user_id: uuid.UUID, plan: PlanType) -> None:
    """Cache plan_type in Redis with TTL."""
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        await r.set(f"entitlement:{user_id}", plan.value, ex=ENTITLEMENT_CACHE_TTL)
    except Exception:
        logger.debug("Failed to write entitlement cache for user %s", user_id, exc_info=True)


async def invalidate_entitlement_cache(user_id: uuid.UUID) -> None:
    """Invalidate cached entitlement. Call after subscription changes.

    FIND-008 fix: failure here is CRITICAL — user paid for upgrade but cache
    still serves stale quota for up to 5 min TTL. Log at error level with
    exc_info so ops can catch payment ↔ quota desync immediately.
    """
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        await r.delete(f"entitlement:{user_id}")
    except Exception as _e:
        logger.error(
            "CRITICAL: Failed to invalidate entitlement cache for user %s "
            "after subscription change — user will see stale quota until TTL: %s",
            user_id, _e, exc_info=True,
        )


async def get_entitlement(user_id: uuid.UUID, db: AsyncSession) -> EntitlementStatus:
    """Get current entitlement status for a user.

    6.3: Checks Redis cache first (entitlement:{user_id} → plan_type, TTL 5min).
    Resolves plan from: cache → seed accounts → role → subscription → scout default.
    Counts today's usage for rate limiting display.
    """
    from sqlalchemy import func as sa_func
    from app.models.user import User
    from app.models.training import TrainingSession, SessionStatus
    from app.models.subscription import UserSubscription

    # Fetch user + subscription in 2 queries (could be 1 join but clarity wins)
    user = await db.get(User, user_id)
    if not user:
        return EntitlementStatus(
            plan=PlanType.scout, is_trial=True, trial_days_remaining=0,
            limits=PLAN_LIMITS[PlanType.scout], sessions_used_today=0,
            pvp_used_today=0, rag_used_today=0, is_seed_account=False,
            subscription_expires=None,
        )

    # Fetch subscription
    sub_result = await db.execute(
        select(UserSubscription).where(UserSubscription.user_id == user_id)
    )
    subscription = sub_result.scalar_one_or_none()

    # 6.3: Try Redis cache first for plan resolution
    cached_plan = await _get_cached_plan(user_id)
    if cached_plan is not None:
        plan = cached_plan
        is_seed = user.email in SEED_ACCOUNT_EMAILS
        # Always re-check seed/elevated roles — they override any cached plan
        role_val = user.role.value if hasattr(user.role, 'value') else str(user.role)
        if is_seed or role_val in ELEVATED_ROLES:
            plan = PlanType.master
    else:
        plan, is_seed = _resolve_plan_for_user(user, subscription)
        await _set_cached_plan(user_id, plan)

    limits = PLAN_LIMITS[plan]

    # Trial calculation (only for scout without subscription)
    is_trial = False
    days_remaining = 0
    if plan == PlanType.scout and not subscription:
        created = user.created_at
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created:
            trial_end = created + timedelta(days=FREE_TRIAL_DAYS)
            days_remaining = max(0, (trial_end - datetime.now(timezone.utc)).days)
            is_trial = days_remaining > 0

    # Count today's usage
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    sessions_r = await db.execute(
        select(sa_func.count()).select_from(TrainingSession).where(
            TrainingSession.user_id == user_id,
            TrainingSession.started_at >= today_start,
        )
    )
    sessions_used = sessions_r.scalar() or 0

    # PvP usage
    pvp_used = 0
    try:
        from app.models.pvp import PvPDuel
        pvp_r = await db.execute(
            select(sa_func.count()).select_from(PvPDuel).where(
                (PvPDuel.challenger_id == user_id) | (PvPDuel.opponent_id == user_id),
                PvPDuel.created_at >= today_start,
            )
        )
        pvp_used = pvp_r.scalar() or 0
    except Exception:
        logger.debug("Failed to count PvP usage for user %s", user_id, exc_info=True)

    # RAG usage (from Redis counter if available)
    rag_used = 0
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        rag_key = f"rag:daily:{user_id}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        rag_val = await r.get(rag_key)
        rag_used = int(rag_val) if rag_val else 0
    except Exception:
        logger.debug("Failed to read RAG usage counter for user %s", user_id, exc_info=True)

    return EntitlementStatus(
        plan=plan,
        is_trial=is_trial,
        trial_days_remaining=days_remaining,
        limits=limits,
        sessions_used_today=sessions_used,
        pvp_used_today=pvp_used,
        rag_used_today=rag_used,
        is_seed_account=is_seed,
        subscription_expires=subscription.expires_at if subscription else None,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Feature checks
# ═══════════════════════════════════════════════════════════════════════════

def check_session_limit(entitlement: EntitlementStatus) -> bool:
    """Return True if user can start a new session."""
    limit = entitlement.limits.sessions_per_day
    if limit == -1:
        return True
    return entitlement.sessions_used_today < limit


def check_pvp_limit(entitlement: EntitlementStatus) -> bool:
    """Return True if user can start a PvP match."""
    limit = entitlement.limits.pvp_matches_per_day
    if limit == -1:
        return True
    return entitlement.pvp_used_today < limit


def check_rag_limit(entitlement: EntitlementStatus) -> bool:
    """Return True if user can make a RAG query."""
    limit = entitlement.limits.rag_queries_per_day
    if limit == -1:
        return True
    return entitlement.rag_used_today < limit


async def increment_rag_usage(user_id: uuid.UUID) -> None:
    """Increment RAG usage counter in Redis."""
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        key = f"rag:daily:{user_id}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        await r.incr(key)
        await r.expire(key, 25 * 3600)
    except Exception:
        logger.debug("Failed to increment RAG usage counter for user %s", user_id, exc_info=True)


def check_feature(entitlement: EntitlementStatus, feature: str) -> bool:
    """Check if a feature is available for the user's plan."""
    limits = entitlement.limits
    feature_map = {
        "ai_coach": limits.ai_coach,
        "wiki_full_access": limits.wiki_full_access,
        "export_reports": limits.export_reports,
        "voice_cloning": limits.voice_cloning,
        "team_management": limits.team_management,
        "team_challenge": limits.team_challenge,
        "priority_matchmaking": limits.priority_matchmaking,
    }
    return feature_map.get(feature, False)


async def check_chapter_feature(
    user_id: uuid.UUID,
    feature: str,
    db: AsyncSession,
) -> bool:
    """Check if a feature is unlocked by the user's story chapter.

    Chapter-based features (from story_chapters.py):
      - daily_drill, traps_level_1, pvp_arena, traps_level_2, traps_level_3,
        pvp_ranked, tournaments, team_challenges, arena_streak, all_archetypes,
        mentor_mode, custom_scenarios, team_missions, corp_tournaments,
        create_tournaments, adaptive_ai, legendary_achievements,
        archetype_creation, community_content, community_voting,
        marathon, hall_of_fame, legendary_skin
    """
    try:
        from app.services.story_chapters import cumulative_unlocked_features
        from app.services.story_progression import get_or_create_story_state
        state = await get_or_create_story_state(user_id, db)
        features = cumulative_unlocked_features(state.current_chapter)
        return feature in features
    except Exception:
        return True  # fail open — don't block on story system errors


def get_plan_comparison() -> list[dict]:
    """Return plan comparison data for pricing page."""
    plans = []
    for plan_type in PlanType:
        limits = PLAN_LIMITS[plan_type]
        plans.append({
            "id": plan_type.value,
            "name": {
                "scout": "Бесплатный",
                "ranger": "Рейнджер",
                "hunter": "Охотник",
                "master": "Мастер",
            }[plan_type.value],
            "is_free": plan_type == PlanType.scout,
            "sessions_per_day": limits.sessions_per_day,
            "pvp_matches_per_day": limits.pvp_matches_per_day,
            "rag_queries_per_day": limits.rag_queries_per_day,
            "ai_coach": limits.ai_coach,
            "export_reports": limits.export_reports,
            "team_challenge": limits.team_challenge,
            "analytics": limits.analytics,
            "llm_priority": limits.llm_priority.value,
            "tournaments": limits.tournaments,
        })
    return plans
