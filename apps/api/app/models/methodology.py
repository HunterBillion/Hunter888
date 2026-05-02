"""Per-team methodology playbooks (TZ-8 §3.3).

The third RAG-eligible row type alongside ``LegalKnowledgeChunk``
(global, factual, with review queue) and ``WikiPage`` (per-manager,
auto-generated from session ingest). Methodology is the *team*
playbook layer: scripts, objection handling, persona-specific tone
guidance — content that belongs to one team, can be authored only by
that team's ROP / admin, and must not surface in the RAG of another
team.

The full design rationale lives in :doc:`docs/TZ-8_methodology_rag.md`.
This module is the schema-only deliverable of PR-A; the REST API,
the retriever and the UI live in PR-B / PR-C.

Key invariants this schema enforces (cross-cut with TZ-8 §1):

  * ``team_id NOT NULL`` — methodology has no global / orphan scope.
    A ROP without a team cannot author one (handled at the API
    layer; this model has the structural slot).
  * ``UNIQUE (team_id, title)`` — duplicate titles inside the same
    team would surface as conflicting playbooks for the same query.
    The constraint forces ROPs to mark old versions ``outdated``
    instead of accreting "Closing v1 / Closing v2 / Closing v3".
  * ``knowledge_status`` reuses the *single* canonical
    :class:`KnowledgeStatus` from :mod:`app.models.knowledge_status`,
    shared with ``LegalKnowledgeChunk`` and ``WikiPage`` (TZ-5
    fixed point #4 — one governance, not three).
  * ``embedding`` is ``Vector(768)`` to match Gemini /
    nomic-embed-text@768 — same provider as legal / wiki RAG.
    pgvector ``ivfflat`` index with ``lists=100`` is the starting
    point; switching to HNSW is one migration when a team crosses
    ~5 k chunks (deferred per TZ-8 §14).
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.knowledge_status import KnowledgeStatus


class MethodologyKind(str, enum.Enum):
    """Semantic category of a playbook chunk.

    The category is *not* free-form — eight values cover the buckets
    pilot ROPs asked for during TZ-8 scoping:

      * ``opener`` — call-opening script (greeting, hook, qualification
        question).
      * ``objection`` — objection handling (price / timing / authority /
        need).
      * ``closing`` — close + next-step (calendar, contract, hand-off).
      * ``discovery`` — qualification / discovery question banks.
      * ``persona_tone`` — tonality cheatsheet keyed to a client
        archetype (e.g. "with ``aggressive_boss`` keep sentences short,
        skip rapport").
      * ``counter_fact`` — pre-formulated "objection → fact" pairs that
        the team curates from real call wins.
      * ``process`` — internal procedure (handoff to senior, escalation
        rules, when to involve legal).
      * ``other`` — escape hatch. Should rarely be used; methodology
        editor UI nudges towards a typed kind on save.

    The retriever uses ``kind`` as a reranker hint (TZ-8 §3.6.1) — a
    coach query about objections boosts ``objection`` and
    ``counter_fact`` over ``opener``. Adding a new kind means a
    classifier update *and* a UI form update (filter dropdown), so we
    keep the list intentionally tight.
    """

    opener = "opener"
    objection = "objection"
    closing = "closing"
    discovery = "discovery"
    persona_tone = "persona_tone"
    counter_fact = "counter_fact"
    process = "process"
    other = "other"


class MethodologyChunk(Base):
    """A team-scoped playbook chunk.

    Authored by ``rop`` / ``admin``, surfaced to coach + judge + (eventually)
    PvP arena RAG when ``knowledge_status`` is in
    :data:`app.models.knowledge_status.STATUSES_VISIBLE_IN_RAG`.
    """

    __tablename__ = "methodology_chunks"

    # ── Identity ──
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Ownership ──
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    """Owning team. ``ON DELETE CASCADE`` is intentional: a team's
    methodology is meaningless without the team — better to lose the
    rows than leave orphan playbooks haunting search results."""

    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    """Original author. ``ON DELETE SET NULL`` because firing a ROP
    must not delete the team's accumulated methodology — the team
    keeps the value, the audit log keeps the history."""

    # ── Content ──
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    """Short title (≤200 chars). UNIQUE per team — see
    ``__table_args__`` for the rationale."""

    body: Mapped[str] = mapped_column(Text, nullable=False)
    """Full markdown body. Length-capped at 10 000 chars in the API
    schema layer (PR-B); the column itself is ``Text`` so a big
    paste doesn't need a schema bump."""

    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    """One of :class:`MethodologyKind`. Stored as plain ``String(30)``
    rather than a Postgres ENUM type so adding a new kind is a code
    change, not a migration. Validated at the API boundary."""

    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    """Free-form labels used by the methodology UI for filtering
    (e.g. ``["скан-код", "тёплый лид"]``). ≤20 elements; not used by
    the retriever."""

    keywords: Mapped[list[str]] = mapped_column(JSONB, default=list)
    """Reranker hints (TZ-8 §3.6) — overlap with the query terms
    boosts a chunk's score by ``+0.04`` per match. Distinct from
    ``tags`` because the two have different audiences (humans
    vs. retriever)."""

    # ── Governance (shared vocabulary with WikiPage + LegalKnowledgeChunk) ──
    knowledge_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=KnowledgeStatus.actual.value,
        server_default=KnowledgeStatus.actual.value,
        index=True,
    )
    """One of :class:`KnowledgeStatus`. ROP writes → ``actual``
    immediately (TZ-5 fixed point #2 — no review queue). State
    transitions live at the service layer; see ``KnowledgeStatus``
    docstring for the allowed graph."""

    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """Set when a reviewer flips ``actual``/``disputed``/``needs_review``
    via the PATCH ``/status`` endpoint (PR-B). Used to decide whether
    a chunk is overdue for re-review."""

    last_reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    review_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    """TTL deadline. NULL = no auto-review. When non-NULL and
    ``< now()``, the scheduled review-policy task (PR-E) auto-flips
    ``actual → needs_review`` *only* — never directly to ``outdated``,
    per TZ-4 §8.3.1 (a day-of-cutover would otherwise wipe the entire
    knowledge base in one go)."""

    # ── Embedding (same shape as wiki / legal RAG) ──
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    """768-dim vector from gemini-embedding-001 or the local
    nomic-embed-text fallback (provider chosen by
    ``app.services.llm.get_embeddings_batch``). Populated by the
    live-backfill worker (TZ-8 §3.5), NULL between save and
    embed-completion (window ≈ seconds)."""

    embedding_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """Provenance: which embedding model produced the vector. Lets
    a future model migration (gemini → next-gen) target rows that
    haven't been re-embedded yet."""

    embedding_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Audit ──
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    """Bumped on every ``PUT`` (the schema-level optimistic-concurrency
    field). Useful for the history UI and for change-detection in
    embedding-staleness checks."""

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )
    """Soft-delete flag (B5-01). Always paired with
    ``knowledge_status='outdated'`` when flipped to True via
    ``DELETE /methodology/chunks/{id}``. The combination is what every
    read site filters on: ``WHERE NOT is_deleted`` is the authoritative
    visibility gate; ``knowledge_status`` carries the lifecycle
    semantics. Pre-2026-05-02 the DELETE endpoint did
    ``await db.delete(chunk)`` (hard delete) — orphaning
    ``ChunkUsageLog`` rows and breaking the audit timeline. The flag
    fixes that without forfeiting the table's history."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        # UNIQUE per team — see TZ-8 §3.3.1 / §13.3 for the call.
        # Deliberately NOT (team_id, kind, title) — disambiguating by
        # kind would let "Closing playbook" exist as both an
        # ``opener`` (mistake) and a ``closing`` (intent), which a
        # confused query would surface twice.
        UniqueConstraint("team_id", "title", name="uq_methodology_team_title"),
        # Hot-path retrieval filters: WHERE team_id = X AND
        # knowledge_status IN ('actual','disputed') AND kind = ?.
        # Compound covering index keeps the planner from a separate
        # bitmap-and over status + kind.
        Index(
            "ix_methodology_chunks_team_status",
            "team_id", "knowledge_status",
        ),
        Index(
            "ix_methodology_chunks_team_kind",
            "team_id", "kind",
        ),
        # ivfflat index for cosine similarity. Declared here so
        # ``alembic check`` recognises it (the actual ivfflat
        # creation lives in migration 20260502_001 via raw SQL —
        # SQLAlchemy ``Index`` cannot express ``USING ivfflat``
        # with ``vector_cosine_ops`` plus ``WITH (lists=100)``).
        # The ``postgresql_using``/``postgresql_ops``/``postgresql_with``
        # kwargs are sufficient for autogenerate to skip a redundant
        # CREATE — the index already exists in the DB at this name.
        Index(
            "ix_methodology_chunks_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"lists": 100},
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover (dev-only ergonomics)
        return (
            f"MethodologyChunk(id={self.id}, team_id={self.team_id}, "
            f"kind={self.kind!r}, title={self.title!r}, "
            f"status={self.knowledge_status!r})"
        )


__all__ = [
    "MethodologyChunk",
    "MethodologyKind",
]
