"""Checkpoint system models (DOC_04).

Two tables:
- CheckpointDefinition: 90 checkpoint definitions seeded from seed_checkpoints.py
- UserCheckpoint: per-user progress tracking for each checkpoint
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.mutable import MutableDict

from app.database import Base
from app.models.training import NormalizedJSONB


class CheckpointDefinition(Base):
    __tablename__ = "checkpoint_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(80), unique=True, nullable=False, index=True)
    level = Column(Integer, nullable=False, index=True)       # 1-20
    order_num = Column(Integer, nullable=False, default=1)     # 1-10 within level
    name = Column(String(120), nullable=False)                  # Russian display name
    description = Column(Text, nullable=False)                  # What to do
    condition = Column(MutableDict.as_mutable(NormalizedJSONB), nullable=False)  # 24 condition types
    xp_reward = Column(Integer, nullable=False, default=50)
    unlock_reward = Column(NormalizedJSONB, nullable=True)     # cosmetic: border, title, effect
    is_required = Column(Boolean, nullable=False, default=True)  # gates level-up?
    category = Column(String(20), nullable=False, default="training")  # training|arena|knowledge|social


class UserCheckpoint(Base):
    __tablename__ = "user_checkpoints"
    __table_args__ = (
        UniqueConstraint("user_id", "checkpoint_id", name="uq_user_checkpoint"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    checkpoint_id = Column(UUID(as_uuid=True), ForeignKey("checkpoint_definitions.id", ondelete="CASCADE"), nullable=False)
    progress = Column(MutableDict.as_mutable(NormalizedJSONB), nullable=True)  # {"current": N, "target": M}
    is_completed = Column(Boolean, nullable=False, default=False)
    completed_at = Column(DateTime, nullable=True)
    xp_awarded = Column(Boolean, nullable=False, default=False)
    is_softened = Column(Boolean, nullable=False, default=False)  # catch-up reduction applied
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)
