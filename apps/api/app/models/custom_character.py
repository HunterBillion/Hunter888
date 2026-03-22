"""Custom character presets saved by users from CharacterBuilder."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class CustomCharacter(Base):
    __tablename__ = "custom_characters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    archetype = Column(String(50), nullable=False)
    profession = Column(String(50), nullable=False)
    lead_source = Column(String(50), nullable=False)
    difficulty = Column(Integer, nullable=False, default=5)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
