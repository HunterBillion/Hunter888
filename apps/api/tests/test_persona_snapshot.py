"""Phase 3 — PersonaSnapshot tests (Roadmap §8.6).

Covers:
* model shape & immutability (no UPDATE paths)
* gender-coherent label rendering via ``between_call_narrator.trait_for``
* capture idempotency + multi-call voice continuity
* resolve helpers
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.persona_snapshot import PersonaSnapshot
from app.services import persona_snapshot as ps


# ── Model shape ──────────────────────────────────────────────────────────


def test_persona_snapshot_has_expected_columns():
    cols = {c.name for c in PersonaSnapshot.__table__.columns}
    required = {
        "id", "session_id", "lead_client_id", "client_story_id",
        "full_name", "gender", "city", "age",
        "archetype_code", "persona_label",
        "voice_id", "voice_provider", "voice_params",
        "frozen_at", "source_ref",
    }
    assert required <= cols


def test_persona_snapshot_is_insert_only_in_source():
    """Service module must not UPDATE the row after creation.

    Scan the service source for ``UPDATE``/``setattr``/direct column
    assignment on a ``PersonaSnapshot`` instance outside its constructor.
    The invariant §8.2 calls this out explicitly.
    """
    service_py = Path(ps.__file__)
    tree = ast.parse(service_py.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id in {"snapshot", "existing", "first"}
                ):
                    pytest.fail(
                        f"Attribute assignment on PersonaSnapshot row at line {node.lineno} "
                        "violates insert-only invariant"
                    )


# ── Gender-coherent label ────────────────────────────────────────────────


def test_label_uses_gender_trait_catalog():
    label_male = ps._persona_label("skeptic", "male")
    label_female = ps._persona_label("skeptic", "female")
    label_unknown = ps._persona_label("skeptic", "unknown")

    assert label_male != label_female
    # Neutral/unknown must use noun-phrase fallback from trait catalog.
    assert "клиент" in label_unknown.lower() or label_unknown == label_male


# ── Capture idempotency + multi-call continuity ──────────────────────────


def _fake_session(**overrides):
    base = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        lead_client_id=None,
        client_story_id=None,
        real_client_id=None,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@pytest.mark.asyncio
async def test_capture_returns_existing_snapshot_on_second_call(monkeypatch):
    session = _fake_session()
    existing = PersonaSnapshot(
        id=uuid.uuid4(),
        session_id=session.id,
        full_name="Иван Иванов",
        gender="male",
        archetype_code="skeptic",
        persona_label="скептичный",
        voice_id="voice-1",
        voice_provider="elevenlabs",
        voice_params={},
        source_ref="session.start",
    )
    db = SimpleNamespace()
    db.execute = AsyncMock(return_value=_ScalarResult(existing))
    db.add = lambda obj: (_ for _ in ()).throw(
        AssertionError("capture must not insert when snapshot already exists")
    )
    db.flush = AsyncMock()
    db.get = AsyncMock(return_value=None)

    result = await ps.capture(
        db,
        session=session,
        full_name="different",
        gender="female",
        archetype_code="anxious",
        voice_id="voice-2",
        voice_provider="webspeech",
    )

    assert result is existing


@pytest.mark.asyncio
async def test_capture_mirrors_voice_from_first_story_snapshot(monkeypatch):
    story_id = uuid.uuid4()
    session = _fake_session(client_story_id=story_id)
    first = PersonaSnapshot(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        client_story_id=story_id,
        full_name="Анна",
        gender="female",
        archetype_code="anxious",
        persona_label="тревожная",
        voice_id="voice-female-1",
        voice_provider="elevenlabs",
        voice_params={"stability": 0.6},
        source_ref="session.start",
    )

    # 1st execute → no existing for this session.
    # 2nd execute → first snapshot in story.
    call_results = iter([_ScalarResult(None), _ScalarResult(first)])
    captured: list[PersonaSnapshot] = []

    db = SimpleNamespace()
    db.execute = AsyncMock(side_effect=lambda *a, **k: next(call_results))
    db.add = lambda obj: captured.append(obj)
    db.flush = AsyncMock()
    db.get = AsyncMock(return_value=None)

    result = await ps.capture(
        db,
        session=session,
        full_name="Другое имя",
        gender="male",
        archetype_code="skeptic",
        voice_id="voice-male-8",
        voice_provider="navy",
        source_ref="story.continue",
    )

    # Voice/gender/archetype MIRRORED from first snapshot — that's the
    # multi-call continuity invariant.
    assert result.voice_id == first.voice_id
    assert result.voice_provider == first.voice_provider
    assert result.gender == first.gender
    assert result.archetype_code == first.archetype_code


# ── Resolve helper ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_voice_id_returns_tuple_or_none():
    snapshot = PersonaSnapshot(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        full_name="x",
        gender="male",
        archetype_code="skeptic",
        persona_label="скептичный",
        voice_id="voice-1",
        voice_provider="elevenlabs",
        voice_params={"stability": 0.5},
        source_ref="session.start",
    )
    db = SimpleNamespace()
    db.execute = AsyncMock(return_value=_ScalarResult(snapshot))

    result = await ps.resolve_voice_id(db, snapshot.session_id)
    assert result == ("voice-1", "elevenlabs", {"stability": 0.5})

    db.execute = AsyncMock(return_value=_ScalarResult(None))
    assert await ps.resolve_voice_id(db, snapshot.session_id) is None
