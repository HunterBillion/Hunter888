"""Objection chain engine v2: branching + archetype/scenario filtering + extended scoring.

Chains make dialogs non-linear. Instead of random objections, the LLM follows
a pre-defined sequence with BRANCHING based on manager response quality.

Architecture v2:
┌─────────────────────────────────────────────────────────────────────┐
│ Chain: "Ценовая цепочка" (difficulty 5)                             │
│                                                                      │
│ Step 0: "Сколько стоит? 150К?! Дорого!" [price]                    │
│   ├─ on_good_response → step 1 (advance)                            │
│   ├─ on_bad_response  → "fail" (chain fails, penalty)               │
│   └─ on_skip          → step 2 (skip ahead)                         │
│                                                                      │
│ Step 1: "А мне обещали за 30К..." [competitor, TRAP]                │
│   ├─ on_good_response → step 2                                      │
│   ├─ on_bad_response  → step 3 (harder branch)                      │
│   └─ on_skip          → step 2                                      │
│                                                                      │
│ Step 2: "Ну ладно, я подумаю..." [timing, TRAP]                    │
│   ├─ on_good_response → "complete" (chain success)                   │
│   └─ on_bad_response  → "fail"                                      │
│                                                                      │
│ Scoring: step_bonus per step + full_chain_bonus if complete          │
│ Filtering: archetype_codes + scenario_types                          │
└─────────────────────────────────────────────────────────────────────┘

Redis state tracks current step + branching history per session.
LLM receives ONLY the next step to inject — not the whole chain.
"""

import json
import logging
import uuid

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_CHAIN_STATE_KEY = "session:{session_id}:chain"
_CHAIN_STATE_TTL = 7200  # 2 hours


# ---------------------------------------------------------------------------
# Chain selection (archetype + scenario filtering)
# ---------------------------------------------------------------------------

def select_chains_for_session(
    available_chains: list[dict],
    archetype_code: str,
    scenario_type: str,
    difficulty_range: tuple[int, int] = (1, 10),
) -> list[dict]:
    """Filter and rank chains suitable for a given archetype and scenario.

    Returns chains sorted by difficulty (ascending), filtered by:
    - archetype_codes contains archetype_code (or empty = universal)
    - scenario_types contains scenario_type (or empty = universal)
    - difficulty within range

    Args:
        available_chains: All active chains from DB
        archetype_code: Client archetype (e.g. "skeptic")
        scenario_type: Session scenario (e.g. "cold_base")
        difficulty_range: (min, max) difficulty filter

    Returns:
        Filtered and sorted list of chain dicts.
    """
    suitable = []
    for chain in available_chains:
        if not chain.get("is_active", True):
            continue

        diff = chain.get("difficulty", 5)
        if diff < difficulty_range[0] or diff > difficulty_range[1]:
            continue

        # Archetype filter: empty list = universal (all archetypes)
        arch_codes = chain.get("archetype_codes", [])
        if arch_codes and archetype_code not in arch_codes:
            continue

        # Scenario filter: empty list = universal (all scenarios)
        scen_types = chain.get("scenario_types", [])
        if scen_types and scenario_type not in scen_types:
            continue

        suitable.append(chain)

    # Sort by difficulty ascending
    suitable.sort(key=lambda c: c.get("difficulty", 5))
    return suitable


# ---------------------------------------------------------------------------
# Chain state management
# ---------------------------------------------------------------------------

async def init_chain(
    session_id: uuid.UUID,
    chain_id: uuid.UUID,
    steps: list[dict],
    chain_meta: dict | None = None,
) -> None:
    """Initialize chain state in Redis for a new session.

    Args:
        session_id: Training session ID
        chain_id: ObjectionChain ID
        steps: List of step dicts from chain.steps JSONB
        chain_meta: Optional chain metadata (step_bonus, full_chain_bonus, max_score)
    """
    meta = chain_meta or {}
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        key = _CHAIN_STATE_KEY.format(session_id=session_id)
        state = json.dumps({
            "chain_id": str(chain_id),
            "current_step": 0,
            "total_steps": len(steps),
            "steps": steps,
            "completed_steps": [],
            "skipped_steps": [],
            "failed_at_step": None,
            "branch_history": [],  # list of {"from_step": N, "to_step": M, "reason": "good|bad|skip"}
            "finished": False,
            "finish_reason": None,  # "complete" | "fail" | "timeout"
            # Scoring config from chain
            "step_bonus": meta.get("step_bonus", 2),
            "full_chain_bonus": meta.get("full_chain_bonus", 5),
            "max_score": meta.get("max_score", 10),
        })
        await r.set(key, state, ex=_CHAIN_STATE_TTL)
        await r.aclose()
        logger.info(
            "Chain initialized for session %s: %d steps (chain %s)", session_id, len(steps), chain_id
        )
    except Exception:
        logger.warning("Failed to init chain for session %s", session_id)


async def get_chain_state(session_id: uuid.UUID) -> dict | None:
    """Get current chain state from Redis."""
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        key = _CHAIN_STATE_KEY.format(session_id=session_id)
        raw = await r.get(key)
        await r.aclose()
        if raw:
            return json.loads(raw)
    except Exception:
        logger.warning("Failed to get chain state for session %s", session_id)
    return None


# ---------------------------------------------------------------------------
# Branching logic
# ---------------------------------------------------------------------------

def _resolve_branch_target(step: dict, response_quality: str) -> int | str:
    """Resolve the next step based on response quality and branching rules.

    Args:
        step: Current step dict
        response_quality: "good" | "bad" | "skip"

    Returns:
        int (step index) or str ("fail", "complete")
    """
    branch_key = f"on_{response_quality}_response"
    if response_quality == "skip":
        branch_key = "on_skip"

    target = step.get(branch_key)

    if target is None:
        # Default branching: good → next step, bad → fail, skip → next+1
        order = step.get("order", 0)
        if response_quality == "good":
            return order + 1
        elif response_quality == "bad":
            return "fail"
        else:  # skip
            return order + 2

    # Target can be int (step index) or str ("fail", "complete")
    if isinstance(target, int):
        return target
    if isinstance(target, str):
        if target.isdigit():
            return int(target)
        return target  # "fail" or "complete"

    return step.get("order", 0) + 1  # fallback


async def advance_chain(
    session_id: uuid.UUID,
    response_quality: str = "good",
) -> dict | None:
    """Advance the chain based on manager's response quality.

    Args:
        session_id: Training session ID
        response_quality: "good" | "bad" | "skip"

    Returns:
        Dict with next step info, or None if chain is finished.
        {
            "step": {...},
            "step_index": N,
            "total_steps": M,
            "is_last": bool,
            "progress_pct": int,
            "branch_reason": "good|bad|skip",
            "chain_finished": bool,
            "finish_reason": "complete|fail" or None,
        }
    """
    state = await get_chain_state(session_id)
    if state is None or state.get("finished"):
        return None

    current = state["current_step"]
    steps = state["steps"]
    total = state["total_steps"]

    if current >= total:
        state["finished"] = True
        state["finish_reason"] = "complete"
        await _save_chain_state(session_id, state)
        return None

    step = steps[current]

    # Record branch history
    target = _resolve_branch_target(step, response_quality)

    state["branch_history"].append({
        "from_step": current,
        "to_step": target if isinstance(target, int) else -1,
        "reason": response_quality,
    })

    # Track completed / skipped
    if response_quality == "good":
        state["completed_steps"].append(current)
    elif response_quality == "skip":
        state["skipped_steps"].append(current)
    elif response_quality == "bad":
        state["completed_steps"].append(current)  # Still counts as visited

    # Handle terminal targets
    if target == "fail":
        state["finished"] = True
        state["finish_reason"] = "fail"
        state["failed_at_step"] = current
        await _save_chain_state(session_id, state)
        return {
            "step": step,
            "step_index": current,
            "total_steps": total,
            "is_last": True,
            "progress_pct": round(((current + 1) / total) * 100),
            "branch_reason": response_quality,
            "chain_finished": True,
            "finish_reason": "fail",
        }

    if target == "complete":
        state["finished"] = True
        state["finish_reason"] = "complete"
        await _save_chain_state(session_id, state)
        return {
            "step": step,
            "step_index": current,
            "total_steps": total,
            "is_last": True,
            "progress_pct": 100,
            "branch_reason": response_quality,
            "chain_finished": True,
            "finish_reason": "complete",
        }

    # Advance to next step
    next_step_idx = int(target)
    if next_step_idx >= total:
        # Chain completed by reaching beyond last step
        state["finished"] = True
        state["finish_reason"] = "complete"
        await _save_chain_state(session_id, state)
        return {
            "step": step,
            "step_index": current,
            "total_steps": total,
            "is_last": True,
            "progress_pct": 100,
            "branch_reason": response_quality,
            "chain_finished": True,
            "finish_reason": "complete",
        }

    state["current_step"] = next_step_idx
    await _save_chain_state(session_id, state)

    next_step = steps[next_step_idx]
    return {
        "step": next_step,
        "step_index": next_step_idx,
        "total_steps": total,
        "is_last": next_step_idx == total - 1,
        "progress_pct": round(((next_step_idx) / total) * 100),
        "branch_reason": response_quality,
        "chain_finished": False,
        "finish_reason": None,
    }


# ---------------------------------------------------------------------------
# LLM prompt injection
# ---------------------------------------------------------------------------

async def get_next_objection_prompt(session_id: uuid.UUID) -> str:
    """Get the LLM prompt injection for the NEXT objection in the chain.

    Returns a string to append to the system prompt. Empty string if no chain
    or chain is finished.
    """
    state = await get_chain_state(session_id)
    if state is None or state.get("finished"):
        return ""

    current = state["current_step"]
    steps = state["steps"]

    if current >= len(steps):
        return ""

    step = steps[current]
    text = step.get("text", "")
    category = step.get("category", "")
    is_trap = step.get("trap", False)

    lines = [
        "\n## Следующее возражение (цепочка)",
        f"Когда контекст диалога позволяет, используй это возражение:",
        f'"{text}"',
    ]

    if is_trap:
        lines.append(
            "Это ловушка: если менеджер даст неправильный ответ, продолжай давить. "
            "Если ответит правильно — переходи к следующему этапу."
        )
    else:
        lines.append(
            "Это обычное возражение. Если менеджер адекватно ответит, переходи дальше."
        )

    total = len(steps)
    if current > 0 and current < total - 1:
        lines.append(
            f"\nЭто шаг {current + 1} из {total} в цепочке. "
            "Не торопись — дай менеджеру шанс ответить на текущее перед следующим."
        )
    elif current == total - 1:
        lines.append(
            "\nЭто ПОСЛЕДНИЙ шаг цепочки. После него — принимай решение "
            "(продолжить разговор или завершить) на основе качества ответов менеджера."
        )

    # Add branch hints for the LLM
    good_target = step.get("on_good_response")
    bad_target = step.get("on_bad_response")
    if bad_target == "fail":
        lines.append(
            "⚠️ Если менеджер ответит плохо на это возражение — заканчивай разговор негативно."
        )
    elif isinstance(bad_target, int) and bad_target < total:
        bad_step = steps[bad_target]
        lines.append(
            f"Если менеджер ответит плохо, переходи к более жёсткому возражению: "
            f'"{bad_step.get("text", "")}"'
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

async def calculate_chain_score(session_id: uuid.UUID) -> dict:
    """Calculate chain traversal score at session end.

    Extended scoring v2:
    - step_bonus per completed step (configurable, default +2)
    - full_chain_bonus if ALL steps completed (configurable, default +5)
    - Penalty for chain failure: -3
    - Bonus for skipped steps: half of step_bonus
    - Maximum capped at max_score (configurable, default 10)

    Returns dict with score and details for scoring_details JSONB.
    """
    state = await get_chain_state(session_id)
    if state is None:
        return {"chain_score": 0, "chain_details": {"has_chain": False}}

    completed = len(state.get("completed_steps", []))
    skipped = len(state.get("skipped_steps", []))
    total = state["total_steps"]
    finish_reason = state.get("finish_reason")

    # Scoring config from chain (stored at init time)
    step_bonus = state.get("step_bonus", 2)
    full_chain_bonus_val = state.get("full_chain_bonus", 5)
    max_score = state.get("max_score", 10)

    # Calculate
    completed_score = completed * step_bonus
    skipped_score = skipped * max(1, step_bonus // 2)
    fail_penalty = -3 if finish_reason == "fail" else 0
    full_bonus = full_chain_bonus_val if finish_reason == "complete" else 0

    total_score = completed_score + skipped_score + fail_penalty + full_bonus
    total_score = max(-10, min(max_score, total_score))  # Clamp

    return {
        "chain_score": total_score,
        "chain_details": {
            "has_chain": True,
            "chain_id": state.get("chain_id"),
            "completed_steps": completed,
            "skipped_steps": skipped,
            "total_steps": total,
            "finish_reason": finish_reason,
            "branch_history": state.get("branch_history", []),
            "completed_score": completed_score,
            "skipped_score": skipped_score,
            "fail_penalty": fail_penalty,
            "full_chain_bonus": full_bonus,
            "final_score": total_score,
        },
    }


# ---------------------------------------------------------------------------
# System prompt building
# ---------------------------------------------------------------------------

def build_chain_system_prompt(steps: list[dict]) -> str:
    """Build the FULL chain context for the initial system prompt.

    The LLM sees the overall chain structure but delivers one step at a time.
    This is injected ONCE at session start.
    """
    if not steps:
        return ""

    lines = [
        "\n## Цепочка возражений (следуй порядку, не перескакивай!)",
        "У тебя есть заранее подготовленная последовательность возражений.",
        "Используй их ПО ПОРЯДКУ, по одному за раз.",
        "Переходи к следующему только после ответа менеджера на текущее.",
        "Не используй все сразу — естественный темп диалога.",
        "",
    ]

    for step in steps:
        order = step.get("order", 0) + 1
        text = step.get("text", "")
        is_trap = step.get("trap", False)
        category = step.get("category", "")
        trap_mark = " [ЛОВУШКА]" if is_trap else ""
        cat_mark = f" ({category})" if category else ""
        lines.append(f'{order}. "{text}"{trap_mark}{cat_mark}')

        # Show branching hints
        on_bad = step.get("on_bad_response")
        if on_bad == "fail":
            lines.append(f"   → при плохом ответе: ЗАВЕРШИТЬ разговор негативно")
        elif isinstance(on_bad, int):
            lines.append(f"   → при плохом ответе: перейти к шагу {on_bad + 1}")

    lines.append(
        "\nПравила: не нумеруй возражения вслух. "
        "Вплетай их в естественную речь. "
        "Если менеджер увёл тему — верни разговор к цепочке."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Cleanup & persistence helpers
# ---------------------------------------------------------------------------

async def cleanup_chain(session_id: uuid.UUID) -> None:
    """Remove chain state from Redis."""
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        key = _CHAIN_STATE_KEY.format(session_id=session_id)
        await r.delete(key)
        await r.aclose()
    except Exception:
        logger.debug("Chain cleanup failed for session %s", session_id)


async def _save_chain_state(session_id: uuid.UUID, state: dict) -> None:
    """Persist chain state to Redis."""
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        key = _CHAIN_STATE_KEY.format(session_id=session_id)
        await r.set(key, json.dumps(state), ex=_CHAIN_STATE_TTL)
        await r.aclose()
    except Exception:
        logger.warning("Failed to save chain state for session %s", session_id)
