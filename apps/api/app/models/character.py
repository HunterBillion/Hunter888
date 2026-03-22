import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EmotionState(str, enum.Enum):
    """10-state nonlinear emotion graph (TZ-02 v2).

    Replaces the legacy 5-state linear chain:
        cold → skeptical → warming → open → deal

    New graph allows branching (guarded has 4+ exits), terminal states
    (hangup is irreversible), and lateral moves (testing, callback).
    """

    cold = "cold"               # Initial — doesn't want to talk
    guarded = "guarded"         # Listening but suspicious (key branching node)
    curious = "curious"         # Interested, asking questions
    considering = "considering" # Seriously evaluating the offer
    negotiating = "negotiating" # Discussing terms, price, timeline
    deal = "deal"               # Agreed — scheduling a meeting
    testing = "testing"         # Testing the manager's competence
    callback = "callback"       # "Call me back later" — deferred interest
    hostile = "hostile"         # Aggressive, insulting, threatening
    hangup = "hangup"           # Hung up — terminal, session ends


# ---------------------------------------------------------------------------
# Legacy mapping for backward compatibility with frontend (Avatar3D, VibeMeter)
# ---------------------------------------------------------------------------
LEGACY_MAP: dict[EmotionState, str] = {
    EmotionState.cold: "cold",
    EmotionState.guarded: "skeptical",
    EmotionState.curious: "warming",
    EmotionState.considering: "open",
    EmotionState.negotiating: "open",
    EmotionState.deal: "deal",
    EmotionState.testing: "skeptical",
    EmotionState.callback: "warming",
    EmotionState.hostile: "cold",
    EmotionState.hangup: "cold",
}


# ---------------------------------------------------------------------------
# State metadata
# ---------------------------------------------------------------------------
TERMINAL_STATES: frozenset[EmotionState] = frozenset({
    EmotionState.hangup,
})

FINAL_STATES: frozenset[EmotionState] = frozenset({
    EmotionState.deal,
    EmotionState.callback,
    EmotionState.hostile,
    EmotionState.hangup,
})

POSITIVE_STATES: frozenset[EmotionState] = frozenset({
    EmotionState.curious,
    EmotionState.considering,
    EmotionState.negotiating,
    EmotionState.deal,
})


# ---------------------------------------------------------------------------
# Visual parameters per state (for Avatar3D / VibeMeter)
# ---------------------------------------------------------------------------
STATE_VISUALS: dict[EmotionState, dict] = {
    EmotionState.cold: {
        "color": "#4A90D9",
        "animation": "idle,arms_crossed",
        "speech_speed": 1.0,
        "volume": 0.7,
        "vibe_zone": "gray",
        "vibe_segment": 3,
    },
    EmotionState.guarded: {
        "color": "#7B8D8E",
        "animation": "lean_back,side_glance",
        "speech_speed": 0.95,
        "volume": 0.8,
        "vibe_zone": "orange",
        "vibe_segment": 4,
    },
    EmotionState.curious: {
        "color": "#F5A623",
        "animation": "lean_forward,nod",
        "speech_speed": 0.9,
        "volume": 0.9,
        "vibe_zone": "yellow",
        "vibe_segment": 6,
    },
    EmotionState.considering: {
        "color": "#8B6914",
        "animation": "chin_stroke,slow_nod",
        "speech_speed": 0.85,
        "volume": 0.85,
        "vibe_zone": "green",
        "vibe_segment": 8,
    },
    EmotionState.negotiating: {
        "color": "#D4AF37",
        "animation": "gesture,point",
        "speech_speed": 1.05,
        "volume": 1.0,
        "vibe_zone": "green",
        "vibe_segment": 9,
    },
    EmotionState.deal: {
        "color": "#7ED321",
        "animation": "handshake,smile",
        "speech_speed": 0.9,
        "volume": 1.0,
        "vibe_zone": "gold",
        "vibe_segment": 10,
    },
    EmotionState.testing: {
        "color": "#9B59B6",
        "animation": "squint,crossed_arms",
        "speech_speed": 1.1,
        "volume": 0.9,
        "vibe_zone": "orange",
        "vibe_segment": 5,
    },
    EmotionState.callback: {
        "color": "#95A5A6",
        "animation": "wave,look_away",
        "speech_speed": 0.95,
        "volume": 0.7,
        "vibe_zone": "yellow",
        "vibe_segment": 7,
    },
    EmotionState.hostile: {
        "color": "#E74C3C",
        "animation": "aggressive_gesture,frown",
        "speech_speed": 1.2,
        "volume": 1.2,
        "vibe_zone": "red",
        "vibe_segment": 1,
    },
    EmotionState.hangup: {
        "color": "#2C3E50",
        "animation": "turn_away,fade_out",
        "speech_speed": 0.0,
        "volume": 0.0,
        "vibe_zone": "red",
        "vibe_segment": 2,
    },
}


class ObjectionCategory(str, enum.Enum):
    price = "price"
    trust = "trust"
    need = "need"
    timing = "timing"
    competitor = "competitor"


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    personality_traits: Mapped[dict] = mapped_column(JSONB, default=dict)
    initial_emotion: Mapped[EmotionState] = mapped_column(
        Enum(EmotionState), default=EmotionState.cold
    )
    difficulty: Mapped[int] = mapped_column(Integer, default=5)
    prompt_version: Mapped[str] = mapped_column(String(50), default="v1")
    prompt_path: Mapped[str] = mapped_column(String(500), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Objection(Base):
    __tablename__ = "objections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category: Mapped[ObjectionCategory] = mapped_column(Enum(ObjectionCategory), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[float] = mapped_column(Float, default=0.5)
    recommended_response_hint: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
