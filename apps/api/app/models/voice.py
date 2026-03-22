"""Voice profile and modulation models for ElevenLabs TTS integration (ТЗ-04).

Architecture:
    VoiceProfile — maps voices to archetypes with base synthesis parameters.
    EmotionVoiceModifier — per-emotion deltas applied to base params.
    PauseConfig — per-emotion pause/hesitation settings for SSML injection.
    CoupleVoiceProfile — two-voice setup for the `couple` archetype.

Usage flow:
    1. Session starts → pick VoiceProfile by gender + archetype
    2. Each reply → get EmotionVoiceModifier for current emotion
    3. Calculate final params: base + delta (clamped)
    4. Apply EMA smoothing from previous params
    5. Inject pauses via PauseConfig
    6. Synthesize with ElevenLabs API
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class VoiceType(str, enum.Enum):
    """Voice character type — determines which pool to draw from."""
    soft = "soft"
    firm = "firm"
    aggressive = "aggressive"
    warm = "warm"
    neutral = "neutral"
    mixed = "mixed"  # couple mode only


class AgeRange(str, enum.Enum):
    """Target age range for voice casting."""
    young = "young"      # 25-35
    middle = "middle"    # 35-50
    senior = "senior"    # 50+


# ---------------------------------------------------------------------------
# Voice Profile
# ---------------------------------------------------------------------------

class VoiceProfile(Base):
    """Maps an ElevenLabs voice to archetypes with base synthesis parameters.

    Each voice has base_* parameters that define its neutral character.
    Emotion modifiers (EmotionVoiceModifier) are added at synthesis time
    to shift the voice toward the current emotional state.

    Selection algorithm (VoiceProfileManager in tts.py):
        1. Filter by gender
        2. Filter by archetype_codes (JSONB array contains archetype)
        3. Prefer matching voice_type
        4. Random from matches (sticky per session)
    """
    __tablename__ = "voice_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # --- ElevenLabs identity ---
    voice_id: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True,
        comment="ElevenLabs voice_id (from API or Voice Library)"
    )
    voice_name: Mapped[str] = mapped_column(
        String(200), nullable=False,
        comment="Human-readable name, e.g. 'Алексей — баритон'"
    )
    voice_code: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True,
        comment="Internal code, e.g. 'aleksey_baritone'"
    )
    gender: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="male | female"
    )

    # --- Base synthesis parameters ---
    base_stability: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5,
        comment="0.0-1.0: higher = more stable/monotone, lower = expressive"
    )
    base_similarity_boost: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.75,
        comment="0.0-1.0: higher = clearer diction"
    )
    base_style: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.3,
        comment="0.0-1.0: higher = more theatrical/expressive"
    )
    base_speed: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0,
        comment="0.5-2.0: speech speed multiplier (1.0 = normal)"
    )

    # --- Classification ---
    archetype_codes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=list,
        comment='Archetypes this voice fits: ["skeptic","paranoid"]'
    )
    age_range: Mapped[str] = mapped_column(
        String(20), nullable=False, default="middle",
        comment="young | middle | senior"
    )
    voice_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="neutral",
        comment="soft | firm | aggressive | warm | neutral | mixed"
    )

    # --- Metadata ---
    description: Mapped[str | None] = mapped_column(
        Text, comment="Timbre description for voice library search"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<VoiceProfile {self.voice_code} ({self.gender}, {self.voice_type})>"


# ---------------------------------------------------------------------------
# Emotion Voice Modifier
# ---------------------------------------------------------------------------

class EmotionVoiceModifier(Base):
    """Per-emotion deltas applied to VoiceProfile base parameters.

    Final params = clamp(base + delta):
        stability:        [0.0, 1.0]
        similarity_boost: [0.0, 1.0]
        style:            [0.0, 1.0]
        speed:            [0.5, 2.0]

    10 rows total (one per EmotionState from ТЗ-02).
    """
    __tablename__ = "emotion_voice_modifiers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    emotion_state: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True,
        comment="One of 10 emotion states: cold, guarded, curious, ..."
    )
    stability_delta: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        comment="Added to base_stability"
    )
    similarity_delta: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        comment="Added to base_similarity_boost"
    )
    style_delta: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        comment="Added to base_style"
    )
    speed_delta: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        comment="Added to base_speed"
    )
    description: Mapped[str | None] = mapped_column(
        Text, comment="How the voice sounds in this state"
    )
    # --- Smoothing overrides ---
    instant_transition: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="Skip EMA smoothing (True for hostile, hangup)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<EmotionVoiceModifier {self.emotion_state}: "
            f"stab={self.stability_delta:+.2f} sim={self.similarity_delta:+.2f} "
            f"sty={self.style_delta:+.2f} spd={self.speed_delta:+.2f}>"
        )


# ---------------------------------------------------------------------------
# Pause Config
# ---------------------------------------------------------------------------

class PauseConfig(Base):
    """Per-emotion pause and prosody configuration for SSML injection.

    Controls <break> tag insertion and hesitation probability
    before text is sent to ElevenLabs API.

    10 rows total (one per EmotionState).
    """
    __tablename__ = "pause_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    emotion_state: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True,
        comment="One of 10 emotion states"
    )
    after_period_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=300,
        comment="Pause after period (end of sentence), milliseconds"
    )
    before_conjunction_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=200,
        comment="Pause before но/однако/хотя/впрочем, milliseconds"
    )
    after_comma_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=150,
        comment="Pause after comma (intra-sentence), milliseconds"
    )
    hesitation_probability: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.1,
        comment="0.0-1.0: probability of injecting э-э/ну/это"
    )
    hesitation_pool: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=list,
        comment='Available hesitations: ["ну...", "э-э...", "это..."]'
    )
    max_hesitations_per_phrase: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
        comment="Cap hesitations per reply"
    )
    dramatic_pause_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Pause before key word (for effect), 0 = disabled"
    )
    breath_probability: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.1,
        comment="0.0-1.0: probability of audible inhale between phrases"
    )
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<PauseConfig {self.emotion_state}: "
            f"period={self.after_period_ms}ms hesit={self.hesitation_probability:.0%}>"
        )


# ---------------------------------------------------------------------------
# Couple Voice Profile (for archetype couple)
# ---------------------------------------------------------------------------

class CoupleVoiceProfile(Base):
    """Two-voice setup for couple archetype sessions.

    Links a training session to two VoiceProfile rows (Partner A and B)
    with independent emotional states and dynamics configuration.
    """
    __tablename__ = "couple_voice_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True,
        comment="Training session UUID"
    )
    partner_a_voice_id: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="ElevenLabs voice_id for Partner A (initiator)"
    )
    partner_b_voice_id: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="ElevenLabs voice_id for Partner B"
    )
    partner_a_params: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
        comment='{"stability":0.55,"similarity_boost":0.75,"style":0.25,"speed":1.0}'
    )
    partner_b_params: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
        comment='{"stability":0.50,"similarity_boost":0.70,"style":0.30,"speed":1.05}'
    )
    dynamics_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="couple_agree",
        comment="couple_agree | couple_conflict | couple_leader | couple_emotional"
    )
    interrupt_probability: Mapped[float] = mapped_column(
        Float, default=0.2,
        comment="0.0-1.0: how often Partner B interrupts A"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<CoupleVoiceProfile session={self.session_id} type={self.dynamics_type}>"
