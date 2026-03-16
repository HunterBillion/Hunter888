import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EmotionState(str, enum.Enum):
    cold = "cold"
    warming = "warming"
    open = "open"


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
