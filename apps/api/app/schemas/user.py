import uuid
from datetime import datetime

from pydantic import BaseModel


class UserProfileResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    team_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserStatsResponse(BaseModel):
    total_sessions: int
    avg_score: float | None
    best_score: float | None
    sessions_this_week: int
    achievements_count: int
