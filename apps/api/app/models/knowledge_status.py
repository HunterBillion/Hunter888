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


# ── Transition graph (B5-07) ────────────────────────────────────────────
#
# Until 2026-05-02 the transition rules in :class:`KnowledgeStatus` lived
# only as a docstring. ``knowledge_review_policy.mark_reviewed`` enforced
# the docstring loosely (one ``AutoOutdatedForbidden`` check), but the
# methodology PATCH endpoint and the TTL scheduler bypassed enforcement
# entirely — letting a ROP do ``outdated → actual`` (recovery from soft
# delete) which the docstring explicitly forbids. Audit B5-07 surfaced
# this; the table below is the single source of truth from now on.
#
# Two sets of rules are encoded:
#   * ``_HUMAN_ALLOWED_TRANSITIONS`` — what a human (admin/rop) may do
#     via the UI / REST PATCH endpoint.
#   * ``_AUTOMATED_ALLOWED_TRANSITIONS`` — what the system itself may
#     do via the TTL scheduler. Strictly narrower than the human set:
#     no automation may flip into ``outdated`` (TZ-4 §8.3.1 — wiping
#     the knowledge base by cron is the failure mode that motivated
#     the entire governance layer).
#
# Both sets implement the docstring on :class:`KnowledgeStatus` exactly.

_HUMAN_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    KnowledgeStatus.actual.value: frozenset({
        KnowledgeStatus.needs_review.value,
        KnowledgeStatus.disputed.value,
        KnowledgeStatus.outdated.value,
    }),
    KnowledgeStatus.needs_review.value: frozenset({
        KnowledgeStatus.actual.value,
        KnowledgeStatus.outdated.value,
    }),
    KnowledgeStatus.disputed.value: frozenset({
        KnowledgeStatus.actual.value,
        KnowledgeStatus.outdated.value,
    }),
    # ``outdated`` is the soft-delete terminal — no exit. Recovery is
    # a fresh INSERT (audit-friendly).
    KnowledgeStatus.outdated.value: frozenset(),
}

_AUTOMATED_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    # The TTL scheduler may only flag rows for review; never delete.
    KnowledgeStatus.actual.value: frozenset({KnowledgeStatus.needs_review.value}),
    # Everything else: automation is forbidden. Human review only.
    KnowledgeStatus.needs_review.value: frozenset(),
    KnowledgeStatus.disputed.value: frozenset(),
    KnowledgeStatus.outdated.value: frozenset(),
}


class IllegalStatusTransition(ValueError):
    """Raised when a caller attempts a status flip the graph forbids.

    ``from_status`` and ``to_status`` are exposed on the instance so
    REST handlers can map to a 409 with a structured payload (the FE
    needs to know which pair was rejected to craft the right toast).
    """

    def __init__(
        self,
        from_status: str,
        to_status: str,
        *,
        automated: bool,
    ) -> None:
        self.from_status = from_status
        self.to_status = to_status
        self.automated = automated
        actor = "automated path" if automated else "manual transition"
        super().__init__(
            f"Illegal {actor}: {from_status} → {to_status}. "
            f"See KnowledgeStatus docstring for the allowed graph."
        )


def validate_transition(
    from_status: str | KnowledgeStatus | None,
    to_status: str | KnowledgeStatus,
    *,
    automated: bool = False,
) -> None:
    """Raise :class:`IllegalStatusTransition` if the flip is not allowed.

    Args:
        from_status: current ``knowledge_status`` value. Tolerant on
            input shape (str / enum / None). ``None`` is treated as
            ``actual`` for parity with :func:`is_visible_in_rag` —
            legacy rows pre-dating the column behave as if ``actual``.
        to_status: target value. Required; ``None`` would be ambiguous
            and is rejected as a TypeError early.
        automated: True when called from a scheduler / bulk job.
            Reads from :data:`_AUTOMATED_ALLOWED_TRANSITIONS` (strictly
            narrower). False (default) reads from
            :data:`_HUMAN_ALLOWED_TRANSITIONS`.

    Idempotent same-state flips (e.g. ``actual → actual``) are
    accepted as a no-op — REST endpoints often re-PATCH on UI
    refresh and we don't want spurious 409s. The caller still gets
    a clean return; the side-effect (event emit, version bump) is
    the caller's choice.
    """
    if to_status is None:
        raise TypeError("validate_transition: to_status must not be None")

    src = (
        from_status.value
        if isinstance(from_status, KnowledgeStatus)
        else (from_status or KnowledgeStatus.actual.value)
    )
    dst = (
        to_status.value
        if isinstance(to_status, KnowledgeStatus)
        else str(to_status)
    )

    if src == dst:
        # Idempotent re-PATCH; not a transition.
        return

    table = (
        _AUTOMATED_ALLOWED_TRANSITIONS if automated
        else _HUMAN_ALLOWED_TRANSITIONS
    )

    allowed = table.get(src, frozenset())
    if dst not in allowed:
        raise IllegalStatusTransition(src, dst, automated=automated)


def allowed_next_states(
    current: str | KnowledgeStatus | None,
    *,
    automated: bool = False,
) -> frozenset[str]:
    """Return the set of legal next states. Read-only mirror of the
    transition graph for UI hints (e.g. greying out forbidden chips).

    Same-state is excluded — UI should treat "no change" separately.
    """
    src = (
        current.value
        if isinstance(current, KnowledgeStatus)
        else (current or KnowledgeStatus.actual.value)
    )
    table = (
        _AUTOMATED_ALLOWED_TRANSITIONS if automated
        else _HUMAN_ALLOWED_TRANSITIONS
    )
    return table.get(src, frozenset())


__all__ = [
    "KnowledgeStatus",
    "STATUSES_VISIBLE_IN_RAG",
    "STATUSES_HIDDEN_FROM_RAG",
    "is_visible_in_rag",
    "IllegalStatusTransition",
    "validate_transition",
    "allowed_next_states",
]
