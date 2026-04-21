"""Story Progression Service — manages the 'Путь Охотника' 12-chapter arc.

Handles:
  - get/create user story state
  - record session completions within chapters
  - check & perform chapter advancement
  - provide chapter context for prompt injection
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import ManagerProgress
from app.models.story_state import UserStoryState
from app.services.story_chapters import (
    CHAPTERS,
    EPOCHS,
    StoryChapter,
    StoryEpoch,
    cumulative_unlocked_archetypes,
    cumulative_unlocked_features,
    cumulative_unlocked_scenarios,
    epoch_for_chapter,
    get_chapter,
    max_difficulty_for_chapter,
)

logger = logging.getLogger(__name__)


@dataclass
class ChapterContext:
    """Context injected into LLM prompts for chapter-aware behavior."""
    chapter_id: int
    chapter_name: str
    epoch_id: int
    epoch_name: str
    narrative_intro: str
    max_difficulty: int
    unlocked_archetypes: list[str]
    unlocked_scenarios: list[str]


@dataclass
class AdvancementResult:
    """Returned when a user advances to the next chapter."""
    old_chapter: int
    new_chapter: int
    old_epoch: int
    new_epoch: int
    epoch_changed: bool
    narrative_trigger: str | None
    new_chapter_name: str
    new_chapter_intro: str
    unlocked_archetypes: list[str]
    unlocked_scenarios: list[str]
    unlocked_features: list[str]

    def to_dict(self) -> dict:
        return {
            "old_chapter": self.old_chapter,
            "new_chapter": self.new_chapter,
            "old_epoch": self.old_epoch,
            "new_epoch": self.new_epoch,
            "epoch_changed": self.epoch_changed,
            "narrative_trigger": self.narrative_trigger,
            "new_chapter_name": self.new_chapter_name,
            "new_chapter_intro": self.new_chapter_intro,
            "unlocked_archetypes": self.unlocked_archetypes,
            "unlocked_scenarios": self.unlocked_scenarios,
            "unlocked_features": self.unlocked_features,
        }


@dataclass
class StoryProgress:
    """Full story progress for API response."""
    current_chapter: int
    current_epoch: int
    chapter_name: str
    epoch_name: str
    epoch_tagline: str
    chapter_intro: str
    chapter_sessions: int
    chapter_avg_score: float
    chapter_best_score: float
    specialization: str | None
    # Next chapter unlock conditions
    next_chapter: int | None
    next_unlock_level: int | None
    next_unlock_sessions: int | None
    next_unlock_score: int | None
    # Current manager level for comparison
    manager_level: int
    # Progress percentage (0-100)
    progress_pct: float
    # Epoch completion flags
    epochs_completed: list[int]

    def to_dict(self) -> dict:
        return {
            "current_chapter": self.current_chapter,
            "current_epoch": self.current_epoch,
            "chapter_name": self.chapter_name,
            "epoch_name": self.epoch_name,
            "epoch_tagline": self.epoch_tagline,
            "chapter_intro": self.chapter_intro,
            "chapter_sessions": self.chapter_sessions,
            "chapter_avg_score": self.chapter_avg_score,
            "chapter_best_score": self.chapter_best_score,
            "specialization": self.specialization,
            "next_chapter": self.next_chapter,
            "next_unlock_level": self.next_unlock_level,
            "next_unlock_sessions": self.next_unlock_sessions,
            "next_unlock_score": self.next_unlock_score,
            "manager_level": self.manager_level,
            "progress_pct": self.progress_pct,
            "epochs_completed": self.epochs_completed,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Core functions
# ═══════════════════════════════════════════════════════════════════════════

async def get_or_create_story_state(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> UserStoryState:
    """Get existing story state or create a new one at Chapter 1."""
    result = await db.execute(
        select(UserStoryState).where(UserStoryState.user_id == user_id)
    )
    state = result.scalar_one_or_none()
    if state is not None:
        return state

    state = UserStoryState(user_id=user_id)
    db.add(state)
    await db.flush()
    logger.info("Created story state for user %s at Chapter 1", user_id)
    return state


async def record_session_completion(
    user_id: uuid.UUID,
    score: float,
    db: AsyncSession,
) -> None:
    """Update chapter stats after a training session completes."""
    state = await get_or_create_story_state(user_id, db)

    n = state.chapter_sessions
    old_avg = state.chapter_avg_score
    state.chapter_sessions = n + 1
    state.chapter_avg_score = (old_avg * n + score) / (n + 1)
    if score > state.chapter_best_score:
        state.chapter_best_score = score

    await db.flush()


async def check_chapter_advancement(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> AdvancementResult | None:
    """Check if the user meets conditions to advance to next chapter.

    Returns AdvancementResult if advanced, None otherwise.
    """
    state = await get_or_create_story_state(user_id, db)

    if state.current_chapter >= 12:
        return None  # Already at final chapter

    current = get_chapter(state.current_chapter)
    next_ch = get_chapter(state.current_chapter + 1)
    if current is None or next_ch is None:
        return None

    # Get manager level
    result = await db.execute(
        select(ManagerProgress.current_level).where(
            ManagerProgress.user_id == user_id
        )
    )
    manager_level = result.scalar_one_or_none() or 1

    # Check all three conditions
    level_ok = manager_level >= next_ch.unlock_level
    sessions_ok = state.chapter_sessions >= next_ch.unlock_sessions
    score_ok = state.chapter_avg_score >= next_ch.unlock_score_threshold

    if not (level_ok and sessions_ok and score_ok):
        return None

    # Advance!
    return await advance_chapter(state, next_ch, db)


async def advance_chapter(
    state: UserStoryState,
    next_ch: StoryChapter,
    db: AsyncSession,
) -> AdvancementResult:
    """Perform the chapter advancement."""
    old_chapter = state.current_chapter
    old_epoch = state.current_epoch
    current_ch = get_chapter(old_chapter)

    # Get narrative trigger from the chapter we're COMPLETING
    narrative_trigger = current_ch.narrative_trigger if current_ch else None

    # Update state
    state.current_chapter = next_ch.id
    state.current_epoch = next_ch.epoch
    state.chapter_started_at = datetime.now(timezone.utc)
    state.chapter_sessions = 0
    state.chapter_avg_score = 0.0
    state.chapter_best_score = 0.0
    state.flashback_shown = False
    state.last_narrative_trigger = narrative_trigger

    # Mark epoch completion if epoch changed
    epoch_changed = next_ch.epoch != old_epoch
    if epoch_changed:
        field_name = f"epoch_{old_epoch}_completed_at"
        if hasattr(state, field_name):
            setattr(state, field_name, datetime.now(timezone.utc))

    await db.flush()

    logger.info(
        "User %s advanced: Chapter %d → %d (Epoch %d → %d)",
        state.user_id, old_chapter, next_ch.id, old_epoch, next_ch.epoch,
    )

    return AdvancementResult(
        old_chapter=old_chapter,
        new_chapter=next_ch.id,
        old_epoch=old_epoch,
        new_epoch=next_ch.epoch,
        epoch_changed=epoch_changed,
        narrative_trigger=narrative_trigger,
        new_chapter_name=next_ch.name,
        new_chapter_intro=next_ch.narrative_intro,
        unlocked_archetypes=next_ch.unlocked_archetypes,
        unlocked_scenarios=next_ch.unlocked_scenarios,
        unlocked_features=next_ch.unlocked_features,
    )


async def get_chapter_context(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> ChapterContext:
    """Get chapter context for prompt injection."""
    state = await get_or_create_story_state(user_id, db)
    ch = get_chapter(state.current_chapter) or CHAPTERS[1]
    ep = epoch_for_chapter(state.current_chapter) or EPOCHS[1]

    return ChapterContext(
        chapter_id=ch.id,
        chapter_name=ch.name,
        epoch_id=ep.id,
        epoch_name=ep.name,
        narrative_intro=ch.narrative_intro,
        max_difficulty=ch.max_difficulty,
        unlocked_archetypes=cumulative_unlocked_archetypes(ch.id),
        unlocked_scenarios=cumulative_unlocked_scenarios(ch.id),
    )


async def get_story_progress(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> StoryProgress:
    """Get full story progress for API response."""
    state = await get_or_create_story_state(user_id, db)
    ch = get_chapter(state.current_chapter) or CHAPTERS[1]
    ep = epoch_for_chapter(state.current_chapter) or EPOCHS[1]

    # Manager level
    result = await db.execute(
        select(ManagerProgress.current_level).where(
            ManagerProgress.user_id == user_id
        )
    )
    manager_level = result.scalar_one_or_none() or 1

    # Next chapter conditions
    next_ch = get_chapter(state.current_chapter + 1)
    next_chapter = next_ch.id if next_ch else None
    next_unlock_level = next_ch.unlock_level if next_ch else None
    next_unlock_sessions = next_ch.unlock_sessions if next_ch else None
    next_unlock_score = next_ch.unlock_score_threshold if next_ch else None

    # Progress percentage (weighted: 40% level, 30% sessions, 30% score)
    progress_pct = 0.0
    if next_ch:
        level_pct = min(1.0, manager_level / next_ch.unlock_level) if next_ch.unlock_level > 0 else 1.0
        sessions_pct = min(1.0, state.chapter_sessions / next_ch.unlock_sessions) if next_ch.unlock_sessions > 0 else 1.0
        score_pct = min(1.0, state.chapter_avg_score / next_ch.unlock_score_threshold) if next_ch.unlock_score_threshold > 0 else 1.0
        progress_pct = round((level_pct * 0.4 + sessions_pct * 0.3 + score_pct * 0.3) * 100, 1)
    else:
        progress_pct = 100.0  # Final chapter

    # Epoch completions
    epochs_completed = []
    if state.epoch_1_completed_at:
        epochs_completed.append(1)
    if state.epoch_2_completed_at:
        epochs_completed.append(2)
    if state.epoch_3_completed_at:
        epochs_completed.append(3)
    if state.epoch_4_completed_at:
        epochs_completed.append(4)

    return StoryProgress(
        current_chapter=state.current_chapter,
        current_epoch=state.current_epoch,
        chapter_name=ch.name,
        epoch_name=ep.name,
        epoch_tagline=ep.tagline,
        chapter_intro=ch.narrative_intro,
        chapter_sessions=state.chapter_sessions,
        chapter_avg_score=round(state.chapter_avg_score, 1),
        chapter_best_score=round(state.chapter_best_score, 1),
        specialization=state.specialization,
        next_chapter=next_chapter,
        next_unlock_level=next_unlock_level,
        next_unlock_sessions=next_unlock_sessions,
        next_unlock_score=next_unlock_score,
        manager_level=manager_level,
        progress_pct=progress_pct,
        epochs_completed=epochs_completed,
    )
