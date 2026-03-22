"""
ТЗ-06: Создание таблиц адаптивной сложности и прогрессии.

Revision ID: 20260320_001
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260320_001"
down_revision = "c863e49a439a"  # After tournament tables — parallel branch for progress/emotion
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── level_definitions (справочник уровней) ──
    op.create_table(
        "level_definitions",
        sa.Column("level", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("xp_required", sa.Integer, nullable=False),
        sa.Column("max_difficulty", sa.Integer, nullable=False),
        sa.Column("unlocked_archetypes", JSONB, nullable=False, server_default="[]"),
        sa.Column("unlocked_scenarios", JSONB, nullable=False, server_default="[]"),
        sa.Column("unlocked_mechanics", JSONB, nullable=False, server_default="[]"),
        sa.CheckConstraint("level BETWEEN 1 AND 20", name="ck_level_def_range"),
        sa.CheckConstraint("xp_required >= 0", name="ck_xp_required_nonneg"),
        sa.CheckConstraint("max_difficulty BETWEEN 1 AND 10", name="ck_max_diff_range"),
    )

    # ── achievement_definitions (справочник достижений) ──
    op.create_table(
        "achievement_definitions",
        sa.Column("code", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("condition", JSONB, nullable=False),
        sa.Column("xp_bonus", sa.Integer, nullable=False),
        sa.Column("rarity", sa.String(20), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.CheckConstraint("xp_bonus >= 0", name="ck_achdef_xp_nonneg"),
        sa.CheckConstraint(
            "rarity IN ('common','uncommon','rare','epic','legendary')",
            name="ck_achdef_rarity",
        ),
        sa.CheckConstraint(
            "category IN ('results','skills','challenges','progression')",
            name="ck_achdef_category",
        ),
    )

    # ── manager_progress ──
    op.create_table(
        "manager_progress",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        # Прогрессия
        sa.Column("current_level", sa.Integer, nullable=False, server_default="1"),
        sa.Column("current_xp", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_xp", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_sessions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_hours", sa.Numeric(8, 2), nullable=False, server_default="0.0"),
        # 6 навыков
        sa.Column("skill_empathy", sa.Integer, nullable=False, server_default="50"),
        sa.Column("skill_knowledge", sa.Integer, nullable=False, server_default="50"),
        sa.Column("skill_objection_handling", sa.Integer, nullable=False, server_default="50"),
        sa.Column("skill_stress_resistance", sa.Integer, nullable=False, server_default="50"),
        sa.Column("skill_closing", sa.Integer, nullable=False, server_default="50"),
        sa.Column("skill_qualification", sa.Integer, nullable=False, server_default="50"),
        # JSONB поля
        sa.Column("unlocked_archetypes", JSONB, nullable=False,
                  server_default='["skeptic","anxious","passive","pragmatic","desperate"]'),
        sa.Column("unlocked_scenarios", JSONB, nullable=False,
                  server_default='["in_website","cold_ad","cold_referral"]'),
        sa.Column("weak_points", JSONB, nullable=False, server_default="[]"),
        sa.Column("focus_recommendation", sa.Text, nullable=True),
        # Streak
        sa.Column("current_deal_streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("best_deal_streak", sa.Integer, nullable=False, server_default="0"),
        # Калибровка
        sa.Column("calibration_complete", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("calibration_sessions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("skill_confidence", sa.String(20), nullable=False, server_default="'low'"),
        # Метаданные
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        # Constraints
        sa.CheckConstraint("current_level BETWEEN 1 AND 20", name="ck_level_range"),
        sa.CheckConstraint("current_xp >= 0", name="ck_xp_nonneg"),
        sa.CheckConstraint("total_xp >= 0", name="ck_total_xp_nonneg"),
        sa.CheckConstraint("skill_empathy BETWEEN 0 AND 100", name="ck_skill_empathy"),
        sa.CheckConstraint("skill_knowledge BETWEEN 0 AND 100", name="ck_skill_knowledge"),
        sa.CheckConstraint("skill_objection_handling BETWEEN 0 AND 100", name="ck_skill_obj"),
        sa.CheckConstraint("skill_stress_resistance BETWEEN 0 AND 100", name="ck_skill_stress"),
        sa.CheckConstraint("skill_closing BETWEEN 0 AND 100", name="ck_skill_closing"),
        sa.CheckConstraint("skill_qualification BETWEEN 0 AND 100", name="ck_skill_qual"),
    )
    op.create_index("idx_manager_progress_level", "manager_progress", ["current_level"])

    # ── session_history ──
    op.create_table(
        "session_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("scenario_code", sa.String(50), nullable=False),
        sa.Column("archetype_code", sa.String(50), nullable=False),
        sa.Column("difficulty", sa.Integer, nullable=False),
        sa.Column("duration_seconds", sa.Integer, nullable=False),
        sa.Column("score_total", sa.Integer, nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("score_breakdown", JSONB, nullable=False, server_default="{}"),
        sa.Column("emotion_peak", sa.String(30), nullable=False),
        sa.Column("traps_fell", sa.Integer, nullable=False, server_default="0"),
        sa.Column("traps_dodged", sa.Integer, nullable=False, server_default="0"),
        sa.Column("chain_completed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("max_good_streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_bad_streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("final_difficulty_modifier", sa.Integer, nullable=False, server_default="0"),
        sa.Column("had_comeback", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("mercy_activated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("xp_earned", sa.Integer, nullable=False, server_default="0"),
        sa.Column("xp_breakdown", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        # Constraints
        sa.CheckConstraint("difficulty BETWEEN 1 AND 10", name="ck_difficulty_range"),
        sa.CheckConstraint("score_total BETWEEN 0 AND 100", name="ck_score_range"),
        sa.CheckConstraint("outcome IN ('deal','callback','hangup','hostile','timeout')", name="ck_outcome_values"),
        sa.CheckConstraint("duration_seconds > 0", name="ck_duration_pos"),
        sa.CheckConstraint("traps_fell >= 0", name="ck_traps_fell_nonneg"),
        sa.CheckConstraint("traps_dodged >= 0", name="ck_traps_dodged_nonneg"),
        sa.CheckConstraint("xp_earned >= 0", name="ck_xp_earned_nonneg"),
    )
    op.create_index("idx_session_history_user_date", "session_history", ["user_id", sa.text("created_at DESC")])
    op.create_index("idx_session_history_scenario", "session_history", ["scenario_code", sa.text("created_at DESC")])
    op.create_index("idx_session_history_archetype", "session_history", ["archetype_code", sa.text("created_at DESC")])
    op.create_index("idx_session_history_outcome", "session_history", ["user_id", "outcome"])
    op.create_index("idx_session_history_score", "session_history", ["user_id", "score_total"])

    # ── earned_achievements ──
    op.create_table(
        "earned_achievements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("achievement_code", sa.String(50), nullable=False),
        sa.Column("achievement_name", sa.String(100), nullable=False),
        sa.Column("achievement_description", sa.Text, nullable=False),
        sa.Column("rarity", sa.String(20), nullable=False),
        sa.Column("xp_bonus", sa.Integer, nullable=False, server_default="0"),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("training_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "achievement_code", name="uq_achievement_user_code"),
        sa.CheckConstraint("xp_bonus >= 0", name="ck_achievement_xp_nonneg"),
        sa.CheckConstraint("rarity IN ('common','uncommon','rare','epic','legendary')", name="ck_rarity_values"),
        sa.CheckConstraint("category IN ('results','skills','challenges','progression')", name="ck_category_values"),
    )
    op.create_index("idx_achievements_user", "earned_achievements", ["user_id", sa.text("unlocked_at DESC")])
    op.create_index("idx_achievements_rarity", "earned_achievements", ["rarity"])

    # ── progress_leaderboard_snapshots ──
    op.create_table(
        "progress_leaderboard_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("board_type", sa.String(20), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entries", JSONB, nullable=False, server_default="[]"),
        sa.Column("total_participants", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("board_type IN ('daily','weekly','monthly','all_time')", name="ck_progress_board_type"),
        sa.UniqueConstraint("board_type", "period_start", "period_end", name="uq_progress_leaderboard_period"),
    )
    op.create_index("idx_progress_leaderboard_type_date", "progress_leaderboard_snapshots", ["board_type", sa.text("period_end DESC")])

    # ── weekly_reports ──
    op.create_table(
        "weekly_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("week_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sessions_completed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_time_minutes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("average_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("best_score", sa.Integer, nullable=True),
        sa.Column("worst_score", sa.Integer, nullable=True),
        sa.Column("score_trend", sa.String(20), nullable=True),
        sa.Column("outcomes", JSONB, nullable=False, server_default="{}"),
        sa.Column("win_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("skills_snapshot", JSONB, nullable=False, server_default="{}"),
        sa.Column("skills_change", JSONB, nullable=False, server_default="{}"),
        sa.Column("xp_earned", sa.Integer, nullable=False, server_default="0"),
        sa.Column("level_at_start", sa.Integer, nullable=False),
        sa.Column("level_at_end", sa.Integer, nullable=False),
        sa.Column("new_achievements", JSONB, nullable=False, server_default="[]"),
        sa.Column("weak_points", JSONB, nullable=False, server_default="[]"),
        sa.Column("recommendations", JSONB, nullable=False, server_default="[]"),
        sa.Column("weekly_rank", sa.Integer, nullable=True),
        sa.Column("rank_change", sa.Integer, nullable=True),
        sa.Column("report_text", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "week_start", name="uq_weekly_report_user_week"),
    )
    op.create_index("idx_weekly_reports_user", "weekly_reports", ["user_id", sa.text("week_start DESC")])

    # ── Триггер updated_at для manager_progress ──
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)
    op.execute("""
        CREATE TRIGGER trg_manager_progress_updated
        BEFORE UPDATE ON manager_progress
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_manager_progress_updated ON manager_progress;")
    op.drop_table("weekly_reports")
    op.drop_table("progress_leaderboard_snapshots")
    op.drop_table("earned_achievements")
    op.drop_table("session_history")
    op.drop_table("manager_progress")
    op.drop_table("achievement_definitions")
    op.drop_table("level_definitions")
