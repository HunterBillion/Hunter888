"""PersonaSnapshot service — capture + resolve (Roadmap §8).

Two public functions:

* :func:`capture` — called exactly once at ``session.start``.
  Builds an immutable ``PersonaSnapshot`` from whatever identity/voice
  context is available at the call site (RealClient, ClientStory, custom
  character params). Returns the snapshot. If the session already has
  one attached (UNIQUE on ``session_id``), returns the existing row
  without mutation — this is the idempotency guarantee §8.2 calls for.

* :func:`get_for_session` — fast lookup used by TTS, character-prompt
  builder, and the session API response. The cutover from
  ``_session_voices`` in-memory dict is staged: consumers check the
  snapshot first, fall back to their legacy path if None.

The capture site also emits a ``persona.snapshot_captured`` DomainEvent
(TZ-1 §9 catalog) so downstream analytics can see the facts that were
frozen at that moment.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.persona_snapshot import PersonaSnapshot
from app.models.roleplay import ClientStory
from app.models.training import TrainingSession

logger = logging.getLogger(__name__)


# ── Persona-label rendering ──────────────────────────────────────────────


def _persona_label(archetype_code: str, gender: str) -> str:
    """Return a gender-agreed label for the UI card.

    Shares the catalogue with the between-call narrator so
    ``results_page`` and the call card never drift apart.
    """
    try:
        from app.services.between_call_narrator import trait_for
    except Exception:  # pragma: no cover — defensive; the module is always importable
        return "клиент"
    normalized_gender = gender if gender in ("male", "female") else "unknown"
    return trait_for(archetype_code, normalized_gender)


# ── Capture ──────────────────────────────────────────────────────────────


async def capture(
    db: AsyncSession,
    *,
    session: TrainingSession,
    full_name: str,
    gender: str,
    archetype_code: str,
    voice_id: str,
    voice_provider: str,
    voice_params: dict[str, Any] | None = None,
    city: str | None = None,
    age: int | None = None,
    source_ref: str = "session.start",
) -> PersonaSnapshot:
    """Create a snapshot for ``session`` or return the existing one.

    Idempotent: if the session already has a snapshot attached, we
    return it unchanged. No UPDATE happens on the existing row — this
    preserves the §8.2 "insert-only" invariant.

    ``voice_params`` defaults to an empty dict so callers with only
    ``voice_id`` (like fallback TTS paths) don't have to stub it.
    """
    existing = (
        await db.execute(
            select(PersonaSnapshot).where(PersonaSnapshot.session_id == session.id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    # Multi-call continuity §8.5: if the session belongs to a story and
    # the story already has a canonical first-call snapshot, mirror its
    # voice_id + gender + persona_label so voice stays stable.
    if session.client_story_id is not None:
        first = (
            await db.execute(
                select(PersonaSnapshot)
                .where(PersonaSnapshot.client_story_id == session.client_story_id)
                .order_by(PersonaSnapshot.frozen_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if first is not None:
            voice_id = first.voice_id
            voice_provider = first.voice_provider
            voice_params = first.voice_params
            gender = first.gender
            archetype_code = first.archetype_code

    normalized_gender = gender if gender in ("male", "female") else "unknown"
    label = _persona_label(archetype_code, normalized_gender)

    snapshot = PersonaSnapshot(
        id=uuid.uuid4(),
        session_id=session.id,
        lead_client_id=session.lead_client_id,
        client_story_id=session.client_story_id,
        full_name=full_name or "Клиент",
        gender=normalized_gender,
        city=city,
        age=age,
        archetype_code=archetype_code,
        persona_label=label,
        voice_id=voice_id,
        voice_provider=voice_provider,
        voice_params=voice_params or {},
        source_ref=source_ref,
    )
    db.add(snapshot)
    await db.flush()

    # Canonical DomainEvent — only emitted when the session has a real
    # CRM anchor. Purely-synthetic game sessions don't populate the
    # client domain (§9.1 semantics).
    if session.real_client_id is not None:
        try:
            from app.models.client import RealClient
            from app.services.client_domain import emit_client_event

            client = await db.get(RealClient, session.real_client_id)
            if client is not None:
                await emit_client_event(
                    db,
                    client=client,
                    event_type="persona.snapshot_captured",
                    actor_type="system",
                    actor_id=session.user_id,
                    source=source_ref,
                    payload={
                        "training_session_id": str(session.id),
                        "persona_snapshot_id": str(snapshot.id),
                        "archetype_code": archetype_code,
                        "gender": normalized_gender,
                        "voice_id": voice_id,
                        "voice_provider": voice_provider,
                    },
                    aggregate_type="persona_snapshot",
                    aggregate_id=snapshot.id,
                    session_id=session.id,
                    idempotency_key=f"persona-snapshot:{session.id}",
                    correlation_id=str(session.id),
                )
        except Exception:
            logger.warning(
                "persona_snapshot.capture: domain event emit failed for session=%s",
                session.id, exc_info=True,
            )

    logger.info(
        "persona_snapshot.captured",
        extra={
            "session_id": str(session.id),
            "snapshot_id": str(snapshot.id),
            "archetype": archetype_code,
            "gender": normalized_gender,
            "voice_id": voice_id,
            "source_ref": source_ref,
        },
    )
    return snapshot


async def capture_from_story(
    db: AsyncSession,
    *,
    session: TrainingSession,
    story: ClientStory,
    archetype_code: str,
    voice_id: str,
    voice_provider: str,
    voice_params: dict[str, Any] | None = None,
    source_ref: str = "story.continue",
) -> PersonaSnapshot:
    """Convenience wrapper for the WS ``story.continue`` flow.

    Pulls identity fields from ``ClientStory.personality_profile`` /
    ``ClientProfile``. Falls back to placeholders if either is missing
    so the snapshot still gets written — downstream readers know
    ``"unknown"`` is a sentinel.
    """
    personality = story.personality_profile or {}
    full_name = personality.get("full_name") or getattr(story, "story_name", None) or "Клиент"
    gender = personality.get("gender") or "unknown"
    city = personality.get("city")
    age = personality.get("age")

    return await capture(
        db,
        session=session,
        full_name=full_name,
        gender=gender,
        city=city,
        age=age,
        archetype_code=archetype_code,
        voice_id=voice_id,
        voice_provider=voice_provider,
        voice_params=voice_params,
        source_ref=source_ref,
    )


# ── Resolve ──────────────────────────────────────────────────────────────


async def get_for_session(
    db: AsyncSession, session_id: uuid.UUID
) -> PersonaSnapshot | None:
    return (
        await db.execute(
            select(PersonaSnapshot).where(PersonaSnapshot.session_id == session_id)
        )
    ).scalar_one_or_none()


async def resolve_voice_id(
    db: AsyncSession, session_id: uuid.UUID
) -> tuple[str, str, dict[str, Any]] | None:
    """Return ``(voice_id, provider, params)`` for the session, or None.

    TTS layer calls this first; legacy ``_session_voices`` stays only as
    fallback for sessions predating the snapshot migration.
    """
    snapshot = await get_for_session(db, session_id)
    if snapshot is None:
        return None
    return (snapshot.voice_id, snapshot.voice_provider, snapshot.voice_params or {})


__all__ = [
    "capture",
    "capture_from_story",
    "get_for_session",
    "resolve_voice_id",
]
