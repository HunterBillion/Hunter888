"""Real-time per-message anti-cheat checks for PvP duels.

Lightweight checks that run on EVERY message during an active duel.
No DB queries, no LLM calls — purely in-memory, O(1) per message.

The full post-match analysis (anti_cheat.py) remains unchanged and runs
after duel completion for deep statistical/behavioral/AI detection.

Architecture:
┌────────────────────────────────────────────────────────────────────┐
│  Per-message (this module)              Post-match (anti_cheat.py) │
│  ─────────────────────────              ──────────────────────────  │
│  • Latency vs length check              • Statistical (50 duels)   │
│  • Copy-paste detection (Jaccard)       • Behavioral (pairwise)    │
│  • Rapid-fire detection                 • AI detector (perplexity) │
│  • Accumulated warning score            • LLM perplexity           │
│  • → WS warning if threshold hit        • Multi-account            │
│  • → Feed signals to post-match         • → DB + rating freeze     │
└────────────────────────────────────────────────────────────────────┘
"""

import logging
import time
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Latency: if response is >50 words and arrived <3 seconds after prompt → suspicious
FAST_RESPONSE_MIN_WORDS = 50
FAST_RESPONSE_MAX_SECONDS = 3.0

# S4-10: Words-per-second threshold — catches sleep(3.1) bypass
# Average human typing: 2-3 wps. Fast typist: 5-8 wps. >15 wps = impossible without paste
SUSPICIOUS_WPS = 15.0
WPS_MIN_WORDS = 10  # Don't check very short messages (can be typed fast)

# Copy-paste: Jaccard similarity between consecutive messages > 0.85
COPY_PASTE_THRESHOLD = 0.85

# Rapid-fire: < 1.5s between messages (bot behavior)
RAPID_FIRE_SECONDS = 1.5

# Warning threshold: accumulated score at which we warn the player
WARN_THRESHOLD = 3.0
# Hard threshold: at which we flag for post-match review
FLAG_THRESHOLD = 5.0


# ---------------------------------------------------------------------------
# Per-player session state
# ---------------------------------------------------------------------------

@dataclass
class PlayerDuelState:
    """In-memory state for a player during an active duel."""
    user_id: uuid.UUID
    duel_id: uuid.UUID
    messages: list[dict] = field(default_factory=list)
    warning_score: float = 0.0
    warnings_sent: int = 0
    flagged: bool = False
    last_message_time: float | None = None
    fast_long_count: int = 0
    copy_paste_count: int = 0
    rapid_fire_count: int = 0
    created_at: float = field(default_factory=time.time)


# Active states: {(user_id, duel_id): PlayerDuelState}
_states: dict[tuple[uuid.UUID, uuid.UUID], PlayerDuelState] = {}

_MAX_STATES = 10000
_MAX_MESSAGES_PER_PLAYER = 500
_STALE_SECONDS = 30 * 60  # 30 minutes


def _sweep_stale_states() -> None:
    """Remove entries older than 30 minutes to prevent memory leaks."""
    now = time.time()
    stale_keys = [k for k, v in _states.items() if now - v.created_at > _STALE_SECONDS]
    for k in stale_keys:
        _states.pop(k, None)
    if stale_keys:
        logger.info("Anti-cheat sweep: removed %d stale states", len(stale_keys))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_player(user_id: uuid.UUID, duel_id: uuid.UUID) -> None:
    """Initialize tracking for a player in a duel. Call when duel starts."""
    if len(_states) > _MAX_STATES:
        _sweep_stale_states()
    _states[(user_id, duel_id)] = PlayerDuelState(user_id=user_id, duel_id=duel_id)


def cleanup_duel(duel_id: uuid.UUID) -> dict[uuid.UUID, dict]:
    """Remove all state for a duel. Returns accumulated signals for post-match.

    Call after duel finalization. The returned signals can be passed to
    the full anti-cheat analysis for additional context.
    """
    signals = {}
    keys_to_remove = [k for k in _states if k[1] == duel_id]
    for key in keys_to_remove:
        state = _states.pop(key)
        signals[state.user_id] = {
            "realtime_warning_score": state.warning_score,
            "fast_long_count": state.fast_long_count,
            "copy_paste_count": state.copy_paste_count,
            "rapid_fire_count": state.rapid_fire_count,
            "flagged": state.flagged,
            "total_messages": len(state.messages),
        }
    return signals


@dataclass
class RealtimeCheckResult:
    """Result of a per-message check."""
    warning_score_delta: float = 0.0
    flags: list[str] = field(default_factory=list)
    should_warn: bool = False
    should_flag: bool = False


def check_message(
    user_id: uuid.UUID,
    duel_id: uuid.UUID,
    text: str,
    timestamp: float | None = None,
) -> RealtimeCheckResult:
    """Run lightweight anti-cheat checks on a single message.

    Call this from _handle_duel_message() for every player message.
    Returns immediately — no IO, no DB, no LLM.
    """
    key = (user_id, duel_id)
    state = _states.get(key)
    if state is None:
        # Player not initialized — skip silently (shouldn't happen)
        return RealtimeCheckResult()

    now = timestamp or time.time()
    result = RealtimeCheckResult()

    # ── Check 1: Fast response for long text ──
    word_count = len(text.split())
    if state.last_message_time is not None:
        elapsed = now - state.last_message_time
        if word_count > FAST_RESPONSE_MIN_WORDS and elapsed < FAST_RESPONSE_MAX_SECONDS:
            state.fast_long_count += 1
            result.warning_score_delta += 1.5
            result.flags.append(
                f"fast_long: {word_count} words in {elapsed:.1f}s"
            )

        # ── Check 1b (S4-10): Words-per-second — catches sleep(3.1) bypass ──
        if elapsed > 0 and word_count >= WPS_MIN_WORDS:
            wps = word_count / elapsed
            if wps > SUSPICIOUS_WPS:
                result.warning_score_delta += 1.0
                result.flags.append(
                    f"high_wps: {wps:.1f} wps ({word_count}w / {elapsed:.1f}s)"
                )

    # ── Check 2: Copy-paste detection (vs previous messages) ──
    if state.messages:
        last_text = state.messages[-1].get("text", "")
        sim = _jaccard(text, last_text)
        if sim > COPY_PASTE_THRESHOLD and len(text.split()) > 5:
            state.copy_paste_count += 1
            result.warning_score_delta += 1.0
            result.flags.append(f"copy_paste: similarity={sim:.2f}")

    # ── Check 3: Rapid-fire messages ──
    if state.last_message_time is not None:
        elapsed = now - state.last_message_time
        if elapsed < RAPID_FIRE_SECONDS and len(text.split()) > 20:
            state.rapid_fire_count += 1
            result.warning_score_delta += 0.5
            result.flags.append(f"rapid_fire: {elapsed:.1f}s gap, {len(text.split())} words")

    # ── Update state ──
    state.messages.append({"text": text, "timestamp": now})
    if len(state.messages) > _MAX_MESSAGES_PER_PLAYER:
        state.messages = state.messages[len(state.messages) // 2:]
    state.last_message_time = now
    state.warning_score += result.warning_score_delta

    # ── Thresholds ──
    if state.warning_score >= FLAG_THRESHOLD and not state.flagged:
        state.flagged = True
        result.should_flag = True
        logger.warning(
            "Anti-cheat FLAGGED: user=%s duel=%s score=%.1f flags=%s",
            user_id, duel_id, state.warning_score, result.flags,
        )

    if (
        state.warning_score >= WARN_THRESHOLD
        and not state.flagged
        and state.warnings_sent < 2  # Max 2 warnings per duel
    ):
        state.warnings_sent += 1
        result.should_warn = True
        logger.info(
            "Anti-cheat WARNING: user=%s duel=%s score=%.1f",
            user_id, duel_id, state.warning_score,
        )

    return result


def get_realtime_signals(user_id: uuid.UUID, duel_id: uuid.UUID) -> dict | None:
    """Get current accumulated signals for a player. Used by post-match analysis."""
    state = _states.get((user_id, duel_id))
    if state is None:
        return None
    return {
        "warning_score": state.warning_score,
        "fast_long_count": state.fast_long_count,
        "copy_paste_count": state.copy_paste_count,
        "rapid_fire_count": state.rapid_fire_count,
        "flagged": state.flagged,
        "total_messages": len(state.messages),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _jaccard(a: str, b: str) -> float:
    """Token-level Jaccard similarity. Same as anti_cheat._jaccard_similarity."""
    set_a = set(a.lower().split())
    set_b = set(b.lower().split())
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)
