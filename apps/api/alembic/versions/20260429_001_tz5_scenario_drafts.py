"""TZ-5 — input funnel: scenario_drafts table + pipeline state extension

Revision ID: 20260429_001
Revises: 20260427_004
Create Date: 2026-04-29

Background
----------

TZ-5 (docs/TZ-5_input_funnel_parser.md) lets ROP/admin upload existing
team materials (.docx/.pdf/.txt/.md/.pptx) and parses them into a
``ScenarioDraft`` -- a pre-filled card the editor can review and turn
into a normal TZ-3 ``ScenarioTemplate`` + ``ScenarioVersion``.

This migration is the foundation:

1. Extends the ``ck_attachments_classification_status`` CHECK to allow
   two new lifecycle values that gate the post-classification
   extraction branch:

      classified (document_type=training_material)
        -> scenario_draft_extracting   (worker picked it up)
        -> scenario_draft_ready        (draft persisted, ROP can edit)

   Note: ``training_material`` is a value of ``Attachment.document_type``
   (free-string column), not a separate state machine. We do not need a
   CHECK on document_type itself -- the existing infer_document_type
   helper produces the canonical token, and the AST guard
   (test_attachment_invariants.py) gates writes through the pipeline.

2. Creates ``scenario_drafts`` -- the holding table for the extractor's
   structured output. One row per attachment; FK to attachments enforces
   single-source-of-truth on the parsed material. ``scenario_template_id``
   is set ONLY after ROP clicks "Create scenario" and the draft is
   converted into a TZ-3 template + initial draft version.

Re-runnability
--------------

* The CHECK swap is "drop if exists -> recreate" with the expanded set;
  the pre-flight UPDATE shape (none here, since the new tokens are
  greenfield) is unnecessary.
* ``scenario_drafts`` creation is idempotent via ``IF NOT EXISTS`` on
  inspector check.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260429_001"
down_revision: Union[str, Sequence[str], None] = "20260427_004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CK_CLASSIFICATION_STATUS = "ck_attachments_classification_status"

# Pre-TZ-5 set (B1 migration 20260427_004)
CLASSIFICATION_VALUES_LEGACY = (
    "not_required",
    "classification_pending",
    "classified",
    "classification_failed",
)
# Post-TZ-5 set: two new values for the training_material extraction branch
CLASSIFICATION_VALUES_TZ5 = (
    *CLASSIFICATION_VALUES_LEGACY,
    "scenario_draft_extracting",
    "scenario_draft_ready",
)


def _constraint_exists(name: str) -> bool:
    bind = op.get_bind()
    return (
        bind.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :name LIMIT 1"),
            {"name": name},
        ).scalar()
        is not None
    )


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return (
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_name = :name "
                "LIMIT 1"
            ),
            {"name": name},
        ).scalar()
        is not None
    )


def upgrade() -> None:
    # ── 1. Extend classification_status CHECK ──────────────────────────
    if _constraint_exists(CK_CLASSIFICATION_STATUS):
        op.drop_constraint(
            CK_CLASSIFICATION_STATUS, "attachments", type_="check"
        )
    op.create_check_constraint(
        CK_CLASSIFICATION_STATUS,
        "attachments",
        f"classification_status IN {CLASSIFICATION_VALUES_TZ5}",
    )

    # ── 1b. Allow client_id NULL for training_material rows ────────────
    #
    # Training materials uploaded by ROP belong to the team, not to a
    # specific CRM client. The existing ``client_id NOT NULL`` constraint
    # was modelled around the assumption that every attachment is a
    # client-side document (passport, contract, screenshot). Relaxing
    # this for training material rows is cleaner than introducing a
    # sentinel "_training_materials" pseudo-client (which would leak
    # into ROP client lists, NBA queries, etc.).
    #
    # Existing readers (api/clients.py:643, next_best_action.py:186)
    # already filter ``Attachment.client_id == X`` so a NULL row simply
    # never appears in their results -- exactly the desired behaviour.
    op.alter_column(
        "attachments",
        "client_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    # ── 2. Create scenario_drafts table ────────────────────────────────
    if not _table_exists("scenario_drafts"):
        op.create_table(
            "scenario_drafts",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "attachment_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("attachments.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column(
                "created_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            # Resulting template (set after ROP clicks "Create scenario").
            # Nullable until then; UNIQUE so a single draft can produce
            # only one template (re-extraction creates a new draft row).
            sa.Column(
                "scenario_template_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("scenario_templates.id", ondelete="SET NULL"),
                nullable=True,
                unique=True,
            ),
            # Lifecycle: extracting -> ready -> edited -> converted | discarded
            sa.Column(
                "status",
                sa.String(length=30),
                nullable=False,
                server_default="extracting",
            ),
            # Extracted structure (full ScenarioDraft dataclass payload).
            # JSONB so future schema growth doesn't need migrations; readers
            # validate against the dataclass at load time.
            sa.Column(
                "extracted",
                postgresql.JSONB,
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            # 0.0..1.0 -- below 0.6 the UI hides the structured draft and
            # shows raw extracted text only (TZ-5 §4 invariant).
            sa.Column(
                "confidence",
                sa.Float(),
                nullable=False,
                server_default="0.0",
            ),
            # Free-text from the source after PII scrubbing (152-FZ §4).
            # Used for the "raw text" fallback view and for quote validation.
            sa.Column(
                "source_text",
                sa.Text(),
                nullable=True,
            ),
            # Reason why extraction failed (LLM error, oversized, parser
            # exception). Populated only when status='failed'.
            sa.Column(
                "error_message",
                sa.Text(),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.CheckConstraint(
                "status IN ('extracting', 'ready', 'edited', "
                "'converted', 'discarded', 'failed')",
                name="ck_scenario_drafts_status",
            ),
            sa.CheckConstraint(
                "confidence >= 0.0 AND confidence <= 1.0",
                name="ck_scenario_drafts_confidence_range",
            ),
        )
        op.create_index(
            "ix_scenario_drafts_status",
            "scenario_drafts",
            ["status"],
        )
        op.create_index(
            "ix_scenario_drafts_created_by",
            "scenario_drafts",
            ["created_by"],
        )


def downgrade() -> None:
    # ── reverse 2: drop scenario_drafts ────────────────────────────────
    if _table_exists("scenario_drafts"):
        op.drop_index("ix_scenario_drafts_created_by", table_name="scenario_drafts")
        op.drop_index("ix_scenario_drafts_status", table_name="scenario_drafts")
        op.drop_table("scenario_drafts")

    # ── reverse 1b: re-tighten client_id to NOT NULL ───────────────────
    # Audit fix (PR-1.1): the original implementation silently DELETE'd
    # every training_material attachment so the ALTER could re-add NOT
    # NULL. That cascades through `ondelete=CASCADE` on
    # `scenario_drafts.attachment_id` and wipes every imported draft.
    # Refuse to run unless the operator explicitly opts in via env var.
    # Mirrors project rule §2 ("rollback via revert PR + git pull, not
    # destructive in-place SQL on prod").
    import os as _os

    bind = op.get_bind()
    orphan_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM attachments "
            "WHERE client_id IS NULL "
            "  AND document_type = 'training_material'"
        )
    ).scalar_one()
    if orphan_count and int(orphan_count) > 0:
        if _os.getenv("ALLOW_TZ5_DOWNGRADE_DATA_LOSS") != "1":
            raise RuntimeError(
                f"Refusing to downgrade TZ-5: {orphan_count} training_material "
                "attachments would be DELETED (cascading to scenario_drafts). "
                "Set ALLOW_TZ5_DOWNGRADE_DATA_LOSS=1 to confirm data loss, "
                "or revert the feature via a forward migration instead."
            )
        bind.execute(
            sa.text(
                "DELETE FROM attachments "
                "WHERE client_id IS NULL "
                "  AND document_type = 'training_material'"
            )
        )
    op.alter_column(
        "attachments",
        "client_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    # ── reverse 1: shrink CHECK back to the B1 set ─────────────────────
    if _constraint_exists(CK_CLASSIFICATION_STATUS):
        op.drop_constraint(
            CK_CLASSIFICATION_STATUS, "attachments", type_="check"
        )
    bind = op.get_bind()
    # Defensive: if any rows already use the new tokens, push them back to
    # 'classified' so the narrower CHECK doesn't reject the ALTER.
    bind.execute(
        sa.text(
            """
            UPDATE attachments
            SET classification_status = 'classified'
            WHERE classification_status IN
                ('scenario_draft_extracting', 'scenario_draft_ready')
            """
        )
    )
    op.create_check_constraint(
        CK_CLASSIFICATION_STATUS,
        "attachments",
        f"classification_status IN {CLASSIFICATION_VALUES_LEGACY}",
    )
