"""TZ-4 D1 — pin every new column on Attachment/LegalKnowledgeChunk + the
two new tables (MemoryPersona, SessionPersonaSnapshot).

ORM-level smoke (no DB needed). Mirrors the pattern from
`test_scenario_lifecycle_fields.py` (TZ-3 C1) — if a refactor accidentally
drops a column declaration, this test fires before alembic upgrade head
silently rebuilds a table without it.
"""

from __future__ import annotations

from app.models.client import Attachment
from app.models.rag import LegalKnowledgeChunk
from app.models.persona import (
    ADDRESS_FORMS,
    GENDERS,
    MemoryPersona,
    PERSONA_CAPTURED_FROM,
    SessionPersonaSnapshot,
    TONES,
)


# ── Attachment new fields (§6.1.1) ──────────────────────────────────────────


def test_attachment_has_call_attempt_id_column():
    col = Attachment.__table__.columns.get("call_attempt_id")
    assert col is not None, "call_attempt_id column missing on attachments"
    assert col.nullable is True
    # NB: no FK in D1 — `call_attempts` table doesn't exist yet
    # (TZ-1 §7.1 reserves the field, model lands later). Verify the
    # column is a plain UUID that's forward-compatible.
    assert len(list(col.foreign_keys)) == 0


def test_attachment_has_domain_event_id_column():
    col = Attachment.__table__.columns.get("domain_event_id")
    assert col is not None
    # NULLable in D1 — orphan rows can't be linked yet (D2 repair job
    # promotes to NOT NULL after cleanup).
    assert col.nullable is True
    fks = list(col.foreign_keys)
    assert len(fks) == 1
    assert fks[0].column.table.name == "domain_events"
    assert fks[0].ondelete == "RESTRICT"


def test_attachment_has_verification_status_column():
    col = Attachment.__table__.columns.get("verification_status")
    assert col is not None
    assert col.nullable is False
    assert col.server_default is not None  # 'unverified'


def test_attachment_has_duplicate_of_self_fk():
    col = Attachment.__table__.columns.get("duplicate_of")
    assert col is not None
    assert col.nullable is True
    fks = list(col.foreign_keys)
    assert len(fks) == 1
    # Self-reference
    assert fks[0].column.table.name == "attachments"
    assert fks[0].ondelete == "SET NULL"


# ── LegalKnowledgeChunk new fields (§6.2.1) ─────────────────────────────────


def test_knowledge_chunk_has_source_type_column():
    col = LegalKnowledgeChunk.__table__.columns.get("source_type")
    assert col is not None
    assert col.server_default is not None  # 'manual'


def test_knowledge_chunk_has_title_column():
    col = LegalKnowledgeChunk.__table__.columns.get("title")
    assert col is not None
    assert col.nullable is True  # nullable in D1; D4 backfills from law_article


def test_knowledge_chunk_has_jurisdiction_column():
    col = LegalKnowledgeChunk.__table__.columns.get("jurisdiction")
    assert col is not None
    assert col.server_default is not None  # 'RU'


def test_knowledge_chunk_has_ttl_columns():
    """`expires_at` is the cron's input for §8.3.1 auto-flip rule."""
    for col_name in ("effective_from", "expires_at"):
        col = LegalKnowledgeChunk.__table__.columns.get(col_name)
        assert col is not None, f"{col_name} missing"
        assert col.nullable is True


def test_knowledge_chunk_has_review_columns():
    for col_name in ("reviewed_by", "reviewed_at", "source_ref"):
        col = LegalKnowledgeChunk.__table__.columns.get(col_name)
        assert col is not None, f"{col_name} missing"
        assert col.nullable is True
    # reviewed_by has FK
    fks = list(LegalKnowledgeChunk.__table__.columns["reviewed_by"].foreign_keys)
    assert len(fks) == 1
    assert fks[0].column.table.name == "users"
    assert fks[0].ondelete == "SET NULL"


# ── MemoryPersona table (§6.3.1) ────────────────────────────────────────────


def test_memory_persona_table_exists():
    assert MemoryPersona.__tablename__ == "memory_personas"


def test_memory_persona_unique_per_lead_client():
    constraints = {c.name for c in MemoryPersona.__table__.constraints}
    assert "uq_memory_personas_lead_client_id" in constraints


def test_memory_persona_has_optimistic_concurrency_version():
    """§9.2.5 — `version` token bumps on update; concurrent updates
    detect conflict via expected_version mismatch."""
    col = MemoryPersona.__table__.columns.get("version")
    assert col is not None
    assert col.nullable is False
    assert col.server_default is not None  # 1


def test_memory_persona_address_form_check_constraint():
    """CHECK constraint enforces enum at DB layer (defence in depth)."""
    constraints = {c.name for c in MemoryPersona.__table__.constraints}
    assert "ck_memory_personas_address_form" in constraints
    assert "ck_memory_personas_gender" in constraints
    assert "ck_memory_personas_tone" in constraints


def test_memory_persona_jsonb_facts_columns():
    """confirmed_facts + do_not_ask_again_slots are JSONB with empty
    defaults — bind-param trap from alembic 20260426_003 explicitly avoided."""
    for col_name in ("confirmed_facts", "do_not_ask_again_slots"):
        col = MemoryPersona.__table__.columns.get(col_name)
        assert col is not None, f"{col_name} missing"
        assert col.nullable is False
        assert col.server_default is not None


# ── SessionPersonaSnapshot table (§6.4.1) ───────────────────────────────────


def test_session_persona_snapshot_table_exists():
    assert SessionPersonaSnapshot.__tablename__ == "session_persona_snapshots"


def test_session_snapshot_session_id_is_pk():
    """Per §6.4.1 — session_id is PK, one snapshot per session, immutable."""
    pk_cols = [c.name for c in SessionPersonaSnapshot.__table__.primary_key.columns]
    assert pk_cols == ["session_id"]


def test_session_snapshot_lead_client_nullable():
    """Simulation sessions have no real client → nullable."""
    col = SessionPersonaSnapshot.__table__.columns.get("lead_client_id")
    assert col is not None
    assert col.nullable is True


def test_session_snapshot_has_observability_counter():
    """`mutation_blocked_count` increments when runtime tries to mutate
    the snapshot — surfaces drift attempts in observability."""
    col = SessionPersonaSnapshot.__table__.columns.get("mutation_blocked_count")
    assert col is not None
    assert col.nullable is False
    assert col.server_default is not None  # 0


def test_session_snapshot_captured_from_check_constraint():
    constraints = {c.name for c in SessionPersonaSnapshot.__table__.constraints}
    assert "ck_session_persona_snapshots_captured_from" in constraints


# ── Enum mirror sanity (§6.5) ───────────────────────────────────────────────


def test_address_form_enum_matches_spec():
    """Python-side mirror of CHECK constraint values. Mismatch =
    callers can pass a value that DB rejects with IntegrityError."""
    assert ADDRESS_FORMS == frozenset({"вы", "ты", "formal", "informal", "auto"})


def test_gender_enum_matches_spec():
    assert GENDERS == frozenset({"male", "female", "other", "unknown"})


def test_tone_enum_matches_spec():
    assert TONES == frozenset(
        {"neutral", "friendly", "formal", "cautious", "hostile"}
    )


def test_captured_from_enum_matches_spec():
    assert PERSONA_CAPTURED_FROM == frozenset(
        {"real_client", "home_preview", "training_simulation", "pvp", "center"}
    )
