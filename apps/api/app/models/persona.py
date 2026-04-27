"""TZ-4 D1 — MemoryPersona + SessionPersonaSnapshot.

Two new ORM tables that formalize the persona memory layer (TZ-4
§6.3.1, §6.4.1, §9). Replaces the ad-hoc `custom_params['persona_
snapshot']` dict written today at `apps/api/app/api/training.py:531-537`
(which is silently dropped on the floor — verified by hotfix PR #55).

**Coexistence with `ClientProfile`** (TZ-4 §6.6):

* `apps/api/app/models/roleplay.py::ClientProfile` stays — it's the
  AI-character training entity (objections, traps, fears, breaking_
  point — behavior of the AI client during a session). Per-session.
* `MemoryPersona` (this file) is the cross-session human-CRM-client
  memory. One row per `lead_client_id`. Identity fields live here;
  AI behavior fields live on ClientProfile.
* `SessionPersonaSnapshot` (this file) is an immutable snapshot
  taken at session start so the runtime cannot silently drift mid-
  session (§9.2 invariant 1).

These tables ship in alembic 20260427_001 (D1). Services that read/
write them land in D3 (`apps/api/app/services/persona_memory.py`).
The hotfix PR #55 (persist_client_profile_from_dict) keeps working
as backstop — D3 cutover migrates the home flow to use the new
tables instead.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ── Address-form / gender / tone enums (TZ-4 §6.3.1, §6.5) ──────────────

# Mirror of CHECK constraints in alembic 20260427_001. Kept here as
# Python-side Final sets so callers can `if value not in ADDRESS_FORMS:`
# raise client-side BEFORE round-tripping to the DB and getting an
# IntegrityError. The DB CHECK is the source of truth — these mirrors
# are convenience.
ADDRESS_FORMS: frozenset[str] = frozenset({"вы", "ты", "formal", "informal", "auto"})
GENDERS: frozenset[str] = frozenset({"male", "female", "other", "unknown"})
TONES: frozenset[str] = frozenset({"neutral", "friendly", "formal", "cautious", "hostile"})

# `captured_from` enum on SessionPersonaSnapshot
PERSONA_CAPTURED_FROM: frozenset[str] = frozenset(
    {"real_client", "home_preview", "training_simulation", "pvp", "center"}
)


class MemoryPersona(Base):
    """Cross-session human-CRM-client persona memory (TZ-4 §6.3).

    One row per ``lead_client_id`` (UNIQUE). Tracks identity facts and
    "do not ask again" slots so that AI in any subsequent session
    (chat / call / center / pvp) does not re-prompt for the same data
    or contradict an already-confirmed fact.

    Mutation contract (§9.2 invariants):
      * Identity fields (``full_name / gender / role_title /
        address_form``) change only via explicit ``persona.updated``
        domain event. Bumps ``source_profile_version``.
      * Any update bumps ``version`` (optimistic concurrency token,
        §9.2.5). Concurrent updates see PersonaConflict 409.
      * ``do_not_ask_again_slots`` and ``confirmed_facts`` may be
        appended to by ``persona.slot_locked`` events.

    Slot-code catalog: see TZ-4 §6.5 (16 slots: full_name / phone /
    email / city / age / gender / role_title / total_debt / creditors /
    income / income_type / family_status / children_count /
    property_status / consent_124fz / next_contact_at / lost_reason).

    `confirmed_facts` JSONB shape:
        {
          "full_name": {"value": "...", "confirmed_at": "...", "source": "..."},
          ...
        }
    """

    __tablename__ = "memory_personas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    lead_client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lead_clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    address_form: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="auto",
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    gender: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="unknown",
    )
    role_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tone: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="neutral",
    )
    do_not_ask_again_slots: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"),
    )
    confirmed_facts: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"),
    )
    source_profile_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1",
    )
    # Optimistic concurrency token (§9.2.5). Bumps on every UPDATE;
    # callers send `expected_version` and get PersonaConflict 409 on
    # mismatch. Pattern mirrored from TZ-3 ScenarioTemplate.draft_revision.
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1",
    )
    last_confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("lead_client_id", name="uq_memory_personas_lead_client_id"),
        CheckConstraint(
            "address_form IN ('вы', 'ты', 'formal', 'informal', 'auto')",
            name="ck_memory_personas_address_form",
        ),
        CheckConstraint(
            "gender IN ('male', 'female', 'other', 'unknown')",
            name="ck_memory_personas_gender",
        ),
        CheckConstraint(
            "tone IN ('neutral', 'friendly', 'formal', 'cautious', 'hostile')",
            name="ck_memory_personas_tone",
        ),
    )


class SessionPersonaSnapshot(Base):
    """Immutable per-session persona snapshot (TZ-4 §6.4).

    One row per ``training_sessions.id`` (PK). Captured at session
    start by ``services/persona_memory.capture_for_session(...)``
    (lands in D3). After INSERT the row is **never updated** — runtime
    reads from it for prompt assembly, mutation attempts increment
    ``mutation_blocked_count`` (observability) and emit
    ``persona.conflict_detected`` event (§9.3).

    Why session-scoped immutability matters:
      * Without this, anyone writing to ``custom_params`` could
        change the AI's perception of who they're talking to mid-
        session — exactly the bug PR #55 hotfixed at one site.
      * With this, the prompt assembler reads ONLY from this snapshot
        for identity fields. Drift becomes architecturally impossible.

    Backfill: alembic 20260427_001 does NOT backfill existing sessions
    (they're already finished or active without snapshot — no value).
    D3 backfill SQL in TZ-4 §12.1.1 handles existing rows for analytics.
    """

    __tablename__ = "session_persona_snapshots"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    lead_client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lead_clients.id", ondelete="SET NULL"),
        nullable=True,
    )
    persona_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1",
    )
    address_form: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="auto",
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    gender: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="unknown",
    )
    role_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tone: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="neutral",
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    captured_from: Mapped[str] = mapped_column(String(40), nullable=False)
    # Observability: bumps every time runtime tries to mutate this
    # snapshot. Healthy session has 0; non-zero = persona drift attempt
    # caught by §9.2 invariant 1 enforcement.
    mutation_blocked_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )

    __table_args__ = (
        Index(
            "ix_session_persona_snapshots_lead_client_id",
            "lead_client_id",
            postgresql_where=sa.text("lead_client_id IS NOT NULL"),
        ),
        CheckConstraint(
            "address_form IN ('вы', 'ты', 'formal', 'informal', 'auto')",
            name="ck_session_persona_snapshots_address_form",
        ),
        CheckConstraint(
            "gender IN ('male', 'female', 'other', 'unknown')",
            name="ck_session_persona_snapshots_gender",
        ),
        CheckConstraint(
            "tone IN ('neutral', 'friendly', 'formal', 'cautious', 'hostile')",
            name="ck_session_persona_snapshots_tone",
        ),
        CheckConstraint(
            "captured_from IN ('real_client', 'home_preview', "
            "'training_simulation', 'pvp', 'center')",
            name="ck_session_persona_snapshots_captured_from",
        ),
    )


__all__ = [
    "ADDRESS_FORMS",
    "GENDERS",
    "MemoryPersona",
    "PERSONA_CAPTURED_FROM",
    "SessionPersonaSnapshot",
    "TONES",
]
