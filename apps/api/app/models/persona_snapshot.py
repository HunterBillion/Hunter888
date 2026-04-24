"""PersonaSnapshot — immutable per-session persona (Roadmap §8).

The platform had four separate sources for "who is this AI client":
``ClientProfile``, ``ClientStory.personality_profile``,
``_session_voices`` in-memory dict in ``tts.py``, and whatever
``custom_params`` carried on the session. They drifted. Same call on
the same client could hear a different voice; adjective agreement
didn't match the avatar's gender; label on the results page disagreed
with the label on the call page.

``PersonaSnapshot`` freezes, per session, the facts that must stay
stable: identity (name/gender/city/age), persona label, voice
parameters. Written once at ``session.start``, never updated — the
service layer enforces insert-only (there is no UPDATE path in the
code, and tests enforce this invariant).

For multi-call stories the first call's snapshot is "canonical" —
subsequent calls in the same story copy its voice_id and gender so
voice continuity holds across calls (§8.5 invariant).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PersonaSnapshot(Base):
    __tablename__ = "persona_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # One snapshot per session — enforced by UNIQUE.
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # Optional CRM links — null for game-only sessions.
    lead_client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lead_clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    client_story_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_stories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Identity — frozen copy, never mutated.
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    gender: Mapped[str] = mapped_column(String(10), nullable=False)  # male | female | unknown
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Runtime persona — what the AI character "is".
    archetype_code: Mapped[str] = mapped_column(String(50), nullable=False)
    persona_label: Mapped[str] = mapped_column(String(200), nullable=False)

    # Voice — TTS resolution point.
    voice_id: Mapped[str] = mapped_column(String(100), nullable=False)
    voice_provider: Mapped[str] = mapped_column(String(30), nullable=False)  # elevenlabs | openai | webspeech | navy
    voice_params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Metadata.
    frozen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source_ref: Mapped[str] = mapped_column(String(60), nullable=False)  # "session.start" | "story.continue" | ...

    __table_args__ = (
        UniqueConstraint("session_id", name="uq_persona_snapshot_session_id"),
    )

    def to_dict(self) -> dict:
        """Shape used by frontend / API schemas."""
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "lead_client_id": str(self.lead_client_id) if self.lead_client_id else None,
            "client_story_id": str(self.client_story_id) if self.client_story_id else None,
            "full_name": self.full_name,
            "gender": self.gender,
            "city": self.city,
            "age": self.age,
            "archetype_code": self.archetype_code,
            "persona_label": self.persona_label,
            "voice_id": self.voice_id,
            "voice_provider": self.voice_provider,
            "voice_params": self.voice_params,
            "frozen_at": self.frozen_at.isoformat() if self.frozen_at else None,
            "source_ref": self.source_ref,
        }
