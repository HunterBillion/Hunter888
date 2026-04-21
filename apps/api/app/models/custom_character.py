"""Custom character presets saved by users from CharacterBuilder (v2: 8-step)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class CustomCharacter(Base):
    __tablename__ = "custom_characters"

    # ── Existing fields ──
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    archetype = Column(String(50), nullable=False)
    profession = Column(String(50), nullable=False)
    lead_source = Column(String(50), nullable=False)
    difficulty = Column(Integer, nullable=False, default=5)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # ── Step 3: Client context (all nullable for backward compat) ──
    family_preset = Column(String(30), nullable=True)       # "single", "married_kids" etc.
    creditors_preset = Column(String(20), nullable=True)    # "1", "2_3", "4_5", "6_plus"
    debt_stage = Column(String(30), nullable=True)          # "pre_court", "execution" etc.
    debt_range = Column(String(30), nullable=True)          # "under_500k", "3m_10m" etc.

    # ── Step 4: Emotional preset ──
    emotion_preset = Column(String(30), nullable=True)      # "neutral", "anxious", "angry" etc.

    # ── Step 6: Environment modifiers ──
    bg_noise = Column(String(20), nullable=True)            # "none", "office", "street" etc.
    time_of_day = Column(String(20), nullable=True)         # "morning", "afternoon" etc.
    client_fatigue = Column(String(20), nullable=True)      # "fresh", "normal", "tired" etc.

    # ── Step 7: Cached preview ──
    cached_dossier = Column(Text, nullable=True)

    # ── Statistics ──
    play_count = Column(Integer, nullable=False, default=0, server_default="0")
    best_score = Column(Integer, nullable=True)
    avg_score = Column(Integer, nullable=True)
    last_played_at = Column(DateTime, nullable=True)

    # ── Metadata ──
    updated_at = Column(DateTime, nullable=True, onupdate=lambda: datetime.now(timezone.utc))
    is_shared = Column(Boolean, nullable=False, default=False, server_default="false")
    share_code = Column(String(20), nullable=True, unique=True)
