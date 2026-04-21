"""Create missing tables that exist in ORM models but lack migrations.

Tables: call_records, session_reports, custom_characters, voice_profiles,
emotion_voice_modifiers, pause_configs, couple_voice_profiles,
outbox_events, scenario_templates, user_fingerprints.

Revision ID: 20260402_004a
Revises: 20260402_004
Create Date: 2026-04-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "20260402_004a"
down_revision: Union[str, None] = "20260402_004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=:t)"
    ), {"t": name})
    return result.scalar()


def _create_if_missing(name: str, *columns, **kw):
    if _table_exists(name):
        return
    op.create_table(name, *columns, **kw)


def upgrade() -> None:
    _uuid = UUID(as_uuid=True)
    _now = sa.text("now()")
    _gen_uuid = sa.text("gen_random_uuid()")

    # ── voice_profiles ──
    _create_if_missing(
        "voice_profiles",
        sa.Column("id", _uuid, primary_key=True, server_default=_gen_uuid),
        sa.Column("voice_id", sa.String(100), nullable=False, unique=True),
        sa.Column("voice_name", sa.String(200), nullable=False),
        sa.Column("voice_code", sa.String(100), nullable=False, unique=True),
        sa.Column("gender", sa.String(20), nullable=False),
        sa.Column("base_stability", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("base_similarity_boost", sa.Float, nullable=False, server_default="0.75"),
        sa.Column("base_style", sa.Float, nullable=False, server_default="0.3"),
        sa.Column("base_speed", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("archetype_codes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("age_range", sa.String(20), nullable=False, server_default="'middle'"),
        sa.Column("voice_type", sa.String(20), nullable=False, server_default="'neutral'"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now),
    )

    # ── emotion_voice_modifiers ──
    _create_if_missing(
        "emotion_voice_modifiers",
        sa.Column("id", _uuid, primary_key=True, server_default=_gen_uuid),
        sa.Column("emotion_state", sa.String(50), nullable=False, unique=True),
        sa.Column("stability_delta", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("similarity_delta", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("style_delta", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("speed_delta", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("instant_transition", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now),
    )

    # ── pause_configs ──
    _create_if_missing(
        "pause_configs",
        sa.Column("id", _uuid, primary_key=True, server_default=_gen_uuid),
        sa.Column("emotion_state", sa.String(50), nullable=False, unique=True),
        sa.Column("after_period_ms", sa.Integer, nullable=False, server_default="300"),
        sa.Column("before_conjunction_ms", sa.Integer, nullable=False, server_default="200"),
        sa.Column("after_comma_ms", sa.Integer, nullable=False, server_default="150"),
        sa.Column("hesitation_probability", sa.Float, nullable=False, server_default="0.1"),
        sa.Column("hesitation_pool", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("max_hesitations_per_phrase", sa.Integer, nullable=False, server_default="1"),
        sa.Column("dramatic_pause_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("breath_probability", sa.Float, nullable=False, server_default="0.1"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now),
    )

    # ── couple_voice_profiles ──
    _create_if_missing(
        "couple_voice_profiles",
        sa.Column("id", _uuid, primary_key=True, server_default=_gen_uuid),
        sa.Column("session_id", sa.String(100), nullable=False, unique=True),
        sa.Column("partner_a_voice_id", sa.String(100), nullable=False),
        sa.Column("partner_b_voice_id", sa.String(100), nullable=False),
        sa.Column("partner_a_params", JSONB, nullable=False),
        sa.Column("partner_b_params", JSONB, nullable=False),
        sa.Column("dynamics_type", sa.String(50), nullable=False, server_default="'couple_agree'"),
        sa.Column("interrupt_probability", sa.Float, server_default="0.2"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now),
    )

    # ── scenario_templates ──
    _create_if_missing(
        "scenario_templates",
        sa.Column("id", _uuid, primary_key=True, server_default=_gen_uuid),
        sa.Column("code", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("group_name", sa.String(100), nullable=False, server_default="'custom'"),
        sa.Column("who_calls", sa.String(20), nullable=False, server_default="'manager'"),
        sa.Column("funnel_stage", sa.String(50), nullable=False, server_default="'lead'"),
        sa.Column("prior_contact", sa.Boolean, server_default="false"),
        sa.Column("initial_emotion", sa.String(50), nullable=False, server_default="'cold'"),
        sa.Column("initial_emotion_variants", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("client_awareness", sa.String(20), nullable=False, server_default="'zero'"),
        sa.Column("client_motivation", sa.String(20), nullable=False, server_default="'none'"),
        sa.Column("typical_duration_minutes", sa.Integer, server_default="8"),
        sa.Column("max_duration_minutes", sa.Integer, server_default="15"),
        sa.Column("typical_reply_count_min", sa.Integer, server_default="6"),
        sa.Column("typical_reply_count_max", sa.Integer, server_default="15"),
        sa.Column("target_outcome", sa.String(50), nullable=False, server_default="'meeting'"),
        sa.Column("difficulty", sa.Integer, server_default="5"),
        sa.Column("archetype_weights", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("lead_sources", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("stages", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("recommended_chains", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("trap_pool_categories", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("traps_count_min", sa.Integer, server_default="1"),
        sa.Column("traps_count_max", sa.Integer, server_default="2"),
        sa.Column("cascades_count", sa.Integer, server_default="0"),
        sa.Column("scoring_modifiers", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("awareness_prompt", sa.Text, nullable=True),
        sa.Column("stage_skip_reactions", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("client_prompt_template", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now),
    )

    # ── custom_characters ──
    _create_if_missing(
        "custom_characters",
        sa.Column("id", _uuid, primary_key=True, server_default=_gen_uuid),
        sa.Column("user_id", _uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("archetype", sa.String(50), nullable=False),
        sa.Column("profession", sa.String(50), nullable=False),
        sa.Column("lead_source", sa.String(50), nullable=False),
        sa.Column("difficulty", sa.Integer, nullable=False, server_default="5"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=_now, nullable=False),
        sa.Column("family_preset", sa.String(30), nullable=True),
        sa.Column("creditors_preset", sa.String(20), nullable=True),
        sa.Column("debt_stage", sa.String(30), nullable=True),
        sa.Column("debt_range", sa.String(30), nullable=True),
        sa.Column("emotion_preset", sa.String(30), nullable=True),
        sa.Column("bg_noise", sa.String(20), nullable=True),
        sa.Column("time_of_day", sa.String(20), nullable=True),
        sa.Column("client_fatigue", sa.String(20), nullable=True),
        sa.Column("cached_dossier", sa.Text, nullable=True),
        sa.Column("play_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("best_score", sa.Integer, nullable=True),
        sa.Column("avg_score", sa.Integer, nullable=True),
        sa.Column("last_played_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
        sa.Column("is_shared", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("share_code", sa.String(20), nullable=True, unique=True),
    )

    # ── call_records ──
    _create_if_missing(
        "call_records",
        sa.Column("id", _uuid, primary_key=True, server_default=_gen_uuid),
        sa.Column("story_id", _uuid, sa.ForeignKey("client_stories.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("session_id", _uuid, sa.ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("call_number", sa.Integer, nullable=False),
        sa.Column("pre_call_brief", sa.Text, nullable=True),
        sa.Column("applied_events", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("simulated_days_gap", sa.Integer, server_default="1"),
        sa.Column("starting_emotion", sa.String(50), server_default="'cold'"),
        sa.Column("starting_trust", sa.Integer, server_default="3"),
        sa.Column("outcome", sa.String(100), nullable=True),
        sa.Column("emotion_trajectory", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("active_factors", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("system_prompt_tokens", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now),
    )

    # ── session_reports ──
    _create_if_missing(
        "session_reports",
        sa.Column("id", _uuid, primary_key=True, server_default=_gen_uuid),
        sa.Column("story_id", _uuid, sa.ForeignKey("client_stories.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("session_id", _uuid, sa.ForeignKey("training_sessions.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("call_number", sa.Integer, nullable=True),
        sa.Column("report_type", sa.String(50), nullable=False),
        sa.Column("content", JSONB, nullable=False),
        sa.Column("score_total", sa.Float, nullable=True),
        sa.Column("generated_by_model", sa.String(100), nullable=True),
        sa.Column("generation_latency_ms", sa.Integer, nullable=True),
        sa.Column("is_final", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now),
    )

    # ── user_fingerprints ──
    _create_if_missing(
        "user_fingerprints",
        sa.Column("id", _uuid, primary_key=True, server_default=_gen_uuid),
        sa.Column("user_id", _uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("ip_address", sa.String(45), nullable=True, index=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("ua_hash", sa.String(32), nullable=True, index=True),
        sa.Column("browser_fingerprint", sa.String(64), nullable=True, index=True),
        sa.Column("session_id", _uuid, nullable=True),
        sa.Column("event_type", sa.String(30), server_default="'login'"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now),
    )

    # ── outbox_events ──
    _create_if_missing(
        "outbox_events",
        sa.Column("id", _uuid, primary_key=True, server_default=_gen_uuid),
        sa.Column("event_type", sa.String(100), nullable=False, index=True),
        sa.Column("user_id", _uuid, nullable=False, index=True),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(20), nullable=False, server_default="'pending'", index=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    if _table_exists("outbox_events"):
        op.get_bind().execute(sa.text(
            'CREATE INDEX IF NOT EXISTS "idx_outbox_pending_retry" '
            'ON "outbox_events" ("status", "next_retry_at")'
        ))


def downgrade() -> None:
    for t in [
        "outbox_events", "user_fingerprints", "session_reports",
        "call_records", "custom_characters", "scenario_templates",
        "couple_voice_profiles", "pause_configs",
        "emotion_voice_modifiers", "voice_profiles",
    ]:
        op.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE')
