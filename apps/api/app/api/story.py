"""Story API — 'Путь Охотника' narrative progression endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.services.story_chapters import CHAPTERS, EPOCHS, get_chapter, epoch_for_chapter
from app.services.story_progression import (
    check_chapter_advancement,
    get_story_progress,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/progress")
async def story_progress(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Current story progress: chapter, epoch, conditions for next."""
    progress = await get_story_progress(user.id, db)
    return progress.to_dict()


@router.get("/chapters")
async def list_chapters(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """All 12 chapters with unlock status relative to the user."""
    progress = await get_story_progress(user.id, db)
    result = []
    for cid in range(1, 13):
        ch = get_chapter(cid)
        if ch is None:
            continue
        ep = epoch_for_chapter(cid)
        is_current = cid == progress.current_chapter
        is_completed = cid < progress.current_chapter
        is_locked = cid > progress.current_chapter
        result.append({
            "id": ch.id,
            "epoch": ch.epoch,
            "epoch_name": ep.name if ep else "",
            "code": ch.code,
            "name": ch.name,
            "narrative_intro": ch.narrative_intro if not is_locked else "",
            "max_difficulty": ch.max_difficulty,
            "weeks": list(ch.weeks),
            "is_current": is_current,
            "is_completed": is_completed,
            "is_locked": is_locked,
            "unlocked_archetypes": ch.unlocked_archetypes if not is_locked else [],
            "unlocked_scenarios": ch.unlocked_scenarios if not is_locked else [],
            "unlocked_features": ch.unlocked_features if not is_locked else [],
            "unlock_level": ch.unlock_level,
            "unlock_sessions": ch.unlock_sessions,
            "unlock_score_threshold": ch.unlock_score_threshold,
        })
    return {"chapters": result}


@router.get("/chapters/{chapter_id}")
async def get_chapter_detail(
    chapter_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Single chapter detail with narrative intro (if unlocked)."""
    ch = get_chapter(chapter_id)
    if ch is None:
        return {"error": "Chapter not found"}, 404
    ep = epoch_for_chapter(chapter_id)
    progress = await get_story_progress(user.id, db)
    is_locked = chapter_id > progress.current_chapter
    return {
        "id": ch.id,
        "epoch": ch.epoch,
        "epoch_name": ep.name if ep else "",
        "name": ch.name,
        "narrative_intro": ch.narrative_intro if not is_locked else "Эта глава ещё закрыта.",
        "max_difficulty": ch.max_difficulty,
        "is_locked": is_locked,
        "is_current": chapter_id == progress.current_chapter,
        "is_completed": chapter_id < progress.current_chapter,
        "unlocked_archetypes": ch.unlocked_archetypes if not is_locked else [],
        "unlocked_scenarios": ch.unlocked_scenarios if not is_locked else [],
        "unlocked_features": ch.unlocked_features if not is_locked else [],
    }


@router.get("/epochs")
async def list_epochs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """All 4 epochs with completion status."""
    progress = await get_story_progress(user.id, db)
    result = []
    for eid in range(1, 5):
        ep = EPOCHS.get(eid)
        if ep is None:
            continue
        result.append({
            "id": ep.id,
            "code": ep.code,
            "name": ep.name,
            "tagline": ep.tagline,
            "months": list(ep.months),
            "chapters": list(ep.chapters),
            "levels": list(ep.levels),
            "is_completed": eid in progress.epochs_completed,
            "is_current": eid == progress.current_epoch,
        })
    return {"epochs": result}


@router.get("/epoch-summary/{epoch_id}")
async def epoch_summary(
    epoch_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Flashback/dossiér: stats for a completed epoch."""
    from sqlalchemy import func, select as sa_select
    from app.models.training import TrainingSession, SessionStatus
    from app.models.progress import SessionHistory
    from app.services.story_chapters import EPOCHS

    ep = EPOCHS.get(epoch_id)
    if not ep:
        return {"error": "Epoch not found"}, 404

    progress = await get_story_progress(user.id, db)
    if epoch_id not in progress.epochs_completed and epoch_id != progress.current_epoch:
        return {"error": "Epoch not yet accessible"}, 403

    # Gather stats from session history
    sessions = await db.execute(
        sa_select(SessionHistory).where(
            SessionHistory.user_id == user.id,
        ).order_by(SessionHistory.created_at)
    )
    all_sessions = sessions.scalars().all()

    total = len(all_sessions)
    scores = [s.score_total for s in all_sessions if s.score_total]
    avg_start = round(sum(scores[:5]) / max(len(scores[:5]), 1), 1) if scores else 0
    avg_end = round(sum(scores[-5:]) / max(len(scores[-5:]), 1), 1) if scores else 0
    growth = round(((avg_end - avg_start) / max(avg_start, 1)) * 100) if avg_start > 0 else 0

    traps_fell = sum(s.traps_fell or 0 for s in all_sessions)
    traps_dodged = sum(s.traps_dodged or 0 for s in all_sessions)
    pvp_wins = sum(1 for s in all_sessions if s.outcome == "deal")
    pvp_losses = sum(1 for s in all_sessions if s.outcome in ("hangup", "hostile"))
    best = max(scores) if scores else 0
    xp = sum(s.xp_earned or 0 for s in all_sessions)

    days = 0
    if all_sessions:
        first = all_sessions[0].created_at
        last = all_sessions[-1].created_at
        if first and last:
            days = max(1, (last - first).days)

    return {
        "epoch": epoch_id,
        "epoch_name": ep.name,
        "chapters_completed": list(ep.chapters),
        "total_sessions": total,
        "avg_score_start": avg_start,
        "avg_score_end": avg_end,
        "score_growth_pct": growth,
        "traps_encountered": traps_fell + traps_dodged,
        "traps_dodged": traps_dodged,
        "pvp_wins": pvp_wins,
        "pvp_losses": pvp_losses,
        "best_score": best,
        "total_xp_earned": xp,
        "days_spent": days,
        "milestones": [],
    }


@router.post("/check-advance")
async def check_advance(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger chapter advancement check."""
    advancement = await check_chapter_advancement(user.id, db)
    if advancement is None:
        return {"advanced": False, "message": "Conditions not met or already at final chapter."}
    await db.commit()
    return {"advanced": True, "advancement": advancement.to_dict()}
