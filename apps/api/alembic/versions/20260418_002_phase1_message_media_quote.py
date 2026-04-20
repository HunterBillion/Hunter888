"""Phase 1.4: Add ``messages.media_url`` and ``messages.quoted_message_id``.

Revision ID: 20260418_002
Revises: 20260418_001
Create Date: 2026-04-18

Rationale:
    Phase 2 (UX) adds two features that both write into the ``messages`` table:
    - ``media_url`` — populated when the AI character "sends" an image via
      the ``generate_image`` MCP tool (nano-banana-2). Frontend renders
      ``<img src={media_url}>`` inside the chat bubble.
    - ``quoted_message_id`` — populated when the manager uses the
      "Ответить" action on an older message; backend resolves the quote and
      injects it into the LLM prompt.

    Both columns are nullable — they remain unset for messages that were sent
    before the Phase 2 UI landed, and the application code treats ``NULL`` as
    "no media / no quote".

CHECK constraint on ``client_profiles.archetype_code`` is DEFERRED to a
separate migration because it requires running the pre-cleanup UPDATE to
remap legacy codes to ``other`` or similar; we don't want that bundled
with a purely additive schema change.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260418_002"
down_revision = "20260418_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # media_url — URL (internal, under /uploads/ai/...) of a generated image.
    # Long enough for reasonable paths but not Text (indexing-friendly if we
    # later decide to search by URL).
    op.add_column(
        "messages",
        sa.Column("media_url", sa.String(length=512), nullable=True),
    )

    # quoted_message_id — self-FK with ON DELETE SET NULL so that removing
    # an older message (shouldn't happen in practice, but defensive) doesn't
    # cascade-delete every quote of it.
    op.add_column(
        "messages",
        sa.Column(
            "quoted_message_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_messages_quoted_message_id",
        source_table="messages",
        referent_table="messages",
        local_cols=["quoted_message_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )
    # Look-up index — the resolve_quote() service queries by this column.
    op.create_index(
        "ix_messages_quoted_message_id",
        "messages",
        ["quoted_message_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_messages_quoted_message_id", table_name="messages")
    op.drop_constraint(
        "fk_messages_quoted_message_id", "messages", type_="foreignkey",
    )
    op.drop_column("messages", "quoted_message_id")
    op.drop_column("messages", "media_url")
