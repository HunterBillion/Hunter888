"""TTS service — ElevenLabs multi-voice integration with personality-driven modulation (ТЗ-04 v2).

Extended architecture (v2):
    story.create → get_or_assign_voice(client_story_id) → permanent voice in ClientStory
    character.response → calculate_voice_params(base, emotion)
                       → modulate_by_human_factors(params, active_factors, pad_state)
                       → clamp all params
                       → smooth_params(current, target)  # EMA
                       → inject_hesitations(text, factors, pad_state)
                       → inject_pauses(text, emotion)
                       → synthesize_speech(text, voice_id, **params)
                       → tts.audio WS message

Key additions over v1:
    - get_or_assign_voice(): persistent voice in ClientStory (DB source of truth)
    - modulate_by_human_factors(): anger/fatigue/anxiety/sarcasm voice modulation
    - inject_hesitations(): text-level hesitations based on PAD arousal
    - generate_breathing_pauses(): sighs and breathing based on active factors
    - Couple mode: per-speaker factors (factors_a, factors_b)
    - Cache v3: key includes active_factors_hash
    - Startup preload via load_voice_data_on_startup()

Modifier order: base → emotion_delta → human_factor_delta → clamp → EMA
"""

import base64
import hashlib
import json
import logging
import math
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# --- Constants ---

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech"
MAX_TEXT_LENGTH = 1000
CHUNK_SIZE = 4096
DEFAULT_OUTPUT_FORMAT = "mp3_22050_32"
SMOOTHING_FACTOR = 0.4  # EMA factor: 0 = no smoothing, 1 = full lag
REDIS_VOICE_TTL = 7200  # 2 hours

# Conjunctions for pause injection (Russian)
_CONJUNCTIONS = ["но", "однако", "хотя", "впрочем", "зато"]

# Hesitation bank — BUG B2 fix (2026-05-04)
# Previously contained literal Russian filler words ("ну...", "э-э...", "как бы...")
# that were prepended to the LLM reply ONLY in the TTS path, not in the visible
# chat. Result: user heard "ну, у меня долг" but read just "у меня долг" —
# audio/text mismatch. Industry approach (Pipecat, LiveKit) is to trust the LLM
# for filler words and only inject paralinguistic CUES (pauses, breath sounds)
# that don't add words the listener can read back.
#
# What we keep:
#   * Plain ellipsis "..." — natural pause, no spoken word, ElevenLabs handles
#     it as a soft pause.
#   * "*вздох*" / "*выдох*" / "*вдох*" / "*пауза*" — these are TRANSFORMED to
#     real ElevenLabs v3 audio tags ([sighs]/[exhales]/[inhales]) by
#     services/tts_sanitizer.sanitize_for_tts() before synthesis (PR #207).
#     They produce real breath sounds, not spoken words.
_HESITATIONS = ["...", "..."]

_FACTOR_HESITATIONS = {
    "fatigue": ["*вздох*", "...", "..."],
    "anxiety": ["...", "*вдох*"],
    "anger": [],  # anger doesn't hesitate — it accelerates
    "sarcasm": ["...", "хм..."],  # "хм" is paralinguistic, kept; "ну-у" dropped
}

_FACTOR_BREATHING = {
    "fatigue": ["*вздох*", "*тяжёлый вздох*", "*пауза*"],
    "anxiety": ["*вдох*", "*нервный вздох*"],
    "anger": ["*выдох*"],
    "sarcasm": [],
}


# =============================================================================
# Types
# =============================================================================

@dataclass
class VoiceParams:
    """Calculated voice synthesis parameters for a single utterance."""
    stability: float = 0.5
    similarity_boost: float = 0.75
    style: float = 0.3
    speed: float = 1.0

    def to_dict(self) -> dict[str, float]:
        return {
            "stability": round(self.stability, 3),
            "similarity_boost": round(self.similarity_boost, 3),
            "style": round(self.style, 3),
            "speed": round(self.speed, 3),
        }

    @classmethod
    def from_dict(cls, d: dict[str, float]) -> "VoiceParams":
        return cls(
            stability=d.get("stability", 0.5),
            similarity_boost=d.get("similarity_boost", 0.75),
            style=d.get("style", 0.3),
            speed=d.get("speed", 1.0),
        )


@dataclass
class PADState:
    """Pleasure-Arousal-Dominance emotional state vector. Range: [-1.0, +1.0] each."""
    pleasure: float = 0.0
    arousal: float = 0.0
    dominance: float = 0.0

    @classmethod
    def from_dict(cls, d: dict[str, float] | None) -> "PADState":
        if not d:
            return cls()
        return cls(
            pleasure=d.get("pleasure", d.get("P", 0.0)),
            arousal=d.get("arousal", d.get("A", 0.0)),
            dominance=d.get("dominance", d.get("D", 0.0)),
        )


@dataclass
class HumanFactor:
    """Active human factor with intensity."""
    factor: str       # anger, fatigue, anxiety, sarcasm
    intensity: float  # 0.0–1.0
    since_call: int = 1

    @classmethod
    def from_dict(cls, d: dict) -> "HumanFactor":
        return cls(
            factor=d.get("factor", ""),
            intensity=d.get("intensity", 0.5),
            since_call=d.get("since_call", 1),
        )


@dataclass
class TTSResult:
    """Result of a TTS synthesis request."""
    audio_bytes: bytes
    format: str
    voice_id: str
    duration_estimate_ms: int
    cached: bool
    latency_ms: int
    characters_used: int
    voice_params: VoiceParams | None = None
    emotion: str | None = None
    active_factors: list[str] = field(default_factory=list)


@dataclass
class CoupleUtterance:
    """Single utterance in couple mode."""
    speaker: str  # "A" | "B" | "AB"
    text: str
    whisper: bool = False


class TTSError(Exception):
    """Raised when TTS synthesis fails."""


class TTSQuotaExhausted(TTSError):
    """Raised when ElevenLabs quota is exhausted (402/429)."""


# =============================================================================
# In-memory stores
# =============================================================================

# client_story_id → {voice_id, voice_code, base_params, archetype, gender}
# Read-through cache: source of truth is ClientStory in PostgreSQL
_story_voice_cache: dict[str, dict[str, Any]] = {}

# Legacy session-based cache (backward compat during migration)
_session_voices: dict[str, dict[str, Any]] = {}

# Audio cache: hash → bytes
_audio_cache: dict[str, bytes] = {}
_CACHE_MAX_SIZE = 200

# In-memory voice profiles (loaded from DB at startup)
_voice_profiles: list[dict[str, Any]] = []

# In-memory emotion modifiers (loaded from DB)
_emotion_modifiers: dict[str, dict[str, float]] = {}

# In-memory pause configs (loaded from DB)
_pause_configs: dict[str, dict[str, Any]] = {}

# Session voice params for EMA smoothing (session_id → VoiceParams)
_session_current_params: dict[str, VoiceParams] = {}

# Flag: voice data loaded from DB
_voice_data_loaded: bool = False

# Shared httpx client for ElevenLabs API (reuses TCP connections)
_shared_http_client: httpx.AsyncClient | None = None


def _get_shared_client() -> httpx.AsyncClient:
    """Get or create a shared httpx AsyncClient for ElevenLabs API."""
    global _shared_http_client
    if _shared_http_client is None or _shared_http_client.is_closed:
        _shared_http_client = httpx.AsyncClient(
            timeout=float(settings.elevenlabs_timeout_seconds),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _shared_http_client


async def close_tts_client() -> None:
    """Close the shared httpx client (call during app shutdown)."""
    global _shared_http_client
    if _shared_http_client and not _shared_http_client.is_closed:
        await _shared_http_client.aclose()
        _shared_http_client = None


# =============================================================================
# Fallback data (used when DB is unavailable)
# =============================================================================

_FALLBACK_EMOTION_MODIFIERS: dict[str, dict[str, float]] = {
    "cold":        {"stability_delta": +0.20, "similarity_delta": +0.05, "style_delta": -0.20, "speed_delta": +0.05, "instant": False},
    "guarded":     {"stability_delta": +0.10, "similarity_delta":  0.00, "style_delta": -0.10, "speed_delta":  0.00, "instant": False},
    "curious":     {"stability_delta": -0.05, "similarity_delta":  0.00, "style_delta": +0.10, "speed_delta": -0.05, "instant": False},
    "considering": {"stability_delta": +0.05, "similarity_delta":  0.00, "style_delta":  0.00, "speed_delta": -0.10, "instant": False},
    "negotiating": {"stability_delta": -0.10, "similarity_delta": +0.05, "style_delta": +0.15, "speed_delta": +0.05, "instant": False},
    "deal":        {"stability_delta": -0.15, "similarity_delta":  0.00, "style_delta": +0.20, "speed_delta": -0.05, "instant": False},
    "testing":     {"stability_delta": +0.15, "similarity_delta": +0.05, "style_delta":  0.00, "speed_delta": +0.10, "instant": False},
    "callback":    {"stability_delta": +0.10, "similarity_delta":  0.00, "style_delta": -0.10, "speed_delta":  0.00, "instant": False},
    "hostile":     {"stability_delta": -0.30, "similarity_delta": -0.10, "style_delta": +0.30, "speed_delta": +0.15, "instant": True},
    "hangup":      {"stability_delta": +0.20, "similarity_delta":  0.00, "style_delta": -0.15, "speed_delta": +0.10, "instant": True},
}

_FALLBACK_PAUSE_CONFIGS: dict[str, dict[str, Any]] = {
    "cold":        {"after_period_ms": 200, "before_conjunction_ms": 100, "after_comma_ms": 100, "hesitation_probability": 0.05, "hesitation_pool": [], "max_hesitations": 0, "dramatic_pause_ms": 0, "breath_probability": 0.10},
    "guarded":     {"after_period_ms": 500, "before_conjunction_ms": 400, "after_comma_ms": 250, "hesitation_probability": 0.25, "hesitation_pool": ["ну...", "это...", "как бы..."], "max_hesitations": 2, "dramatic_pause_ms": 300, "breath_probability": 0.20},
    "curious":     {"after_period_ms": 200, "before_conjunction_ms": 150, "after_comma_ms": 100, "hesitation_probability": 0.05, "hesitation_pool": [], "max_hesitations": 0, "dramatic_pause_ms": 200, "breath_probability": 0.15},
    "considering": {"after_period_ms": 800, "before_conjunction_ms": 600, "after_comma_ms": 400, "hesitation_probability": 0.30, "hesitation_pool": ["хм...", "ну...", "вот...", "значит...", "то есть..."], "max_hesitations": 3, "dramatic_pause_ms": 500, "breath_probability": 0.25},
    "negotiating": {"after_period_ms": 300, "before_conjunction_ms": 250, "after_comma_ms": 150, "hesitation_probability": 0.10, "hesitation_pool": ["так..."], "max_hesitations": 1, "dramatic_pause_ms": 400, "breath_probability": 0.15},
    "deal":        {"after_period_ms": 400, "before_conjunction_ms": 200, "after_comma_ms": 200, "hesitation_probability": 0.05, "hesitation_pool": [], "max_hesitations": 0, "dramatic_pause_ms": 300, "breath_probability": 0.15},
    "testing":     {"after_period_ms": 300, "before_conjunction_ms": 200, "after_comma_ms": 150, "hesitation_probability": 0.05, "hesitation_pool": [], "max_hesitations": 0, "dramatic_pause_ms": 500, "breath_probability": 0.10},
    "callback":    {"after_period_ms": 500, "before_conjunction_ms": 300, "after_comma_ms": 250, "hesitation_probability": 0.15, "hesitation_pool": ["ну...", "давайте..."], "max_hesitations": 2, "dramatic_pause_ms": 0, "breath_probability": 0.20},
    "hostile":     {"after_period_ms": 100, "before_conjunction_ms": 50,  "after_comma_ms": 50,  "hesitation_probability": 0.0,  "hesitation_pool": [], "max_hesitations": 0, "dramatic_pause_ms": 0, "breath_probability": 0.30},
    "hangup":      {"after_period_ms": 200, "before_conjunction_ms": 0,   "after_comma_ms": 100, "hesitation_probability": 0.0,  "hesitation_pool": [], "max_hesitations": 0, "dramatic_pause_ms": 300, "breath_probability": 0.05},
}

_ARCHETYPE_VOICE_TYPE: dict[str, str] = {
    "skeptic": "firm", "anxious": "soft", "aggressive": "aggressive",
    "passive": "soft", "paranoid": "firm", "manipulator": "warm",
    "desperate": "soft", "know_it_all": "firm", "sarcastic": "neutral",
    "hostile": "aggressive", "couple": "mixed", "blamer": "aggressive",
    "delegator": "neutral", "returner": "neutral", "pragmatic": "firm",
    "negotiator": "warm", "ashamed": "soft", "shopper": "firm",
    "rushed": "firm", "grateful": "warm", "avoidant": "neutral",
    "crying": "soft", "overwhelmed": "neutral", "referred": "warm",
    "lawyer_client": "firm",
}

_ARCHETYPE_BASE_PARAMS: dict[str, dict[str, float]] = {
    "skeptic":       {"stability": 0.60, "similarity_boost": 0.80, "style": 0.20, "speed": 1.00},
    "anxious":       {"stability": 0.40, "similarity_boost": 0.70, "style": 0.15, "speed": 0.90},
    "aggressive":    {"stability": 0.30, "similarity_boost": 0.70, "style": 0.45, "speed": 1.10},
    "passive":       {"stability": 0.70, "similarity_boost": 0.65, "style": 0.10, "speed": 0.85},
    "paranoid":      {"stability": 0.50, "similarity_boost": 0.75, "style": 0.30, "speed": 1.05},
    "manipulator":   {"stability": 0.50, "similarity_boost": 0.75, "style": 0.40, "speed": 0.95},
    "desperate":     {"stability": 0.30, "similarity_boost": 0.65, "style": 0.35, "speed": 1.00},
    "know_it_all":   {"stability": 0.65, "similarity_boost": 0.85, "style": 0.30, "speed": 1.10},
    "sarcastic":     {"stability": 0.50, "similarity_boost": 0.75, "style": 0.50, "speed": 1.05},
    "hostile":       {"stability": 0.20, "similarity_boost": 0.60, "style": 0.50, "speed": 1.20},
    "couple":        {"stability": 0.50, "similarity_boost": 0.75, "style": 0.30, "speed": 1.00},
    "blamer":        {"stability": 0.35, "similarity_boost": 0.70, "style": 0.40, "speed": 1.05},
    "delegator":     {"stability": 0.65, "similarity_boost": 0.70, "style": 0.15, "speed": 0.95},
    "returner":      {"stability": 0.55, "similarity_boost": 0.75, "style": 0.25, "speed": 0.95},
    "pragmatic":     {"stability": 0.70, "similarity_boost": 0.85, "style": 0.15, "speed": 1.05},
    "negotiator":    {"stability": 0.55, "similarity_boost": 0.80, "style": 0.35, "speed": 1.00},
    "ashamed":       {"stability": 0.45, "similarity_boost": 0.60, "style": 0.10, "speed": 0.85},
    "shopper":       {"stability": 0.60, "similarity_boost": 0.80, "style": 0.25, "speed": 1.05},
    "rushed":        {"stability": 0.55, "similarity_boost": 0.70, "style": 0.20, "speed": 1.25},
    "grateful":      {"stability": 0.60, "similarity_boost": 0.80, "style": 0.35, "speed": 0.95},
    "avoidant":      {"stability": 0.60, "similarity_boost": 0.70, "style": 0.20, "speed": 0.90},
    "crying":        {"stability": 0.25, "similarity_boost": 0.60, "style": 0.40, "speed": 0.80},
    "overwhelmed":   {"stability": 0.40, "similarity_boost": 0.65, "style": 0.25, "speed": 0.85},
    "referred":      {"stability": 0.55, "similarity_boost": 0.80, "style": 0.30, "speed": 1.00},
    "lawyer_client": {"stability": 0.70, "similarity_boost": 0.85, "style": 0.20, "speed": 1.05},
}

# Human factor → voice modulation deltas (applied as multipliers of intensity)
# Format: at intensity=1.0 these are the full deltas
_HUMAN_FACTOR_DELTAS: dict[str, dict[str, float]] = {
    "anger": {
        "stability_delta": -0.30,       # very unstable when angry
        "similarity_delta": -0.05,
        "style_delta": +0.25,           # more expressive/theatrical
        "speed_delta": +0.20,           # +20% speed
    },
    "fatigue": {
        "stability_delta": +0.20,       # monotone, flat
        "similarity_delta": -0.05,
        "style_delta": -0.15,           # less expressive
        "speed_delta": -0.25,           # -25% speed
    },
    "anxiety": {
        "stability_delta": -0.20,       # voice trembles
        "similarity_delta": -0.10,      # slight tremor via similarity reduction
        "style_delta": +0.10,
        "speed_delta": +0.15,           # +15% speed (rushed)
    },
    "sarcasm": {
        "stability_delta": -0.05,       # slightly uneven (deliberate)
        "similarity_delta": +0.05,
        "style_delta": +0.20,           # style=0.50+ for theatrical delivery
        "speed_delta": +0.05,           # slightly faster
    },
}


# =============================================================================
# Internal helpers
# =============================================================================

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _clamp_params(params: VoiceParams) -> VoiceParams:
    """Clamp all params to valid ElevenLabs ranges."""
    return VoiceParams(
        stability=_clamp(params.stability, 0.0, 1.0),
        similarity_boost=_clamp(params.similarity_boost, 0.0, 1.0),
        style=_clamp(params.style, 0.0, 1.0),
        speed=_clamp(params.speed, 0.5, 2.0),
    )


def _get_emotion_modifier(emotion: str) -> dict[str, float]:
    """Get emotion modifier from loaded DB data or fallback."""
    if _emotion_modifiers:
        return _emotion_modifiers.get(emotion, _FALLBACK_EMOTION_MODIFIERS.get(emotion, {}))
    return _FALLBACK_EMOTION_MODIFIERS.get(emotion, {})


def _get_pause_config(emotion: str) -> dict[str, Any]:
    """Get pause config from loaded DB data or fallback."""
    if _pause_configs:
        return _pause_configs.get(emotion, _FALLBACK_PAUSE_CONFIGS.get(emotion, {}))
    return _FALLBACK_PAUSE_CONFIGS.get(emotion, {})


def _active_factors_hash(factors: list[HumanFactor]) -> str:
    """Deterministic hash of active factors for cache key."""
    if not factors:
        return "nf"
    items = sorted((f.factor, round(f.intensity, 1)) for f in factors)
    return hashlib.md5(str(items).encode()).hexdigest()[:8]


# =============================================================================
# VoiceProfileManager — persistent voice assignment
# =============================================================================

class VoiceProfileManager:
    """Selects and assigns voices to client stories (persistent) or sessions (legacy)."""

    @staticmethod
    async def get_or_assign_voice(
        client_story_id: str,
        gender: str | None = None,
        archetype: str | None = None,
        age_range: str | None = None,
        extraversion: float | None = None,
        db_session=None,
    ) -> dict[str, Any]:
        """Assign a permanent voice to a ClientStory.

        First call: selects voice based on archetype/gender/age/extraversion,
        stores in ClientStory.voice_id + voice_params_snapshot.
        Subsequent calls: returns cached/DB voice.

        Selection algorithm:
            1. Check in-memory cache
            2. Check DB (ClientStory.voice_id)
            3. If unassigned: pick from profiles, write to DB, cache
            4. Extraversion modulates base_style (+/-0.1 from mean)

        Returns:
            dict with: voice_id, voice_code, base_stability, base_similarity_boost,
                       base_style, base_speed, gender, archetype.
        """
        story_key = str(client_story_id)

        # 1. In-memory cache hit — but validate gender, reject mismatched
        if story_key in _story_voice_cache:
            cached = _story_voice_cache[story_key]
            if gender and cached.get("gender") and cached["gender"] != gender:
                logger.warning(
                    "TTS voice cache gender mismatch for story %s: cached=%s, requested=%s — reassigning",
                    story_key, cached.get("gender"), gender,
                )
                _story_voice_cache.pop(story_key, None)
            else:
                return cached

        # 2. Check DB — same validation
        if db_session:
            try:
                assignment = await VoiceProfileManager._load_from_db(story_key, db_session)
                if assignment:
                    if gender and assignment.get("gender") and assignment["gender"] != gender:
                        logger.warning(
                            "TTS voice DB gender mismatch for story %s: stored=%s, requested=%s — reassigning",
                            story_key, assignment.get("gender"), gender,
                        )
                        # Skip DB cache; fall through to re-pick
                    else:
                        _story_voice_cache[story_key] = assignment
                        return assignment
            except Exception as exc:
                logger.warning("Failed to load voice from DB for story %s: %s", story_key, exc)

        # 3. Pick new voice
        assignment = VoiceProfileManager._pick_from_profiles(gender, archetype, age_range)
        if not assignment:
            # Fallback to legacy env-based
            voice_id = VoiceProfileManager._pick_legacy(gender)
            base = _ARCHETYPE_BASE_PARAMS.get(archetype or "skeptic", _ARCHETYPE_BASE_PARAMS["skeptic"])
            assignment = {
                "voice_id": voice_id,
                "voice_code": f"env_{voice_id[:8]}",
                "base_stability": base["stability"],
                "base_similarity_boost": base["similarity_boost"],
                "base_style": base["style"],
                "base_speed": base["speed"],
                "gender": gender or "unknown",
                "archetype": archetype,
            }

        # Apply extraversion modulation to base_style
        if extraversion is not None:
            # Extraversion [-1, 1] or [0, 1] → style shift
            # High extraversion → more expressive, low → more restrained
            e_norm = extraversion if -1 <= extraversion <= 1 else (extraversion - 0.5) * 2
            style_shift = e_norm * 0.10  # ±0.10 range
            assignment["base_style"] = _clamp(
                assignment["base_style"] + style_shift, 0.0, 1.0
            )

        assignment["archetype"] = archetype

        # 4. Persist to DB
        if db_session:
            try:
                await VoiceProfileManager._save_to_db(
                    story_key, assignment, db_session
                )
            except Exception as exc:
                logger.warning("Failed to save voice to DB for story %s: %s", story_key, exc)

        # 5. Cache
        _story_voice_cache[story_key] = assignment
        logger.info(
            "TTS_VOICE_ASSIGN | story=%s | voice=%s | archetype=%s | gender=%s",
            story_key, assignment.get("voice_code"), archetype, gender,
        )
        return assignment

    @staticmethod
    async def _load_from_db(story_id: str, db_session) -> dict[str, Any] | None:
        """Load voice assignment from ClientStory in DB."""
        from app.models.roleplay import ClientStory
        from sqlalchemy import select

        result = await db_session.execute(
            select(ClientStory).where(ClientStory.id == story_id)
        )
        story = result.scalar_one_or_none()
        if not story or not story.voice_id:
            return None

        snapshot = story.voice_params_snapshot or {}
        return {
            "voice_id": story.voice_id,
            "voice_code": snapshot.get("voice_code", f"db_{story.voice_id[:8]}"),
            "base_stability": snapshot.get("stability", 0.5),
            "base_similarity_boost": snapshot.get("similarity_boost", 0.75),
            "base_style": snapshot.get("style", 0.3),
            "base_speed": snapshot.get("speed", 1.0),
            "gender": snapshot.get("gender", "unknown"),
            "archetype": snapshot.get("archetype"),
        }

    @staticmethod
    async def _save_to_db(story_id: str, assignment: dict, db_session) -> None:
        """Persist voice assignment to ClientStory."""
        from app.models.roleplay import ClientStory
        from sqlalchemy import select, update

        snapshot = {
            "voice_code": assignment.get("voice_code"),
            "stability": assignment["base_stability"],
            "similarity_boost": assignment["base_similarity_boost"],
            "style": assignment["base_style"],
            "speed": assignment["base_speed"],
            "gender": assignment.get("gender"),
            "archetype": assignment.get("archetype"),
        }

        await db_session.execute(
            update(ClientStory)
            .where(ClientStory.id == story_id)
            .values(
                voice_id=assignment["voice_id"],
                voice_params_snapshot=snapshot,
            )
        )
        await db_session.commit()
        logger.info("TTS voice persisted to DB for story %s", story_id)

    @staticmethod
    def _pick_from_profiles(
        gender: str | None,
        archetype: str | None,
        age_range: str | None = None,
    ) -> dict[str, Any] | None:
        """Pick from loaded DB voice profiles."""
        candidates = _voice_profiles
        if not candidates:
            return None

        # Filter by gender — FAIL CLOSED: if requested gender has no matches,
        # return None so caller falls back to env-based _pick_legacy which has
        # proper per-gender pools. Previously soft-fallback silently picked
        # a wrong-gender voice (bug: female client → male voice).
        if gender:
            gendered = [vp for vp in candidates if vp.get("gender") == gender]
            if not gendered:
                return None
            candidates = gendered

        # Filter by archetype
        if archetype:
            matched = [
                vp for vp in candidates
                if archetype in (vp.get("archetype_codes") or [])
            ]
            if matched:
                candidates = matched
            else:
                # Fallback: match by voice_type
                target_type = _ARCHETYPE_VOICE_TYPE.get(archetype, "neutral")
                type_matched = [vp for vp in candidates if vp.get("voice_type") == target_type]
                if type_matched:
                    candidates = type_matched

        # Filter by age_range
        if age_range:
            age_matched = [vp for vp in candidates if vp.get("age_range") == age_range]
            if age_matched:
                candidates = age_matched

        if not candidates:
            return None

        vp = random.choice(candidates)
        return {
            "voice_id": vp["voice_id"],
            "voice_code": vp["voice_code"],
            "base_stability": vp["base_stability"],
            "base_similarity_boost": vp["base_similarity_boost"],
            "base_style": vp["base_style"],
            "base_speed": vp["base_speed"],
            "gender": vp.get("gender", "unknown"),
        }

    @staticmethod
    def _pick_legacy(gender: str | None) -> str:
        """Fallback: pick from env-based voice pools."""
        if gender == "female" and settings.elevenlabs_female_voices:
            voices = settings.elevenlabs_female_voices
        elif gender == "male" and settings.elevenlabs_male_voices:
            voices = settings.elevenlabs_male_voices
        else:
            voices = settings.elevenlabs_voice_list

        if not voices:
            raise TTSError("No ElevenLabs voices configured")
        return random.choice(voices)


# --- Legacy API compatibility ---

def pick_voice_for_session(
    session_id: str,
    gender: str | None = None,
    archetype: str | None = None,
) -> str:
    """Legacy sync API: assign voice to session. Returns voice_id."""
    if session_id in _session_voices:
        return _session_voices[session_id]["voice_id"]

    assignment = VoiceProfileManager._pick_from_profiles(gender, archetype)
    if not assignment:
        voice_id = VoiceProfileManager._pick_legacy(gender)
        base = _ARCHETYPE_BASE_PARAMS.get(archetype or "skeptic", _ARCHETYPE_BASE_PARAMS["skeptic"])
        assignment = {
            "voice_id": voice_id,
            "voice_code": f"env_{voice_id[:8]}",
            "base_stability": base["stability"],
            "base_similarity_boost": base["similarity_boost"],
            "base_style": base["style"],
            "base_speed": base["speed"],
            "gender": gender or "unknown",
            "archetype": archetype,
        }

    _session_voices[session_id] = assignment
    return assignment["voice_id"]


def get_session_voice(session_id: str) -> str | None:
    """Get the voice_id assigned to a session."""
    assignment = _session_voices.get(session_id)
    return assignment["voice_id"] if assignment else None


def get_session_assignment(session_id: str) -> dict[str, Any] | None:
    """Get full voice assignment for a session."""
    return _session_voices.get(session_id)


def release_session_voice(session_id: str) -> None:
    """Clean up voice assignment and smoothing state when session ends."""
    removed = _session_voices.pop(session_id, None)
    _session_current_params.pop(session_id, None)
    if removed:
        logger.debug("TTS voice released for session %s", session_id)


def get_available_voices() -> list[str]:
    return settings.elevenlabs_voice_list


# =============================================================================
# Voice parameter calculation pipeline
# =============================================================================

def calculate_voice_params(
    base_params: dict[str, float],
    emotion: str,
) -> VoiceParams:
    """Step 1: base + emotion delta (NOT clamped yet — clamping after factors)."""
    modifier = _get_emotion_modifier(emotion)
    if not modifier:
        return VoiceParams(**{k: v for k, v in base_params.items()
                              if k in ("stability", "similarity_boost", "style", "speed")})

    return VoiceParams(
        stability=base_params.get("stability", 0.5) + modifier.get("stability_delta", 0),
        similarity_boost=base_params.get("similarity_boost", 0.75) + modifier.get("similarity_delta", 0),
        style=base_params.get("style", 0.3) + modifier.get("style_delta", 0),
        speed=base_params.get("speed", 1.0) + modifier.get("speed_delta", 0),
    )


def modulate_by_human_factors(
    params: VoiceParams,
    active_factors: list[HumanFactor],
    pad_state: PADState | None = None,
) -> VoiceParams:
    """Step 2: Apply human factor deltas scaled by intensity.

    Each active factor contributes: delta * intensity.
    Multiple factors stack additively.
    PAD arousal modulates overall expressiveness.

    Args:
        params: Voice params after emotion delta (NOT yet clamped).
        active_factors: List of active human factors with intensities.
        pad_state: Current PAD emotional vector.

    Returns:
        VoiceParams with factor deltas applied (NOT yet clamped).
    """
    if not active_factors:
        # Even without factors, PAD arousal can modulate
        if pad_state and abs(pad_state.arousal) > 0.3:
            arousal_effect = pad_state.arousal * 0.08
            params = VoiceParams(
                stability=params.stability - arousal_effect,  # high arousal → less stable
                similarity_boost=params.similarity_boost,
                style=params.style + abs(arousal_effect),     # more dynamic
                speed=params.speed + arousal_effect * 0.5,    # high arousal → faster
            )
        return params

    stab_delta = 0.0
    sim_delta = 0.0
    style_delta = 0.0
    speed_delta = 0.0

    for hf in active_factors:
        deltas = _HUMAN_FACTOR_DELTAS.get(hf.factor)
        if not deltas:
            continue
        intensity = _clamp(hf.intensity, 0.0, 1.0)
        stab_delta += deltas["stability_delta"] * intensity
        sim_delta += deltas["similarity_delta"] * intensity
        style_delta += deltas["style_delta"] * intensity
        speed_delta += deltas["speed_delta"] * intensity

    # PAD arousal on top (if significant)
    if pad_state and abs(pad_state.arousal) > 0.3:
        arousal_effect = pad_state.arousal * 0.08
        stab_delta -= arousal_effect
        style_delta += abs(arousal_effect)
        speed_delta += arousal_effect * 0.5

    return VoiceParams(
        stability=params.stability + stab_delta,
        similarity_boost=params.similarity_boost + sim_delta,
        style=params.style + style_delta,
        speed=params.speed + speed_delta,
    )


def smooth_params(
    current: VoiceParams,
    target: VoiceParams,
    emotion: str,
    factor: float = SMOOTHING_FACTOR,
) -> VoiceParams:
    """Step 4: EMA smoothing between replies.

    Exceptions (instant transition, no smoothing):
        - hostile: anger is sudden
        - hangup: abrupt disconnect
    """
    modifier = _get_emotion_modifier(emotion)
    if modifier.get("instant", False):
        return target

    return VoiceParams(
        stability=current.stability + factor * (target.stability - current.stability),
        similarity_boost=current.similarity_boost + factor * (target.similarity_boost - current.similarity_boost),
        style=current.style + factor * (target.style - current.style),
        speed=current.speed + factor * (target.speed - current.speed),
    )


def get_modulated_params(
    session_id: str,
    emotion: str,
    active_factors: list[HumanFactor] | None = None,
    pad_state: PADState | None = None,
    client_story_id: str | None = None,
) -> VoiceParams:
    """Full pipeline: base → emotion → factors → clamp → EMA → store.

    Call this for each reply to get the final params for synthesis.
    """
    # Get base assignment (prefer story, fallback to session)
    if client_story_id and str(client_story_id) in _story_voice_cache:
        assignment = _story_voice_cache[str(client_story_id)]
    else:
        assignment = get_session_assignment(session_id)
    if not assignment:
        return VoiceParams()

    base = {
        "stability": assignment.get("base_stability", 0.5),
        "similarity_boost": assignment.get("base_similarity_boost", 0.75),
        "style": assignment.get("base_style", 0.3),
        "speed": assignment.get("base_speed", 1.0),
    }

    # Step 1: base + emotion delta
    after_emotion = calculate_voice_params(base, emotion)

    # Step 2: + human factor deltas
    after_factors = modulate_by_human_factors(
        after_emotion, active_factors or [], pad_state
    )

    # Step 3: clamp to valid ranges
    clamped = _clamp_params(after_factors)

    # Step 4: EMA smoothing
    current = _session_current_params.get(session_id)
    if current:
        final = smooth_params(current, clamped, emotion)
    else:
        final = clamped

    _session_current_params[session_id] = final
    return final


# =============================================================================
# Text processing: hesitations + pauses (two-pass)
# =============================================================================

def inject_hesitations(
    text: str,
    active_factors: list[HumanFactor] | None = None,
    pad_state: PADState | None = None,
) -> str:
    """Pass 1: Insert text-level hesitations and breathing based on factors + PAD.

    Called BEFORE inject_pauses() to avoid breaking SSML tags.

    Rules:
        - Probability based on PAD arousal: high arousal → more hesitations
        - Factor-specific hesitation pools
        - Anger suppresses hesitations (replaces with emphatic pauses)
        - Fatigue adds sighs between sentences
        - Max 2 hesitations per utterance to avoid overload
    """
    # 2026-04-22: removed early return when no factors. Real humans hesitate
    # naturally even when calm — the model previously sounded too "polished"
    # because it skipped hesitations on default cold/curious states (no
    # active factors, low arousal). Now we always allow a small probability
    # (~10%) of base hesitation per sentence so replies don't sound scripted.
    factors_dict = {hf.factor: hf for hf in (active_factors or [])}

    # Anger suppresses hesitations
    if "anger" in factors_dict and factors_dict["anger"].intensity > 0.5:
        return text

    # Calculate hesitation probability from arousal
    base_prob = 0.1
    if pad_state:
        # Higher arousal (positive = agitated) → more hesitations
        # But very high arousal (anger) → suppressed (handled above)
        arousal_bonus = max(0, pad_state.arousal) * 0.3
        base_prob += arousal_bonus

    # Factor-specific probability boosts
    if "anxiety" in factors_dict:
        base_prob += factors_dict["anxiety"].intensity * 0.25
    if "fatigue" in factors_dict:
        base_prob += factors_dict["fatigue"].intensity * 0.15

    base_prob = min(base_prob, 0.7)  # cap at 70%

    # Build hesitation pool from active factors
    pool = list(_HESITATIONS)  # copy base pool
    for factor_name, hf in factors_dict.items():
        extra = _FACTOR_HESITATIONS.get(factor_name, [])
        if extra and hf.intensity > 0.3:
            pool.extend(extra)

    # Insert hesitations
    max_inserts = 2
    inserted = 0
    sentences = text.split(". ")
    result_parts = []

    for i, sent in enumerate(sentences):
        if not sent.strip():
            result_parts.append(sent)
            continue

        # Maybe insert breathing (fatigue)
        if "fatigue" in factors_dict and i > 0:
            breath_pool = _FACTOR_BREATHING.get("fatigue", [])
            fatigue_intensity = factors_dict["fatigue"].intensity
            if breath_pool and random.random() < fatigue_intensity * 0.3:
                sent = random.choice(breath_pool) + " " + sent

        # Maybe insert hesitation at start of sentence
        if inserted < max_inserts and pool and random.random() < base_prob:
            hesitation = random.choice(pool)
            sent = hesitation + " " + sent
            inserted += 1

        # Anxiety: maybe insert mid-sentence hesitation before a comma
        if "anxiety" in factors_dict and inserted < max_inserts:
            anxiety_i = factors_dict["anxiety"].intensity
            comma_pos = sent.find(", ")
            if comma_pos > 10 and random.random() < anxiety_i * 0.3:
                anxiety_pool = _FACTOR_HESITATIONS.get("anxiety", pool)
                h = random.choice(anxiety_pool) if anxiety_pool else random.choice(pool)
                insert_at = comma_pos + 2
                sent = sent[:insert_at] + h + " " + sent[insert_at:]
                inserted += 1

        result_parts.append(sent)

    return ". ".join(result_parts)


def inject_pauses(text: str, emotion: str, active_factors: list[HumanFactor] | None = None) -> str:
    """Pass 2: Insert SSML <break> tags based on emotion state + factors.

    Factor modulations on pause timing:
        - anger: shorter all pauses (×0.5)
        - fatigue: longer all pauses (×1.5)
        - anxiety: slightly shorter (×0.8)
        - sarcasm: micro-pauses before key words (+150ms dramatic)
    """
    config = _get_pause_config(emotion)
    if not config:
        return text

    # Calculate factor multiplier for pause duration
    pause_mult = 1.0
    has_sarcasm = False
    if active_factors:
        for hf in active_factors:
            if hf.factor == "anger" and hf.intensity > 0.3:
                pause_mult *= max(0.5, 1.0 - hf.intensity * 0.5)
            elif hf.factor == "fatigue" and hf.intensity > 0.3:
                pause_mult *= min(1.5, 1.0 + hf.intensity * 0.5)
            elif hf.factor == "anxiety" and hf.intensity > 0.3:
                pause_mult *= max(0.8, 1.0 - hf.intensity * 0.2)
            elif hf.factor == "sarcasm" and hf.intensity > 0.3:
                has_sarcasm = True

    # 1. Pauses after periods
    after_period = int(config.get("after_period_ms", 300) * pause_mult)
    if after_period > 0:
        text = re.sub(
            r'\. ',
            f'. <break time="{after_period}ms"/> ',
            text,
        )

    # 2. Pauses before conjunctions
    before_conj = int(config.get("before_conjunction_ms", 200) * pause_mult)
    if before_conj > 0:
        for conj in _CONJUNCTIONS:
            text = text.replace(
                f" {conj} ",
                f' <break time="{before_conj}ms"/> {conj} ',
            )

    # 3. Pauses after commas (only if significant)
    after_comma = int(config.get("after_comma_ms", 150) * pause_mult)
    if after_comma > 200:
        text = re.sub(
            r', ',
            f', <break time="{after_comma}ms"/> ',
            text,
        )

    # 4. Hesitations from pause config (legacy, kept for backward compat)
    hesit_prob = config.get("hesitation_probability", 0)
    hesit_pool = config.get("hesitation_pool", [])
    max_hesit = config.get("max_hesitations", 1)
    if hesit_prob > 0 and hesit_pool and random.random() < hesit_prob:
        n_hesit = min(random.randint(1, max_hesit), max_hesit)
        for _ in range(n_hesit):
            hesitation = random.choice(hesit_pool)
            first_comma = text.find(", ")
            if first_comma > 0 and random.random() < 0.5:
                insert_pos = first_comma + 2
                text = text[:insert_pos] + f'{hesitation} <break time="300ms"/> ' + text[insert_pos:]
            else:
                text = f'{hesitation} <break time="300ms"/> ' + text

    # 5. Sarcasm micro-pauses: <break time="150ms"/> before question marks and exclamations
    if has_sarcasm:
        text = re.sub(r'(\S)\?', r'\1 <break time="150ms"/>?', text)
        text = re.sub(r'(\S)!', r'\1 <break time="150ms"/>!', text)

    return text


# =============================================================================
# Couple mode — [A]/[B] parsing with per-speaker factors
# =============================================================================

_COUPLE_PATTERN = re.compile(
    r'\[(A|B|AB)(?:\s+шёпот)?\]\s*(.+?)(?=\[(?:A|B|AB)|$)',
    re.DOTALL,
)


def parse_couple_response(text: str) -> list[CoupleUtterance]:
    """Parse LLM couple-mode response into individual utterances."""
    if not re.search(r'\[(A|B|AB)', text):
        return [CoupleUtterance(speaker="A", text=text.strip())]

    utterances = []
    for match in re.finditer(r'\[(A|B|AB)(\s+шёпот)?\]\s*(.+?)(?=\[(?:A|B|AB)|$)', text, re.DOTALL):
        speaker = match.group(1)
        whisper = bool(match.group(2))
        utt_text = match.group(3).strip()
        if utt_text:
            utterances.append(CoupleUtterance(speaker=speaker, text=utt_text, whisper=whisper))

    return utterances or [CoupleUtterance(speaker="A", text=text.strip())]


# =============================================================================
# Cache v3 — includes voice params + active factors hash
# =============================================================================

def _cache_key_v3(
    text: str,
    voice_id: str,
    model_id: str,
    params: VoiceParams,
    factors: list[HumanFactor] | None = None,
) -> str:
    """Generate cache key including voice params + factor hash."""
    rounded = {
        "s": round(params.stability, 1),
        "b": round(params.similarity_boost, 1),
        "t": round(params.style, 1),
        "p": round(params.speed, 1),
    }
    fh = _active_factors_hash(factors or [])
    content = f"{voice_id}:{model_id}:{json.dumps(rounded, sort_keys=True)}:{fh}:{text.strip().lower()}"
    return hashlib.md5(content.encode()).hexdigest()


# Legacy cache keys (backward compat)
def _cache_key_v2(text: str, voice_id: str, model_id: str, params: VoiceParams) -> str:
    return _cache_key_v3(text, voice_id, model_id, params)


def _cache_key(text: str, voice_id: str, model_id: str) -> str:
    return _cache_key_v3(text, voice_id, model_id, VoiceParams())


# =============================================================================
# Helpers
# =============================================================================

def _estimate_duration_ms(text: str, speed: float = 1.0) -> int:
    """Rough estimate: ~150 words/min for Russian, adjusted by speed."""
    chars = len(text.strip())
    words = chars / 6.0
    minutes = words / 150.0 / max(speed, 0.5)
    return int(minutes * 60 * 1000)


def _is_configured() -> bool:
    # Either ElevenLabs fully configured, OR navy TTS enabled as primary
    if settings.navy_tts_enabled and settings.local_llm_url and settings.local_llm_api_key:
        return True
    return bool(
        settings.elevenlabs_api_key
        and settings.elevenlabs_voice_list
        and settings.elevenlabs_enabled
    )


async def _synthesize_navy(text: str, voice: str | None = None, speed: float = 1.0) -> bytes:
    """Fallback TTS via navy.api OpenAI-compatible endpoint.

    Called when ElevenLabs is unavailable. Returns raw mp3 audio bytes.
    Raises TTSError on failure — caller should fall back to browser Web Speech.
    """
    if not (settings.navy_tts_enabled and settings.local_llm_url and settings.local_llm_api_key):
        raise TTSError("Navy TTS not configured")

    # Ensure /v1/ prefix for OpenAI-compat endpoint
    _tts_base = settings.local_llm_url.rstrip("/")
    if not _tts_base.endswith("/v1"):
        _tts_base += "/v1"
    url = f"{_tts_base}/audio/speech"
    payload = {
        "model": settings.navy_tts_model,
        "input": text[:4096],  # OpenAI/ElevenLabs limit
        "voice": voice or settings.navy_tts_voice,
        "speed": max(0.25, min(4.0, speed)),
        "response_format": "mp3",
    }
    headers = {
        "Authorization": f"Bearer {settings.local_llm_api_key}",
        "Content-Type": "application/json",
    }

    try:
        client = _get_shared_client()
        response = await client.post(url, json=payload, headers=headers)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as exc:
        logger.error("Navy TTS unavailable: %s", exc)
        raise TTSError(f"Navy TTS unavailable: {exc}")

    if response.status_code != 200:
        detail = response.text[:200]
        logger.error("Navy TTS error %d: %s", response.status_code, detail)
        raise TTSError(f"Navy TTS returned {response.status_code}")

    audio_bytes = response.content
    if len(audio_bytes) < 100:
        raise TTSError("Navy TTS returned empty audio")

    logger.info("NAVY_TTS_USAGE | chars=%d | model=%s | voice=%s | audio_bytes=%d",
                len(text), settings.navy_tts_model, voice or settings.navy_tts_voice, len(audio_bytes))
    return audio_bytes


# =============================================================================
# Main synthesis API
# =============================================================================

async def synthesize_speech(
    text: str,
    voice_id: str,
    *,
    model_id: str | None = None,
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    style: float = 0.3,
    speed: float = 1.0,
    use_cache: bool = True,
    voice_params: VoiceParams | None = None,
    emotion: str | None = None,
    active_factors: list[HumanFactor] | None = None,
) -> TTSResult:
    """Synthesize speech from text using ElevenLabs API.

    Accepts either individual params or VoiceParams object (preferred).
    """
    text = text.strip()
    if not text:
        raise TTSError("Empty text for TTS")
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]
        logger.warning("TTS text truncated to %d chars", MAX_TEXT_LENGTH)

    # 2026-05-03 prod fix: convert *вздох* / (sigh) / <whisper> markers
    # into ElevenLabs v3 audio tags ([sighs], [whispers], …) so the
    # voice performs the sound instead of literally speaking the word.
    # Pure function; affects both Navy and direct-ElevenLabs paths.
    from app.services.tts_sanitizer import sanitize_for_tts
    text = sanitize_for_tts(text)
    if not text:
        raise TTSError("Empty text for TTS after sanitization")

    mid = model_id or settings.elevenlabs_model

    if voice_params:
        stability = voice_params.stability
        similarity_boost = voice_params.similarity_boost
        style = voice_params.style
        speed = voice_params.speed
    else:
        voice_params = VoiceParams(stability=stability, similarity_boost=similarity_boost, style=style, speed=speed)

    # Navy-primary path: if no ElevenLabs key but navy TTS enabled, route directly.
    if not settings.elevenlabs_api_key:
        if settings.navy_tts_enabled and settings.local_llm_url and settings.local_llm_api_key:
            start_ts = time.monotonic()
            # 2026-04-22: prefer the per-session voice_id picked by
            # pick_voice_for_session — gives each client a distinct voice
            # (male/female/archetype variation) instead of one global voice
            # from settings. Falls back to settings.navy_tts_voice when the
            # caller didn't pre-assign (e.g. system messages, first warmup).
            # Works because Navy.api proxies ElevenLabs models through the
            # OpenAI /v1/audio/speech endpoint and accepts ElevenLabs
            # voice_ids in the `voice` field directly when model is an
            # eleven_* model.
            _navy_voice = voice_id if voice_id else settings.navy_tts_voice
            audio_bytes = await _synthesize_navy(text, voice=_navy_voice, speed=speed)
            latency_ms = int((time.monotonic() - start_ts) * 1000)
            return TTSResult(
                audio_bytes=audio_bytes,
                format="mp3",
                voice_id=voice_id,
                duration_estimate_ms=_estimate_duration_ms(text, speed),
                cached=False,
                latency_ms=latency_ms,
                characters_used=len(text),
                voice_params=voice_params,
                emotion=emotion,
                active_factors=[f.factor for f in (active_factors or [])],
            )
        raise TTSError("ElevenLabs API key not configured")

    # Check cache (v3 key includes factors)
    if use_cache:
        key = _cache_key_v3(text, voice_id, mid, voice_params, active_factors)
        if key in _audio_cache:
            logger.debug("TTS cache hit (v3) | chars=%d | voice=%s | emotion=%s", len(text), voice_id, emotion)
            return TTSResult(
                audio_bytes=_audio_cache[key],
                format="mp3",
                voice_id=voice_id,
                duration_estimate_ms=_estimate_duration_ms(text, speed),
                cached=True,
                latency_ms=0,
                characters_used=0,
                voice_params=voice_params,
                emotion=emotion,
                active_factors=[f.factor for f in (active_factors or [])],
            )

    # Call ElevenLabs API (or navy.api proxy if elevenlabs_base_url is set)
    _base = (settings.elevenlabs_base_url or "").rstrip("/")
    _tts_endpoint = f"{_base}/v1/text-to-speech" if _base else ELEVENLABS_TTS_URL

    # IL-2 (2026-04-30): when streaming flag is on, hit the /stream endpoint
    # with optimize_streaming_latency. ElevenLabs starts emitting audio as
    # soon as the first text token has been processed — the response body
    # is byte-streamed back. Network wall-clock is faster (~100-300ms saved
    # per sentence) and the public return type stays identical (full mp3
    # bytes accumulated server-side). Sets up infrastructure for future
    # incremental sub-sentence audio streaming over WS (IL-2.5).
    _il2_streaming = bool(getattr(settings, "elevenlabs_streaming_enabled", False))
    if _il2_streaming:
        url = f"{_tts_endpoint}/{voice_id}/stream"
    else:
        url = f"{_tts_endpoint}/{voice_id}"
    params_qs = {"output_format": DEFAULT_OUTPUT_FORMAT}
    if _il2_streaming:
        # 0=highest quality, 4=max optimisation. 3 is the sweet spot per
        # ElevenLabs latency docs — minimal quality drop, ~30-40% TTFB win.
        params_qs["optimize_streaming_latency"] = "3"
    headers = {
        "xi-api-key": settings.elevenlabs_api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload: dict[str, Any] = {
        "text": text,
        "model_id": mid,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "use_speaker_boost": True,
        },
    }
    if abs(speed - 1.0) > 0.01:
        payload["voice_settings"]["speed"] = speed

    start_ts = time.monotonic()

    factors_str = ",".join(f.factor for f in (active_factors or [])) or "none"
    proxy = settings.elevenlabs_proxy or None
    logger.info(
        "TTS_REQUEST | voice=%s | model=%s | chars=%d | emotion=%s | factors=%s | "
        "stab=%.2f sim=%.2f sty=%.2f spd=%.2f | proxy=%s",
        voice_id, mid, len(text), emotion or "none", factors_str,
        stability, similarity_boost, style, speed,
        proxy or "direct",
    )

    # Navy TTS fallback helper — runs if ElevenLabs fails for any non-quota reason.
    # TTSQuotaExhausted still bubbles up (client does browser Web Speech fallback).
    async def _try_navy_fallback(reason: str) -> bytes | None:
        if not settings.navy_tts_enabled:
            return None
        try:
            logger.warning("ElevenLabs fallback → navy TTS (%s)", reason)
            return await _synthesize_navy(text, speed=speed)
        except TTSError as e:
            logger.error("Navy TTS fallback also failed: %s", e)
            return None

    from types import SimpleNamespace as _NS
    response = None
    audio_bytes = b""
    try:
        client = _get_shared_client()
        if _il2_streaming:
            # Stream-accumulate so generation begins as early as ElevenLabs
            # internal pipeline allows. Total wall-clock is shorter than
            # /text-to-speech because the server doesn't buffer the full
            # mp3 before flushing. We still aggregate the bytes locally so
            # the public return type stays identical (full-mp3 TTSResult).
            _stream_buf = bytearray()
            _status = 0
            _err_body = b""
            async with client.stream(
                "POST", url, json=payload, headers=headers, params=params_qs,
            ) as _resp:
                _status = _resp.status_code
                if _status == 200:
                    async for _chunk in _resp.aiter_bytes():
                        if _chunk:
                            _stream_buf.extend(_chunk)
                else:
                    _err_body = await _resp.aread()
            # Build a response shim with the same surface the legacy block
            # below expects: ``status_code``, ``content``, ``text``.
            if _status == 200:
                audio_bytes = bytes(_stream_buf)
                response = _NS(status_code=200, content=audio_bytes, text="")
            else:
                _err_text = _err_body.decode("utf-8", errors="replace") if _err_body else ""
                response = _NS(status_code=_status, content=b"", text=_err_text)
        else:
            response = await client.post(url, json=payload, headers=headers, params=params_qs)
    except httpx.ConnectError:
        logger.error("ElevenLabs API unavailable")
        fallback_audio = await _try_navy_fallback("connect_error")
        if fallback_audio:
            audio_bytes = fallback_audio
            response = None
        else:
            raise TTSError("ElevenLabs API unavailable")
    except httpx.TimeoutException:
        logger.error("ElevenLabs API timeout (%ds)", settings.elevenlabs_timeout_seconds)
        fallback_audio = await _try_navy_fallback("timeout")
        if fallback_audio:
            audio_bytes = fallback_audio
            response = None
        else:
            raise TTSError("ElevenLabs API timeout")
    except httpx.HTTPError as exc:
        logger.error("ElevenLabs HTTP error: %s", exc)
        fallback_audio = await _try_navy_fallback(f"http_error:{exc}")
        if fallback_audio:
            audio_bytes = fallback_audio
            response = None
        else:
            raise TTSError(f"ElevenLabs HTTP error: {exc}")

    latency_ms = int((time.monotonic() - start_ts) * 1000)

    # Only do status-code checks if we actually got a response (i.e. ElevenLabs responded).
    if response is not None:
        if response.status_code == 401:
            raise TTSError("Invalid ElevenLabs API key")
        if response.status_code in (402, 429):
            # Quota is unique — bubble up so client switches to browser Web Speech.
            raise TTSQuotaExhausted("ElevenLabs quota exhausted — fallback to browser TTS")
        if response.status_code != 200:
            detail = response.text[:300]
            logger.error("ElevenLabs error %d: %s", response.status_code, detail)
            fallback_audio = await _try_navy_fallback(f"http_{response.status_code}")
            if fallback_audio:
                audio_bytes = fallback_audio
            else:
                raise TTSError(f"ElevenLabs returned {response.status_code}")
        else:
            audio_bytes = response.content
            if len(audio_bytes) < 100:
                raise TTSError("ElevenLabs returned empty audio")

    # Cache short phrases
    if use_cache and len(text) < 200:
        key = _cache_key_v3(text, voice_id, mid, voice_params, active_factors)
        if len(_audio_cache) >= _CACHE_MAX_SIZE:
            oldest_key = next(iter(_audio_cache))
            del _audio_cache[oldest_key]
        _audio_cache[key] = audio_bytes

    logger.info(
        "TTS_USAGE | chars=%d | voice=%s | model=%s | emotion=%s | factors=%s | latency_ms=%d | audio_bytes=%d",
        len(text), voice_id, mid, emotion or "none", factors_str, latency_ms, len(audio_bytes),
    )

    return TTSResult(
        audio_bytes=audio_bytes,
        format="mp3",
        voice_id=voice_id,
        duration_estimate_ms=_estimate_duration_ms(text, speed),
        cached=False,
        latency_ms=latency_ms,
        characters_used=len(text),
        voice_params=voice_params,
        emotion=emotion,
        active_factors=[f.factor for f in (active_factors or [])],
    )


# =============================================================================
# High-level convenience API
# =============================================================================

async def get_tts_audio_b64(
    text: str,
    session_id: str,
    emotion: str = "cold",
    active_factors: list[dict] | None = None,
    pad_state: dict | None = None,
    client_story_id: str | None = None,
) -> dict[str, Any] | None:
    """Full pipeline: modulate → hesitations → pauses → synthesize → base64.

    Returns dict with keys: audio, format, emotion, voice_params, duration_ms, active_factors.
    Returns None if TTS not configured or fails.
    """
    if not _is_configured():
        return None

    # Parse factors
    factors = [HumanFactor.from_dict(f) for f in (active_factors or [])]
    pad = PADState.from_dict(pad_state)

    # Ensure voice is assigned
    if client_story_id and str(client_story_id) not in _story_voice_cache:
        # Try session fallback
        assignment = get_session_assignment(session_id)
        if not assignment:
            try:
                pick_voice_for_session(session_id)
                assignment = get_session_assignment(session_id)
            except TTSError:
                return None
    else:
        assignment = (
            _story_voice_cache.get(str(client_story_id))
            if client_story_id
            else get_session_assignment(session_id)
        )
        if not assignment:
            try:
                pick_voice_for_session(session_id)
                assignment = get_session_assignment(session_id)
            except TTSError:
                return None

    voice_id = assignment["voice_id"]

    # Calculate modulated params (full pipeline)
    params = get_modulated_params(session_id, emotion, factors, pad, client_story_id)

    # Pass 1: inject hesitations (text-level)
    processed_text = inject_hesitations(text, factors, pad)

    # Pass 2: inject SSML pauses
    processed_text = inject_pauses(processed_text, emotion, factors)

    try:
        result = await synthesize_speech(
            processed_text,
            voice_id,
            voice_params=params,
            emotion=emotion,
            active_factors=factors,
        )
        audio_b64 = base64.b64encode(result.audio_bytes).decode("ascii")
        return {
            "audio": audio_b64,
            "format": result.format,
            "emotion": emotion,
            "voice_params": params.to_dict(),
            "duration_ms": result.duration_estimate_ms,
            "active_factors": [f.factor for f in factors],
        }
    except TTSQuotaExhausted:
        raise
    except TTSError as exc:
        logger.warning("TTS failed, frontend should fallback: %s", exc)
        return None


async def get_tts_couple_audio(
    text: str,
    session_id: str,
    emotion_a: str = "cold",
    emotion_b: str = "cold",
    factors_a: list[dict] | None = None,
    factors_b: list[dict] | None = None,
    pad_a: dict | None = None,
    pad_b: dict | None = None,
    client_story_id: str | None = None,
) -> dict[str, Any] | None:
    """Couple mode: synthesize [A]/[B] utterances with two voices + per-speaker factors.

    Returns dict with keys: couple_mode, utterances[], partner_a_emotion, partner_b_emotion.
    """
    if not _is_configured():
        return None

    hf_a = [HumanFactor.from_dict(f) for f in (factors_a or [])]
    hf_b = [HumanFactor.from_dict(f) for f in (factors_b or [])]
    pad_state_a = PADState.from_dict(pad_a)
    pad_state_b = PADState.from_dict(pad_b)

    utterances = parse_couple_response(text)
    results = []

    # Get voice assignment for couple
    couple_config = None
    if client_story_id:
        story_cache = _story_voice_cache.get(str(client_story_id), {})
        couple_config = story_cache.get("couple_voice_config")

    for utt in utterances:
        is_a = utt.speaker in ("A", "AB")
        emotion = emotion_a if is_a else emotion_b
        factors = hf_a if is_a else hf_b
        pad_st = pad_state_a if is_a else pad_state_b

        # Determine voice_id per speaker
        voice_id = get_session_voice(session_id)
        if couple_config:
            speaker_key = "partner_a" if is_a else "partner_b"
            voice_id = couple_config.get(speaker_key, {}).get("voice_id", voice_id)

        if not voice_id:
            continue

        assignment = get_session_assignment(session_id)
        if not assignment:
            continue

        base = {
            "stability": assignment.get("base_stability", 0.5),
            "similarity_boost": assignment.get("base_similarity_boost", 0.75),
            "style": assignment.get("base_style", 0.3),
            "speed": assignment.get("base_speed", 1.0),
        }

        # Pipeline per speaker
        after_emotion = calculate_voice_params(base, emotion)
        after_factors = modulate_by_human_factors(after_emotion, factors, pad_st)
        params = _clamp_params(after_factors)

        processed = inject_hesitations(utt.text, factors, pad_st)
        processed = inject_pauses(processed, emotion, factors)

        try:
            result = await synthesize_speech(
                processed, voice_id, voice_params=params, emotion=emotion,
                active_factors=factors,
            )
            results.append({
                "speaker": utt.speaker,
                "audio": base64.b64encode(result.audio_bytes).decode("ascii"),
                "format": result.format,
                "duration_ms": result.duration_estimate_ms,
                "emotion": emotion,
                "whisper": utt.whisper,
                "voice_params": params.to_dict(),
                "active_factors": [f.factor for f in factors],
            })
        except TTSError:
            continue

    if not results:
        return None

    return {
        "couple_mode": True,
        "utterances": results,
        "partner_a_emotion": emotion_a,
        "partner_b_emotion": emotion_b,
        "pause_between_ms": 300,
    }


# =============================================================================
# Data loading from DB + startup preload
# =============================================================================

async def load_voice_data_from_db(db_session) -> None:
    """Load VoiceProfile, EmotionVoiceModifier, PauseConfig from DB into memory.

    Call once at app startup via load_voice_data_on_startup().
    Falls back to hardcoded values if DB is empty/unavailable.
    """
    global _voice_profiles, _emotion_modifiers, _pause_configs, _voice_data_loaded

    try:
        from app.models.voice import VoiceProfile as VP, EmotionVoiceModifier as EVM, PauseConfig as PC
        from sqlalchemy import select

        result = await db_session.execute(select(VP).where(VP.is_active == True))
        profiles = result.scalars().all()
        _voice_profiles = [
            {
                "voice_id": vp.voice_id,
                "voice_code": vp.voice_code,
                "voice_name": vp.voice_name,
                "gender": vp.gender,
                "base_stability": vp.base_stability,
                "base_similarity_boost": vp.base_similarity_boost,
                "base_style": vp.base_style,
                "base_speed": vp.base_speed,
                "archetype_codes": vp.archetype_codes or [],
                "age_range": vp.age_range,
                "voice_type": vp.voice_type,
            }
            for vp in profiles
        ]
        logger.info("Loaded %d voice profiles from DB", len(_voice_profiles))

        result = await db_session.execute(select(EVM))
        modifiers = result.scalars().all()
        _emotion_modifiers = {
            em.emotion_state: {
                "stability_delta": em.stability_delta,
                "similarity_delta": em.similarity_delta,
                "style_delta": em.style_delta,
                "speed_delta": em.speed_delta,
                "instant": em.instant_transition,
            }
            for em in modifiers
        }
        logger.info("Loaded %d emotion voice modifiers from DB", len(_emotion_modifiers))

        result = await db_session.execute(select(PC))
        configs = result.scalars().all()
        _pause_configs = {
            pc.emotion_state: {
                "after_period_ms": pc.after_period_ms,
                "before_conjunction_ms": pc.before_conjunction_ms,
                "after_comma_ms": pc.after_comma_ms,
                "hesitation_probability": pc.hesitation_probability,
                "hesitation_pool": pc.hesitation_pool or [],
                "max_hesitations": pc.max_hesitations_per_phrase,
                "dramatic_pause_ms": pc.dramatic_pause_ms,
                "breath_probability": pc.breath_probability,
            }
            for pc in configs
        }
        logger.info("Loaded %d pause configs from DB", len(_pause_configs))

        _voice_data_loaded = True

    except Exception as exc:
        logger.warning("Failed to load voice data from DB, using hardcoded fallbacks: %s", exc)


async def load_voice_data_on_startup() -> None:
    """Call from @app.on_event('startup') to preload voice data.

    Usage in main.py:
        @app.on_event("startup")
        async def startup():
            from app.services.tts import load_voice_data_on_startup
            await load_voice_data_on_startup()
    """
    try:
        from app.database import async_session
        async with async_session() as session:
            await load_voice_data_from_db(session)
    except Exception as exc:
        logger.warning("TTS startup preload failed (will use fallbacks): %s", exc)


# =============================================================================
# Monitoring
# =============================================================================

def is_tts_available() -> bool:
    return _is_configured()


def get_tts_stats() -> dict:
    return {
        "configured": _is_configured(),
        "voices_count": len(settings.elevenlabs_voice_list),
        "voices": settings.elevenlabs_voice_list,
        "profiles_loaded": len(_voice_profiles),
        "voice_data_from_db": _voice_data_loaded,
        "active_story_voices": len(_story_voice_cache),
        "active_session_voices": len(_session_voices),
        "cache_size": len(_audio_cache),
        "cache_max": _CACHE_MAX_SIZE,
        "model": settings.elevenlabs_model,
        "emotion_modifiers_loaded": len(_emotion_modifiers),
        "pause_configs_loaded": len(_pause_configs),
    }
