"""Add emotion and trap tables (Phase 2: TZ-02, TZ-03)

Revision ID: 20260320_002
Revises: 20260320_001
Create Date: 2026-03-20

Tables:
  - emotion_transitions       — допустимые переходы
  - archetype_emotion_configs — Mood Buffer + матрица для архетипа
  - fake_transition_defs      — ложные переходы (8 архетипов)
  - emotion_session_log       — лог эмоций сессии
  - trap_definitions          — 100 ловушек
  - objection_chain_defs      — 30 цепочек возражений
  - chain_steps               — шаги цепочек
  - trap_cascade_defs         — 10 каскадов
  - cascade_levels            — уровни каскадов
  - trap_session_log          — лог ловушек сессии
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "20260320_002"
down_revision = "20260320_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ════════════════════════════════════════════════════════════
    #  EMOTION TABLES (ТЗ-02)
    # ════════════════════════════════════════════════════════════

    op.create_table(
        "emotion_transitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("from_state", sa.String(30), nullable=False, index=True),
        sa.Column("trigger_code", sa.String(50), nullable=False, index=True),
        sa.Column("to_state", sa.String(30), nullable=False),
        sa.Column("base_energy", sa.Float, nullable=False, server_default="0"),
        sa.Column("description", sa.Text, nullable=True),
        sa.UniqueConstraint("from_state", "trigger_code", "to_state",
                            name="uq_emotion_transition"),
    )

    op.create_table(
        "archetype_emotion_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("archetype_code", sa.String(50), nullable=False, index=True),
        sa.Column("initial_state", sa.String(30), nullable=False, server_default="cold"),
        sa.Column("initial_energy", sa.Float, nullable=False, server_default="0"),
        sa.Column("threshold_positive", sa.Float, nullable=False),
        sa.Column("threshold_negative", sa.Float, nullable=False),
        sa.Column("decay_coefficient", sa.Float, nullable=False),
        sa.Column("ema_alpha", sa.Float, nullable=False),
        sa.Column("trigger_modifiers", JSONB, nullable=False, server_default="{}"),
        sa.Column("counter_gated_triggers", JSONB, nullable=False, server_default="[]"),
        sa.Column("transition_matrix", JSONB, nullable=False, server_default="{}"),
        sa.UniqueConstraint("archetype_code", name="uq_archetype_emotion_config"),
        sa.CheckConstraint("threshold_positive > 0", name="ck_threshold_pos"),
        sa.CheckConstraint("threshold_negative < 0", name="ck_threshold_neg"),
        sa.CheckConstraint("decay_coefficient BETWEEN 0.01 AND 1.0", name="ck_decay"),
        sa.CheckConstraint("ema_alpha BETWEEN 0.01 AND 1.0", name="ck_ema"),
    )

    op.create_table(
        "fake_transition_defs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("archetype_code", sa.String(50), nullable=False, index=True),
        sa.Column("real_state", sa.String(30), nullable=False),
        sa.Column("fake_state", sa.String(30), nullable=False),
        sa.Column("real_energy", sa.Float, nullable=False),
        sa.Column("fake_energy", sa.Float, nullable=False),
        sa.Column("activation_condition", sa.String(100), nullable=False),
        sa.Column("reveal_triggers", JSONB, nullable=False),
        sa.Column("duration_sec", sa.Integer, nullable=False, server_default="60"),
        sa.Column("description", sa.Text, nullable=True),
        sa.UniqueConstraint("archetype_code", name="uq_fake_transition_archetype"),
    )

    op.create_table(
        "emotion_session_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("turn_number", sa.Integer, nullable=False),
        sa.Column("from_state", sa.String(30), nullable=False),
        sa.Column("to_state", sa.String(30), nullable=False),
        sa.Column("trigger_code", sa.String(50), nullable=False),
        sa.Column("energy_delta", sa.Float, nullable=False),
        sa.Column("energy_before", sa.Float, nullable=False),
        sa.Column("energy_after", sa.Float, nullable=False),
        sa.Column("energy_smoothed", sa.Float, nullable=False),
        sa.Column("is_fake", sa.Boolean, server_default="false"),
        sa.Column("fake_real_state", sa.String(30), nullable=True),
        sa.Column("mood_buffer_zone", sa.String(20), nullable=False, server_default="neutral"),
        sa.Column("metadata_extra", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index(
        "ix_emotion_log_session_turn",
        "emotion_session_log",
        ["session_id", "turn_number"],
    )

    # ════════════════════════════════════════════════════════════
    #  TRAP TABLES (ТЗ-03)
    # ════════════════════════════════════════════════════════════

    op.create_table(
        "trap_definitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(30), nullable=False, index=True),
        sa.Column("subcategory", sa.String(50), nullable=True),
        sa.Column("difficulty", sa.Integer, nullable=False),
        sa.Column("client_phrase", sa.Text, nullable=False),
        sa.Column("client_phrase_variants", JSONB, nullable=False, server_default="[]"),
        sa.Column("wrong_response_keywords", JSONB, nullable=False, server_default="[]"),
        sa.Column("correct_response_keywords", JSONB, nullable=False, server_default="[]"),
        sa.Column("wrong_response_patterns", JSONB, nullable=False, server_default="[]"),
        sa.Column("correct_response_patterns", JSONB, nullable=False, server_default="[]"),
        sa.Column("semantic_threshold", sa.Float, nullable=False, server_default="0.7"),
        sa.Column("penalty", sa.Integer, nullable=False, server_default="-2"),
        sa.Column("bonus", sa.Integer, nullable=False, server_default="1"),
        sa.Column("correct_response_example", sa.Text, nullable=False),
        sa.Column("wrong_response_example", sa.Text, nullable=False),
        sa.Column("explanation", sa.Text, nullable=False),
        sa.Column("law_reference", sa.Text, nullable=True),
        sa.Column("archetype_codes", JSONB, nullable=False, server_default="[]"),
        sa.Column("profession_codes", JSONB, nullable=False, server_default="[]"),
        sa.Column("emotion_states", JSONB, nullable=False, server_default="[]"),
        sa.Column("triggers_trap_id", sa.String(20), nullable=True),
        sa.Column("blocked_by_trap_id", sa.String(20), nullable=True),
        sa.Column("fell_emotion_trigger", sa.String(50), nullable=True),
        sa.Column("dodged_emotion_trigger", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true", index=True),
        sa.UniqueConstraint("code", name="uq_trap_code"),
        sa.CheckConstraint("difficulty BETWEEN 1 AND 10", name="ck_trap_difficulty"),
        sa.CheckConstraint("penalty <= 0", name="ck_trap_penalty"),
        sa.CheckConstraint("bonus >= 0", name="ck_trap_bonus"),
    )

    op.create_table(
        "objection_chain_defs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("difficulty", sa.Integer, nullable=False),
        sa.Column("archetype_codes", JSONB, nullable=False, server_default="[]"),
        sa.Column("scenario_types", JSONB, nullable=False, server_default="[]"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true", index=True),
        sa.UniqueConstraint("code", name="uq_chain_code"),
        sa.CheckConstraint("difficulty BETWEEN 1 AND 10", name="ck_chain_difficulty"),
    )

    op.create_table(
        "chain_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("chain_id", UUID(as_uuid=True),
                  sa.ForeignKey("objection_chain_defs.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("step_order", sa.Integer, nullable=False),
        sa.Column("client_text", sa.Text, nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("has_trap", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("trap_code", sa.String(20), nullable=True),
        sa.Column("on_good_target", sa.String(20), nullable=False),
        sa.Column("on_bad_target", sa.String(20), nullable=False),
        sa.Column("on_skip_target", sa.String(20), nullable=True),
        sa.UniqueConstraint("chain_id", "step_order", name="uq_chain_step_order"),
    )
    op.create_index("ix_chain_step_chain", "chain_steps", ["chain_id"])

    op.create_table(
        "trap_cascade_defs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("root_trap_code", sa.String(20), nullable=False),
        sa.Column("activation_archetypes", JSONB, nullable=False, server_default="[]"),
        sa.Column("activation_states", JSONB, nullable=False, server_default="[]"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.UniqueConstraint("code", name="uq_cascade_code"),
    )

    op.create_table(
        "cascade_levels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cascade_id", UUID(as_uuid=True),
                  sa.ForeignKey("trap_cascade_defs.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("trap_code", sa.String(20), nullable=False),
        sa.Column("condition", sa.String(20), nullable=False, server_default="fell"),
        sa.Column("next_level", sa.Integer, nullable=True),
        sa.Column("emotion_trigger_on_fell", sa.String(50), nullable=True),
        sa.Column("penalty_multiplier", sa.Float, nullable=False, server_default="1.0"),
        sa.UniqueConstraint("cascade_id", "level", name="uq_cascade_level"),
    )

    op.create_table(
        "trap_session_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("turn_number", sa.Integer, nullable=False),
        sa.Column("trap_code", sa.String(20), nullable=False, index=True),
        sa.Column("chain_code", sa.String(20), nullable=True),
        sa.Column("cascade_code", sa.String(20), nullable=True),
        sa.Column("cascade_level", sa.Integer, nullable=True),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("detection_method", sa.String(20), nullable=False),
        sa.Column("detection_confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("manager_response", sa.Text, nullable=False),
        sa.Column("score_delta", sa.Integer, nullable=False),
        sa.Column("emotion_trigger_fired", sa.String(50), nullable=True),
        sa.Column("metadata_extra", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index(
        "ix_trap_log_session_turn",
        "trap_session_log",
        ["session_id", "turn_number"],
    )


def downgrade() -> None:
    op.drop_table("trap_session_log")
    op.drop_table("cascade_levels")
    op.drop_table("trap_cascade_defs")
    op.drop_table("chain_steps")
    op.drop_table("objection_chain_defs")
    op.drop_table("trap_definitions")
    op.drop_table("emotion_session_log")
    op.drop_table("fake_transition_defs")
    op.drop_table("archetype_emotion_configs")
    op.drop_table("emotion_transitions")
