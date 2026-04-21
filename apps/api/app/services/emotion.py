"""
Emotion engine for Hunter888 sales training simulator.

Manages client emotional states across 10-state nonlinear graph with energy-based
MoodBuffer for 25 archetypes. Supports V1 (linear), V2 (single-trigger), and
V3 (multi-trigger energy-based with EMA smoothing and fake transitions) emotion transitions.

Architecture:
  - ALLOWED_TRANSITIONS: directed graph of valid state transitions
  - MoodBuffer: energy accumulation with EMA smoothing, decay, and threshold crossing
  - InteractionMemory: tracks history, rollbacks, peak state
  - FakeTransition: deceptive state progression with activation logic
  - ArchetypeConfig: per-archetype behavior customization with EMA coefficients
  - Redis persistence: all state, buffers, memory, fakes (with connection pooling)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, asdict, field
from typing import Optional
from datetime import datetime, timezone

import redis.asyncio as aioredis

from app.models.character import EmotionState, TERMINAL_STATES, FINAL_STATES
from app.config import settings

# v6 extension imports (module-level for performance, with fallback)
try:
    from app.services.emotion_v6 import (
        NEW_TRIGGERS as _V6_NEW_TRIGGERS,
        NEW_TRIGGER_ENERGY as _V6_NEW_TRIGGER_ENERGY,
        TRIGGER_CONFLICTS as _V6_TRIGGER_CONFLICTS,
        get_transitions_for_archetype as _v6_get_archetype_graph,
    )
    _HAS_V6 = True
except ImportError:
    _HAS_V6 = False
    _V6_NEW_TRIGGERS = []
    _V6_NEW_TRIGGER_ENERGY = {}
    _V6_TRIGGER_CONFLICTS = {}

    def _v6_get_archetype_graph(code: str) -> dict:  # type: ignore
        return ALLOWED_TRANSITIONS
from app.core.redis_pool import get_redis

logger = logging.getLogger(__name__)

# ============================================================================
# State Graph & Transitions
# ============================================================================

# Replace linear STATES list with nonlinear state graph.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "cold": {"guarded", "hostile"},
    "guarded": {"curious", "testing", "callback", "hostile", "cold"},  # KEY branching node
    "curious": {"considering", "testing", "callback", "cold"},
    "considering": {"negotiating", "testing", "callback", "cold"},
    "negotiating": {"deal", "testing", "callback", "cold"},
    "deal": {"testing", "considering", "hostile"},  # can crash to hostile on critical failure
    "testing": {"guarded", "callback", "hostile", "cold", "considering"},
    "callback": {"guarded", "curious", "cold", "deal"},  # client can upgrade during callback wait
    "hostile": {"guarded", "hangup"},  # can only exit via calm_response/empathy or hangup
    "hangup": set(),  # terminal, no exits
}

# V1 backward-compat: direct transitions by response quality
TRANSITIONS: dict[str, dict[str, str]] = {
    "cold": {"high": "guarded", "medium": "cold", "low": "hostile"},
    "guarded": {"high": "curious", "medium": "guarded", "low": "cold"},
    "curious": {"high": "considering", "medium": "curious", "low": "guarded"},
    "considering": {"high": "negotiating", "medium": "considering", "low": "guarded"},
    "negotiating": {"high": "deal", "medium": "negotiating", "low": "considering"},
    "deal": {"high": "deal", "medium": "deal", "low": "testing"},
    "testing": {"high": "guarded", "medium": "testing", "low": "hostile"},
    "callback": {"high": "curious", "medium": "callback", "low": "cold"},
    "hostile": {"high": "guarded", "medium": "hostile", "low": "hangup"},
    "hangup": {"high": "hangup", "medium": "hangup", "low": "hangup"},
}

# ============================================================================
# Triggers & Default Energy
# ============================================================================

TRIGGERS = [
    "empathy", "facts", "pressure", "bad_response", "acknowledge",
    "name_use", "motivator", "speed", "boundary", "personal",
    "hook", "challenge", "defer", "resolve_fear", "insult",
    "correct_answer", "expert_answer", "wrong_answer", "honest_uncertainty",
    "calm_response", "flexible_offer", "silence", "counter_aggression",
]

DEFAULT_ENERGY: dict[str, float] = {
    "empathy": 0.3,
    "facts": 0.25,
    "hook": 0.5,
    "resolve_fear": 0.5,
    "expert_answer": 0.4,
    "correct_answer": 0.3,
    "name_use": 0.1,
    "acknowledge": 0.2,
    "motivator": 0.3,
    "speed": 0.15,
    "boundary": 0.35,
    "flexible_offer": 0.3,
    "calm_response": 0.3,
    "honest_uncertainty": 0.15,
    "pressure": -0.4,
    "bad_response": -0.35,
    "insult": -1.0,
    "wrong_answer": -0.6,
    "counter_aggression": -0.8,
    "silence": -0.2,
    "challenge": 0.0,
    "defer": 0.0,
    "personal": 0.15,
}

# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class MoodBuffer:
    """Energy accumulation buffer with EMA smoothing, decay, and threshold-based transitions."""
    current_energy: float = 0.0
    energy_smoothed: float = 0.0
    ema_alpha: float = 0.3
    threshold_positive: float = 0.6
    threshold_negative: float = -0.5
    decay_rate: float = 0.1

    def apply_decay(self) -> None:
        """Decay energy toward zero when no triggers fire."""
        if self.current_energy > 0:
            self.current_energy = max(0.0, self.current_energy * (1.0 - self.decay_rate))
        elif self.current_energy < 0:
            self.current_energy = min(0.0, self.current_energy * (1.0 - self.decay_rate))

    def apply_ema(self) -> None:
        """Exponential moving average for smooth transitions."""
        self.energy_smoothed = (
            self.ema_alpha * self.current_energy
            + (1.0 - self.ema_alpha) * self.energy_smoothed
        )

    def clamp(self) -> None:
        """Clamp energy to valid range."""
        self.current_energy = max(-100.0, min(100.0, self.current_energy))
        self.energy_smoothed = max(-100.0, min(100.0, self.energy_smoothed))

    def update(self, energy_delta: float) -> None:
        """Full update cycle: add delta, decay, EMA, clamp."""
        self.current_energy += energy_delta
        self.apply_decay()
        self.apply_ema()
        self.clamp()

    def should_transition_forward(self) -> bool:
        """Check if smoothed energy exceeds positive threshold."""
        return self.energy_smoothed >= self.threshold_positive

    def should_transition_backward(self) -> bool:
        """Check if smoothed energy falls below negative threshold."""
        return self.energy_smoothed <= self.threshold_negative

    def reset_after_transition(self) -> None:
        """Reset energy to 0 after a state transition occurs."""
        self.current_energy = 0.0
        self.energy_smoothed = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> MoodBuffer:
        return MoodBuffer(**data)


@dataclass
class InteractionMemory:
    """Tracks interaction history and progression patterns."""
    last_5_triggers: list[str] = field(default_factory=list)
    last_3_states: list[str] = field(default_factory=list)
    rollback_count: int = 0
    peak_state: str = "cold"
    consecutive_rollbacks: int = 0

    def is_oscillating(self) -> bool:
        """Detect A→B→A ping-pong pattern in recent states."""
        if len(self.last_3_states) < 3:
            return False
        return (
            self.last_3_states[0] == self.last_3_states[2]
            and self.last_3_states[0] != self.last_3_states[1]
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> InteractionMemory:
        # Backward compat: old data may lack new fields
        data.setdefault("last_3_states", [])
        data.setdefault("consecutive_rollbacks", 0)
        return InteractionMemory(**data)


@dataclass
class FakeTransition:
    """Deceptive state progression (appears one way, actually another)."""
    apparent_state: str
    real_state: str
    trigger_reveal: Optional[str]
    duration: int
    turns_remaining: int

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> FakeTransition:
        return FakeTransition(**data)


@dataclass
class ArchetypeConfig:
    """Customized behavior for each archetype."""
    initial_state: str
    initial_energy: float
    threshold_positive: float
    threshold_negative: float
    decay_rate: float
    ema_alpha: float = 0.3
    energy_modifiers: dict[str, float] = field(default_factory=dict)  # trigger → multiplier
    counter_gates: dict[str, int] = field(default_factory=dict)  # trigger → count needed
    transition_overrides: dict[tuple[str, str], str] = field(default_factory=dict)
    fake_transitions: Optional[list[dict]] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> ArchetypeConfig:
        return ArchetypeConfig(**data)


# ============================================================================
# Archetype Configurations (25 total)
# ============================================================================

ARCHETYPE_CONFIGS: dict[str, ArchetypeConfig] = {
    "skeptic": ArchetypeConfig(
        initial_state="cold",
        initial_energy=0.0,
        threshold_positive=0.7,
        threshold_negative=-0.5,
        decay_rate=0.1,
        ema_alpha=0.3,
        energy_modifiers={"facts": 1.5, "empathy": 0.5},
        counter_gates={"facts": 2},
    ),
    "anxious": ArchetypeConfig(
        initial_state="cold",
        initial_energy=0.0,
        threshold_positive=0.6,
        threshold_negative=-0.3,
        decay_rate=0.12,
        ema_alpha=0.4,
        energy_modifiers={"empathy": 1.5, "pressure": 2.0},
    ),
    "passive": ArchetypeConfig(
        initial_state="cold",
        initial_energy=0.0,
        threshold_positive=0.65,
        threshold_negative=-0.4,
        decay_rate=0.1,
        ema_alpha=0.25,
        energy_modifiers={"empathy": 1.3, "motivator": 1.2},
    ),
    "avoidant": ArchetypeConfig(
        initial_state="cold",
        initial_energy=0.0,
        threshold_positive=0.75,
        threshold_negative=-0.3,
        decay_rate=0.08,
        ema_alpha=0.3,
        energy_modifiers={"hook": 1.4, "personal": 0.5},
    ),
    "paranoid": ArchetypeConfig(
        initial_state="cold",
        initial_energy=0.0,
        threshold_positive=0.8,
        threshold_negative=-0.4,
        decay_rate=0.1,
        ema_alpha=0.2,
        energy_modifiers={"challenge": 2.0, "facts": 1.2},
        counter_gates={"facts": 3},
        fake_transitions=[{"apparent": "guarded", "real": "testing", "trigger_reveal": None, "duration": 3}],
    ),
    "ashamed": ArchetypeConfig(
        initial_state="cold",
        initial_energy=0.0,
        threshold_positive=0.55,
        threshold_negative=-0.6,
        decay_rate=0.12,
        ema_alpha=0.3,
        # pressure is NEGATIVE for ashamed: causes shame spiral, blocks progress
        energy_modifiers={"empathy": 1.8, "acknowledge": 1.5, "pressure": -1.5},
    ),
    "aggressive": ArchetypeConfig(
        initial_state="cold",
        initial_energy=0.0,
        threshold_positive=0.6,
        threshold_negative=-0.3,
        decay_rate=0.11,
        ema_alpha=0.35,
        energy_modifiers={"acknowledge": 2.0, "pressure": 1.5, "boundary": 1.2},
        transition_overrides={("cold", "pressure"): "hostile"},
    ),
    "hostile": ArchetypeConfig(
        initial_state="cold",
        initial_energy=-0.2,
        threshold_positive=0.7,
        threshold_negative=-0.2,
        decay_rate=0.08,
        ema_alpha=0.3,
        energy_modifiers={"calm_response": 1.8, "boundary": 1.5, "empathy": 1.4},
    ),
    "blamer": ArchetypeConfig(
        initial_state="guarded",
        initial_energy=0.1,
        threshold_positive=0.65,
        threshold_negative=-0.35,
        decay_rate=0.1,
        ema_alpha=0.3,
        energy_modifiers={"acknowledge": 1.3, "facts": 1.2, "empathy": 0.6},
    ),
    "sarcastic": ArchetypeConfig(
        initial_state="guarded",
        initial_energy=0.0,
        threshold_positive=0.6,
        threshold_negative=-0.4,
        decay_rate=0.1,
        ema_alpha=0.3,
        energy_modifiers={"acknowledge": 1.4, "hook": 1.3},
        fake_transitions=[{"apparent": "curious", "real": "testing", "trigger_reveal": None, "duration": 2}],
    ),
    "manipulator": ArchetypeConfig(
        initial_state="cold",
        initial_energy=0.0,
        threshold_positive=0.65,
        threshold_negative=-0.4,
        decay_rate=0.09,
        ema_alpha=0.3,
        energy_modifiers={"boundary": 2.0, "empathy": 0.5, "facts": 1.1},
        fake_transitions=[
            {"apparent": "curious", "real": "guarded", "trigger_reveal": "boundary", "duration": 3},
            {"apparent": "considering", "real": "testing", "trigger_reveal": "boundary", "duration": 2},
        ],
    ),
    "pragmatic": ArchetypeConfig(
        initial_state="cold",
        initial_energy=0.0,
        threshold_positive=0.6,
        threshold_negative=-0.5,
        decay_rate=0.1,
        ema_alpha=0.3,
        energy_modifiers={"facts": 1.4, "empathy": 0.5, "speed": 1.3},
    ),
    "delegator": ArchetypeConfig(
        initial_state="guarded",
        initial_energy=0.1,
        threshold_positive=0.55,
        threshold_negative=-0.45,
        decay_rate=0.1,
        ema_alpha=0.3,
        energy_modifiers={"motivator": 1.4, "boundary": 1.2, "speed": 1.3},
    ),
    "know_it_all": ArchetypeConfig(
        initial_state="testing",
        initial_energy=0.2,
        threshold_positive=0.65,
        threshold_negative=-0.3,
        decay_rate=0.1,
        ema_alpha=0.3,
        energy_modifiers={"expert_answer": 1.5, "challenge": 3.0, "facts": 1.3},
        transition_overrides={("testing", "wrong_answer"): "hostile"},
    ),
    "negotiator": ArchetypeConfig(
        initial_state="guarded",
        initial_energy=0.15,
        threshold_positive=0.55,
        threshold_negative=-0.45,
        decay_rate=0.11,
        ema_alpha=0.3,
        energy_modifiers={"flexible_offer": 1.5, "boundary": 1.3, "motivator": 1.2},
    ),
    "shopper": ArchetypeConfig(
        initial_state="curious",
        initial_energy=0.1,
        threshold_positive=0.5,
        threshold_negative=-0.55,
        decay_rate=0.12,
        ema_alpha=0.3,
        energy_modifiers={"hook": 1.4, "speed": 0.8, "facts": 1.2},
    ),
    "desperate": ArchetypeConfig(
        initial_state="curious",
        initial_energy=0.4,
        threshold_positive=0.45,
        threshold_negative=-0.6,
        decay_rate=0.13,
        ema_alpha=0.45,
        energy_modifiers={"facts": 0.8, "empathy": 1.3, "motivator": 1.4, "hook": 1.3},
    ),
    "crying": ArchetypeConfig(
        initial_state="cold",
        initial_energy=-0.1,
        threshold_positive=0.5,
        threshold_negative=-0.7,
        decay_rate=0.1,
        ema_alpha=0.3,
        energy_modifiers={"empathy": 2.0, "acknowledge": 1.8, "calm_response": 1.6},
    ),
    "grateful": ArchetypeConfig(
        initial_state="curious",
        initial_energy=0.3,
        threshold_positive=0.5,
        threshold_negative=-0.6,
        decay_rate=0.12,
        ema_alpha=0.3,
        energy_modifiers={"empathy": 1.3, "hook": 1.2, "acknowledge": 1.2},
    ),
    "overwhelmed": ArchetypeConfig(
        initial_state="cold",
        initial_energy=-0.1,
        threshold_positive=0.55,
        threshold_negative=-0.4,
        decay_rate=0.11,
        ema_alpha=0.2,
        energy_modifiers={"calm_response": 1.5, "facts": 0.7, "speed": 1.3, "empathy": 1.4},
    ),
    "returner": ArchetypeConfig(
        initial_state="guarded",
        initial_energy=0.3,
        threshold_positive=0.6,
        threshold_negative=-0.45,
        decay_rate=0.1,
        ema_alpha=0.3,
        energy_modifiers={"name_use": 1.5, "motivator": 1.3, "hook": 1.2},
    ),
    "referred": ArchetypeConfig(
        initial_state="curious",
        initial_energy=0.7,
        threshold_positive=0.5,
        threshold_negative=-0.5,
        decay_rate=0.1,
        ema_alpha=0.3,
        energy_modifiers={"expert_answer": 1.3, "motivator": 1.2, "hook": 1.1},
    ),
    "rushed": ArchetypeConfig(
        initial_state="cold",
        initial_energy=0.0,
        threshold_positive=0.5,
        threshold_negative=-0.5,
        decay_rate=0.14,
        ema_alpha=0.5,
        energy_modifiers={"speed": 2.0, "silence": 2.0, "facts": 1.1},
    ),
    "lawyer_client": ArchetypeConfig(
        initial_state="guarded",
        initial_energy=0.05,
        threshold_positive=0.75,
        threshold_negative=-0.4,
        decay_rate=0.09,
        ema_alpha=0.3,
        energy_modifiers={"facts": 1.6, "expert_answer": 1.4, "empathy": 0.6},
        counter_gates={"facts": 2},
    ),
    "couple": ArchetypeConfig(
        initial_state="cold",
        initial_energy=0.0,
        threshold_positive=0.55,
        threshold_negative=-0.5,
        decay_rate=0.1,
        ema_alpha=0.3,
        energy_modifiers={"empathy": 1.8, "acknowledge": 1.6, "personal": 1.4},
    ),
}

# ============================================================================
# Redis Key Patterns
# ============================================================================

def _emotion_key(session_id: uuid.UUID) -> str:
    return f"session:{session_id}:emotion"

def _timeline_key(session_id: uuid.UUID) -> str:
    return f"session:{session_id}:emotion_timeline"

def _counter_key(session_id: uuid.UUID, trigger: str) -> str:
    return f"session:{session_id}:trigger_counter:{trigger}"

def _mood_buffer_key(session_id: uuid.UUID) -> str:
    return f"session:{session_id}:mood_buffer"

def _memory_key(session_id: uuid.UUID) -> str:
    return f"session:{session_id}:interaction_memory"

def _fake_key(session_id: uuid.UUID) -> str:
    return f"session:{session_id}:fake_transition"

def _message_index_key(session_id: uuid.UUID) -> str:
    return f"session:{session_id}:message_index"

_KEY_TTL = 7200  # 2 hours

# ============================================================================
# Redis Connection (uses centralized pool from app.core.redis_pool)
# ============================================================================

async def _get_redis() -> Optional[aioredis.Redis]:
    """Get Redis connection from the centralized shared connection pool.

    Returns None on failure to preserve graceful degradation — all callers
    fall back to defaults (e.g. "cold" emotion) when Redis is unavailable.
    """
    try:
        return get_redis()
    except Exception as e:
        logger.warning(f"Failed to connect to Redis: {e}")
        return None

# ============================================================================
# V1 Backward-Compatible Functions
# ============================================================================

def get_next_emotion(current: str, response_quality: str) -> str:
    """
    V1: Direct state transition by response quality.
    Maps response_quality (high/medium/low) to next state.
    Backward-compatible with old callers.
    """
    if current not in TRANSITIONS:
        return "cold"
    transitions = TRANSITIONS[current]
    quality = response_quality.lower()
    if quality not in transitions:
        return current
    return transitions[quality]


async def get_emotion(session_id: uuid.UUID) -> str:
    """Get current emotion state from Redis."""
    try:
        redis = await _get_redis()
        if not redis:
            return "cold"
        state = await redis.get(_emotion_key(session_id))
        return state or "cold"
    except Exception as e:
        logger.warning(f"Failed to get emotion state: {e}")
        return "cold"


async def set_emotion(
    session_id: uuid.UUID,
    state: str,
    *,
    previous_state: Optional[str] = None,
    triggers: Optional[list[str]] = None,
    energy_before: Optional[float] = None,
    energy_after: Optional[float] = None,
    is_fake: bool = False,
    rollback: bool = False,
    message_index: Optional[int] = None,
) -> None:
    """
    Set current emotion state and append to timeline with rich metadata.
    Expanded to track timestamp and comprehensive transition data.
    """
    try:
        redis = await _get_redis()
        if not redis:
            return

        pipeline = redis.pipeline()
        pipeline.set(_emotion_key(session_id), state, ex=_KEY_TTL)

        # Append to timeline with rich metadata
        timeline_entry = {
            "state": state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "previous_state": previous_state,
            "triggers": triggers or [],
            "energy_before": energy_before,
            "energy_after": energy_after,
            "is_fake": is_fake,
            "rollback": rollback,
            "message_index": message_index,
        }
        pipeline.rpush(_timeline_key(session_id), json.dumps(timeline_entry))
        pipeline.expire(_timeline_key(session_id), _KEY_TTL)

        await pipeline.execute()
    except Exception as e:
        logger.warning(f"Failed to set emotion state: {e}")


async def get_emotion_timeline(session_id: uuid.UUID) -> list[dict]:
    """Get timeline of all emotion state changes."""
    try:
        redis = await _get_redis()
        if not redis:
            return []

        timeline = await redis.lrange(_timeline_key(session_id), 0, -1)
        return [json.loads(entry) for entry in timeline] if timeline else []
    except Exception as e:
        logger.warning(f"Failed to get emotion timeline: {e}")
        return []


async def init_emotion(session_id: uuid.UUID, initial_state: str = "cold") -> None:
    """Initialize emotion state for a new session."""
    try:
        redis = await _get_redis()
        if not redis:
            return

        pipeline = redis.pipeline()
        pipeline.set(_emotion_key(session_id), initial_state, ex=_KEY_TTL)

        # Initialize timeline with first entry
        timeline_entry = {
            "state": initial_state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "previous_state": None,
            "triggers": [],
            "energy_before": None,
            "energy_after": None,
            "is_fake": False,
            "rollback": False,
            "message_index": 0,
        }
        pipeline.rpush(_timeline_key(session_id), json.dumps(timeline_entry))
        pipeline.expire(_timeline_key(session_id), _KEY_TTL)

        # Initialize mood buffer
        buffer = MoodBuffer()
        pipeline.set(_mood_buffer_key(session_id), json.dumps(buffer.to_dict()), ex=_KEY_TTL)

        # Initialize memory
        memory = InteractionMemory()
        pipeline.set(_memory_key(session_id), json.dumps(memory.to_dict()), ex=_KEY_TTL)

        # Initialize message index
        pipeline.set(_message_index_key(session_id), "0", ex=_KEY_TTL)

        await pipeline.execute()
    except Exception as e:
        logger.warning(f"Failed to initialize emotion: {e}")


async def init_emotion_v3(session_id: uuid.UUID, archetype_code: str) -> str:
    """
    Initialize emotion for V3 engine using archetype config.
    Sets up mood buffer with archetype-specific parameters.
    """
    try:
        config = ARCHETYPE_CONFIGS.get(archetype_code, ARCHETYPE_CONFIGS["skeptic"])

        redis = await _get_redis()
        if not redis:
            return config.initial_state

        pipeline = redis.pipeline()
        pipeline.set(_emotion_key(session_id), config.initial_state, ex=_KEY_TTL)

        # Initialize timeline with first entry
        timeline_entry = {
            "state": config.initial_state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "previous_state": None,
            "triggers": [],
            "energy_before": None,
            "energy_after": config.initial_energy,
            "is_fake": False,
            "rollback": False,
            "message_index": 0,
        }
        pipeline.rpush(_timeline_key(session_id), json.dumps(timeline_entry))
        pipeline.expire(_timeline_key(session_id), _KEY_TTL)

        # Initialize mood buffer with archetype-specific thresholds and EMA
        buffer = MoodBuffer(
            current_energy=config.initial_energy,
            energy_smoothed=config.initial_energy,
            ema_alpha=config.ema_alpha,
            threshold_positive=config.threshold_positive,
            threshold_negative=config.threshold_negative,
            decay_rate=config.decay_rate,
        )
        pipeline.set(_mood_buffer_key(session_id), json.dumps(buffer.to_dict()), ex=_KEY_TTL)

        # Initialize memory
        memory = InteractionMemory(peak_state=config.initial_state)
        pipeline.set(_memory_key(session_id), json.dumps(memory.to_dict()), ex=_KEY_TTL)

        # Initialize message index
        pipeline.set(_message_index_key(session_id), "0", ex=_KEY_TTL)

        await pipeline.execute()
        return config.initial_state
    except Exception as e:
        logger.warning(f"Failed to initialize emotion v3: {e}")
        return "cold"


async def cleanup_emotion(session_id: uuid.UUID) -> list[dict]:
    """
    Clean up emotion data for a session.
    Returns the final timeline before cleanup.
    """
    try:
        redis = await _get_redis()
        if not redis:
            return []

        # Get timeline before cleanup
        timeline = await get_emotion_timeline(session_id)

        # Delete all emotion-related keys
        keys_to_delete = [
            _emotion_key(session_id),
            _timeline_key(session_id),
            _mood_buffer_key(session_id),
            _memory_key(session_id),
            _fake_key(session_id),
            _message_index_key(session_id),
        ]

        # Also delete trigger counters
        cursor = 0
        pattern = f"session:{session_id}:trigger_counter:*"
        while True:
            cursor, keys = await redis.scan(cursor, match=pattern, count=100)
            if keys:
                await redis.delete(*keys)
            if cursor == 0:
                break

        await redis.delete(*keys_to_delete)

        # Clean up per-session lock (prevents memory leak on long-running server)
        remove_session_lock(session_id)

        return timeline
    except Exception as e:
        logger.warning(f"Failed to cleanup emotion: {e}")
        return []


async def transition_emotion(session_id: uuid.UUID, response_quality: str) -> str:
    """
    V1: Simple response-quality-based transition.
    Backward-compatible; wraps get_emotion + get_next_emotion + set_emotion.
    """
    current = await get_emotion(session_id)
    next_state = get_next_emotion(current, response_quality)
    await set_emotion(session_id, next_state)
    return next_state


# ============================================================================
# V3 Engine: Per-Session Lock (prevents concurrent emotion updates)
# ============================================================================

_session_locks: dict[str, asyncio.Lock] = {}
_session_locks_guard = asyncio.Lock()

_MAX_SESSION_LOCKS = 10000  # Prevent unbounded growth


async def _get_session_lock(session_id: uuid.UUID) -> asyncio.Lock:
    """Get or create a per-session asyncio.Lock to serialize emotion state mutations.

    Emotion updates do GET→mutate→SET on Redis. Without locking, concurrent
    WebSocket messages can interleave and lose each other's state changes.
    """
    key = str(session_id)
    if key in _session_locks:
        return _session_locks[key]
    async with _session_locks_guard:
        if key not in _session_locks:
            # Evict oldest if too many locks (stale sessions)
            if len(_session_locks) >= _MAX_SESSION_LOCKS:
                # Remove first 20% of keys (FIFO approximation)
                to_remove = list(_session_locks.keys())[: _MAX_SESSION_LOCKS // 5]
                for k in to_remove:
                    _session_locks.pop(k, None)
            _session_locks[key] = asyncio.Lock()
        return _session_locks[key]


def remove_session_lock(session_id: uuid.UUID) -> None:
    """Clean up lock when session ends."""
    _session_locks.pop(str(session_id), None)


# ============================================================================
# V3 Engine: Mood Buffer Redis Helpers
# ============================================================================

async def _get_mood_buffer(session_id: uuid.UUID) -> MoodBuffer:
    """Retrieve mood buffer from Redis."""
    try:
        redis = await _get_redis()
        if not redis:
            return MoodBuffer()

        data = await redis.get(_mood_buffer_key(session_id))

        if data:
            return MoodBuffer.from_dict(json.loads(data))
        return MoodBuffer()
    except Exception as e:
        logger.warning(f"Failed to get mood buffer: {e}")
        return MoodBuffer()


async def _set_mood_buffer(session_id: uuid.UUID, buffer: MoodBuffer) -> None:
    """Store mood buffer to Redis."""
    try:
        redis = await _get_redis()
        if not redis:
            return

        await redis.set(_mood_buffer_key(session_id), json.dumps(buffer.to_dict()), ex=_KEY_TTL)
    except Exception as e:
        logger.warning(f"Failed to set mood buffer: {e}")


# ============================================================================
# V3 Engine: Memory Redis Helpers
# ============================================================================

async def _get_memory(session_id: uuid.UUID) -> InteractionMemory:
    """Retrieve interaction memory from Redis."""
    try:
        redis = await _get_redis()
        if not redis:
            return InteractionMemory()

        data = await redis.get(_memory_key(session_id))

        if data:
            return InteractionMemory.from_dict(json.loads(data))
        return InteractionMemory()
    except Exception as e:
        logger.warning(f"Failed to get memory: {e}")
        return InteractionMemory()


async def _update_memory(
    session_id: uuid.UUID,
    triggers: list[str],
    new_state: str,
    rollback: bool = False,
) -> InteractionMemory:
    try:
        memory = await _get_memory(session_id)

        # Update trigger ring buffer
        for trigger in triggers:
            memory.last_5_triggers.append(trigger)
            if len(memory.last_5_triggers) > 5:
                memory.last_5_triggers.pop(0)

        # Update state ring buffer for oscillation detection
        memory.last_3_states.append(new_state)
        if len(memory.last_3_states) > 3:
            memory.last_3_states.pop(0)

        # Track rollbacks (total + consecutive streak)
        if rollback:
            memory.rollback_count += 1
            memory.consecutive_rollbacks += 1
        else:
            memory.consecutive_rollbacks = 0

        # Track peak state (closer to "deal" is better)
        state_rank = {
            "cold": 0, "guarded": 1, "curious": 2, "considering": 3,
            "negotiating": 4, "deal": 5, "testing": 2, "callback": 1,
            "hostile": -1, "hangup": -2,
        }
        current_rank = state_rank.get(new_state, 0)
        peak_rank = state_rank.get(memory.peak_state, 0)

        if current_rank > peak_rank:
            memory.peak_state = new_state

        redis = await _get_redis()
        if redis:
            await redis.set(_memory_key(session_id), json.dumps(memory.to_dict()), ex=_KEY_TTL)

        return memory
    except Exception as e:
        logger.warning(f"Failed to update memory: {e}")
        return InteractionMemory()


# ============================================================================
# V3 Engine: Fake Transition Redis Helpers
# ============================================================================

async def _get_fake(session_id: uuid.UUID) -> Optional[FakeTransition]:
    """Retrieve active fake transition."""
    try:
        redis = await _get_redis()
        if not redis:
            return None

        data = await redis.get(_fake_key(session_id))

        if data:
            return FakeTransition.from_dict(json.loads(data))
        return None
    except Exception as e:
        logger.warning(f"Failed to get fake transition: {e}")
        return None


async def _set_fake(session_id: uuid.UUID, fake: FakeTransition) -> None:
    """Store fake transition to Redis."""
    try:
        redis = await _get_redis()
        if not redis:
            return

        await redis.set(_fake_key(session_id), json.dumps(fake.to_dict()), ex=_KEY_TTL)
    except Exception as e:
        logger.warning(f"Failed to set fake transition: {e}")


async def _clear_fake(session_id: uuid.UUID) -> None:
    """Clear active fake transition."""
    try:
        redis = await _get_redis()
        if not redis:
            return

        await redis.delete(_fake_key(session_id))
    except Exception as e:
        logger.warning(f"Failed to clear fake transition: {e}")


async def _get_next_message_index(session_id: uuid.UUID) -> int:
    """Get and increment message index for this session."""
    try:
        redis = await _get_redis()
        if not redis:
            return 0

        index = await redis.incr(_message_index_key(session_id))
        await redis.expire(_message_index_key(session_id), _KEY_TTL)
        return index
    except Exception as e:
        logger.warning(f"Failed to get next message index: {e}")
        return 0


# ============================================================================
# V3 Engine: Fake Transition Activation
# ============================================================================

async def _maybe_activate_fake(
    session_id: uuid.UUID,
    new_state: str,
    config: ArchetypeConfig,
) -> Optional[FakeTransition]:
    """
    Check if entering new_state should trigger a fake transition.
    Activates a new FakeTransition if conditions are met (right state reached).
    """
    if not config.fake_transitions:
        return None

    # Check if there's already an active fake
    existing = await _get_fake(session_id)
    if existing:
        return None

    # Check if any fake config matches the new state
    for ft_config in config.fake_transitions:
        # Activate if the real state matches what the fake expects
        if new_state == ft_config.get("real", ""):
            fake = FakeTransition(
                apparent_state=ft_config["apparent"],
                real_state=ft_config["real"],
                trigger_reveal=ft_config.get("trigger_reveal"),
                duration=ft_config.get("duration", 3),
                turns_remaining=ft_config.get("duration", 3),
            )
            await _set_fake(session_id, fake)
            return fake

    return None


# ============================================================================
# V3 Engine: Fake Transition Prompt Injection
# ============================================================================

def build_fake_transition_prompt(fake: FakeTransition, archetype_code: str) -> str:
    """
    Build LLM prompt injection for fake state behavior.
    Returns instruction telling the LLM to act as if in apparent_state
    while really in real_state.
    """
    if not fake:
        return ""

    # Russian-language prompt for psychological immersion
    reveal_hint = ""
    if fake.turns_remaining <= 1 and not fake.trigger_reveal:
        reveal_hint = (
            " Вы вот-вот раскроете своё истинное отношение — "
            "начните проявлять лёгкие признаки недоверия и подозрительности."
        )

    prompt = (
        f"\n[СКРЫТАЯ ИНСТРУКЦИЯ: Вы находитесь в состоянии '{fake.apparent_state}', "
        f"но на самом деле в состоянии '{fake.real_state}'. "
        f"Ведите себя как будто в '{fake.apparent_state}', "
        f"но сохраняйте истинное отношение '{fake.real_state}'.{reveal_hint}]"
    )
    return prompt


async def get_fake_prompt(session_id: uuid.UUID, archetype_code: str) -> Optional[str]:
    """
    Get fake transition prompt injection for LLM.
    Returns None if no fake active.
    """
    try:
        fake = await _get_fake(session_id)
        if not fake:
            return None

        return build_fake_transition_prompt(fake, archetype_code)
    except Exception as e:
        logger.warning(f"Failed to get fake prompt: {e}")
        return None


# ============================================================================
# V3 Engine: Trigger Application
# ============================================================================

async def _apply_triggers(
    session_id: uuid.UUID,
    archetype_code: str,
    triggers: list[str],
    config: ArchetypeConfig,
) -> tuple[float, list[str]]:
    """
    Apply multiple triggers with priority rules, modifiers, and counter gates.

    Priority rules:
    1. insult overrides everything (immediate -1.0, skip others)
    2. wrong_answer overrides facts
    3. pressure + empathy → only pressure counts
    4. Apply order: negative → neutral → positive
    5. Max 3 triggers per turn

    Returns (total_energy_delta, filtered_triggers).
    """
    if not triggers:
        return 0.0, []

    # Enforce max 3 triggers per turn
    triggers = triggers[:3]

    # Rule 1: insult overrides everything
    if "insult" in triggers:
        return -1.0, ["insult"]

    # Deduplicate and check for counter gates (atomic Lua script)
    # Lua script: atomically increment counter and check if gate is passed
    _COUNTER_GATE_LUA = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then
        redis.call('EXPIRE', KEYS[1], ARGV[2])
    end
    if count >= tonumber(ARGV[1]) then
        redis.call('DEL', KEYS[1])
        return 1
    end
    return 0
    """
    filtered_triggers = []
    try:
        redis = await _get_redis()

        # v6 integration: accept both original (23) and new (22) triggers
        _all_known = set(TRIGGERS) | set(_V6_NEW_TRIGGERS)

        for trigger in triggers:
            if trigger not in _all_known:
                continue

            # Check counter gate (atomic: increment + threshold check in one op)
            if trigger in config.counter_gates:
                required_count = config.counter_gates[trigger]
                counter_key = _counter_key(session_id, trigger)

                if redis:
                    gate_passed = await redis.eval(
                        _COUNTER_GATE_LUA, 1, counter_key,
                        str(required_count), str(_KEY_TTL),
                    )
                    if not gate_passed:
                        continue
                else:
                    pass  # No Redis — allow trigger through

            filtered_triggers.append(trigger)

    except Exception as e:
        logger.warning(f"Error checking counter gates: {e}")
        filtered_triggers = triggers

    if not filtered_triggers:
        return 0.0, []

    # Rule 2: wrong_answer overrides facts
    if "wrong_answer" in filtered_triggers and "facts" in filtered_triggers:
        filtered_triggers = [t for t in filtered_triggers if t != "facts"]

    # Rule 3: pressure + empathy → only pressure
    if "pressure" in filtered_triggers and "empathy" in filtered_triggers:
        filtered_triggers = [t for t in filtered_triggers if t != "empathy"]

    # v6 Rule 4: Apply TRIGGER_CONFLICTS from emotion_v6
    _trigger_set = set(filtered_triggers)
    for winner, losers in _V6_TRIGGER_CONFLICTS.items():
        if winner in _trigger_set:
            for loser in losers:
                if loser in _trigger_set:
                    filtered_triggers = [t for t in filtered_triggers if t != loser]
                    _trigger_set.discard(loser)

    # Sort by energy: negative → neutral → positive (v6: merged energy dict)
    _merged_energy = {**DEFAULT_ENERGY, **_V6_NEW_TRIGGER_ENERGY}

    def energy_sort_key(trigger: str) -> tuple:
        energy = _merged_energy.get(trigger, 0.0)
        return (energy >= 0, energy)  # Negatives first, then by magnitude

    filtered_triggers.sort(key=energy_sort_key)

    # Check for repeated triggers (diminishing returns)
    memory = await _get_memory(session_id)
    multiplier = 1.0

    if len(memory.last_5_triggers) >= 2:
        same_count = sum(1 for t in memory.last_5_triggers[-3:] if t == filtered_triggers[0])
        if same_count >= 3:
            multiplier = 0.5

    # Calculate total energy (v6: use merged energy dict)
    total_energy = 0.0
    for trigger in filtered_triggers:
        base_energy = _merged_energy.get(trigger, 0.0)
        modifier = config.energy_modifiers.get(trigger, 1.0)
        energy = base_energy * modifier * multiplier
        total_energy += energy

    return total_energy, filtered_triggers


# ============================================================================
# V3 Engine: Fake Transition Checking
# ============================================================================

async def _check_fake_transition(
    session_id: uuid.UUID,
    current_state: str,
    triggers: list[str],
) -> Optional[FakeTransition]:
    """
    Check if current fake transition should be revealed or activated.
    Returns the fake transition if one is active, or None.
    """
    fake = await _get_fake(session_id)

    if fake is None:
        return None

    # Decrement turns remaining
    fake.turns_remaining -= 1

    # Check reveal trigger
    if fake.trigger_reveal and fake.trigger_reveal in triggers:
        # Reveal happens now
        fake.turns_remaining = 0

    # Check auto-reveal by duration expiry
    if fake.turns_remaining <= 0:
        await _clear_fake(session_id)
        # When no explicit trigger_reveal, the fake expires with a "dramatic reveal":
        # inject negative energy penalty to represent the client dropping the mask
        if not fake.trigger_reveal:
            buffer = await _get_mood_buffer(session_id)
            buffer.current_energy -= 0.4  # trust penalty for deception reveal
            buffer.apply_ema()
            await _set_mood_buffer(session_id, buffer)
            logger.info(
                f"Fake transition auto-revealed for session {session_id}: "
                f"{fake.apparent_state} → {fake.real_state} (energy penalty applied)"
            )
        return None

    # Update fake transition
    await _set_fake(session_id, fake)
    return fake


# ============================================================================
# V3 Engine: Transition Resolution
# ============================================================================

async def _resolve_transition(
    current: str,
    energy: float,
    config: ArchetypeConfig,
    archetype_code: str = "skeptic",
) -> Optional[str]:
    """
    Determine target state based on accumulated energy and thresholds.

    v6: Uses archetype-specific graph variants instead of base ALLOWED_TRANSITIONS.
    """
    # v6: Get archetype-specific transition graph
    transitions = _v6_get_archetype_graph(archetype_code) if _HAS_V6 else ALLOWED_TRANSITIONS

    # Check for threshold crossing
    if energy >= config.threshold_positive:
        # Forward transition
        available_forward = transitions.get(current, set())
        if not available_forward:
            return None

        # Rank by closeness to "deal"
        state_rank = {
            "deal": 5, "negotiating": 4, "considering": 3,
            "curious": 2, "guarded": 1, "testing": 2, "callback": 1,
            "cold": 0, "hostile": -1, "hangup": -2,
        }

        best = max(available_forward, key=lambda s: state_rank.get(s, 0))
        return best

    elif energy <= config.threshold_negative:
        # Backward transition
        available_backward = transitions.get(current, set())
        if not available_backward:
            return None

        # Prefer colder states
        state_rank = {
            "cold": 0, "guarded": 1, "callback": 1, "testing": 2,
            "curious": 2, "considering": 3, "negotiating": 4,
            "deal": 5, "hostile": -1, "hangup": -2,
        }

        worst = min(available_backward, key=lambda s: state_rank.get(s, 0))
        return worst

    return None


# ============================================================================
# V3 Engine: Main Transition Function
# ============================================================================

async def transition_emotion_v3(
    session_id: uuid.UUID,
    archetype_code: str,
    triggers: list[str],
    blend: float = 1.0,
    secondary_archetype: Optional[str] = None,
) -> tuple[str, dict]:
    """
    Main V3 entry point for emotion transitions with multi-trigger support.

    Args:
        session_id: Session identifier
        archetype_code: Primary archetype code (must be in ARCHETYPE_CONFIGS)
        triggers: List of trigger codes that occurred this turn
        blend: Blending factor for hybrid archetypes (0.0-1.0)
        secondary_archetype: Optional secondary archetype for blending

    Returns:
        Tuple of (new_state, metadata_dict) where metadata includes:
            - energy_before: energy before triggers
            - energy_after: energy after triggers and EMA
            - energy_smoothed: EMA-smoothed energy
            - energy_delta: net energy change
            - triggers_applied: list of triggers that were applied
            - transition: whether a state transition occurred
            - previous_state: state before transition
            - rollback: whether this was a backward transition
            - is_fake: whether fake transition is active
            - fake_prompt: LLM injection for fake state (if active)
            - rollback_count: total rollbacks in session
            - peak_state: best state achieved
            - message_index: auto-incremented message index
    """
    # Serialize entire emotion transition per session to prevent concurrent
    # GET→mutate→SET races on buffer, memory, and state.
    lock = await _get_session_lock(session_id)
    async with lock:
        return await _transition_emotion_v3_inner(
            session_id, archetype_code, triggers, blend, secondary_archetype,
        )


async def _transition_emotion_v3_inner(
    session_id: uuid.UUID,
    archetype_code: str,
    triggers: list[str],
    blend: float = 1.0,
    secondary_archetype: Optional[str] = None,
) -> tuple[str, dict]:
    """Inner implementation of transition_emotion_v3 (called under session lock)."""
    try:
        # Get archetype config
        if archetype_code not in ARCHETYPE_CONFIGS:
            logger.warning(f"Unknown archetype: {archetype_code}, using skeptic")
            archetype_code = "skeptic"

        config = ARCHETYPE_CONFIGS[archetype_code]

        # Get current state
        current_state = await get_emotion(session_id)
        if not current_state:
            current_state = config.initial_state

        # Get mood buffer
        buffer = await _get_mood_buffer(session_id)
        if buffer.current_energy == 0.0 and buffer.energy_smoothed == 0.0:
            buffer.current_energy = config.initial_energy
            buffer.energy_smoothed = config.initial_energy
            buffer.ema_alpha = config.ema_alpha

        energy_before = buffer.current_energy

        # Apply decay
        buffer.apply_decay()

        # Apply triggers with priority rules
        trigger_delta, applied_triggers = await _apply_triggers(
            session_id, archetype_code, triggers, config
        )

        # Check for transition overrides
        target_override = None
        for trigger in applied_triggers:
            override_key = (current_state, trigger)
            if override_key in config.transition_overrides:
                target_override = config.transition_overrides[override_key]
                break

        # Handle special triggers
        if "insult" in applied_triggers:
            if current_state == "hostile":
                target_override = "hangup"
            else:
                target_override = "hostile"

        if "counter_aggression" in applied_triggers:
            if current_state == "hostile":
                target_override = "hangup"
            else:
                target_override = "hostile"

        if "challenge" in applied_triggers:
            if current_state in ("guarded", "curious", "considering"):
                target_override = "testing"

        if "defer" in applied_triggers:
            if current_state in ("guarded", "curious", "considering", "testing", "callback"):
                target_override = "callback"

        # Update buffer energy and apply EMA
        buffer.current_energy += trigger_delta
        buffer.apply_ema()
        energy_after = buffer.current_energy

        # Check fake transition
        fake = await _check_fake_transition(session_id, current_state, applied_triggers)

        # Resolve transition using EMA-smoothed energy
        new_state = current_state
        rollback = False
        transition_occurred = False

        # v6: Use archetype graph for override validation
        _arch_transitions = _v6_get_archetype_graph(archetype_code) if _HAS_V6 else ALLOWED_TRANSITIONS
        if target_override and target_override in _arch_transitions.get(current_state, set()):
            new_state = target_override
            transition_occurred = True
            buffer.reset_after_transition()
        else:
            resolved = await _resolve_transition(current_state, buffer.energy_smoothed, config, archetype_code)
            if resolved and resolved != current_state:
                new_state = resolved
                transition_occurred = True
                rollback = resolved in ("cold", "guarded", "callback")

                # Check for rollback from peak state
                memory = await _get_memory(session_id)
                state_rank = {
                    "cold": 0, "guarded": 1, "curious": 2, "considering": 3,
                    "negotiating": 4, "deal": 5, "testing": 2, "callback": 1,
                    "hostile": -1, "hangup": -2,
                }
                if state_rank.get(resolved, 0) < state_rank.get(memory.peak_state, 0):
                    rollback = True

                buffer.reset_after_transition()

        # Update memory with new state
        memory = await _update_memory(session_id, applied_triggers, new_state, rollback)

        # --- Anti-oscillation: suppress A→B→A ping-pong ---
        if transition_occurred and memory.is_oscillating():
            # Revert transition — client is stuck, don't let them bounce
            new_state = current_state
            transition_occurred = False
            rollback = False
            # Dampen energy to break the cycle
            buffer.current_energy *= 0.5
            buffer.energy_smoothed *= 0.5
            await _set_mood_buffer(session_id, buffer)
            logger.info(f"Anti-oscillation dampened for session {session_id}: suppressed {current_state}→{new_state}")

        # --- Rollback frustration escalation ---
        if memory.rollback_count >= 3:
            # Each rollback beyond 2 adds cumulative frustration penalty
            frustration_penalty = -0.1 * (memory.rollback_count - 2)
            buffer.current_energy += frustration_penalty
            buffer.apply_ema()
            await _set_mood_buffer(session_id, buffer)

        # 3+ consecutive rollbacks: tighten negative threshold (easier to regress further)
        if memory.consecutive_rollbacks >= 3:
            buffer.threshold_negative *= 0.8  # 20% more sensitive to regression
            await _set_mood_buffer(session_id, buffer)

        # Force hangup on excessive total rollbacks — but only from valid states
        if memory.rollback_count >= 5:
            if "hangup" in _arch_transitions.get(new_state, set()):
                new_state = "hangup"
                transition_occurred = True
            else:
                # Can't reach hangup from current state (e.g. "deal") — mark hostile if allowed
                if "hostile" in _arch_transitions.get(new_state, set()):
                    new_state = "hostile"
                    transition_occurred = True
                logger.warning(
                    "Session %s: 5+ rollbacks but hangup unreachable from %s",
                    session_id, new_state,
                )

        # Maybe activate fake transition
        if transition_occurred:
            await _maybe_activate_fake(session_id, new_state, config)

        # Get message index
        message_index = await _get_next_message_index(session_id)

        # Save state and buffer
        await set_emotion(
            session_id,
            new_state,
            previous_state=current_state,
            triggers=applied_triggers,
            energy_before=energy_before,
            energy_after=energy_after,
            is_fake=fake is not None,
            rollback=rollback,
            message_index=message_index,
        )
        await _set_mood_buffer(session_id, buffer)

        # Get fake prompt if active
        fake_prompt = await get_fake_prompt(session_id, archetype_code)

        # Build metadata (v6: include thresholds for intensity calculation)
        metadata = {
            "energy_before": energy_before,
            "energy_after": energy_after,
            "energy_smoothed": buffer.energy_smoothed,
            "energy_delta": trigger_delta,
            "triggers_applied": applied_triggers,
            "transition": transition_occurred,
            "previous_state": current_state,
            "rollback": rollback,
            "is_fake": fake is not None,
            "fake_prompt": fake_prompt,
            "rollback_count": memory.rollback_count,
            "peak_state": memory.peak_state,
            "message_index": message_index,
            "threshold_pos": config.threshold_positive,
            "threshold_neg": config.threshold_negative,
        }

        return new_state, metadata

    except Exception as e:
        logger.error(f"Error in transition_emotion_v3: {e}")
        return "cold", {"error": str(e)}


# ============================================================================
# V2 Backward Compatibility
# ============================================================================

async def transition_emotion_v2(
    session_id: uuid.UUID,
    archetype_code: str,
    trigger: str,
) -> tuple[str, dict]:
    """
    V2: Wrapper around V3 with single trigger support.
    Backward-compatible interface for clients using single-trigger model.
    """
    return await transition_emotion_v3(session_id, archetype_code, [trigger])


async def save_journey_snapshot(session_id: uuid.UUID) -> dict:
    """
    Package the full emotion journey for DB persistence before Redis cleanup.

    Returns a dict containing:
      - timeline: list of enriched timeline entries (state, triggers, energy, is_fake, rollback...)
      - summary: stats about the journey (total_transitions, rollbacks, peak_state, fake_count...)
      - mood_buffer_final: final MoodBuffer snapshot
      - memory_final: final InteractionMemory snapshot
    """
    try:
        timeline = await get_emotion_timeline(session_id)
        buffer = await _get_mood_buffer(session_id)
        memory = await _get_memory(session_id)
        fake = await _get_fake(session_id)

        # Compute summary stats
        total_transitions = sum(
            1 for e in timeline
            if e.get("previous_state") and e["state"] != e.get("previous_state")
        )
        rollback_entries = [e for e in timeline if e.get("rollback")]
        fake_entries = [e for e in timeline if e.get("is_fake")]
        unique_states = list(dict.fromkeys(e["state"] for e in timeline))

        # Identify turning points: transitions where direction changes
        turning_points = []
        state_rank = {
            "cold": 0, "guarded": 1, "curious": 2, "considering": 3,
            "negotiating": 4, "deal": 5, "testing": 2, "callback": 1,
            "hostile": -1, "hangup": -2,
        }
        prev_direction = 0  # 1 = forward, -1 = backward
        for entry in timeline:
            if not entry.get("previous_state"):
                continue
            rank_diff = state_rank.get(entry["state"], 0) - state_rank.get(entry["previous_state"], 0)
            direction = 1 if rank_diff > 0 else (-1 if rank_diff < 0 else 0)
            if direction != 0 and direction != prev_direction and prev_direction != 0:
                turning_points.append({
                    "message_index": entry.get("message_index"),
                    "from_state": entry["previous_state"],
                    "to_state": entry["state"],
                    "direction": "forward" if direction > 0 else "backward",
                    "triggers": entry.get("triggers", []),
                })
            if direction != 0:
                prev_direction = direction

        return {
            "timeline": timeline,
            "summary": {
                "total_entries": len(timeline),
                "total_transitions": total_transitions,
                "rollback_count": memory.rollback_count,
                "peak_state": memory.peak_state,
                "fake_count": len(fake_entries),
                "unique_states": unique_states,
                "turning_points": turning_points,
                "final_state": timeline[-1]["state"] if timeline else "cold",
                "has_active_fake": fake is not None,
            },
            "mood_buffer_final": buffer.to_dict(),
            "memory_final": memory.to_dict(),
        }
    except Exception as e:
        logger.warning(f"Failed to save journey snapshot: {e}")
        return {"timeline": [], "summary": {}, "mood_buffer_final": {}, "memory_final": {}}


def get_archetype_matrices(archetype_code: str) -> dict:
    """
    Computed property: return ARCHETYPE_MATRICES for backward compatibility.
    Maps archetype to its energy modifiers as a "matrix".
    """
    if archetype_code not in ARCHETYPE_CONFIGS:
        return {}

    config = ARCHETYPE_CONFIGS[archetype_code]
    return {
        "energy_modifiers": config.energy_modifiers,
        "counter_gates": config.counter_gates,
        "initial_state": config.initial_state,
        "initial_energy": config.initial_energy,
        "ema_alpha": config.ema_alpha,
    }
