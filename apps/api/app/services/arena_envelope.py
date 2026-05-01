"""Envelope for arena events flowing through the bus (Эпик 2).

Every cross-component message in the arena — WS-event broadcast, AI-call
result, state-machine transition, finalize attempt — gets wrapped in an
``ArenaEvent`` before publishing to the bus. The envelope carries:

* ``msg_id``         — bus-level dedup key (uuid hex). Consumers track
  processed ids to make replays idempotent.
* ``correlation_id`` — joins all events of one logical unit (duel_id,
  session_id, queue_id). Same value the LogContextFilter (PR A) writes
  into JSON logs, so a Loki/CloudWatch query joins logs ↔ bus events.
* ``type``           — short event name like ``duel.message``,
  ``judge.degraded``, ``match.found``. Mirrors the WS-event-type on the
  wire (intentional — WS protocol stays the canonical contract).
* ``payload``        — event body as a JSON-serialisable dict.
* ``producer``       — short identifier of the emitting subsystem
  (``ws.pvp.handler``, ``matchmaker.task``, ``pvp_judge``).
* ``ts``             — emit time (``time.time()``).
* ``version``        — envelope schema version. Bumped only when the
  envelope itself changes (rare); payload schema versioning is the
  caller's responsibility (e.g. via the ``type`` discriminator).

Why a custom envelope rather than re-using the WS-event shape directly:
the WS-event is the contract with the FE and must stay back-compat;
the envelope is internal and can carry strictly-typed bus metadata
without polluting the FE schema.

Redis Streams stores fields as a flat ``{str: str}`` map per entry;
``to_redis()`` / ``from_redis()`` convert on the wire so consumers don't
have to know the on-disk shape.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any


_ENVELOPE_VERSION = 1


@dataclass(frozen=True)
class ArenaEvent:
    """Immutable bus envelope. Construct via ``ArenaEvent.create(...)``."""

    msg_id: str
    correlation_id: str
    type: str
    payload: dict[str, Any]
    producer: str
    ts: float
    version: int = _ENVELOPE_VERSION

    @classmethod
    def create(
        cls,
        *,
        type: str,
        payload: dict[str, Any],
        correlation_id: str | None = None,
        producer: str = "unknown",
    ) -> "ArenaEvent":
        """Stamp a fresh ``msg_id`` + ``ts`` and return a ready-to-publish event."""
        return cls(
            msg_id=uuid.uuid4().hex,
            correlation_id=correlation_id or "",
            type=type,
            payload=payload,
            producer=producer,
            ts=time.time(),
        )

    def to_redis(self) -> dict[str, str]:
        """Flatten to a string-only mapping suitable for ``XADD`` fields.

        Redis Streams require all values be bytes/str; we serialise
        ``payload`` as JSON and stringify scalars. Round-trips through
        ``from_redis`` losslessly.
        """
        return {
            "msg_id": self.msg_id,
            "correlation_id": self.correlation_id,
            "type": self.type,
            "payload": json.dumps(self.payload, ensure_ascii=False, default=str),
            "producer": self.producer,
            "ts": repr(self.ts),
            "version": str(self.version),
        }

    @classmethod
    def from_redis(cls, fields: dict[str, str]) -> "ArenaEvent":
        """Inverse of ``to_redis``. Raises ``KeyError`` on missing fields
        (we deliberately don't paper over a malformed envelope — the
        consumer should ack-and-skip on ValueError instead of silent drop).
        """
        return cls(
            msg_id=fields["msg_id"],
            correlation_id=fields["correlation_id"],
            type=fields["type"],
            payload=json.loads(fields["payload"]) if fields.get("payload") else {},
            producer=fields["producer"],
            ts=float(fields["ts"]),
            version=int(fields.get("version", _ENVELOPE_VERSION)),
        )


__all__ = ["ArenaEvent"]
