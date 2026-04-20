"""Arena power-ups — active mid-match modifiers (×2 XP, shield, etc.).

Phase C (2026-04-20). Lifelines (hint / skip / 50-50) are *passive*
helpers — they surface data or debit a round. Power-ups are *active*
modifiers — they change the next answer's scoring rules.

v1 ships **`doublexp`** only (the "×2 очков на следующий правильный
ответ" button). Architecture is generalised for future power-ups
(`shield`, `freeze_opponent`, `steal_xp`, etc.) — add a new entry to
``POWERUP_DEFS`` and a matching case in ``pop_active_multiplier`` /
UI.

Storage:
  * ``powerup:quota:{session_id}:{user_id}``       — remaining charges per kind (JSON)
  * ``powerup:active:{session_id}:{user_id}``      — currently armed power-up kind (single-arm for v1, 120 s TTL)

Fail-open: every function degrades gracefully if Redis is down — no
exception bubbles to the WS layer; the user just sees "нет зарядов"
or plays without the modifier.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal, Optional

logger = logging.getLogger(__name__)

Mode = Literal["arena", "duel", "rapid", "pve", "tournament"]
Kind = Literal["doublexp"]


@dataclass(frozen=True)
class PowerupDef:
    kind: Kind
    title_ru: str
    multiplier: float                 # applied to score_delta on successful answer
    quota_by_mode: dict[Mode, int]    # how many charges per match by mode
    arm_ttl_seconds: int = 120        # how long the "armed" state stays hot


POWERUP_DEFS: dict[Kind, PowerupDef] = {
    "doublexp": PowerupDef(
        kind="doublexp",
        title_ru="×2 очков",
        multiplier=2.0,
        quota_by_mode={
            "arena": 1,
            "duel": 0,        # duel scoring is qualitative, judge-based — skip
            "rapid": 1,
            "pve": 2,         # practice-friendly
            "tournament": 0,  # no modifiers on the road to glory
        },
        arm_ttl_seconds=120,
    ),
}


def _quota_key(session_id: str, user_id: str) -> str:
    return f"powerup:quota:{session_id}:{user_id}"


def _active_key(session_id: str, user_id: str) -> str:
    return f"powerup:active:{session_id}:{user_id}"


REDIS_QUOTA_TTL_SECONDS = 60 * 60 * 2  # 2 h — same as lifelines


async def init_for_match(
    *, session_id: str, user_id: str, mode: Mode,
) -> dict[Kind, int]:
    """Seed the per-match quota for this user. Idempotent via SETNX."""

    quota: dict[Kind, int] = {
        k: d.quota_by_mode.get(mode, 0) for k, d in POWERUP_DEFS.items()
    }
    try:
        from app.core.redis_pool import get_redis

        r = get_redis()
        key = _quota_key(session_id, user_id)
        existing = await r.get(key)
        if not existing:
            await r.setex(key, REDIS_QUOTA_TTL_SECONDS, json.dumps(quota))
    except Exception:  # noqa: BLE001 — fail-open
        logger.debug("powerups.init_for_match redis miss", exc_info=True)
    return quota


async def get_remaining(
    *, session_id: str, user_id: str,
) -> dict[str, int]:
    try:
        from app.core.redis_pool import get_redis

        r = get_redis()
        raw = await r.get(_quota_key(session_id, user_id))
        if not raw:
            return {k: 0 for k in POWERUP_DEFS}
        data = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode())
        return {k: int(data.get(k, 0)) for k in POWERUP_DEFS}
    except Exception:
        logger.debug("powerups.get_remaining redis miss", exc_info=True)
        return {k: 0 for k in POWERUP_DEFS}


async def activate(
    *, session_id: str, user_id: str, kind: Kind,
) -> tuple[bool, Optional[str]]:
    """Atomically consume one charge of ``kind`` AND arm the active slot.

    Returns ``(consumed, reason)``. ``reason`` is a short error key on
    failure: ``"no_quota"``, ``"already_armed"``, ``"unknown_kind"``,
    ``"storage_error"``.

    v1 single-arm contract: the user can only have ONE active power-up
    at a time. If another is already armed, this call fails — prevents
    stacking effects we haven't tuned for yet.
    """

    defn = POWERUP_DEFS.get(kind)
    if defn is None:
        return False, "unknown_kind"

    try:
        from app.core.redis_pool import get_redis

        r = get_redis()

        # Reject if something is already armed.
        already = await r.get(_active_key(session_id, user_id))
        if already:
            return False, "already_armed"

        quota_key = _quota_key(session_id, user_id)
        raw = await r.get(quota_key)
        if not raw:
            return False, "no_quota"
        data = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode())
        if int(data.get(kind, 0)) <= 0:
            return False, "no_quota"

        # Debit charge + arm in a pair of writes. Not strictly atomic
        # across both keys, but acceptable: the failure mode of a crash
        # between them is "user lost a charge without arming", which is
        # correct from the player's POV (they can retry; quota reflects
        # the ledger truth).
        data[kind] = int(data[kind]) - 1
        await r.setex(quota_key, REDIS_QUOTA_TTL_SECONDS, json.dumps(data))
        await r.setex(_active_key(session_id, user_id), defn.arm_ttl_seconds, kind)
        logger.info(
            "powerup.activate session=%s user=%s kind=%s remaining=%s",
            session_id, user_id, kind, data[kind],
        )
        return True, None
    except Exception:
        logger.debug("powerups.activate redis error", exc_info=True)
        return False, "storage_error"


async def peek_active(
    *, session_id: str, user_id: str,
) -> Optional[Kind]:
    """Return the currently armed power-up kind (or None)."""
    try:
        from app.core.redis_pool import get_redis

        r = get_redis()
        raw = await r.get(_active_key(session_id, user_id))
        if not raw:
            return None
        kind = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
        if kind in POWERUP_DEFS:
            return kind  # type: ignore[return-value]
        return None
    except Exception:
        logger.debug("powerups.peek_active redis miss", exc_info=True)
        return None


async def pop_active_multiplier(
    *, session_id: str, user_id: str,
) -> float:
    """Consume the armed power-up (if any) and return the score multiplier
    to apply to the current answer.

    Called from the answer-scoring path in ``services/knowledge_quiz.py``.
    Returns ``1.0`` when nothing is armed — safe default.
    """

    try:
        from app.core.redis_pool import get_redis

        r = get_redis()
        key = _active_key(session_id, user_id)
        raw = await r.get(key)
        if not raw:
            return 1.0
        kind_s = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
        defn = POWERUP_DEFS.get(kind_s)  # type: ignore[arg-type]
        # Single-use: delete the armed slot regardless of success so the
        # effect cannot linger into the next round.
        await r.delete(key)
        if defn is None:
            return 1.0
        return float(defn.multiplier)
    except Exception:
        logger.debug("powerups.pop_active_multiplier redis error", exc_info=True)
        return 1.0


async def clear_active(
    *, session_id: str, user_id: str,
) -> bool:
    """Explicitly drop the armed power-up without applying effect.

    Useful when the player skips the round: we don't want their ×2 to
    burn on an empty answer.
    """

    try:
        from app.core.redis_pool import get_redis

        r = get_redis()
        await r.delete(_active_key(session_id, user_id))
        return True
    except Exception:
        logger.debug("powerups.clear_active redis error", exc_info=True)
        return False
