"""Phase 3 audit: add FK indexes, ondelete policies, fix pool/model issues.

This migration covers all database-level changes from Phase 3 of the Hunter888
platform audit. Changes are applied in a safe order:
1. Create missing indexes on foreign key columns
2. Alter foreign key constraints to add ondelete policies

Revision ID: 20260402_005
Revises: 20260402_004
Create Date: 2026-04-02
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers
revision: str = "20260402_005"
down_revision: Union[str, None] = "20260402_004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Helper: safely add index (skip if already exists) ──
def _create_index_safe(name: str, table: str, columns: list[str]) -> None:
    """Create index if it doesn't already exist."""
    try:
        op.create_index(name, table, columns)
    except Exception:
        pass  # Index already exists


# ── Helper: alter FK ondelete (PostgreSQL) ──
def _alter_fk_ondelete(
    table: str,
    constraint_name: str,
    local_col: str,
    remote_table: str,
    remote_col: str,
    ondelete: str,
    nullable: bool = False,
) -> None:
    """Drop old FK and recreate with ondelete policy."""
    try:
        op.drop_constraint(constraint_name, table, type_="foreignkey")
    except Exception:
        pass  # Constraint might not exist with this name
    op.create_foreign_key(
        constraint_name, table, remote_table,
        [local_col], [remote_col],
        ondelete=ondelete,
    )


def upgrade() -> None:
    # ════════════════════════════════════════════════════════════════════════
    # 1. CREATE MISSING INDEXES ON FK COLUMNS
    # ════════════════════════════════════════════════════════════════════════

    # training.py
    _create_index_safe("ix_training_sessions_user_id", "training_sessions", ["user_id"])
    _create_index_safe("ix_training_sessions_scenario_id", "training_sessions", ["scenario_id"])
    _create_index_safe("ix_training_sessions_client_story_id", "training_sessions", ["client_story_id"])
    _create_index_safe("ix_messages_session_id", "messages", ["session_id"])
    _create_index_safe("ix_assigned_trainings_user_id", "assigned_trainings", ["user_id"])
    _create_index_safe("ix_assigned_trainings_scenario_id", "assigned_trainings", ["scenario_id"])
    _create_index_safe("ix_assigned_trainings_assigned_by", "assigned_trainings", ["assigned_by"])
    _create_index_safe("ix_call_records_story_id", "call_records", ["story_id"])
    _create_index_safe("ix_call_records_session_id", "call_records", ["session_id"])
    _create_index_safe("ix_session_reports_story_id", "session_reports", ["story_id"])
    _create_index_safe("ix_session_reports_session_id", "session_reports", ["session_id"])

    # knowledge.py
    _create_index_safe("ix_knowledge_quiz_sessions_user_id", "knowledge_quiz_sessions", ["user_id"])
    _create_index_safe("ix_quiz_participants_session_id", "quiz_participants", ["session_id"])
    _create_index_safe("ix_quiz_participants_user_id", "quiz_participants", ["user_id"])
    _create_index_safe("ix_knowledge_answers_session_id", "knowledge_answers", ["session_id"])
    _create_index_safe("ix_knowledge_answers_user_id", "knowledge_answers", ["user_id"])
    _create_index_safe("ix_user_answer_history_user_id", "user_answer_history", ["user_id"])
    _create_index_safe("ix_quiz_challenges_session_id", "quiz_challenges", ["session_id"])

    # tournament.py
    _create_index_safe("ix_tournaments_scenario_id", "tournaments", ["scenario_id"])
    _create_index_safe("ix_tournament_entries_tournament_id", "tournament_entries", ["tournament_id"])
    _create_index_safe("ix_tournament_entries_user_id", "tournament_entries", ["user_id"])
    _create_index_safe("ix_tournament_entries_session_id", "tournament_entries", ["session_id"])
    _create_index_safe("ix_tournament_participants_tournament_id", "tournament_participants", ["tournament_id"])
    _create_index_safe("ix_tournament_participants_user_id", "tournament_participants", ["user_id"])
    _create_index_safe("ix_bracket_matches_tournament_id", "bracket_matches", ["tournament_id"])
    _create_index_safe("ix_bracket_matches_player1_id", "bracket_matches", ["player1_id"])
    _create_index_safe("ix_bracket_matches_player2_id", "bracket_matches", ["player2_id"])
    _create_index_safe("ix_bracket_matches_winner_id", "bracket_matches", ["winner_id"])
    _create_index_safe("ix_bracket_matches_duel_id", "bracket_matches", ["duel_id"])
    _create_index_safe("ix_bracket_matches_forfeit_by_id", "bracket_matches", ["forfeit_by_id"])

    # behavior.py
    _create_index_safe("ix_behavior_snapshots_user_id", "behavior_snapshots", ["user_id"])
    _create_index_safe("ix_progress_trends_user_id", "progress_trends", ["user_id"])
    _create_index_safe("ix_daily_advice_user_id", "daily_advice", ["user_id"])

    # rag.py
    _create_index_safe("ix_chunk_usage_log_chunk_id", "chunk_usage_log", ["chunk_id"])
    _create_index_safe("ix_chunk_usage_log_user_id", "chunk_usage_log", ["user_id"])
    _create_index_safe("ix_legal_validation_results_session_id", "legal_validation_results", ["session_id"])
    _create_index_safe("ix_legal_validation_results_knowledge_chunk_id", "legal_validation_results", ["knowledge_chunk_id"])

    # pvp.py
    _create_index_safe("ix_pvp_duels_player1_id", "pvp_duels", ["player1_id"])
    _create_index_safe("ix_pvp_duels_player2_id", "pvp_duels", ["player2_id"])
    _create_index_safe("ix_pvp_duels_scenario_id", "pvp_duels", ["scenario_id"])
    _create_index_safe("ix_pvp_match_queue_user_id", "pvp_match_queue", ["user_id"])
    _create_index_safe("ix_anti_cheat_logs_duel_id", "anti_cheat_logs", ["duel_id"])

    # client.py
    _create_index_safe("ix_client_consents_recorded_by", "client_consents", ["recorded_by"])
    _create_index_safe("ix_client_interactions_manager_id", "client_interactions", ["manager_id"])
    _create_index_safe("ix_audit_log_actor_id", "audit_log", ["actor_id"])

    # roleplay.py
    _create_index_safe("ix_traps_triggers_trap_id", "traps", ["triggers_trap_id"])
    _create_index_safe("ix_traps_blocked_by_trap_id", "traps", ["blocked_by_trap_id"])

    # scenario.py
    _create_index_safe("ix_scenarios_character_id", "scenarios", ["character_id"])
    _create_index_safe("ix_scenarios_script_id", "scenarios", ["script_id"])
    _create_index_safe("ix_scenarios_template_id", "scenarios", ["template_id"])

    # script.py
    _create_index_safe("ix_checkpoints_script_id", "checkpoints", ["script_id"])
    _create_index_safe("ix_script_embeddings_checkpoint_id", "script_embeddings", ["checkpoint_id"])

    # user.py
    _create_index_safe("ix_users_team_id", "users", ["team_id"])
    _create_index_safe("ix_user_consents_user_id", "user_consents", ["user_id"])

    # ════════════════════════════════════════════════════════════════════════
    # 2. ALTER FK CONSTRAINTS TO ADD ONDELETE POLICIES
    # ════════════════════════════════════════════════════════════════════════
    # NOTE: PostgreSQL requires DROP + CREATE to alter FK ondelete.
    # Constraint names follow SQLAlchemy auto-naming: {table}_{column}_fkey
    # If your DB uses different naming, adjust constraint names accordingly.

    # ── training_sessions ──
    _alter_fk_ondelete("training_sessions", "training_sessions_user_id_fkey",
                       "user_id", "users", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("training_sessions", "training_sessions_scenario_id_fkey",
                       "scenario_id", "scenarios", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("training_sessions", "training_sessions_client_story_id_fkey",
                       "client_story_id", "client_stories", "id", "SET NULL", nullable=True)

    # ── messages ──
    _alter_fk_ondelete("messages", "messages_session_id_fkey",
                       "session_id", "training_sessions", "id", "CASCADE")

    # ── assigned_trainings ──
    _alter_fk_ondelete("assigned_trainings", "assigned_trainings_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("assigned_trainings", "assigned_trainings_scenario_id_fkey",
                       "scenario_id", "scenarios", "id", "CASCADE")
    _alter_fk_ondelete("assigned_trainings", "assigned_trainings_assigned_by_fkey",
                       "assigned_by", "users", "id", "SET NULL", nullable=True)

    # ── call_records ──
    _alter_fk_ondelete("call_records", "call_records_story_id_fkey",
                       "story_id", "client_stories", "id", "CASCADE")
    _alter_fk_ondelete("call_records", "call_records_session_id_fkey",
                       "session_id", "training_sessions", "id", "CASCADE")

    # ── session_reports ──
    _alter_fk_ondelete("session_reports", "session_reports_story_id_fkey",
                       "story_id", "client_stories", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("session_reports", "session_reports_session_id_fkey",
                       "session_id", "training_sessions", "id", "SET NULL", nullable=True)

    # ── knowledge tables ──
    _alter_fk_ondelete("knowledge_quiz_sessions", "knowledge_quiz_sessions_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("quiz_participants", "quiz_participants_session_id_fkey",
                       "session_id", "knowledge_quiz_sessions", "id", "CASCADE")
    _alter_fk_ondelete("quiz_participants", "quiz_participants_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("knowledge_answers", "knowledge_answers_session_id_fkey",
                       "session_id", "knowledge_quiz_sessions", "id", "CASCADE")
    _alter_fk_ondelete("knowledge_answers", "knowledge_answers_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("user_answer_history", "user_answer_history_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("quiz_challenges", "quiz_challenges_session_id_fkey",
                       "session_id", "knowledge_quiz_sessions", "id", "SET NULL", nullable=True)

    # ── client tables ──
    _alter_fk_ondelete("real_clients", "real_clients_manager_id_fkey",
                       "manager_id", "users", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("client_consents", "client_consents_client_id_fkey",
                       "client_id", "real_clients", "id", "CASCADE")
    _alter_fk_ondelete("client_consents", "client_consents_recorded_by_fkey",
                       "recorded_by", "users", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("client_interactions", "client_interactions_client_id_fkey",
                       "client_id", "real_clients", "id", "CASCADE")
    _alter_fk_ondelete("client_interactions", "client_interactions_manager_id_fkey",
                       "manager_id", "users", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("client_notifications", "client_notifications_client_id_fkey",
                       "client_id", "real_clients", "id", "CASCADE")
    _alter_fk_ondelete("manager_reminders", "manager_reminders_manager_id_fkey",
                       "manager_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("manager_reminders", "manager_reminders_client_id_fkey",
                       "client_id", "real_clients", "id", "CASCADE")
    _alter_fk_ondelete("audit_log", "audit_log_actor_id_fkey",
                       "actor_id", "users", "id", "SET NULL", nullable=True)

    # ── behavior tables ──
    _alter_fk_ondelete("behavior_snapshots", "behavior_snapshots_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("manager_emotion_profiles", "manager_emotion_profiles_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("progress_trends", "progress_trends_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("daily_advice", "daily_advice_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")

    # ── rag tables ──
    _alter_fk_ondelete("chunk_usage_log", "chunk_usage_log_chunk_id_fkey",
                       "chunk_id", "legal_knowledge_chunks", "id", "CASCADE")
    _alter_fk_ondelete("chunk_usage_log", "chunk_usage_log_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("legal_validation_results", "legal_validation_results_session_id_fkey",
                       "session_id", "training_sessions", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("legal_validation_results", "legal_validation_results_knowledge_chunk_id_fkey",
                       "knowledge_chunk_id", "legal_knowledge_chunks", "id", "SET NULL", nullable=True)

    # ── tournament tables ──
    _alter_fk_ondelete("tournaments", "tournaments_scenario_id_fkey",
                       "scenario_id", "scenarios", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("tournament_entries", "tournament_entries_tournament_id_fkey",
                       "tournament_id", "tournaments", "id", "CASCADE")
    _alter_fk_ondelete("tournament_entries", "tournament_entries_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("tournament_entries", "tournament_entries_session_id_fkey",
                       "session_id", "training_sessions", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("tournament_participants", "tournament_participants_tournament_id_fkey",
                       "tournament_id", "tournaments", "id", "CASCADE")
    _alter_fk_ondelete("tournament_participants", "tournament_participants_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("bracket_matches", "bracket_matches_tournament_id_fkey",
                       "tournament_id", "tournaments", "id", "CASCADE")
    _alter_fk_ondelete("bracket_matches", "bracket_matches_player1_id_fkey",
                       "player1_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("bracket_matches", "bracket_matches_player2_id_fkey",
                       "player2_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("bracket_matches", "bracket_matches_winner_id_fkey",
                       "winner_id", "users", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("bracket_matches", "bracket_matches_duel_id_fkey",
                       "duel_id", "pvp_duels", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("bracket_matches", "bracket_matches_forfeit_by_id_fkey",
                       "forfeit_by_id", "users", "id", "SET NULL", nullable=True)

    # ── pvp tables ──
    _alter_fk_ondelete("pvp_duels", "pvp_duels_player1_id_fkey",
                       "player1_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("pvp_duels", "pvp_duels_player2_id_fkey",
                       "player2_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("pvp_duels", "pvp_duels_scenario_id_fkey",
                       "scenario_id", "scenarios", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("pvp_ratings", "pvp_ratings_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("pvp_match_queue", "pvp_match_queue_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("anti_cheat_logs", "anti_cheat_logs_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("anti_cheat_logs", "anti_cheat_logs_duel_id_fkey",
                       "duel_id", "pvp_duels", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("user_fingerprints", "user_fingerprints_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")

    # ── roleplay tables ──
    _alter_fk_ondelete("client_profiles", "client_profiles_session_id_fkey",
                       "session_id", "training_sessions", "id", "CASCADE")
    _alter_fk_ondelete("client_profiles", "client_profiles_profession_id_fkey",
                       "profession_id", "profession_profiles", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("client_profiles", "client_profiles_chain_id_fkey",
                       "chain_id", "objection_chains", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("episodic_memories", "episodic_memories_story_id_fkey",
                       "story_id", "client_stories", "id", "CASCADE")
    _alter_fk_ondelete("episodic_memories", "episodic_memories_session_id_fkey",
                       "session_id", "training_sessions", "id", "CASCADE")
    _alter_fk_ondelete("story_stage_directions", "story_stage_directions_story_id_fkey",
                       "story_id", "client_stories", "id", "CASCADE")
    _alter_fk_ondelete("story_stage_directions", "story_stage_directions_session_id_fkey",
                       "session_id", "training_sessions", "id", "CASCADE")

    # ── scenario ──
    _alter_fk_ondelete("scenarios", "scenarios_character_id_fkey",
                       "character_id", "characters", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("scenarios", "scenarios_script_id_fkey",
                       "script_id", "scripts", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("scenarios", "scenarios_template_id_fkey",
                       "template_id", "scenario_templates", "id", "SET NULL", nullable=True)

    # ── script ──
    _alter_fk_ondelete("checkpoints", "checkpoints_script_id_fkey",
                       "script_id", "scripts", "id", "CASCADE")
    _alter_fk_ondelete("script_embeddings", "script_embeddings_checkpoint_id_fkey",
                       "checkpoint_id", "checkpoints", "id", "CASCADE")

    # ── user ──
    _alter_fk_ondelete("users", "users_team_id_fkey",
                       "team_id", "teams", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("user_consents", "user_consents_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")

    # ── analytics ──
    _alter_fk_ondelete("user_achievements", "user_achievements_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("user_achievements", "user_achievements_achievement_id_fkey",
                       "achievement_id", "achievements", "id", "CASCADE")
    _alter_fk_ondelete("leaderboard_snapshots", "leaderboard_snapshots_user_id_fkey",
                       "user_id", "users", "id", "CASCADE")
    _alter_fk_ondelete("leaderboard_snapshots", "leaderboard_snapshots_team_id_fkey",
                       "team_id", "teams", "id", "SET NULL", nullable=True)
    _alter_fk_ondelete("api_logs", "api_logs_session_id_fkey",
                       "session_id", "training_sessions", "id", "SET NULL", nullable=True)


def downgrade() -> None:
    # Downgrade is complex (would need to drop all indexes and revert all FK constraints).
    # For safety, this migration is forward-only in production.
    # To rollback: restore from backup or manually recreate constraints without ondelete.
    pass
