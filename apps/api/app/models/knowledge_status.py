"""Shared `KnowledgeStatus` vocabulary for RAG-eligible tables.

TZ-8 PR-A foundation. Promotes the four-state governance vocabulary
that until now existed only as untyped string constants in
``app.services.knowledge_governance`` (used solely by the legal RAG
path) into a formal :class:`enum.Enum` shared by **every** table that
holds user-curated RAG content:

  * :class:`app.models.rag.LegalKnowledgeChunk`
  * :class:`app.models.manager_wiki.WikiPage`
  * :class:`app.models.methodology.MethodologyChunk` (new in TZ-8)

Centralising the values here is the TZ-5 fixed point #4 — *one*
governance model, not three drifted copies. Service-layer code and
SQL filters import :data:`STATUSES_VISIBLE_IN_RAG` /
:data:`STATUSES_HIDDEN_FROM_RAG` from this module so a future change
to the visibility contract (e.g. promoting ``disputed`` to hidden or
splitting ``outdated`` into ``superseded`` + ``retired``) propagates
to every consumer in one PR instead of three.

The string values are *deliberately* identical to the legacy
``KNOWLEDGE_STATUS_*`` constants in
``app.services.knowledge_governance`` so existing
``legal_knowledge_chunks.knowledge_status`` rows stay readable
without a migration step. The legacy module re-exports these names
for back-compat — see its docstring for the deprecation timeline.

Why ``str, enum.Enum`` not :class:`enum.StrEnum`
------------------------------------------------

The codebase targets Python 3.12+ (CI runs 3.12, dev runs 3.13), so
:class:`StrEnum` would work. We use the explicit ``(str, enum.Enum)``
mixin to match the rest of the project (``UserRole``, ``WikiStatus``,
``MethodologyKind``, etc.) — readability + grep-ability win.
"""
from __future__ import annotations

import enum


class KnowledgeStatus(str, enum.Enum):
    """Lifecycle state of a single RAG-eligible row.

    Transitions allowed (enforced in service layer, not a DB CHECK,
    so a corrective UPDATE in psql still works during incidents):

      * ``actual``        ← initial state for ROP/admin-authored rows
                            and for the auto-publish path of arena
                            chunks (PR #139, ``original_confidence ≥
                            0.85``).
      * ``actual``        → ``needs_review``  (auto-flip by TTL only;
                                              never auto → outdated —
                                              see TZ-4 §8.3.1).
      * ``actual``        → ``disputed``     (manual; another author
                                              flagged the row).
      * ``actual``        → ``outdated``     (manual; superseded).
      * ``needs_review``  → ``actual``       (manual re-acknowledge).
      * ``needs_review``  → ``outdated``     (manual; reviewer decides
                                              the row no longer
                                              applies).
      * ``disputed``      → ``actual``       (manual; dispute resolved
                                              in favour of keeping).
      * ``disputed``      → ``outdated``     (manual; dispute resolved
                                              in favour of removal).

    No transition is allowed *out of* ``outdated`` — that's a soft
    delete. Recovering an outdated row is a fresh INSERT with new
    ``created_at`` (audit-friendly).
    """

    actual = "actual"
    """Row is current, surfaces in RAG without warnings."""

    disputed = "disputed"
    """Row is current but flagged sentinel-style: surfaces in RAG
    with a downward rerank bias and a UI warning chip. Used when a
    reviewer disagrees but the row hasn't been replaced yet."""

    outdated = "outdated"
    """Soft delete. Hidden from RAG retrieval entirely. Kept in the
    table for audit + ``ChunkUsageLog`` join history."""

    needs_review = "needs_review"
    """Row's TTL expired (``review_due_at < now()``) without a manual
    re-acknowledge. Hidden from RAG retrieval until a reviewer
    flips it back to ``actual`` or forward to ``outdated``. The
    auto-flip is the *only* automated transition into this state —
    every other transition out of ``actual`` is human-initiated."""


# ── SQL filter helpers ──────────────────────────────────────────────────
#
# These two frozensets are the canonical filter contract: anything that
# decides "should this row appear in coach/training/judge RAG?" reads
# from :data:`STATUSES_VISIBLE_IN_RAG`. A future change to the contract
# (e.g. demote ``disputed`` to hidden) is one edit here, no source
# walk required.

STATUSES_VISIBLE_IN_RAG: frozenset[str] = frozenset(
    {KnowledgeStatus.actual.value, KnowledgeStatus.disputed.value}
)
"""Statuses whose rows are returned by RAG retrievers.

``disputed`` is included on purpose — see :class:`KnowledgeStatus`
docstring for the rationale (visible-with-warning vs. hidden).
"""

STATUSES_HIDDEN_FROM_RAG: frozenset[str] = frozenset(
    {KnowledgeStatus.outdated.value, KnowledgeStatus.needs_review.value}
)
"""Statuses excluded from RAG retrieval. Their rows still exist in
the table for history / audit / ``ChunkUsageLog`` joins."""


def is_visible_in_rag(status: str | KnowledgeStatus | None) -> bool:
    """Single-row equivalent of :data:`STATUSES_VISIBLE_IN_RAG`.

    Tolerant on input shape because callers vary — SQL-fetched rows
    arrive as plain strings, ORM-fetched rows arrive as enum members,
    legacy rows that pre-date the column are ``None``. ``None`` is
    treated as ``actual`` for backwards compatibility (the column
    defaults to ``actual`` going forward, so this only matters for
    in-flight migration windows).
    """
    if status is None:
        return True
    if isinstance(status, KnowledgeStatus):
        return status.value in STATUSES_VISIBLE_IN_RAG
    return str(status) in STATUSES_VISIBLE_IN_RAG


__all__ = [
    "KnowledgeStatus",
    "STATUSES_VISIBLE_IN_RAG",
    "STATUSES_HIDDEN_FROM_RAG",
    "is_visible_in_rag",
]
