"""Correlation IDs propagated through async tasks via contextvars.

Two independent IDs:

* ``request_id``    — short hex set by ``RequestIDMiddleware`` (HTTP) or
  ``_attach_ws_request_id`` (WS). Mirrors the ``X-Request-ID`` header so a
  log line can be joined with nginx access logs and browser devtools.

* ``correlation_id`` — domain-level identifier (``duel_id`` for arena,
  ``session_id`` for training). Set by handlers when entering a logical
  unit of work; survives spawned ``asyncio.create_task`` calls because
  contextvars are copied into new tasks (PEP 567).

A single ``LogContextFilter`` injects both into every ``LogRecord`` so
existing ``logger.info("...")`` calls automatically get the IDs without
having to pass ``extra={...}`` everywhere. The JSON formatter
(``app.core.logging_config.JSONFormatter``) already whitelists these
fields — no other code changes needed for log enrichment.

Why two IDs, not one: a single request can span multiple correlation
contexts (e.g. an admin endpoint that bulk-finalises 10 duels), and a
single correlation can outlive its originating request (e.g. a duel
that started on REST and continues over WS).
"""

from __future__ import annotations

import contextlib
import logging
from contextvars import ContextVar, Token
from typing import Optional


_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def get_request_id() -> Optional[str]:
    return _request_id.get()


def get_correlation_id() -> Optional[str]:
    return _correlation_id.get()


def bind_request_id(value: Optional[str]) -> Token:
    """Bind a request_id for the current task. Returns a Token usable for reset."""
    return _request_id.set(value)


def bind_correlation_id(value: Optional[str]) -> Token:
    """Bind a correlation_id for the current task. Returns a Token usable for reset."""
    return _correlation_id.set(value)


def reset_request_id(token: Token) -> None:
    _request_id.reset(token)


def reset_correlation_id(token: Token) -> None:
    _correlation_id.reset(token)


@contextlib.contextmanager
def correlation_scope(correlation_id: Optional[str]):
    """Bind a correlation_id for the duration of a ``with`` block.

    Use inside async handlers so that nested logger calls automatically
    pick up the duel/session id without having to pass ``extra=`` through
    every helper.
    """
    token = bind_correlation_id(correlation_id)
    try:
        yield
    finally:
        reset_correlation_id(token)


class LogContextFilter(logging.Filter):
    """Attach request_id and correlation_id from contextvars to each record.

    Idempotent: if a caller already passed ``extra={"request_id": "x"}``
    that takes precedence (we only fill if the attribute is missing).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", None):
            rid = _request_id.get()
            if rid is not None:
                record.request_id = rid
        if not getattr(record, "correlation_id", None):
            cid = _correlation_id.get()
            if cid is not None:
                record.correlation_id = cid
        return True


__all__ = [
    "LogContextFilter",
    "bind_correlation_id",
    "bind_request_id",
    "correlation_scope",
    "get_correlation_id",
    "get_request_id",
    "reset_correlation_id",
    "reset_request_id",
]
