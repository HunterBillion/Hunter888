"""Hunter Score leaderboard aggregator.

Returns ranked list of managers by their composite `hunter_score`. Lazily
refreshes scores older than 1h. Scope: team (ROP), company (admin).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import ManagerProgress
from app.models.rating_contribution import RatingContribution
from app.models.user import User
from app.services.hunter_score import update_hunter_score


@dataclass
class HunterRankEntry:
    rank: int
    user_id: str
    full_name: str
    avatar_url: str | None
    hunter_score: float
    current_level: int
    week_tp: int
    prev_week_tp: int
    delta_vs_last_week: int
    is_me: bool


def _iso_monday(d: datetime | date) -> date:
    if isinstance(d, datetime):
        d = d.date()
    return d - timedelta(days=d.weekday())


async def _week_tp_map(
    db: AsyncSession, user_ids: list[uuid.UUID], week_start: date
) -> dict[uuid.UUID, int]:
    if not user_ids:
        return {}
    q = await db.execute(
        select(
            RatingContribution.user_id,
            func.coalesce(func.sum(RatingContribution.points), 0).label("tp"),
        )
        .where(
            RatingContribution.user_id.in_(user_ids),
            RatingContribution.week_start == week_start,
        )
        .group_by(RatingContribution.user_id)
    )
    return {row.user_id: int(row.tp) for row in q.all()}


async def get_hunter_leaderboard(
    db: AsyncSession,
    *,
    viewer: User,
    scope: Literal["team", "company"] = "company",
    limit: int = 50,
    refresh_stale_minutes: int = 60,
) -> list[HunterRankEntry]:
    """Return sorted list of managers by hunter_score.

    Refreshes stale (>N min) hunter_score rows before ranking.
    `scope="team"` limits to viewer's team (for ROP/manager views).
    `scope="company"` is admin-only (raises if viewer not admin).
    """
    # Build user query based on scope
    user_q = select(User).where(User.is_active.is_(True))
    if scope == "team":
        team_id = getattr(viewer, "team_id", None)
        if team_id is None:
            return []
        user_q = user_q.where(User.team_id == team_id)
    # company scope — all active users (route layer enforces admin-only)

    users_result = await db.execute(user_q)
    users = users_result.scalars().all()
    if not users:
        return []

    user_ids = [u.id for u in users]

    # Ensure a ManagerProgress row exists and hunter_score is fresh
    mp_q = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id.in_(user_ids))
    )
    progress_map = {p.user_id: p for p in mp_q.scalars().all()}

    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=refresh_stale_minutes)
    for u in users:
        p = progress_map.get(u.id)
        needs_refresh = (
            p is None
            or p.hunter_score_updated_at is None
            or p.hunter_score_updated_at < stale_cutoff
        )
        if needs_refresh:
            try:
                await update_hunter_score(db, u.id)
            except Exception:
                # Non-fatal: keep stale value rather than break whole leaderboard
                pass

    # Reload after refresh
    mp_q2 = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id.in_(user_ids))
    )
    progress_map = {p.user_id: p for p in mp_q2.scalars().all()}

    # Weekly TP — current and previous week
    today = datetime.now(timezone.utc).date()
    this_monday = _iso_monday(today)
    prev_monday = this_monday - timedelta(days=7)
    tp_current = await _week_tp_map(db, user_ids, this_monday)
    tp_prev = await _week_tp_map(db, user_ids, prev_monday)

    # Build rank rows, sort by hunter_score DESC
    rows: list[tuple[User, ManagerProgress | None, int, int]] = []
    for u in users:
        p = progress_map.get(u.id)
        cur_tp = tp_current.get(u.id, 0)
        prev_tp = tp_prev.get(u.id, 0)
        rows.append((u, p, cur_tp, prev_tp))

    rows.sort(
        key=lambda r: (
            float(r[1].hunter_score) if r[1] and r[1].hunter_score else 0.0,
            r[2],  # tiebreak: current week TP
        ),
        reverse=True,
    )

    entries: list[HunterRankEntry] = []
    for idx, (u, p, cur_tp, prev_tp) in enumerate(rows[:limit], start=1):
        entries.append(
            HunterRankEntry(
                rank=idx,
                user_id=str(u.id),
                full_name=u.full_name or u.email,
                avatar_url=u.avatar_url,
                hunter_score=round(float(p.hunter_score) if p and p.hunter_score else 0.0, 1),
                current_level=int(p.current_level) if p else 1,
                week_tp=cur_tp,
                prev_week_tp=prev_tp,
                delta_vs_last_week=cur_tp - prev_tp,
                is_me=(u.id == viewer.id),
            )
        )

    # Ensure viewer is visible even if not in top-N
    if viewer.id in user_ids and not any(e.is_me for e in entries):
        for idx, (u, p, cur_tp, prev_tp) in enumerate(rows, start=1):
            if u.id == viewer.id:
                entries.append(
                    HunterRankEntry(
                        rank=idx,
                        user_id=str(u.id),
                        full_name=u.full_name or u.email,
                        hunter_score=round(float(p.hunter_score) if p and p.hunter_score else 0.0, 1),
                        current_level=int(p.current_level) if p else 1,
                        week_tp=cur_tp,
                        prev_week_tp=prev_tp,
                        delta_vs_last_week=cur_tp - prev_tp,
                        is_me=True,
                    )
                )
                break

    return entries


async def get_my_tp_breakdown(
    db: AsyncSession, user_id: uuid.UUID
) -> dict[str, int]:
    """Current ISO week TP breakdown by source for a single user.

    Returns: {training, pvp, knowledge, story, total}.
    """
    this_monday = _iso_monday(datetime.now(timezone.utc).date())
    q = await db.execute(
        select(
            RatingContribution.source,
            func.coalesce(func.sum(RatingContribution.points), 0).label("tp"),
        )
        .where(
            RatingContribution.user_id == user_id,
            RatingContribution.week_start == this_monday,
        )
        .group_by(RatingContribution.source)
    )
    out = {"training": 0, "pvp": 0, "knowledge": 0, "story": 0}
    for row in q.all():
        key = row.source.value if hasattr(row.source, "value") else str(row.source)
        out[key] = int(row.tp)
    out["total"] = sum(v for k, v in out.items() if k != "total")
    return out


async def get_weekly_tp_ranking(
    db: AsyncSession,
    *,
    viewer: User,
    scope: Literal["team", "company"] = "company",
    limit: int = 50,
) -> list[dict]:
    """Weekly TP leaderboard (current ISO week) for the scope."""
    user_q = select(User).where(User.is_active.is_(True))
    if scope == "team":
        team_id = getattr(viewer, "team_id", None)
        if team_id is None:
            return []
        user_q = user_q.where(User.team_id == team_id)

    users_result = await db.execute(user_q)
    users = users_result.scalars().all()
    if not users:
        return []

    user_ids = [u.id for u in users]
    this_monday = _iso_monday(datetime.now(timezone.utc).date())
    tp_map = await _week_tp_map(db, user_ids, this_monday)

    rows = sorted(
        ((u, tp_map.get(u.id, 0)) for u in users),
        key=lambda x: x[1],
        reverse=True,
    )

    return [
        {
            "rank": idx,
            "user_id": str(u.id),
            "full_name": u.full_name or u.email,
            "avatar_url": u.avatar_url,
            "week_tp": tp,
            "is_me": u.id == viewer.id,
        }
        for idx, (u, tp) in enumerate(rows[:limit], start=1)
    ]
