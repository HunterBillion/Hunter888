"""DOC_16: Prompt version registry for data-driven prompt management."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PromptVersion(Base):
    """Versioned prompt template (DOC_16: prompt_versions table)."""

    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("prompt_type", "prompt_key", "version", name="uq_prompt_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_type: Mapped[str] = mapped_column(String(30), nullable=False)  # archetype|scenario|emotion|judge|personality|bot|template
    prompt_key: Mapped[str] = mapped_column(String(80), nullable=False)   # skeptic|cold_modifier|cold_low|...
    version: Mapped[str] = mapped_column(String(20), nullable=False, server_default="v2")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)     # A/B test results
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
