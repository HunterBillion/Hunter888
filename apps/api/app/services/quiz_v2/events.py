"""quiz_v2.events — server-issued IDs and ArenaBus publish helpers (A0 skeleton).

Owns the wire-protocol identity layer. Every event carries an
``answer_id`` (server-allocated UUID v4) so the client and server can
dedup independently. No event is ever identified by chat position.

Events emitted (server → client):
  - quiz_v2.question.shown         (idempotent on question_id)
  - quiz_v2.answer.accepted        (idempotent on answer_id)
  - quiz_v2.verdict.emitted        (idempotent on answer_id)
  - quiz_v2.explanation.streamed   (append-only by (answer_id, seq))
  - quiz_v2.explanation.completed  (idempotent on answer_id)
  - quiz_v2.score.updated          (replace state)
  - quiz_v2.session.expired        (terminal)

Every event is also published through ``services.arena_bus.publish``
(when ``arena_bus_dual_write_enabled``) so AuditLogConsumer captures it
without parallel infrastructure.

Design doc: docs/QUIZ_V2_ARENA_DESIGN.md §5.
A0 contains the public surface only. A4 fills in the publish path.
"""

from __future__ import annotations

import uuid


def new_answer_id() -> str:
    """Allocate a fresh ``answer_id`` for a user submission.

    UUID v4 hex; server is the only source. Echoed in every subsequent
    event for that answer so client + server dedup independently.
    """

    return uuid.uuid4().hex


async def publish_verdict(
    *,
    correlation_id: str,
    payload: dict,
) -> None:
    """Publish a ``quiz_v2.verdict.emitted`` event through ArenaBus.

    A0 implementation: raises ``NotImplementedError``. A4 wires this to
    ``arena_bus.publish(ArenaEvent.create(...))`` and gates on
    ``settings.arena_bus_dual_write_enabled``.
    """

    raise NotImplementedError("quiz_v2.events.publish_verdict — A0 skeleton, A4 will implement")
