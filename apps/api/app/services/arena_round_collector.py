"""Simultaneous round answer collection for PvP Arena.

Manages the lifecycle of a single PvP round:
1. Start round (publish question)
2. Collect answers from all players (atomic, via Redis Lua scripts)
3. Wait for all answers or timeout
4. Calculate speed bonuses
5. Return results for evaluation
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.services.arena_redis import ArenaRedis, SubmitResult

logger = logging.getLogger(__name__)


def calculate_speed_bonuses(
    speed_rankings: list[tuple[str, int]],
    evaluation_players: list[dict],
) -> dict[str, int]:
    """Calculate speed bonuses for correct answers.

    1st correct answer: +3 points
    2nd correct answer: +2 points
    3rd correct answer: +1 point
    4th+ correct answer: +0 points

    Ties (same position/submission time) get the same bonus.
    """
    # Build a set of correct user_ids
    correct_uids = set()
    for p in evaluation_players:
        if p.get("is_correct"):
            correct_uids.add(p.get("user_id"))

    bonuses: dict[str, int] = {}
    correct_rank = 0
    prev_position = -1

    for user_id, position in speed_rankings:
        if user_id in correct_uids:
            # If same position as previous (tie), keep same rank/bonus
            if position != prev_position:
                correct_rank += 1
            prev_position = position
            bonuses[user_id] = max(0, 4 - correct_rank)  # 3, 2, 1, 0
        else:
            bonuses[user_id] = 0

    # Fill in any players not in speed_rankings (didn't answer)
    for p in evaluation_players:
        uid = p.get("user_id")
        if uid and uid not in bonuses:
            bonuses[uid] = 0

    return bonuses


async def wait_for_all_answers(
    arena: ArenaRedis,
    session_id: str,
    round_number: int,
    expected_count: int,
    timeout_seconds: int = 45,
    poll_interval: float = 0.5,
) -> bool:
    """Wait until all players have answered or timeout expires.

    Returns True if all answered, False if timeout.
    Uses polling (not blocking) to remain cancellable.
    """
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        count = await arena.get_round_answer_count(session_id, round_number)
        if count >= expected_count:
            return True
        await asyncio.sleep(poll_interval)

    return False
