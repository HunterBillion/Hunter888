"""Redis state management for PvP Arena (Knowledge Quiz).

All PvP arena state lives in Redis to support multi-worker Uvicorn deployment.
Uses atomic Lua scripts and pipelines to prevent race conditions.

Key schema:
    arena:challenge:{id}              Hash — challenge metadata
    arena:challenges:active           Set  — active challenge IDs
    arena:match:{id}                  Hash — match metadata
    arena:match:{id}:players          Hash — {user_id: JSON{name,score,correct,connected,is_bot}}
    arena:match:{id}:round:{n}        Hash — round state
    arena:match:{id}:answers:{n}      Hash — {user_id: JSON{text,submitted_at}}
    arena:user:{id}:active_match      Str  — session_id (prevents concurrent matches)
    arena:reconnect:{id}              Str  — session_id (TTL=60s, grace period)
    arena:events:{session_id}         PubSub — per-match events
    arena:events:global               PubSub — global events (challenges, broadcasts)
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

from app.core.redis_pool import get_redis

logger = logging.getLogger(__name__)

# ── Key templates ────────────────────────────────────────────────────────────

CHALLENGE_KEY = "arena:challenge:{challenge_id}"
CHALLENGES_ACTIVE = "arena:challenges:active"
MATCH_KEY = "arena:match:{session_id}"
MATCH_PLAYERS_KEY = "arena:match:{session_id}:players"
MATCH_ROUND_KEY = "arena:match:{session_id}:round:{round_number}"
MATCH_ANSWERS_KEY = "arena:match:{session_id}:answers:{round_number}"
USER_ACTIVE_MATCH = "arena:user:{user_id}:active_match"
RECONNECT_KEY = "arena:reconnect:{user_id}"
MATCH_EVENTS_CHANNEL = "arena:events:{session_id}"
GLOBAL_EVENTS_CHANNEL = "arena:events:global"
MATCH_GAME_LOCK = "arena:match:{session_id}:game_lock"

# TTLs (seconds)
CHALLENGE_TTL = 70  # 60s expiry + 10s buffer
MATCH_TTL = 3600  # 1 hour
ROUND_TTL = 120  # 2 minutes per round data
RECONNECT_TTL = 60  # 60s grace period
GAME_LOCK_TTL = 900  # 15 min max game duration

# ── Lua Scripts ──────────────────────────────────────────────────────────────

LUA_SUBMIT_ANSWER = """
-- Atomic answer submission: only accept if not already answered
-- KEYS[1] = answers hash key, KEYS[2] = round state key
-- ARGV[1] = user_id, ARGV[2] = answer JSON
local existing = redis.call('HEXISTS', KEYS[1], ARGV[1])
if existing == 1 then
    return {0, 0, 0}
end
redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
local count = redis.call('HLEN', KEYS[1])
local expected = tonumber(redis.call('HGET', KEYS[2], 'expected_answers') or '0')
return {1, count, expected}
"""

LUA_ACCEPT_CHALLENGE = """
-- Atomic challenge accept: add user, check if full
-- KEYS[1] = challenge hash key
-- ARGV[1] = user_id, ARGV[2] = user JSON data, ARGV[3] = max_players
local active = redis.call('HGET', KEYS[1], 'is_active')
if active ~= '1' then
    return {0, 0}
end
local accepted_raw = redis.call('HGET', KEYS[1], 'accepted_by') or '[]'
local challenger_id = redis.call('HGET', KEYS[1], 'challenger_id')
if ARGV[1] == challenger_id then
    return {-1, 0}
end
-- Check if already accepted
if string.find(accepted_raw, ARGV[1]) then
    return {-2, 0}
end
-- Add to accepted list
local accepted = cjson.decode(accepted_raw)
table.insert(accepted, cjson.decode(ARGV[2]))
redis.call('HSET', KEYS[1], 'accepted_by', cjson.encode(accepted))
local total = #accepted + 1
local needed = tonumber(ARGV[3])
local is_full = 0
if total >= needed then
    is_full = 1
    redis.call('HSET', KEYS[1], 'is_active', '0')
end
return {1, is_full}
"""


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class ChallengeData:
    challenge_id: str
    challenger_id: str
    challenger_name: str
    category: str | None
    max_players: int
    accepted_by: list[dict]  # [{user_id, name}]
    is_active: bool
    expires_at: float  # unix timestamp
    created_at: float


@dataclass
class MatchData:
    session_id: str
    player_ids: list[str]
    players_info: list[dict]  # [{user_id, name, rating, is_bot}]
    total_rounds: int
    category: str | None
    contains_bot: bool
    status: str  # "active", "completed"
    current_round: int
    created_at: float


@dataclass
class PlayerData:
    user_id: str
    name: str
    score: float
    correct: int
    connected: bool
    is_bot: bool
    rating: float


@dataclass
class SubmitResult:
    accepted: bool
    all_answered: bool
    position: int
    response_time_ms: int
    reason: str | None = None


# ── ArenaRedis class ─────────────────────────────────────────────────────────

class ArenaRedis:
    """Redis operations for the PvP Knowledge Arena.

    All methods are atomic or use pipelines to prevent race conditions
    in multi-worker deployments.
    """

    def __init__(self, redis: aioredis.Redis | None = None):
        self._redis = redis or get_redis()

    @property
    def redis(self) -> aioredis.Redis:
        return self._redis

    # ── Challenge operations ─────────────────────────────────────────────

    async def create_challenge(
        self,
        challenge_id: str,
        challenger_id: str,
        challenger_name: str,
        category: str | None,
        max_players: int,
        expires_at: float,
    ) -> None:
        """Create a new PvP challenge in Redis."""
        key = CHALLENGE_KEY.format(challenge_id=challenge_id)
        now = time.time()

        pipe = self._redis.pipeline()
        pipe.hset(key, mapping={
            "challenge_id": challenge_id,
            "challenger_id": challenger_id,
            "challenger_name": challenger_name,
            "category": category or "",
            "max_players": str(max_players),
            "accepted_by": "[]",
            "is_active": "1",
            "expires_at": str(expires_at),
            "created_at": str(now),
        })
        pipe.expire(key, CHALLENGE_TTL)
        pipe.sadd(CHALLENGES_ACTIVE, challenge_id)
        await pipe.execute()

    async def get_challenge(self, challenge_id: str) -> ChallengeData | None:
        """Get challenge data from Redis."""
        key = CHALLENGE_KEY.format(challenge_id=challenge_id)
        data = await self._redis.hgetall(key)
        if not data:
            return None
        return ChallengeData(
            challenge_id=data["challenge_id"],
            challenger_id=data["challenger_id"],
            challenger_name=data["challenger_name"],
            category=data["category"] or None,
            max_players=int(data["max_players"]),
            accepted_by=json.loads(data.get("accepted_by", "[]")),
            is_active=data["is_active"] == "1",
            expires_at=float(data["expires_at"]),
            created_at=float(data["created_at"]),
        )

    async def accept_challenge(
        self,
        challenge_id: str,
        user_id: str,
        user_name: str,
        max_players: int,
    ) -> tuple[bool, bool]:
        """Atomically accept a challenge.

        Returns: (accepted: bool, match_full: bool)
        Errors: returns (False, False) if challenge expired/invalid
        """
        key = CHALLENGE_KEY.format(challenge_id=challenge_id)
        user_data = json.dumps({"user_id": user_id, "name": user_name})

        result = await self._redis.eval(
            LUA_ACCEPT_CHALLENGE, 1, key,
            user_id, user_data, str(max_players),
        )

        status, is_full = result[0], result[1]
        if status <= 0:
            # 0 = inactive, -1 = self-challenge, -2 = already accepted
            return False, False
        return True, bool(is_full)

    async def expire_challenge(self, challenge_id: str) -> None:
        """Mark challenge as expired."""
        key = CHALLENGE_KEY.format(challenge_id=challenge_id)
        pipe = self._redis.pipeline()
        pipe.hset(key, "is_active", "0")
        pipe.srem(CHALLENGES_ACTIVE, challenge_id)
        await pipe.execute()

    async def get_active_challenges(self) -> list[str]:
        """Get all active challenge IDs."""
        return list(await self._redis.smembers(CHALLENGES_ACTIVE))

    # ── Match operations ─────────────────────────────────────────────────

    async def create_match(
        self,
        session_id: str,
        players_info: list[dict],
        total_rounds: int,
        category: str | None,
        contains_bot: bool = False,
    ) -> None:
        """Create match state in Redis."""
        match_key = MATCH_KEY.format(session_id=session_id)
        players_key = MATCH_PLAYERS_KEY.format(session_id=session_id)
        player_ids = [p["user_id"] for p in players_info]
        now = time.time()

        pipe = self._redis.pipeline()
        pipe.hset(match_key, mapping={
            "session_id": session_id,
            "player_ids": json.dumps(player_ids),
            "players_info": json.dumps(players_info),
            "total_rounds": str(total_rounds),
            "category": category or "",
            "contains_bot": "1" if contains_bot else "0",
            "status": "active",
            "current_round": "0",
            "created_at": str(now),
        })
        pipe.expire(match_key, MATCH_TTL)

        # Per-player state
        for p in players_info:
            pipe.hset(players_key, p["user_id"], json.dumps({
                "name": p["name"],
                "score": 0.0,
                "correct": 0,
                "connected": True,
                "is_bot": p.get("is_bot", False),
                "rating": p.get("rating", 1500.0),
            }))
        pipe.expire(players_key, MATCH_TTL)

        # Block concurrent matches per user
        for p in players_info:
            if not p.get("is_bot", False):
                user_match_key = USER_ACTIVE_MATCH.format(user_id=p["user_id"])
                pipe.setex(user_match_key, MATCH_TTL, session_id)

        await pipe.execute()

    async def get_match(self, session_id: str) -> MatchData | None:
        """Get match metadata."""
        key = MATCH_KEY.format(session_id=session_id)
        data = await self._redis.hgetall(key)
        if not data:
            return None
        return MatchData(
            session_id=data["session_id"],
            player_ids=json.loads(data["player_ids"]),
            players_info=json.loads(data["players_info"]),
            total_rounds=int(data["total_rounds"]),
            category=data["category"] or None,
            contains_bot=data["contains_bot"] == "1",
            status=data["status"],
            current_round=int(data["current_round"]),
            created_at=float(data["created_at"]),
        )

    async def set_match_round(self, session_id: str, round_number: int) -> None:
        """Update current round number."""
        key = MATCH_KEY.format(session_id=session_id)
        await self._redis.hset(key, "current_round", str(round_number))

    async def set_match_contains_bot(self, session_id: str) -> None:
        """Mark match as containing a bot (no rating changes)."""
        key = MATCH_KEY.format(session_id=session_id)
        await self._redis.hset(key, "contains_bot", "1")

    async def complete_match(self, session_id: str) -> None:
        """Mark match as completed."""
        key = MATCH_KEY.format(session_id=session_id)
        await self._redis.hset(key, "status", "completed")

    async def get_user_active_match(self, user_id: str) -> str | None:
        """Check if user is already in an active match."""
        key = USER_ACTIVE_MATCH.format(user_id=user_id)
        return await self._redis.get(key)

    async def clear_user_active_match(self, user_id: str) -> None:
        """Remove active match lock for a user."""
        key = USER_ACTIVE_MATCH.format(user_id=user_id)
        await self._redis.delete(key)

    # ── Player operations ────────────────────────────────────────────────

    async def get_player(self, session_id: str, user_id: str) -> PlayerData | None:
        """Get player data from match."""
        key = MATCH_PLAYERS_KEY.format(session_id=session_id)
        raw = await self._redis.hget(key, user_id)
        if not raw:
            return None
        data = json.loads(raw)
        return PlayerData(
            user_id=user_id,
            name=data["name"],
            score=data["score"],
            correct=data["correct"],
            connected=data["connected"],
            is_bot=data["is_bot"],
            rating=data.get("rating", 1500.0),
        )

    async def get_all_players(self, session_id: str) -> list[PlayerData]:
        """Get all players in a match."""
        key = MATCH_PLAYERS_KEY.format(session_id=session_id)
        raw_all = await self._redis.hgetall(key)
        players = []
        for uid, raw in raw_all.items():
            data = json.loads(raw)
            players.append(PlayerData(
                user_id=uid,
                name=data["name"],
                score=data["score"],
                correct=data["correct"],
                connected=data["connected"],
                is_bot=data["is_bot"],
                rating=data.get("rating", 1500.0),
            ))
        return players

    async def update_player_score(
        self, session_id: str, user_id: str, score_delta: float, is_correct: bool,
    ) -> None:
        """Atomically update player score and correct count."""
        key = MATCH_PLAYERS_KEY.format(session_id=session_id)
        raw = await self._redis.hget(key, user_id)
        if not raw:
            return
        data = json.loads(raw)
        data["score"] = data["score"] + score_delta
        if is_correct:
            data["correct"] = data["correct"] + 1
        await self._redis.hset(key, user_id, json.dumps(data))

    async def set_player_connected(
        self, session_id: str, user_id: str, connected: bool,
    ) -> None:
        """Update player connection status."""
        key = MATCH_PLAYERS_KEY.format(session_id=session_id)
        raw = await self._redis.hget(key, user_id)
        if not raw:
            return
        data = json.loads(raw)
        data["connected"] = connected
        await self._redis.hset(key, user_id, json.dumps(data))

    # ── Round operations ─────────────────────────────────────────────────

    async def start_round(
        self,
        session_id: str,
        round_number: int,
        question: dict,
        expected_answers: int,
        timeout_seconds: int = 45,
    ) -> None:
        """Initialize a round in Redis."""
        round_key = MATCH_ROUND_KEY.format(session_id=session_id, round_number=round_number)
        answers_key = MATCH_ANSWERS_KEY.format(session_id=session_id, round_number=round_number)
        now = time.time()

        pipe = self._redis.pipeline()
        pipe.hset(round_key, mapping={
            "question": json.dumps(question),
            "started_at": str(now),
            "deadline": str(now + timeout_seconds),
            "status": "collecting",
            "expected_answers": str(expected_answers),
        })
        pipe.expire(round_key, ROUND_TTL)
        pipe.expire(answers_key, ROUND_TTL)
        await pipe.execute()

    async def submit_answer(
        self,
        session_id: str,
        round_number: int,
        user_id: str,
        answer_text: str,
    ) -> SubmitResult:
        """Atomically submit an answer for a round."""
        round_key = MATCH_ROUND_KEY.format(session_id=session_id, round_number=round_number)
        answers_key = MATCH_ANSWERS_KEY.format(session_id=session_id, round_number=round_number)

        # Check deadline
        deadline_str = await self._redis.hget(round_key, "deadline")
        if not deadline_str:
            return SubmitResult(accepted=False, all_answered=False, position=0,
                                response_time_ms=0, reason="round_not_found")

        now = time.time()
        deadline = float(deadline_str)
        if now > deadline:
            return SubmitResult(accepted=False, all_answered=False, position=0,
                                response_time_ms=0, reason="timeout")

        started_at_str = await self._redis.hget(round_key, "started_at")
        started_at = float(started_at_str) if started_at_str else now

        answer_data = json.dumps({
            "text": answer_text,
            "submitted_at": now,
        })

        result = await self._redis.eval(
            LUA_SUBMIT_ANSWER, 2, answers_key, round_key,
            user_id, answer_data,
        )

        accepted, count, expected = int(result[0]), int(result[1]), int(result[2])
        response_time_ms = int((now - started_at) * 1000)

        if not accepted:
            return SubmitResult(
                accepted=False, all_answered=False, position=0,
                response_time_ms=response_time_ms, reason="already_answered",
            )

        return SubmitResult(
            accepted=True,
            all_answered=count >= expected,
            position=count,
            response_time_ms=response_time_ms,
        )

    async def get_round_started_at(
        self, session_id: str, round_number: int,
    ) -> float | None:
        """Get the Unix timestamp when the round started."""
        key = MATCH_ROUND_KEY.format(session_id=session_id, round_number=round_number)
        val = await self._redis.hget(key, "started_at")
        return float(val) if val else None

    async def get_round_answers(
        self, session_id: str, round_number: int,
    ) -> dict[str, dict]:
        """Get all submitted answers for a round."""
        key = MATCH_ANSWERS_KEY.format(session_id=session_id, round_number=round_number)
        raw_all = await self._redis.hgetall(key)
        return {uid: json.loads(data) for uid, data in raw_all.items()}

    async def get_round_answer_count(
        self, session_id: str, round_number: int,
    ) -> int:
        """Get number of submitted answers."""
        key = MATCH_ANSWERS_KEY.format(session_id=session_id, round_number=round_number)
        return await self._redis.hlen(key)

    async def get_speed_rankings(
        self, session_id: str, round_number: int,
    ) -> list[tuple[str, int]]:
        """Return [(user_id, rank)] sorted by submission time."""
        answers = await self.get_round_answers(session_id, round_number)
        sorted_by_time = sorted(
            [(uid, data) for uid, data in answers.items() if data.get("submitted_at")],
            key=lambda x: x[1]["submitted_at"],
        )
        return [(uid, rank + 1) for rank, (uid, _) in enumerate(sorted_by_time)]

    # ── Disconnect / Reconnect ───────────────────────────────────────────

    async def set_reconnect_grace(self, user_id: str, session_id: str) -> None:
        """Set reconnect grace period for a disconnected player."""
        key = RECONNECT_KEY.format(user_id=user_id)
        await self._redis.setex(key, RECONNECT_TTL, session_id)

    async def check_reconnect(self, user_id: str) -> str | None:
        """Check if user has a reconnect grace period active. Returns session_id."""
        key = RECONNECT_KEY.format(user_id=user_id)
        return await self._redis.get(key)

    async def clear_reconnect(self, user_id: str) -> None:
        """Clear reconnect grace period (player reconnected)."""
        key = RECONNECT_KEY.format(user_id=user_id)
        await self._redis.delete(key)

    # ── Pub/Sub ──────────────────────────────────────────────────────────

    async def publish_match_event(self, session_id: str, event: dict) -> None:
        """Publish event to match-specific channel."""
        channel = MATCH_EVENTS_CHANNEL.format(session_id=session_id)
        await self._redis.publish(channel, json.dumps(event))

    async def publish_global_event(self, event: dict) -> None:
        """Publish event to global arena channel."""
        await self._redis.publish(GLOBAL_EVENTS_CHANNEL, json.dumps(event))

    def subscribe_match(self, session_id: str) -> aioredis.client.PubSub:
        """Get a PubSub subscriber for a match channel."""
        pubsub = self._redis.pubsub()
        return pubsub

    async def subscribe_match_events(
        self, session_id: str, pubsub: aioredis.client.PubSub,
    ) -> None:
        """Subscribe to match events."""
        channel = MATCH_EVENTS_CHANNEL.format(session_id=session_id)
        await pubsub.subscribe(channel)

    async def subscribe_global_events(
        self, pubsub: aioredis.client.PubSub,
    ) -> None:
        """Subscribe to global arena events."""
        await pubsub.subscribe(GLOBAL_EVENTS_CHANNEL)

    # ── Distributed Lock ─────────────────────────────────────────────────

    async def acquire_game_lock(self, session_id: str) -> bool:
        """Try to acquire game loop lock (only one worker runs the game)."""
        key = MATCH_GAME_LOCK.format(session_id=session_id)
        # SET NX with TTL — atomic
        return bool(await self._redis.set(key, "1", nx=True, ex=GAME_LOCK_TTL))

    async def release_game_lock(self, session_id: str) -> None:
        """Release game loop lock."""
        key = MATCH_GAME_LOCK.format(session_id=session_id)
        await self._redis.delete(key)

    async def extend_game_lock(self, session_id: str, seconds: int = 60) -> None:
        """Extend game lock TTL (heartbeat from game loop)."""
        key = MATCH_GAME_LOCK.format(session_id=session_id)
        await self._redis.expire(key, seconds)

    # ── Cleanup ──────────────────────────────────────────────────────────

    async def cleanup_match(self, session_id: str) -> None:
        """Clean up all Redis keys for a match (delayed, after grace period)."""
        match_key = MATCH_KEY.format(session_id=session_id)
        players_key = MATCH_PLAYERS_KEY.format(session_id=session_id)
        lock_key = MATCH_GAME_LOCK.format(session_id=session_id)

        # Get player IDs to clean up user active match
        match_data = await self.get_match(session_id)
        if match_data:
            pipe = self._redis.pipeline()
            for pid in match_data.player_ids:
                user_match_key = USER_ACTIVE_MATCH.format(user_id=pid)
                pipe.delete(user_match_key)
            await pipe.execute()

        # Set short TTL on match keys (keep for 5 min for late reconnects)
        pipe = self._redis.pipeline()
        pipe.expire(match_key, 300)
        pipe.expire(players_key, 300)
        pipe.delete(lock_key)

        # Clean up round/answer keys
        if match_data:
            for rn in range(1, match_data.total_rounds + 1):
                round_key = MATCH_ROUND_KEY.format(session_id=session_id, round_number=rn)
                answers_key = MATCH_ANSWERS_KEY.format(session_id=session_id, round_number=rn)
                pipe.expire(round_key, 300)
                pipe.expire(answers_key, 300)

        await pipe.execute()


def get_arena_redis() -> ArenaRedis:
    """Get ArenaRedis instance using the shared connection pool."""
    return ArenaRedis(get_redis())
