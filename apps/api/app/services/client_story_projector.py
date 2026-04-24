"""ClientStory projection bridge (TZ-1 §11.2, §14.4).

``ClientStory`` was historically a source-of-truth for AI roleplay continuity.
TZ-1 downgrades it to a *projection* over the canonical event log: changes to
the relationship score, lifecycle state, and director_state emit
``DomainEvent`` rows when the story is linked to a real CRM client, so the
projection can be rebuilt from history.

Only story changes that resolve to a ``RealClient`` via a ``TrainingSession``
with ``real_client_id`` produce a DomainEvent — purely synthetic game stories
do not populate the real CRM.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import RealClient
from app.models.domain_event import DomainEvent
from app.models.roleplay import ClientStory
from app.models.training import TrainingSession
from app.services.client_domain import emit_client_event

logger = logging.getLogger(__name__)


async def resolve_real_client_for_story(
    db: AsyncSession, *, story: ClientStory
) -> RealClient | None:
    """Walk story → training session → real client.

    Returns the most recent linked RealClient or None. Synthetic stories
    (no session with ``real_client_id``) yield None — that's the signal to
    skip domain emission.
    """
    real_client_id = (await db.execute(
        select(TrainingSession.real_client_id)
        .where(
            TrainingSession.client_story_id == story.id,
            TrainingSession.real_client_id.isnot(None),
        )
        .order_by(TrainingSession.started_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if real_client_id is None:
        return None
    return await db.get(RealClient, real_client_id)


async def record_story_lifecycle_change(
    db: AsyncSession,
    *,
    story: ClientStory,
    old_state: str | None,
    new_state: str | None,
    actor_id: uuid.UUID | None,
    source: str = "game_director",
    extra: dict[str, Any] | None = None,
) -> DomainEvent | None:
    if old_state == new_state:
        return None
    client = await resolve_real_client_for_story(db, story=story)
    if client is None:
        return None
    payload: dict[str, Any] = {
        "story_id": str(story.id),
        "old_state": old_state,
        "new_state": new_state,
        "relationship_score": getattr(story, "relationship_score", None),
        "total_calls": getattr(story, "total_calls", None),
    }
    if extra:
        payload.update(extra)
    return await emit_client_event(
        db,
        client=client,
        event_type="story.lifecycle_changed",
        actor_type="system",
        actor_id=actor_id,
        source=source,
        payload=payload,
        aggregate_type="client_story",
        aggregate_id=story.id,
        idempotency_key=f"story-lifecycle:{story.id}:{old_state}->{new_state}:{story.total_calls}",
        correlation_id=str(story.id),
    )


async def record_story_game_event(
    db: AsyncSession,
    *,
    story: ClientStory,
    game_event_type: str,
    game_event_id: uuid.UUID | None,
    payload: dict[str, Any] | None,
    actor_id: uuid.UUID | None,
    source: str,
) -> DomainEvent | None:
    """Mirror a GameClientEvent into the canonical DomainEvent log.

    No-op when the story is not linked to a real CRM client — synthetic
    game continuity keeps living in ``GameClientEvent`` alone, as TZ §11.3
    permits during migration.
    """
    client = await resolve_real_client_for_story(db, story=story)
    if client is None:
        return None
    full_payload: dict[str, Any] = {
        "story_id": str(story.id),
        "game_event_id": str(game_event_id) if game_event_id else None,
        "game_event_type": game_event_type,
    }
    if payload:
        full_payload.update(payload)
    key_anchor = str(game_event_id) if game_event_id else uuid.uuid4().hex
    return await emit_client_event(
        db,
        client=client,
        event_type=f"game.{game_event_type}",
        actor_type="system",
        actor_id=actor_id,
        source=source,
        payload=full_payload,
        aggregate_type="game_client_event",
        aggregate_id=game_event_id,
        idempotency_key=f"game-event:{key_anchor}",
        correlation_id=str(story.id),
    )
