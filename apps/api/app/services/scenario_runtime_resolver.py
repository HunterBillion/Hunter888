"""TZ-3 §10 — scenario runtime resolver.

Single canonical entrypoint for the training runtime to obtain a
scenario snapshot. Returns the immutable snapshot from
``ScenarioVersion`` (the source of truth per §8 invariant 4) and the
``scenario_version_id`` that the caller stamps on
``training_sessions.scenario_version_id`` for historical reproducibility.

Resolution order (§10.1)
------------------------

  1. If ``version_id`` is explicitly supplied — load it directly and
     return its snapshot. Used by replay, retry, and "rerun this exact
     historical session" flows.

  2. If ``template_id`` is supplied — follow
     ``ScenarioTemplate.current_published_version_id`` and load that
     version. This is the normal "start a new session for template X"
     path.

  3. Fallback (legacy compatibility) — if a template exists but has no
     `current_published_version_id` AND no published `ScenarioVersion`
     row, build a snapshot from the live template fields and emit a
     loud WARNING so the operator knows to publish v1 explicitly. This
     fallback exists ONLY because PR C2 verification on prod showed
     60 templates with 0 versions (templates created after migration
     `20260423_002` v1 backfill ran). Once those 60 are published via
     `POST /rop/scenarios/{id}/publish`, this branch is dead code and
     C5 will add an AST-guard preventing its return.

Atomicity
---------

The resolver runs ONE read transaction (no locks, no writes). The
caller decides whether to wrap it in their session's transaction.
The returned snapshot is a frozen dict — mutating it does not
affect the DB row.

Why a separate module
---------------------

Inlining the version-id lookup in `api/training.py` (as today, lines
678-695) means every other start path (WS reconnect, gauntlet replay,
PvP duel) re-implements the same logic and drifts. The resolver is
the SINGLE place where "given a template/version, give me the snapshot
to run with" is answered — see §10.3 of the spec.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scenario import ScenarioTemplate, ScenarioVersion
from app.services.scenario_publisher import _build_snapshot

logger = logging.getLogger(__name__)


# ── Public types ────────────────────────────────────────────────────────────


class ScenarioNotFound(Exception):
    """The supplied template_id / version_id does not exist."""


@dataclass(frozen=True, slots=True)
class ResolvedScenario:
    """Result of a resolution call.

    ``scenario_version_id`` is None ONLY in the legacy-fallback branch
    (template with no published version) — callers should treat that
    as a hint to surface a "publish required" warning to the operator.
    """

    snapshot: dict[str, Any]
    scenario_version_id: uuid.UUID | None
    template_id: uuid.UUID
    version_number: int | None
    source: str  # "explicit_version" | "template_pointer" | "legacy_template"


# ── Public entrypoint ──────────────────────────────────────────────────────


async def resolve_for_runtime(
    db: AsyncSession,
    *,
    template_id: uuid.UUID | None = None,
    version_id: uuid.UUID | None = None,
) -> ResolvedScenario:
    """Resolve a scenario for a training-runtime start.

    Exactly one of ``template_id`` / ``version_id`` should be supplied.
    Both supplied → ``version_id`` wins (the explicit reference is
    treated as an override).

    Raises ``ScenarioNotFound`` if neither path resolves.
    """
    if version_id is None and template_id is None:
        raise ValueError(
            "resolve_for_runtime requires at least one of template_id / version_id"
        )

    # ── 1. Explicit version_id ──
    if version_id is not None:
        version = await db.get(ScenarioVersion, version_id)
        if version is None:
            raise ScenarioNotFound(f"ScenarioVersion {version_id} not found")
        return ResolvedScenario(
            snapshot=_freeze(version.snapshot),
            scenario_version_id=version.id,
            template_id=version.template_id,
            version_number=int(version.version_number),
            source="explicit_version",
        )

    # ── 2. Template pointer ──
    template = await db.get(ScenarioTemplate, template_id)
    if template is None:
        raise ScenarioNotFound(f"ScenarioTemplate {template_id} not found")

    if template.current_published_version_id is not None:
        version = await db.get(
            ScenarioVersion, template.current_published_version_id
        )
        if version is not None and version.status in ("published", "superseded"):
            # Even superseded counts here — a freshly-superseded version
            # is still a valid runtime artifact for sessions that started
            # before the new publish landed (the cutover happens at start
            # time, not mid-session).
            return ResolvedScenario(
                snapshot=_freeze(version.snapshot),
                scenario_version_id=version.id,
                template_id=template.id,
                version_number=int(version.version_number),
                source="template_pointer",
            )

    # Pointer is NULL or stale — try the latest published version directly.
    latest = (
        await db.execute(
            select(ScenarioVersion)
            .where(
                ScenarioVersion.template_id == template.id,
                ScenarioVersion.status == "published",
            )
            .order_by(ScenarioVersion.version_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is not None:
        # Pointer drift: template has a published version but pointer is
        # NULL. Log so we can detect this in the wild — the publisher
        # should have set the pointer.
        logger.warning(
            "scenario_runtime_resolver.pointer_drift",
            extra={
                "template_id": str(template.id),
                "found_version_id": str(latest.id),
                "found_version_number": latest.version_number,
            },
        )
        return ResolvedScenario(
            snapshot=_freeze(latest.snapshot),
            scenario_version_id=latest.id,
            template_id=template.id,
            version_number=int(latest.version_number),
            source="template_pointer",
        )

    # ── 3. Legacy fallback — no version exists ──
    # 60-template-no-versions reality on prod (verified 2026-04-26).
    # Build an ad-hoc snapshot from the live template so old sessions
    # don't 500. The session is stamped with scenario_version_id=NULL
    # so it's clearly distinguishable from properly-published runs.
    logger.warning(
        "scenario_runtime_resolver.legacy_template_fallback",
        extra={
            "template_id": str(template.id),
            "code": template.code,
            "remediation": (
                "POST /rop/scenarios/{id}/publish to mint v1 — fallback "
                "is a backstop, not the contract."
            ),
        },
    )
    return ResolvedScenario(
        snapshot=_freeze(_build_snapshot(template)),
        scenario_version_id=None,  # signals "no published version"
        template_id=template.id,
        version_number=None,
        source="legacy_template",
    )


# ── Helpers ─────────────────────────────────────────────────────────────────


def _freeze(snapshot: Any) -> dict[str, Any]:
    """Return a shallow-copied dict so callers can mutate freely without
    touching the SQLAlchemy attribute (Postgres would happily flag the
    JSONB as dirty and write it back on commit otherwise)."""
    if not isinstance(snapshot, dict):
        return {}
    return dict(snapshot)


__all__ = [
    "ResolvedScenario",
    "ScenarioNotFound",
    "resolve_for_runtime",
]
