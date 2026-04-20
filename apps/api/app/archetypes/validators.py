"""Validators for archetype codes at the ORM / API boundary.

``ClientProfile.archetype_code`` is stored as a plain string (historical
reason: JSONB compatibility, story snapshots). Nothing stops a developer or
old migration from writing ``"skeptc"`` instead of ``"skeptic"`` and silently
breaking scenario generation.

Two guards:

1. ``normalise_archetype_code(raw)`` — call from service code. Returns the
   canonical enum value, logs warning if the input was fixed (e.g. trimmed
   whitespace), raises ``InvalidArchetypeCodeError`` for garbage.

2. ``assert_known(code)`` — cheap membership check, used in SQLAlchemy
   ``@validates("archetype_code")`` hooks.

Heads-up: a full CHECK constraint at the DB level is introduced by the
Alembic migration ``2026_04_18_phase1_foundation.py`` (Phase 1.4). Application-level
validation catches bad inputs **before** they reach the DB, so the CHECK
constraint only fires on schema regressions.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class InvalidArchetypeCodeError(ValueError):
    """Raised when an archetype code cannot be normalised."""


def known_codes() -> frozenset[str]:
    """Return the frozen set of codes defined by ``ArchetypeCode`` enum."""

    # Lazy import — keeps the validators module SQLAlchemy-free.
    from app.models.roleplay import ArchetypeCode

    return frozenset(c.value for c in ArchetypeCode)


def normalise_archetype_code(raw: str | None) -> str:
    """Return the canonical archetype code for ``raw``.

    Strips whitespace, lower-cases, and maps a handful of well-known aliases
    (``"skeptc"`` → ``"skeptic"``, ``"agresive"`` → ``"aggressive"``) that we've
    seen in legacy data. Raises ``InvalidArchetypeCodeError`` if we can't map it.
    """

    if not raw or not isinstance(raw, str):
        raise InvalidArchetypeCodeError(f"archetype_code empty/non-string: {raw!r}")

    cleaned = raw.strip().lower()
    if cleaned != raw:
        logger.debug("archetype code whitespace/case fixed: %r → %r", raw, cleaned)

    known = known_codes()
    if cleaned in known:
        return cleaned

    aliased = _ALIASES.get(cleaned)
    if aliased and aliased in known:
        logger.warning(
            "archetype code alias applied: %r → %r (update caller to use canonical)",
            raw, aliased,
        )
        return aliased

    raise InvalidArchetypeCodeError(
        f"archetype_code {raw!r} is not in ArchetypeCode enum"
    )


def assert_known(code: str) -> None:
    """Raise ``InvalidArchetypeCodeError`` when ``code`` isn't in the enum.

    Used from SQLAlchemy ``@validates`` hooks where we can't afford a fuzzy
    alias — invalid codes should bubble up as DB errors early.
    """

    if code not in known_codes():
        raise InvalidArchetypeCodeError(
            f"archetype_code {code!r} not a member of ArchetypeCode enum"
        )


# Known misspellings / legacy names found in existing DB dumps or test fixtures.
# Keep this list short — every entry is a debt item, the real fix is to clean
# up the source.
_ALIASES: dict[str, str] = {
    "skeptc": "skeptic",
    "sceptic": "skeptic",
    "agresive": "aggressive",
    "manipul": "manipulator",
    "passive_agressive": "passive_aggressive",
    "lawyerclient": "lawyer_client",
    "knowitall": "know_it_all",
}
