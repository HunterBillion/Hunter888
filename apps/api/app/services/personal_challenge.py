"""Personal Challenge Service — Петля 7: micro-events between sessions.

Returns personalized micro-events that pull users back:
  - Trap Revenge: 2+ fails on same trap → challenge to retry
  - Skill Unlock Preview: close to next level/chapter → show what's coming
  - Rival Update: colleague overtook in leaderboard
  - Chapter Teaser: close to next chapter → preview
  - Weekly Boss: every Friday → special scenario with 2x XP
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_personal_challenges(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict]:
    """Get active micro-events for the user. Max 3 returned, priority-ordered."""
    events: list[dict] = []

    try:
        events.extend(await _check_trap_revenge(user_id, db))
        events.extend(await _check_skill_unlock(user_id, db))
        events.extend(await _check_rival_update(user_id, db))
        events.extend(await _check_chapter_teaser(user_id, db))
        events.extend(await _check_weekly_boss(user_id, db))
    except Exception as e:
        logger.debug("Personal challenge check failed: %s", e)

    # Sort by priority, return top 3
    events.sort(key=lambda e: e.get("priority", 99))
    return events[:3]


async def _check_trap_revenge(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """Trap Revenge: find traps the user failed 2+ times recently."""
    from app.models.progress import SessionHistory

    result = await db.execute(
        select(SessionHistory).where(
            SessionHistory.user_id == user_id,
        ).order_by(SessionHistory.created_at.desc()).limit(10)
    )
    sessions = result.scalars().all()

    trap_fails: dict[str, int] = {}
    for s in sessions:
        bd = s.score_breakdown or {}
        trap = bd.get("worst_trap_name") or bd.get("_trap_name")
        if trap and s.traps_fell and s.traps_fell > 0:
            trap_fails[trap] = trap_fails.get(trap, 0) + s.traps_fell

    events = []
    for trap, count in trap_fails.items():
        if count >= 2:
            events.append({
                "type": "trap_revenge",
                "title": f"Ловушка '{trap}'",
                "body": f"Ты попался {count} раз. Попробуешь ещё?",
                "priority": 1,
                "action": "start_training",
            })
            break  # Only the worst one
    return events


async def _check_skill_unlock(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """Skill Unlock Preview: close to next level."""
    from app.models.progress import ManagerProgress
    from scripts.seed_levels import LEVEL_XP_THRESHOLDS, LEVEL_NAMES

    result = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user_id)
    )
    mp = result.scalar_one_or_none()
    if not mp or mp.current_level >= 20:
        return []

    next_level = mp.current_level + 1
    next_xp = LEVEL_XP_THRESHOLDS.get(next_level, 999999)
    remaining = next_xp - mp.total_xp
    next_name = LEVEL_NAMES.get(next_level, f"Ур. {next_level}")

    # Only show if within 30% of next level
    level_gap = next_xp - LEVEL_XP_THRESHOLDS.get(mp.current_level, 0)
    if level_gap > 0 and remaining / level_gap <= 0.3:
        return [{
            "type": "skill_unlock",
            "title": f"До '{next_name}' — {remaining} XP",
            "body": "Одна тренировка — и новый ранг твой.",
            "priority": 2,
            "action": "start_training",
        }]
    return []


async def _check_rival_update(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """Rival Update: colleague overtook in weekly leaderboard."""
    from app.services.gamification import get_leaderboard

    try:
        lb = await get_leaderboard(db, period="week", limit=20)
        my_pos = None
        for i, entry in enumerate(lb):
            if entry["user_id"] == str(user_id):
                my_pos = i
                break

        if my_pos is not None and my_pos > 0:
            rival = lb[my_pos - 1]
            diff = round(rival["total_score"] - lb[my_pos]["total_score"], 1)
            if diff > 0 and diff < 500:  # Only show if gap is small (catchable)
                rival_name = rival["full_name"].split(" ")[0]
                return [{
                    "type": "rival_update",
                    "title": f"{rival_name} впереди на {diff} очков",
                    "body": "Разрыв небольшой. Одна хорошая сессия — и ты обгонишь.",
                    "priority": 3,
                    "action": "start_training",
                }]
    except Exception:
        pass
    return []


async def _check_chapter_teaser(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """Chapter Teaser: close to next chapter unlock."""
    try:
        from app.services.story_progression import get_story_progress
        progress = await get_story_progress(user_id, db)

        if progress.next_chapter and 50 <= progress.progress_pct < 90:
            from app.services.story_chapters import get_chapter
            next_ch = get_chapter(progress.next_chapter)
            if next_ch:
                return [{
                    "type": "chapter_teaser",
                    "title": f"Глава {next_ch.id}: {next_ch.name}",
                    "body": f"Прогресс: {progress.progress_pct:.0f}%. Скоро откроется новый этап.",
                    "priority": 4,
                    "action": "view_story",
                }]
    except Exception:
        pass
    return []


async def _check_weekly_boss(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """Weekly Boss: every Friday, special challenge with 2x XP."""
    today = datetime.now(timezone.utc)
    if today.weekday() != 4:  # 4 = Friday
        return []

    return [{
        "type": "weekly_boss",
        "title": "Босс недели",
        "body": "Специальный сценарий повышенной сложности. Побеждаешь = 2x XP.",
        "priority": 5,
        "action": "start_boss",
    }]
