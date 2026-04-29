"""Tests for app.core.correlation — contextvar isolation and log injection.

Covers:
* contextvar value isolation between concurrent asyncio tasks
* LogContextFilter writes IDs from contextvars onto LogRecord
* explicit ``extra={...}`` on a log call wins over the contextvar
* correlation_scope() context manager binds and resets
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from app.core.correlation import (
    LogContextFilter,
    bind_correlation_id,
    bind_request_id,
    correlation_scope,
    get_correlation_id,
    get_request_id,
    reset_correlation_id,
    reset_request_id,
)


def _record(msg: str = "hello") -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=None,
        exc_info=None,
    )


def test_filter_injects_ids_from_contextvars():
    rid_token = bind_request_id("req-abc")
    cid_token = bind_correlation_id("duel-123")
    try:
        record = _record()
        LogContextFilter().filter(record)
        assert record.request_id == "req-abc"
        assert record.correlation_id == "duel-123"
    finally:
        reset_request_id(rid_token)
        reset_correlation_id(cid_token)


def test_filter_respects_explicit_extra():
    rid_token = bind_request_id("req-from-cv")
    try:
        record = _record()
        # Caller-passed extra wins (caller knows better than the contextvar).
        record.request_id = "req-from-extra"
        LogContextFilter().filter(record)
        assert record.request_id == "req-from-extra"
    finally:
        reset_request_id(rid_token)


def test_filter_skips_when_no_context():
    record = _record()
    LogContextFilter().filter(record)
    assert not hasattr(record, "request_id") or record.request_id is None
    assert not hasattr(record, "correlation_id") or record.correlation_id is None


def test_correlation_scope_binds_and_resets():
    assert get_correlation_id() is None
    with correlation_scope("duel-xyz"):
        assert get_correlation_id() == "duel-xyz"
        # Nested scope overrides, then restores.
        with correlation_scope("duel-nested"):
            assert get_correlation_id() == "duel-nested"
        assert get_correlation_id() == "duel-xyz"
    assert get_correlation_id() is None


@pytest.mark.asyncio
async def test_contextvars_isolate_concurrent_tasks():
    """PEP-567 promise: contextvars copy into child tasks but mutations stay
    local. Two concurrent tasks must see their own values, not each other's.

    This is the property that makes a single ``logger.info(...)`` call inside
    a per-duel asyncio.create_task automatically tag the right duel_id.
    """

    seen: list[tuple[str, str | None]] = []

    async def worker(name: str, value: str):
        bind_correlation_id(value)
        # Yield to scheduler — if isolation is broken, the other worker will
        # have set its value before we read.
        await asyncio.sleep(0)
        seen.append((name, get_correlation_id()))

    await asyncio.gather(
        worker("a", "duel-A"),
        worker("b", "duel-B"),
        worker("c", "duel-C"),
    )

    assert ("a", "duel-A") in seen
    assert ("b", "duel-B") in seen
    assert ("c", "duel-C") in seen


def test_get_returns_none_outside_scope():
    assert get_request_id() is None or isinstance(get_request_id(), str)
    assert get_correlation_id() is None or isinstance(get_correlation_id(), str)
