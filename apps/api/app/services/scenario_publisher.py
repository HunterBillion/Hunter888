"""TZ-3 §9 — scenario publisher.

Single canonical entrypoint that turns a ScenarioTemplate draft into an
immutable ScenarioVersion. Replaces the implicit auto-publish that used
to live in `apps/api/app/api/rop.py:update_scenario` (see TZ-3 §7.3.1
— removal of that call is the load-bearing fix of PR C2).

Atomicity contract
------------------
The publish operation is a single DB transaction with these steps,
in order:

    1. ``SELECT ... FOR UPDATE`` on the template row — serialises
       concurrent publishes for the same template_id.
    2. Compare actual ``draft_revision`` vs ``expected_draft_revision``
       passed by the caller. Mismatch → raise ``PublishConflict`` with
       both numbers — REST handler turns this into 409 (§15.1).
    3. Run ``scenario_validator.validate_template_for_publish``. Any
       error-level issue → raise ``PublishValidationFailed`` with the
       full ValidationReport — handler turns into 422.
    4. Build the snapshot (frozen dict from current template fields).
    5. Compute ``content_hash = sha256_hex(canonical_json(snapshot))``.
    6. Look up the next ``version_number`` (last + 1) and INSERT the
       new ``ScenarioVersion`` row with status='published'.
    7. Mark the previous active published version as ``superseded``
       (per §9.1 step 7).
    8. Update the template: ``current_published_version_id`` to the
       new version, ``draft_revision`` is left unchanged (publish does
       not bump the draft cursor — only ``update_scenario`` does that
       after PR C2).

If any step fails, the whole transaction rolls back. The session row
the caller holds is unchanged; the FE can prompt to retry.

Concurrent publish race (CLAUDE.md §4.1)
----------------------------------------
Two simultaneous ``POST /rop/scenarios/{id}/publish`` requests with the
same ``expected_draft_revision`` will both pass step 2 individually
because they read the row before either writes. Step 1 (FOR UPDATE)
serialises them — the loser waits, then re-reads in its own transaction
and sees the new ``draft_revision`` already at +1, so step 2 raises
PublishConflict on the loser. Test
``test_scenario_publisher.py::test_concurrent_publish_only_one_succeeds``
proves this with ``asyncio.gather``.

Backfill of pre-existing rows
-----------------------------
Templates created before this PR may not have a ``current_published_
version_id`` (verified on prod 2026-04-26: 60 templates, 0 versions —
the migration ``20260423_002`` v1 backfill ran before those templates
existed). The first call to ``publish_template`` for such a template
creates v1 normally — there is no special "rescue" code path. A
companion CLI script `scripts/scenario_backfill_v1.py` does the same
thing in bulk for ops convenience (out of scope for this PR — added
in C2.5 if needed).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scenario import ScenarioTemplate, ScenarioVersion
from app.services.scenario_validator import (
    ValidationReport,
    validate_template_for_publish,
)

logger = logging.getLogger(__name__)


# ── Exceptions (caught by the REST handler) ────────────────────────────────


class PublishConflict(Exception):
    """Raised when ``expected_draft_revision`` doesn't match actual.

    The handler returns 409 with both numbers in the body so FE can
    show "another user edited this — refresh and republish" modal
    (TZ-3 §15.1).
    """

    def __init__(self, expected: int, actual: int):
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Publish conflict: expected_draft_revision={expected}, actual={actual}"
        )


class PublishValidationFailed(Exception):
    """Raised when the validator returns at least one error-level issue.

    Handler returns 422 with the full validation report so FE can
    highlight failing fields.
    """

    def __init__(self, report: ValidationReport):
        self.report = report
        super().__init__(
            f"Publish validation failed: {len(report.issues)} issues"
        )


class TemplateNotFound(Exception):
    """Template id does not exist or is archived."""


# ── Result dataclass ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PublishResult:
    template_id: uuid.UUID
    new_version_id: uuid.UUID
    new_version_number: int
    content_hash: str
    superseded_version_id: uuid.UUID | None
    validation_report: dict[str, Any]


# ── Public entrypoint ──────────────────────────────────────────────────────


async def publish_template(
    db: AsyncSession,
    *,
    template_id: uuid.UUID,
    expected_draft_revision: int | None,
    actor_id: uuid.UUID | None,
    schema_version: int = 1,
) -> PublishResult:
    """Atomically publish ``template_id``.

    ``expected_draft_revision``:
        If provided, must match the current value or the call raises
        ``PublishConflict``. ``None`` means "trust last writer" — used
        only by legacy-client compatibility (logs a warning per §15.1).
    ``actor_id``:
        Recorded on ``ScenarioVersion.created_by`` for audit.
    ``schema_version``:
        Stored on the new version row. Defaults to 1 — bump when the
        validator's rule-set materially changes.
    """
    # Step 1: lock the template row. Concurrent publishes for the same
    # template serialise here; different templates publish in parallel.
    template = (
        await db.execute(
            select(ScenarioTemplate)
            .where(ScenarioTemplate.id == template_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if template is None:
        raise TemplateNotFound(f"ScenarioTemplate {template_id} not found")
    if template.status == "archived":
        raise TemplateNotFound(f"ScenarioTemplate {template_id} is archived")

    # Step 2: optimistic concurrency check.
    actual_revision = int(template.draft_revision)
    if expected_draft_revision is None:
        logger.warning(
            "scenario_publisher.legacy_publish_no_revision",
            extra={"template_id": str(template_id), "actual_revision": actual_revision},
        )
    elif expected_draft_revision != actual_revision:
        raise PublishConflict(expected=expected_draft_revision, actual=actual_revision)

    # Step 3: validate.
    report = validate_template_for_publish(template, schema_version=schema_version)
    if report.has_errors:
        raise PublishValidationFailed(report)

    # Step 4: build the snapshot. Always derive from the locked row so
    # we don't pick up half-written values.
    snapshot = _build_snapshot(template)

    # Step 5: deterministic content hash.
    content_hash = _content_hash(snapshot)

    # Step 6: next version_number.
    last_version_number = (
        await db.execute(
            select(ScenarioVersion.version_number)
            .where(ScenarioVersion.template_id == template_id)
            .order_by(ScenarioVersion.version_number.desc())
            .limit(1)
        )
    ).scalar() or 0
    next_version_number = int(last_version_number) + 1

    new_version = ScenarioVersion(
        id=uuid.uuid4(),
        template_id=template_id,
        version_number=next_version_number,
        status="published",
        snapshot=snapshot,
        created_by=actor_id,
        published_at=datetime.now(UTC),
        schema_version=schema_version,
        content_hash=content_hash,
        validation_report=report.to_jsonb(),
    )
    db.add(new_version)
    await db.flush()  # populates new_version.id

    # Step 7: supersede previous active published version (if any).
    superseded_id: uuid.UUID | None = None
    if template.current_published_version_id is not None:
        previous = await db.get(
            ScenarioVersion, template.current_published_version_id
        )
        if previous is not None and previous.status == "published":
            previous.status = "superseded"
            superseded_id = previous.id

    # Step 8: point the template at the new version. Don't touch
    # draft_revision — publish doesn't bump the editor cursor.
    template.current_published_version_id = new_version.id
    await db.flush()

    logger.info(
        "scenario_publisher.published",
        extra={
            "template_id": str(template_id),
            "new_version_id": str(new_version.id),
            "new_version_number": next_version_number,
            "content_hash": content_hash,
            "superseded": str(superseded_id) if superseded_id else None,
            "actor_id": str(actor_id) if actor_id else None,
        },
    )

    return PublishResult(
        template_id=template_id,
        new_version_id=new_version.id,
        new_version_number=next_version_number,
        content_hash=content_hash,
        superseded_version_id=superseded_id,
        validation_report=report.to_jsonb(),
    )


# ── Snapshot + hash helpers ────────────────────────────────────────────────


# Snapshot keys mirror ``rop.py:_scenario_template_snapshot`` so the
# version row carries everything the runtime needs to reconstitute a
# session WITHOUT touching the mutable template again. If you add a
# template column that the runtime cares about, add it here too — the
# AST guard in PR C5 will enforce that the publisher and the runtime
# resolver stay in sync.
_SNAPSHOT_FIELDS = (
    "code", "name", "description", "group_name",
    "who_calls", "funnel_stage", "prior_contact",
    "initial_emotion", "initial_emotion_variants",
    "client_awareness", "client_motivation",
    "typical_duration_minutes", "max_duration_minutes",
    "typical_reply_count_min", "typical_reply_count_max",
    "target_outcome", "difficulty",
    "archetype_weights", "lead_sources",
    "stages",
    "recommended_chains", "trap_pool_categories",
    "traps_count_min", "traps_count_max", "cascades_count",
    "scoring_modifiers",
    "awareness_prompt", "stage_skip_reactions", "client_prompt_template",
    "is_active",
)


def _build_snapshot(template: ScenarioTemplate) -> dict[str, Any]:
    """Read the TZ-3 §7.3 snapshot fields off a locked template row."""
    return {field: getattr(template, field) for field in _SNAPSHOT_FIELDS}


def _content_hash(snapshot: dict[str, Any]) -> str:
    """SHA256-hex of the canonical JSON encoding of the snapshot.

    ``sort_keys=True`` and ``separators=(",", ":")`` make the encoding
    deterministic — the same snapshot always hashes the same way, so
    duplicate publishes produce the same hash and downstream caches
    stay valid. Matches the ``content_hash`` column shape (64 hex chars).
    """
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json_default(value: Any) -> Any:
    """Coerce ORM/Postgres types JSON can't natively serialise."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value") and not isinstance(value, (str, bytes, bytearray)):
        try:
            return value.value
        except Exception:
            return str(value)
    return str(value)


__all__ = [
    "PublishConflict",
    "PublishResult",
    "PublishValidationFailed",
    "TemplateNotFound",
    "publish_template",
]
