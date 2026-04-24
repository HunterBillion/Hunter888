"""Cutover read-path tests (TZ-1 Фаза 5).

Verifies ``client_timeline_reader.read_client_interactions`` applies the
canonical-event filter only when ``client_domain_cutover_read_enabled``
is on. Before cutover all rows pass through (legacy behaviour preserved);
after cutover only rows carrying ``metadata.domain_event_id`` are
returned.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import client_timeline_reader


class _ScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))


def _fake_session(rows):
    db = SimpleNamespace()
    db.execute = AsyncMock(return_value=_ScalarsResult(rows))
    return db


@pytest.mark.asyncio
async def test_pre_cutover_returns_all_rows(monkeypatch):
    monkeypatch.setattr(
        client_timeline_reader.settings,
        "client_domain_cutover_read_enabled",
        False,
        raising=False,
    )
    rows = [MagicMock(), MagicMock(), MagicMock()]
    db = _fake_session(rows)

    result = await client_timeline_reader.read_client_interactions(
        db, client_id=uuid.uuid4(), limit=10
    )

    assert result == rows
    # query was issued once; we don't assert on the exact SQL because the
    # filter is applied at the orm level — behaviour is covered by shape.
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_post_cutover_still_returns_rows_but_stmt_has_filter(monkeypatch):
    monkeypatch.setattr(
        client_timeline_reader.settings,
        "client_domain_cutover_read_enabled",
        True,
        raising=False,
    )
    rows = [MagicMock()]
    db = _fake_session(rows)

    result = await client_timeline_reader.read_client_interactions(
        db, client_id=uuid.uuid4()
    )

    assert result == rows
    # the statement passed to db.execute should contain an AND clause with
    # metadata['domain_event_id']. We verify via compile() string.
    call_args = db.execute.await_args
    stmt = call_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "domain_event_id" in compiled, (
        "post-cutover read must filter rows on metadata.domain_event_id"
    )
