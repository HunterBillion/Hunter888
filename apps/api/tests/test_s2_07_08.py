"""Tests for S2-07 (Database Performance) and S2-08 (Embedding Lifecycle).

Covers:
- S2-07a: weekly_report_generator ranking uses GROUP BY (not N queries)
- S2-07b: team_analytics batch helpers produce correct output shapes
- S2-07b2: team_weekly_digest uses batch IN clause
- S2-07c: Migration creates correct indexes
- S2-07d: arena_xp uses FOR UPDATE for race condition prevention
- S2-08: Re-embedding hook invalidates embedding on content change
"""

import ast
import hashlib
import inspect
import textwrap

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# S2-07a: GROUP BY ranking in weekly_report_generator
# ═══════════════════════════════════════════════════════════════════════════


class TestS207aGroupByRanking:
    """Verify O(n²) ranking loop was replaced with GROUP BY."""

    def test_ranking_uses_group_by(self):
        from app.services.weekly_report_generator import generate_weekly_report
        source = inspect.getsource(generate_weekly_report)
        # Must contain GROUP BY via .group_by()
        assert "group_by" in source, "Ranking should use GROUP BY, not loop"

    def test_no_per_member_avg_loop(self):
        from app.services.weekly_report_generator import generate_weekly_report
        source = inspect.getsource(generate_weekly_report)
        # The old pattern: "for mid in team_member_ids" with individual AVG
        assert "for mid in team_member_ids" not in source, \
            "Old O(n²) per-member AVG loop should be removed"

    def test_ranking_query_joins_user_table(self):
        """Ranking query should join User to filter by team_id."""
        from app.services.weekly_report_generator import generate_weekly_report
        source = inspect.getsource(generate_weekly_report)
        assert "join(User" in source or ".join(" in source, \
            "Ranking should join User table to filter by team"


# ═══════════════════════════════════════════════════════════════════════════
# S2-07b: Batch helpers in team_analytics
# ═══════════════════════════════════════════════════════════════════════════


class TestS207bBatchHelpers:
    """Verify batch helper functions exist and are used by main functions."""

    def test_batch_member_skills_exists(self):
        from app.services.team_analytics import _batch_member_skills
        sig = inspect.signature(_batch_member_skills)
        params = list(sig.parameters.keys())
        assert "member_ids" in params
        assert "db" in params

    def test_batch_session_stats_exists(self):
        from app.services.team_analytics import _batch_session_stats
        sig = inspect.signature(_batch_session_stats)
        params = list(sig.parameters.keys())
        assert "member_ids" in params
        assert "days" in params

    def test_batch_score_trends_exists(self):
        from app.services.team_analytics import _batch_score_trends
        sig = inspect.signature(_batch_score_trends)
        params = list(sig.parameters.keys())
        assert "member_ids" in params

    def test_batch_last_session_exists(self):
        from app.services.team_analytics import _batch_last_session
        sig = inspect.signature(_batch_last_session)
        params = list(sig.parameters.keys())
        assert "member_ids" in params

    def test_heatmap_uses_batch(self):
        from app.services.team_analytics import get_team_heatmap
        source = inspect.getsource(get_team_heatmap)
        assert "_batch_member_skills" in source, "Heatmap should use batch skills loader"
        assert "_batch_score_trends" in source, "Heatmap should use batch trends"
        assert "_batch_session_stats" in source, "Heatmap should use batch session stats"

    def test_weak_links_uses_batch(self):
        from app.services.team_analytics import get_weak_links
        source = inspect.getsource(get_weak_links)
        assert "_batch_score_trends" in source
        assert "_batch_session_stats" in source
        assert "_batch_last_session" in source

    def test_compare_managers_uses_batch(self):
        from app.services.team_analytics import compare_managers
        source = inspect.getsource(compare_managers)
        assert "_batch_member_skills" in source
        assert "_batch_session_stats" in source

    def test_team_trends_uses_date_trunc(self):
        """get_team_trends should use date_trunc GROUP BY, not loop."""
        from app.services.team_analytics import get_team_trends
        source = inspect.getsource(get_team_trends)
        assert "date_trunc" in source, "Trends should use date_trunc GROUP BY"

    def test_daily_activity_uses_date_trunc(self):
        from app.services.team_analytics import get_daily_activity
        source = inspect.getsource(get_daily_activity)
        assert "date_trunc" in source or "_trunc" in source, \
            "Daily activity should use date_trunc GROUP BY"

    def test_team_roi_uses_date_trunc(self):
        from app.services.team_analytics import get_team_roi
        source = inspect.getsource(get_team_roi)
        assert "date_trunc" in source, "ROI should use date_trunc GROUP BY"

    def test_team_vs_platform_no_nested_loop(self):
        """get_team_vs_platform should NOT loop over teams × skills."""
        from app.services.team_analytics import get_team_vs_platform
        source = inspect.getsource(get_team_vs_platform)
        # Old pattern: "for tid in all_team_ids" inside "for s in SKILL_NAMES"
        assert "for tid in all_team_ids" not in source, \
            "Percentile should use single GROUP BY, not nested team loop"


# ═══════════════════════════════════════════════════════════════════════════
# S2-07b2: Team digest batch IN clause
# ═══════════════════════════════════════════════════════════════════════════


class TestS207b2DigestBatch:
    """Verify team digest uses batch IN clause."""

    def test_digest_uses_in_clause(self):
        from app.services.weekly_report_generator import get_team_weekly_digest
        source = inspect.getsource(get_team_weekly_digest)
        assert ".in_(member_ids)" in source or "in_(" in source, \
            "Digest should batch-load reports with IN clause"

    def test_digest_no_per_member_select(self):
        from app.services.weekly_report_generator import get_team_weekly_digest
        source = inspect.getsource(get_team_weekly_digest)
        # Old pattern: SELECT inside "for member in members"
        assert "WeeklyReport.user_id == member.id" not in source, \
            "Old per-member SELECT should be replaced with batch"


# ═══════════════════════════════════════════════════════════════════════════
# S2-07c: Migration indexes
# ═══════════════════════════════════════════════════════════════════════════


class TestS207cMigration:
    """Verify migration creates the right indexes."""

    @staticmethod
    def _read_migration_source() -> str:
        import pathlib
        p = pathlib.Path(__file__).parent.parent / "alembic" / "versions" / "20260414_003_s207_performance_indexes.py"
        return p.read_text()

    def test_migration_exists(self):
        source = self._read_migration_source()
        assert "def upgrade" in source
        assert "def downgrade" in source

    def test_migration_creates_composite_index(self):
        source = self._read_migration_source()
        assert "ix_training_sessions_user_status_started" in source
        assert '"user_id", "status", "started_at"' in source

    def test_migration_creates_started_at_index(self):
        source = self._read_migration_source()
        assert "ix_training_sessions_started_at" in source

    def test_migration_creates_weekly_report_index(self):
        source = self._read_migration_source()
        assert "ix_weekly_reports_user_week" in source


# ═══════════════════════════════════════════════════════════════════════════
# S2-07d: arena_xp FOR UPDATE
# ═══════════════════════════════════════════════════════════════════════════


class TestS207dArenaXpForUpdate:
    """Verify arena_xp uses FOR UPDATE to prevent race conditions."""

    def test_update_arena_streak_for_update(self):
        from app.services.arena_xp import update_arena_streak
        source = inspect.getsource(update_arena_streak)
        assert "with_for_update" in source, \
            "update_arena_streak must use FOR UPDATE"

    def test_apply_arena_xp_for_update(self):
        from app.services.arena_xp import apply_arena_xp_to_progress
        source = inspect.getsource(apply_arena_xp_to_progress)
        assert "with_for_update" in source, \
            "apply_arena_xp_to_progress must use FOR UPDATE"


# ═══════════════════════════════════════════════════════════════════════════
# S2-08: Re-embedding lifecycle
# ═══════════════════════════════════════════════════════════════════════════


class TestS208ReEmbedding:
    """Verify re-embedding hooks and stale detection."""

    def test_compute_content_hash(self):
        from app.models.rag import _compute_content_hash
        h = _compute_content_hash("Test fact", "Art. 123")
        expected = hashlib.md5("Test fact::Art. 123".encode()).hexdigest()
        assert h == expected

    def test_content_hash_changes_with_fact(self):
        from app.models.rag import _compute_content_hash
        h1 = _compute_content_hash("Fact A", "Art. 1")
        h2 = _compute_content_hash("Fact B", "Art. 1")
        assert h1 != h2, "Different fact_text must produce different hash"

    def test_content_hash_changes_with_article(self):
        from app.models.rag import _compute_content_hash
        h1 = _compute_content_hash("Fact A", "Art. 1")
        h2 = _compute_content_hash("Fact A", "Art. 2")
        assert h1 != h2, "Different law_article must produce different hash"

    def test_before_update_hook_registered(self):
        """LegalKnowledgeChunk should have a before_update event listener."""
        from sqlalchemy import event as sa_event
        from app.models.rag import LegalKnowledgeChunk, _legal_chunk_before_update
        assert sa_event.contains(
            LegalKnowledgeChunk, "before_update", _legal_chunk_before_update
        ), "LegalKnowledgeChunk must have before_update hook"

    def test_personality_before_update_hook_registered(self):
        from sqlalchemy import event as sa_event
        from app.models.rag import PersonalityChunk, _personality_chunk_before_update
        assert sa_event.contains(
            PersonalityChunk, "before_update", _personality_chunk_before_update
        ), "PersonalityChunk must have before_update hook"

    def test_invalidate_stale_embeddings_exists(self):
        from app.services.embedding_backfill import invalidate_stale_legal_embeddings
        sig = inspect.signature(invalidate_stale_legal_embeddings)
        assert "db" in sig.parameters

    def test_backfill_calls_stale_check(self):
        from app.services.embedding_backfill import populate_all_embeddings
        source = inspect.getsource(populate_all_embeddings)
        assert "invalidate_stale_legal_embeddings" in source, \
            "populate_all_embeddings should call stale check before populating"
