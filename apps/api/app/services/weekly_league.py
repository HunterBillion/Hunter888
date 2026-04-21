"""Weekly League — social pressure engine for within-company competition.

Mechanics:
  - Monday 08:00: form groups of 10-15 from same team, same tier
  - All week: XP from training/drills/arena accumulates as weekly_xp
  - Sunday 23:59: finalize week — top 3 promoted, bottom 3 demoted
  - 5 tiers: Стажёр (0) → Специалист (1) → Профессионал (2) → Эксперт (3) → Легенда (4)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.league import WeeklyLeagueGroup, WeeklyLeagueMembership
from app.models.progress import ManagerProgress
from app.models.user import User

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

LEAGUE_TIERS = ["Стажёр", "Специалист", "Профессионал", "Эксперт", "Легенда"]
MAX_TIER = len(LEAGUE_TIERS) - 1  # 4
GROUP_SIZE_MIN = 5
GROUP_SIZE_MAX = 15
PROMOTION_TOP = 3    # top 3 promote
DEMOTION_BOTTOM = 3  # bottom 3 demote


@dataclass
class LeagueSnapshot:
    """Current user's league view."""
    tier: int
    tier_name: str
    group_size: int
    rank: int
    weekly_xp: int
    standings: list[dict]  # [{user_id, full_name, weekly_xp, rank, is_me}]
    week_start: str
    promotion_zone: int  # rank <= this = promotion
    demotion_zone: int   # rank >= this = demotion
    days_remaining: int


def _current_week_start() -> datetime:
    """Monday 00:00 UTC of current week."""
    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def _days_remaining_in_week() -> int:
    now = datetime.now(timezone.utc)
    sunday = _current_week_start() + timedelta(days=6, hours=23, minutes=59)
    delta = sunday - now
    return max(0, delta.days)


# ── Core Service ─────────────────────────────────────────────────────────────


async def ensure_membership(user_id: uuid.UUID, db: AsyncSession) -> WeeklyLeagueMembership:
    """Get or create league membership for a user."""
    result = await db.execute(
        select(WeeklyLeagueMembership).where(WeeklyLeagueMembership.user_id == user_id)
    )
    membership = result.scalar_one_or_none()
    if membership:
        return membership

    membership = WeeklyLeagueMembership(user_id=user_id, current_tier=0)
    db.add(membership)
    await db.flush()
    return membership


async def add_weekly_xp(user_id: uuid.UUID, xp: int, db: AsyncSession) -> None:
    """Add XP to user's weekly league counter. Called after any XP-earning event."""
    membership = await ensure_membership(user_id, db)
    membership.weekly_xp += xp

    # Update standings in group if assigned
    if membership.group_id:
        result = await db.execute(
            select(WeeklyLeagueGroup).where(WeeklyLeagueGroup.id == membership.group_id)
        )
        group = result.scalar_one_or_none()
        if group and group.standings:
            uid_str = str(user_id)
            for entry in group.standings:
                if entry.get("user_id") == uid_str:
                    entry["weekly_xp"] = membership.weekly_xp
                    break
            # Re-sort and re-rank
            group.standings.sort(key=lambda x: x.get("weekly_xp", 0), reverse=True)
            for i, entry in enumerate(group.standings):
                entry["rank"] = i + 1
            # Flag JSONB as modified
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(group, "standings")


async def get_my_league(user_id: uuid.UUID, db: AsyncSession) -> LeagueSnapshot | None:
    """Get current league view for a user."""
    membership = await ensure_membership(user_id, db)

    if not membership.group_id:
        return LeagueSnapshot(
            tier=membership.current_tier,
            tier_name=LEAGUE_TIERS[membership.current_tier],
            group_size=0,
            rank=0,
            weekly_xp=membership.weekly_xp,
            standings=[],
            week_start=_current_week_start().isoformat(),
            promotion_zone=PROMOTION_TOP,
            demotion_zone=0,
            days_remaining=_days_remaining_in_week(),
        )

    result = await db.execute(
        select(WeeklyLeagueGroup).where(WeeklyLeagueGroup.id == membership.group_id)
    )
    group = result.scalar_one_or_none()
    if not group:
        return None

    uid_str = str(user_id)
    standings_with_me = []
    my_rank = 0
    for entry in (group.standings or []):
        is_me = entry.get("user_id") == uid_str
        if is_me:
            my_rank = entry.get("rank", 0)
        standings_with_me.append({**entry, "is_me": is_me})

    group_size = len(group.standings or [])
    demotion_start = max(group_size - DEMOTION_BOTTOM + 1, PROMOTION_TOP + 1)

    return LeagueSnapshot(
        tier=membership.current_tier,
        tier_name=LEAGUE_TIERS[membership.current_tier],
        group_size=group_size,
        rank=my_rank,
        weekly_xp=membership.weekly_xp,
        standings=standings_with_me,
        week_start=group.week_start.isoformat() if group.week_start else _current_week_start().isoformat(),
        promotion_zone=PROMOTION_TOP,
        demotion_zone=demotion_start,
        days_remaining=_days_remaining_in_week(),
    )


async def form_weekly_groups(db: AsyncSession) -> int:
    """Form league groups for the current week. Called Monday 08:00.

    Groups users by team_id and tier, then creates groups of GROUP_SIZE_MAX.
    Returns number of groups created.
    """
    week_start = _current_week_start()

    # Check if already formed for this week
    existing = await db.execute(
        select(func.count(WeeklyLeagueGroup.id)).where(
            WeeklyLeagueGroup.week_start == week_start
        )
    )
    if (existing.scalar() or 0) > 0:
        logger.info("League groups already formed for week %s", week_start.date())
        return 0

    # Reset all weekly_xp
    await db.execute(
        update(WeeklyLeagueMembership).values(weekly_xp=0, group_id=None, rank_in_group=0)
    )

    # Get all users with their team
    users_result = await db.execute(
        select(User.id, User.full_name, User.team_id, User.avatar_url).where(
            User.is_active == True,  # noqa: E712
        )
    )
    users = users_result.all()

    # Get memberships
    memberships = {}
    mem_result = await db.execute(select(WeeklyLeagueMembership))
    for m in mem_result.scalars().all():
        memberships[m.user_id] = m

    # Group by (team_id, tier) — skip users without a team
    from collections import defaultdict
    buckets: dict[tuple, list] = defaultdict(list)
    for user_row in users:
        if not user_row.team_id:
            continue  # Users without a team are not placed in leagues
        uid = user_row.id
        if uid not in memberships:
            # Create membership
            mem = WeeklyLeagueMembership(user_id=uid, current_tier=0)
            db.add(mem)
            memberships[uid] = mem
        tier = memberships[uid].current_tier
        buckets[(user_row.team_id, tier)].append({
            "user_id": uid,
            "full_name": user_row.full_name or "User",
            "avatar_url": user_row.avatar_url,
        })

    await db.flush()

    # Create groups
    groups_created = 0
    for (team_id, tier), user_list in buckets.items():
        if len(user_list) < 2:
            continue  # Skip groups too small

        # Chunk into groups of GROUP_SIZE_MAX
        for i in range(0, len(user_list), GROUP_SIZE_MAX):
            chunk = user_list[i:i + GROUP_SIZE_MAX]
            if len(chunk) < 2:
                continue

            standings = [
                {
                    "user_id": str(u["user_id"]),
                    "full_name": u["full_name"],
                    "avatar_url": u.get("avatar_url"),
                    "weekly_xp": 0,
                    "rank": idx + 1,
                }
                for idx, u in enumerate(chunk)
            ]

            group = WeeklyLeagueGroup(
                week_start=week_start,
                team_id=team_id,
                league_tier=tier,
                user_ids=[str(u["user_id"]) for u in chunk],
                standings=standings,
            )
            db.add(group)
            await db.flush()

            # Update memberships
            for u in chunk:
                mem = memberships[u["user_id"]]
                mem.group_id = group.id

            groups_created += 1

    await db.flush()
    logger.info("Formed %d league groups for week %s", groups_created, week_start.date())
    return groups_created


async def finalize_week(db: AsyncSession) -> dict:
    """Finalize current week: promote top 3, demote bottom 3. Called Sunday 23:59.

    Returns summary: {groups_finalized, promotions, demotions}
    """
    week_start = _current_week_start()

    result = await db.execute(
        select(WeeklyLeagueGroup).where(
            WeeklyLeagueGroup.week_start == week_start,
            WeeklyLeagueGroup.finalized == False,  # noqa: E712
        )
    )
    groups = result.scalars().all()

    promotions = 0
    demotions = 0
    groups_finalized = 0

    for group in groups:
        if not group.standings or len(group.standings) < 2:
            group.finalized = True
            continue

        # Sort final standings
        group.standings.sort(key=lambda x: x.get("weekly_xp", 0), reverse=True)
        for i, entry in enumerate(group.standings):
            entry["rank"] = i + 1

        total = len(group.standings)
        promo_cutoff = PROMOTION_TOP
        demo_cutoff = total - DEMOTION_BOTTOM

        for entry in group.standings:
            uid = uuid.UUID(entry["user_id"])
            rank = entry["rank"]

            mem_result = await db.execute(
                select(WeeklyLeagueMembership).where(WeeklyLeagueMembership.user_id == uid)
            )
            mem = mem_result.scalar_one_or_none()
            if not mem:
                continue

            old_tier = mem.current_tier
            action = "stayed"

            if rank <= promo_cutoff and old_tier < MAX_TIER:
                mem.current_tier = old_tier + 1
                action = "promoted"
                promotions += 1
            elif rank > demo_cutoff and old_tier > 0:
                mem.current_tier = old_tier - 1
                action = "demoted"
                demotions += 1

            # Record in history
            history = list(mem.promotion_history or [])
            history.append({
                "week": week_start.isoformat(),
                "old_tier": old_tier,
                "new_tier": mem.current_tier,
                "rank": rank,
                "action": action,
                "weekly_xp": entry.get("weekly_xp", 0),
            })
            mem.promotion_history = history[-20:]  # Keep last 20 weeks

            # Update ManagerProgress league_tier
            await db.execute(
                update(ManagerProgress)
                .where(ManagerProgress.user_id == uid)
                .values(league_tier=mem.current_tier)
            )

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(group, "standings")
        group.finalized = True
        groups_finalized += 1

    await db.flush()

    summary = {
        "groups_finalized": groups_finalized,
        "promotions": promotions,
        "demotions": demotions,
    }
    logger.info("Week finalized: %s", summary)
    return summary
