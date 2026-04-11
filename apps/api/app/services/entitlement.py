"""Entitlement Service — subscription and feature access control.

Plans (from landing page):
  - Базовый (Scout): 14 days free trial, limited sessions/day
  - Охотник (Hunter): Full access, priority matchmaking
  - Enterprise: Custom limits, team management

Features gated by plan:
  - sessions_per_day: Scout=3, Hunter=unlimited, Enterprise=unlimited
  - pvp_enabled: Scout=limited(3/day), Hunter=yes, Enterprise=yes
  - ai_coach: Scout=no, Hunter=yes, Enterprise=yes
  - wiki_access: Scout=read_only, Hunter=full, Enterprise=full
  - export_reports: Scout=no, Hunter=yes, Enterprise=yes
  - voice_cloning: Scout=no, Hunter=no, Enterprise=yes
  - team_management: Scout=no, Hunter=no, Enterprise=yes
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class PlanType(str, Enum):
    scout = "scout"      # Базовый (free trial)
    hunter = "hunter"    # Охотник (paid)
    enterprise = "enterprise"


@dataclass
class PlanLimits:
    sessions_per_day: int       # -1 = unlimited
    pvp_matches_per_day: int    # -1 = unlimited
    ai_coach: bool
    wiki_full_access: bool
    export_reports: bool
    voice_cloning: bool
    team_management: bool
    priority_matchmaking: bool


PLAN_LIMITS: dict[PlanType, PlanLimits] = {
    PlanType.scout: PlanLimits(
        sessions_per_day=3,
        pvp_matches_per_day=3,
        ai_coach=False,
        wiki_full_access=False,
        export_reports=False,
        voice_cloning=False,
        team_management=False,
        priority_matchmaking=False,
    ),
    PlanType.hunter: PlanLimits(
        sessions_per_day=-1,
        pvp_matches_per_day=-1,
        ai_coach=True,
        wiki_full_access=True,
        export_reports=True,
        voice_cloning=False,
        team_management=False,
        priority_matchmaking=True,
    ),
    PlanType.enterprise: PlanLimits(
        sessions_per_day=-1,
        pvp_matches_per_day=-1,
        ai_coach=True,
        wiki_full_access=True,
        export_reports=True,
        voice_cloning=True,
        team_management=True,
        priority_matchmaking=True,
    ),
}

FREE_TRIAL_DAYS = 14


@dataclass
class EntitlementStatus:
    plan: PlanType
    is_trial: bool
    trial_days_remaining: int
    limits: PlanLimits
    sessions_used_today: int
    pvp_used_today: int


async def get_entitlement(user_id, db) -> EntitlementStatus:
    """Get current entitlement status for a user.

    For now: all users get Scout plan with 14-day free trial.
    When payment is integrated, check subscription record.
    """
    from sqlalchemy import func, select
    from app.models.user import User
    from app.models.training import TrainingSession, SessionStatus

    # Get user
    user = await db.get(User, user_id)
    if not user:
        return EntitlementStatus(
            plan=PlanType.scout,
            is_trial=True,
            trial_days_remaining=0,
            limits=PLAN_LIMITS[PlanType.scout],
            sessions_used_today=0,
            pvp_used_today=0,
        )

    # TODO: When payment is integrated, check user.subscription_plan field
    # For now: all users get Scout plan
    plan = PlanType.scout

    # Calculate trial days remaining
    created = user.created_at
    if created and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    trial_end = created + timedelta(days=FREE_TRIAL_DAYS) if created else datetime.now(timezone.utc)
    days_remaining = max(0, (trial_end - datetime.now(timezone.utc)).days)
    is_trial = days_remaining > 0

    # Count today's usage
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    sessions_today = await db.execute(
        select(func.count())
        .select_from(TrainingSession)
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.started_at >= today_start,
        )
    )
    sessions_used = sessions_today.scalar() or 0

    return EntitlementStatus(
        plan=plan,
        is_trial=is_trial,
        trial_days_remaining=days_remaining,
        limits=PLAN_LIMITS[plan],
        sessions_used_today=sessions_used,
        pvp_used_today=0,  # TODO: count PvP matches today
    )


def check_session_limit(entitlement: EntitlementStatus) -> bool:
    """Return True if user can start a new session. False if limit reached."""
    limit = entitlement.limits.sessions_per_day
    if limit == -1:
        return True
    return entitlement.sessions_used_today < limit


def check_feature(entitlement: EntitlementStatus, feature: str) -> bool:
    """Check if a feature is available for the user's plan."""
    limits = entitlement.limits
    feature_map = {
        "ai_coach": limits.ai_coach,
        "wiki_full_access": limits.wiki_full_access,
        "export_reports": limits.export_reports,
        "voice_cloning": limits.voice_cloning,
        "team_management": limits.team_management,
        "priority_matchmaking": limits.priority_matchmaking,
    }
    return feature_map.get(feature, False)
