"""TZ-3 §10 — runtime resolver integration tests against CI Postgres.

Same fixture pattern as `test_scenario_publisher.py`:
  * Skip locally (no DATABASE_URL).
  * Run on CI's pg16 service where JSONB + alembic migrations work.

Covers (§10.1 resolution order):
  1. explicit version_id wins
  2. template_id → current_published_version_id pointer
  3. pointer-drift fallback (template has version but pointer NULL)
  4. legacy fallback (template with no published version)
  5. error path: unknown template/version → ScenarioNotFound
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.scenario import ScenarioTemplate, ScenarioVersion
from app.services.scenario_publisher import publish_template
from app.services.scenario_runtime_resolver import (
    ScenarioNotFound,
    resolve_for_runtime,
)


def _pg_url() -> str | None:
    raw = os.getenv("DATABASE_URL")
    if not raw or not raw.startswith("postgresql+asyncpg"):
        return None
    return raw


pytestmark = pytest.mark.skipif(
    _pg_url() is None,
    reason="needs DATABASE_URL pointing at Postgres (provided by CI's pg16 service)",
)


@pytest.fixture
async def engine():
    e = create_async_engine(_pg_url(), echo=False)
    yield e
    await e.dispose()


@pytest.fixture
async def session(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        try:
            yield s
        finally:
            await s.rollback()


def _valid_stages():
    return [
        {
            "order": 1,
            "name": "S1",
            "description": "First stage description.",
            "manager_goals": ["g"],
        }
    ]


async def _make_template(session: AsyncSession) -> ScenarioTemplate:
    t = ScenarioTemplate(
        code=f"resolver_{uuid.uuid4().hex[:10]}",
        name="Resolver test",
        description="Resolver test template",
        difficulty=5,
        typical_duration_minutes=8,
        max_duration_minutes=15,
        archetype_weights={"skeptic": 100},
        stages=_valid_stages(),
    )
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return t


# ── 1. Explicit version_id ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_explicit_version_id_wins(session):
    t = await _make_template(session)
    pub = await publish_template(
        session, template_id=t.id, expected_draft_revision=0, actor_id=None,
    )
    await session.commit()

    resolved = await resolve_for_runtime(session, version_id=pub.new_version_id)
    assert resolved.scenario_version_id == pub.new_version_id
    assert resolved.template_id == t.id
    assert resolved.version_number == 1
    assert resolved.source == "explicit_version"
    assert "stages" in resolved.snapshot
    assert resolved.snapshot["code"] == t.code


@pytest.mark.asyncio
async def test_explicit_unknown_version_raises_not_found(session):
    with pytest.raises(ScenarioNotFound):
        await resolve_for_runtime(session, version_id=uuid.uuid4())


# ── 2. Template pointer ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_template_pointer_resolves_to_current_published(session):
    t = await _make_template(session)
    pub = await publish_template(
        session, template_id=t.id, expected_draft_revision=0, actor_id=None,
    )
    await session.commit()

    resolved = await resolve_for_runtime(session, template_id=t.id)
    assert resolved.scenario_version_id == pub.new_version_id
    assert resolved.source == "template_pointer"
    assert resolved.version_number == 1


@pytest.mark.asyncio
async def test_template_pointer_after_republish_resolves_to_v2(session):
    """First publish → v1 (current). Second publish → v2 (current),
    v1 marked superseded. Resolver must return v2."""
    t = await _make_template(session)
    v1 = await publish_template(
        session, template_id=t.id, expected_draft_revision=0, actor_id=None,
    )
    await session.commit()
    v2 = await publish_template(
        session, template_id=t.id, expected_draft_revision=0, actor_id=None,
    )
    await session.commit()

    resolved = await resolve_for_runtime(session, template_id=t.id)
    assert resolved.scenario_version_id == v2.new_version_id
    assert resolved.scenario_version_id != v1.new_version_id


# ── 3. Pointer-drift fallback ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pointer_null_falls_back_to_latest_published(session):
    """If the template pointer somehow becomes NULL but a published
    version exists, the resolver finds it via the table query and
    logs a warning (not a hard error — sessions must keep starting)."""
    t = await _make_template(session)
    pub = await publish_template(
        session, template_id=t.id, expected_draft_revision=0, actor_id=None,
    )
    await session.commit()

    # Simulate pointer drift: NULL the pointer out-of-band.
    refreshed = await session.get(ScenarioTemplate, t.id)
    refreshed.current_published_version_id = None
    await session.commit()

    resolved = await resolve_for_runtime(session, template_id=t.id)
    assert resolved.scenario_version_id == pub.new_version_id
    assert resolved.source == "template_pointer"


# ── 4. Legacy fallback (no version at all) ──────────────────────────────────


@pytest.mark.asyncio
async def test_template_with_no_versions_uses_legacy_fallback(session):
    """The 60-templates-no-versions reality on prod (verified
    2026-04-26). Resolver builds a snapshot from the live template
    fields, returns scenario_version_id=None, logs a remediation hint."""
    t = await _make_template(session)
    # Don't publish — the template stays in the unpublished state.

    resolved = await resolve_for_runtime(session, template_id=t.id)
    assert resolved.scenario_version_id is None
    assert resolved.source == "legacy_template"
    assert resolved.version_number is None
    assert resolved.snapshot["code"] == t.code
    assert "stages" in resolved.snapshot


# ── 5. Errors ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_template_raises_not_found(session):
    with pytest.raises(ScenarioNotFound):
        await resolve_for_runtime(session, template_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_no_arguments_raises_value_error(session):
    with pytest.raises(ValueError):
        await resolve_for_runtime(session)


# ── Snapshot isolation (no accidental DB write back) ────────────────────────


@pytest.mark.asyncio
async def test_returned_snapshot_is_a_copy_not_orm_attribute(session):
    """Mutating the returned snapshot must not flag the JSONB column
    as dirty — otherwise the next commit() would write the modified
    snapshot back to the DB and break §8 invariant 2."""
    t = await _make_template(session)
    pub = await publish_template(
        session, template_id=t.id, expected_draft_revision=0, actor_id=None,
    )
    await session.commit()

    resolved = await resolve_for_runtime(session, version_id=pub.new_version_id)
    # Mutate the dict
    resolved.snapshot["code"] = "MUTATED"

    # Re-read the version row — original snapshot must be intact
    fresh = await session.get(ScenarioVersion, pub.new_version_id)
    assert fresh.snapshot["code"] == t.code
    assert fresh.snapshot["code"] != "MUTATED"
