"""Phase A — Arena schema bundle.

Revision ID: 20260420_003
Revises: 20260420_002
Create Date: 2026-04-20

Single migration covering all six schema deltas flagged by the deep audit
of Phase A (2026-04-20):

  1. `rag_chunk_links` junction table (cross-article relations for enrichment S2).
  2. `legal_documents.qa_generated_at` + `legal_documents.summary`
     (RAG enrichment S3/S5 readiness).
  3. `training_sessions.difficulty_params_snapshot` JSONB — freezes the
     DifficultyParams row used at session-start so replays/reports stay
     deterministic even when we tune the table.
  4. `pvp_duels` post-match analytics fields:
       • `summary TEXT`       — 2-3 sentence judge summary
       • `breakdown JSONB`    — {key_moments, flags, legal_details, ...}
       • `turning_point INT`  — message index where momentum shifted
     (Data is already computed by services/pvp_judge.py — this just gives
     it a persistent home so we can stop re-parsing round_*_data on load.)
  5. `quiz_participants.streak_counter` + `xp_earned` — progression bookkeeping.
  6. `lifelines_usage_log` — persistent audit of every hint/skip/fifty consume
     so we can flag anti-cheat patterns and build "where hints helped" analytics.
  7. Performance indexes on pvp_duels(status, created_at) and
     pvp_duels(tournament_id, created_at) — matchmaking and tournament
     history queries degrade without these as volume grows.

All columns are NULLABLE / have defaults so this is safe to apply on a
production database with live traffic. Down-migration drops everything.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers
revision = "20260420_003"
down_revision = "20260420_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. rag_chunk_links ──────────────────────────────────────────────
    op.create_table(
        "rag_chunk_links",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        # Phase A fix (2026-04-20): legal_knowledge_chunks.id is UUID, not
        # Integer — mismatch caught by live `alembic upgrade`.
        sa.Column(
            "a_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_knowledge_chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "b_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_knowledge_chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation", sa.String(32), nullable=False),
        sa.Column(
            "weight",
            sa.Float,
            nullable=False,
            server_default="1.0",
            comment="0..1 confidence score from the enrichment pipeline",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("a_id", "b_id", "relation", name="uq_rag_chunk_links_edge"),
    )
    op.create_index("ix_rag_chunk_links_a", "rag_chunk_links", ["a_id", "relation"])
    op.create_index("ix_rag_chunk_links_b", "rag_chunk_links", ["b_id", "relation"])

    # ── 2. legal_documents.qa_generated_at + summary ────────────────────
    # NOTE: existing rows stay NULL; seeding is the job of
    # services/rag/enrichment/{qa_generator,summarization}.py.
    op.add_column(
        "legal_document",
        sa.Column("qa_generated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "legal_document",
        sa.Column("summary", sa.Text, nullable=True),
    )

    # ── 3. training_sessions.difficulty_params_snapshot ─────────────────
    op.add_column(
        "training_sessions",
        sa.Column(
            "difficulty_params_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Snapshot of DifficultyParams at session-start — freezes "
                "temperature, threshold, OCEAN shift so replays stay reproducible."
            ),
        ),
    )

    # ── 4. pvp_duels analytics fields ───────────────────────────────────
    op.add_column(
        "pvp_duels",
        sa.Column("summary", sa.Text, nullable=True),
    )
    op.add_column(
        "pvp_duels",
        sa.Column(
            "breakdown",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "pvp_duels",
        sa.Column("turning_point", sa.Integer, nullable=True),
    )

    # ── 5. quiz_participants.streak_counter + xp_earned ─────────────────
    op.add_column(
        "quiz_participants",
        sa.Column(
            "streak_counter",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "quiz_participants",
        sa.Column(
            "xp_earned",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
    )

    # ── 6. lifelines_usage_log ──────────────────────────────────────────
    op.create_table(
        "lifelines_usage_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kind",
            sa.String(16),
            nullable=False,
            comment="hint | skip | fifty",
        ),
        sa.Column(
            "mode",
            sa.String(16),
            nullable=False,
            comment="arena | duel | rapid | pve | tournament",
        ),
        sa.Column(
            "remaining_after",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Arbitrary payload: article returned, question_text, etc.",
        ),
        sa.Column(
            "consumed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_lifelines_usage_user_time",
        "lifelines_usage_log",
        ["user_id", "consumed_at"],
    )
    op.create_index(
        "ix_lifelines_usage_session",
        "lifelines_usage_log",
        ["session_id"],
    )

    # ── 7. pvp_duels performance indexes ────────────────────────────────
    # Only (status, created_at DESC) — a tournament_id column was planned
    # in the audit but never made it into the PvPDuel model (tournaments
    # use TournamentBracketMatch → PvPDuel via a separate bracket_match
    # table). Revisit when the bracket join becomes a real bottleneck.
    op.create_index(
        "ix_pvp_duels_status_created",
        "pvp_duels",
        ["status", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    # Drop in reverse order of create
    op.drop_index("ix_pvp_duels_status_created", table_name="pvp_duels")

    op.drop_index("ix_lifelines_usage_session", table_name="lifelines_usage_log")
    op.drop_index("ix_lifelines_usage_user_time", table_name="lifelines_usage_log")
    op.drop_table("lifelines_usage_log")

    op.drop_column("quiz_participants", "xp_earned")
    op.drop_column("quiz_participants", "streak_counter")

    op.drop_column("pvp_duels", "turning_point")
    op.drop_column("pvp_duels", "breakdown")
    op.drop_column("pvp_duels", "summary")

    op.drop_column("training_sessions", "difficulty_params_snapshot")

    op.drop_column("legal_document", "summary")
    op.drop_column("legal_document", "qa_generated_at")

    op.drop_index("ix_rag_chunk_links_b", table_name="rag_chunk_links")
    op.drop_index("ix_rag_chunk_links_a", table_name="rag_chunk_links")
    op.drop_table("rag_chunk_links")
