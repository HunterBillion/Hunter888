"""DOC_14/17: Cross-recommendation cache for unified Training↔Arena suggestions."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CrossRecommendationCache(Base):
    """Cached cross-module recommendations per user (DOC_14: cross_recommendation_cache table)."""

    __tablename__ = "cross_recommendation_cache"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    recommendations: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ttl_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")
