"""Regression tests for Issue #169 — backend pickup of `character_id`.

Before this PR, FE sent `character_id` in queue.join WS payload and
`/pvp/accept-pve` REST body, but the matchmaker silently dropped it. As a
result the «Расширенные настройки: персонаж» picker on /pvp had zero
runtime effect — the bot archetype was always `random.choice` from
`_PVP_ARCHETYPES`, regardless of which CustomCharacter the user picked.

These tests prove the new wiring:

  1. ``join_queue(..., character_id=X)`` writes the UUID into the queue
     meta hash so a downstream PvE-fallback can resolve it.
  2. ``create_pve_duel(..., character_id=X)`` looks up the CustomCharacter
     and writes ``archetype`` + sibling fields into ``duel.pve_metadata``,
     where ``ws/pvp.py:_ensure_session`` already reads it.
  3. When ``character_id`` is None but the queue meta has one,
     ``create_pve_duel`` falls back to the meta value (REST
     `/pvp/accept-pve` path which doesn't carry the id in the body).
  4. When the chosen character belongs to another user and is not
     ``is_shared``, the lookup returns nothing and pve_metadata stays
     None (random archetype, no leak).
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest


class _FakeRedis:
    """Minimal in-memory Redis replacement for matchmaker tests.

    Implements just enough of the redis-py async surface to exercise
    `join_queue` + `create_pve_duel`: hashes (hset/hget), sorted sets
    (zadd/zscore/zrem/zcard), expire/delete. No persistence, no TTL
    enforcement — the unit under test doesn't depend on those.
    """

    def __init__(self):
        self.hashes: dict[str, dict[str, str]] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.scalars: dict[str, str] = {}

    async def hset(self, key, mapping=None, **_):
        slot = self.hashes.setdefault(key, {})
        if mapping:
            slot.update({str(k): str(v) for k, v in mapping.items()})
        return len(slot)

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def expire(self, key, _ttl):
        return 1

    async def delete(self, *keys):
        n = 0
        for k in keys:
            if k in self.hashes:
                del self.hashes[k]; n += 1
            if k in self.zsets:
                del self.zsets[k]; n += 1
            if k in self.scalars:
                del self.scalars[k]; n += 1
        return n

    async def set(self, key, val, nx=False, ex=None):
        if nx and key in self.scalars:
            return None
        self.scalars[key] = str(val)
        return True

    async def get(self, key):
        return self.scalars.get(key)

    async def zadd(self, key, mapping):
        slot = self.zsets.setdefault(key, {})
        for member, score in mapping.items():
            slot[str(member)] = float(score)
        return len(mapping)

    async def zscore(self, key, member):
        return self.zsets.get(key, {}).get(str(member))

    async def zrem(self, key, *members):
        slot = self.zsets.get(key, {})
        n = 0
        for m in members:
            if str(m) in slot:
                del slot[str(m)]; n += 1
        return n

    async def zcard(self, key):
        return len(self.zsets.get(key, {}))


@pytest.fixture
def fake_redis():
    """Patch get_redis() everywhere matchmaker / api uses it."""
    fr = _FakeRedis()
    with patch("app.core.redis_pool.get_redis", return_value=fr), \
         patch("app.services.pvp_matchmaker._redis", return_value=fr):
        yield fr


@pytest.mark.asyncio
async def test_join_queue_persists_character_id_in_meta(
    fake_redis, db_session, user_factory,
):
    from app.models.user import User
    from app.services.pvp_matchmaker import QUEUE_META_KEY, join_queue

    me = User(**user_factory())
    db_session.add(me)
    await db_session.commit()

    cid = uuid.uuid4()
    await join_queue(me.id, db_session, character_id=cid)

    raw = await fake_redis.hget(QUEUE_META_KEY.format(user_id=me.id), "character_id")
    assert raw == str(cid)


@pytest.mark.asyncio
async def test_join_queue_without_character_id_does_not_set_field(
    fake_redis, db_session, user_factory,
):
    """No regression: existing callers (REST invitation flow, queue.watch)
    that don't pass character_id must not get a phantom key in meta hash."""
    from app.models.user import User
    from app.services.pvp_matchmaker import QUEUE_META_KEY, join_queue

    me = User(**user_factory())
    db_session.add(me)
    await db_session.commit()

    await join_queue(me.id, db_session)
    meta = await fake_redis.hgetall(QUEUE_META_KEY.format(user_id=me.id))
    assert "character_id" not in meta
    assert "rating" in meta  # baseline keys still present


@pytest.mark.asyncio
async def test_create_pve_duel_uses_explicit_character(
    fake_redis, db_session, user_factory,
):
    """character_id passed explicitly → archetype copied into pve_metadata."""
    from app.models.custom_character import CustomCharacter
    from app.models.user import User
    from app.services.pvp_matchmaker import create_pve_duel

    me = User(**user_factory())
    db_session.add(me)
    await db_session.commit()

    cc = CustomCharacter(
        id=uuid.uuid4(),
        user_id=me.id,
        name="Тестовый скептик",
        archetype="skeptic",
        profession="лавочник",
        lead_source="ozon",
        difficulty=5,
        tone="harsh",
        emotion_preset="neutral",
        is_shared=False,
    )
    db_session.add(cc)
    await db_session.commit()

    duel = await create_pve_duel(me.id, db_session, character_id=cc.id)

    assert duel.pve_metadata is not None
    assert duel.pve_metadata["archetype"] == "skeptic"
    assert duel.pve_metadata["custom_character_id"] == str(cc.id)
    assert duel.pve_metadata["tone"] == "harsh"
    assert duel.pve_metadata["profession"] == "лавочник"
    assert duel.pve_metadata["emotion_preset"] == "neutral"


@pytest.mark.asyncio
async def test_create_pve_duel_falls_back_to_queue_meta(
    fake_redis, db_session, user_factory,
):
    """character_id=None + queue meta hash has it → duel still picks it up.

    Reproduces REST `/pvp/accept-pve` flow: FE chose a character at
    queue.join WS time, then 58s timer fired and the FE called the REST
    endpoint without a body. The endpoint reads queue meta and forwards.
    """
    from app.models.custom_character import CustomCharacter
    from app.models.user import User
    from app.services.pvp_matchmaker import QUEUE_META_KEY, create_pve_duel

    me = User(**user_factory())
    db_session.add(me)
    await db_session.commit()

    cc = CustomCharacter(
        id=uuid.uuid4(),
        user_id=me.id,
        name="Test paranoid",
        archetype="paranoid",
        profession="riding instructor",
        lead_source="vk",
        difficulty=7,
        is_shared=False,
    )
    db_session.add(cc)
    await db_session.commit()

    # Simulate join_queue having recorded character_id in meta hash
    await fake_redis.hset(
        QUEUE_META_KEY.format(user_id=me.id),
        mapping={"character_id": str(cc.id)},
    )

    duel = await create_pve_duel(me.id, db_session, character_id=None)

    assert duel.pve_metadata is not None
    assert duel.pve_metadata["archetype"] == "paranoid"
    assert duel.pve_metadata["custom_character_id"] == str(cc.id)


@pytest.mark.asyncio
async def test_create_pve_duel_rejects_other_users_private_character(
    fake_redis, db_session, user_factory,
):
    """Picking another user's NON-shared preset → meta stays None (random)."""
    from app.models.custom_character import CustomCharacter
    from app.models.user import User
    from app.services.pvp_matchmaker import create_pve_duel

    me = User(**user_factory())
    other = User(**user_factory(email="other@trainer.local"))
    db_session.add_all([me, other])
    await db_session.commit()

    cc = CustomCharacter(
        id=uuid.uuid4(),
        user_id=other.id,
        name="Stranger's preset",
        archetype="manipulator",
        profession="lawyer",
        lead_source="vk",
        difficulty=5,
        is_shared=False,
    )
    db_session.add(cc)
    await db_session.commit()

    duel = await create_pve_duel(me.id, db_session, character_id=cc.id)

    # Lookup must reject — pve_metadata must NOT carry the rejected character.
    assert duel.pve_metadata is None or "custom_character_id" not in (duel.pve_metadata or {})


@pytest.mark.asyncio
async def test_create_pve_duel_accepts_shared_character(
    fake_redis, db_session, user_factory,
):
    """``is_shared=True`` preset created by another user is reachable for everyone."""
    from app.models.custom_character import CustomCharacter
    from app.models.user import User
    from app.services.pvp_matchmaker import create_pve_duel

    me = User(**user_factory())
    other = User(**user_factory(email="author@trainer.local"))
    db_session.add_all([me, other])
    await db_session.commit()

    cc = CustomCharacter(
        id=uuid.uuid4(),
        user_id=other.id,
        name="Public sample",
        archetype="aggressive",
        profession="contractor",
        lead_source="ozon",
        difficulty=6,
        is_shared=True,
    )
    db_session.add(cc)
    await db_session.commit()

    duel = await create_pve_duel(me.id, db_session, character_id=cc.id)

    assert duel.pve_metadata is not None
    assert duel.pve_metadata["archetype"] == "aggressive"
