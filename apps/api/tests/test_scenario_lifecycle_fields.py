"""TZ-3 C1 — pin the new lifecycle fields on ScenarioTemplate / ScenarioVersion.

Pure ORM-level smoke that the new columns are declared correctly. The
migration `20260426_003` adds them at the SQL layer; CI runs alembic
upgrade head before pytest, so a divergence between this test and the
migration would surface as either a test failure (missing attribute)
or a CI red (alembic refuses).
"""

from __future__ import annotations

import pytest

from app.models.scenario import ScenarioTemplate, ScenarioVersion


# ── ScenarioTemplate new columns ────────────────────────────────────────────


def test_scenario_template_has_status_column():
    """`status` is declared, has a column object, and accepts the lattice."""
    col = ScenarioTemplate.__table__.columns.get("status")
    assert col is not None, "status column missing on scenario_templates"
    assert col.nullable is False
    # server_default ensures existing rows get 'published' on backfill
    assert col.server_default is not None


def test_scenario_template_has_draft_revision_column():
    col = ScenarioTemplate.__table__.columns.get("draft_revision")
    assert col is not None
    assert col.nullable is False
    assert col.server_default is not None


def test_scenario_template_has_current_published_version_id_column():
    col = ScenarioTemplate.__table__.columns.get("current_published_version_id")
    assert col is not None
    assert col.nullable is True  # nullable until first publish
    # Must be a foreign key to scenario_versions.id
    fks = list(col.foreign_keys)
    assert len(fks) == 1
    assert fks[0].column.table.name == "scenario_versions"
    assert fks[0].ondelete == "SET NULL"


# ── ScenarioVersion new columns ─────────────────────────────────────────────


def test_scenario_version_has_schema_version_column():
    col = ScenarioVersion.__table__.columns.get("schema_version")
    assert col is not None
    assert col.nullable is False
    assert col.server_default is not None


def test_scenario_version_has_content_hash_column():
    col = ScenarioVersion.__table__.columns.get("content_hash")
    assert col is not None
    # NOT NULL — every published version must carry a hash. The publisher
    # in PR C2 computes SHA256(snapshot::text) before insert. The migration
    # backfilled existing rows.
    assert col.nullable is False
    # No server_default — publisher must always compute it explicitly.
    assert col.server_default is None


def test_scenario_version_has_validation_report_column():
    col = ScenarioVersion.__table__.columns.get("validation_report")
    assert col is not None
    assert col.nullable is False
    # Has a server_default so backfilled rows get
    # `{"backfilled":true,"issues":[]}` automatically.
    assert col.server_default is not None


# ── Cross-table relationship sanity ─────────────────────────────────────────


def test_template_pointer_can_be_set_and_read_in_python():
    """Round-trip the new attributes in pure-Python so a refactor that
    accidentally drops one of them fails the test, not the runtime."""
    t = ScenarioTemplate(
        code="test",
        name="Test",
        description="Test scenario",
        archetype_weights={},
        stages=[],
    )
    # Defaults from model declaration (NOT from migration server_default —
    # those only apply at INSERT time on a real DB)
    # status / draft_revision are server_default only, so attribute is None
    # in Python until INSERT. That's fine — we just test the attr exists.
    assert hasattr(t, "status")
    assert hasattr(t, "draft_revision")
    assert hasattr(t, "current_published_version_id")

    v = ScenarioVersion(
        template_id=None,  # not validated at construction
        version_number=1,
        snapshot={"foo": "bar"},
        content_hash="a" * 64,  # required — see test above
    )
    assert hasattr(v, "schema_version")
    assert hasattr(v, "content_hash")
    assert hasattr(v, "validation_report")
    assert v.content_hash == "a" * 64
