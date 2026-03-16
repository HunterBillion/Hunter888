import uuid
from datetime import datetime

from pydantic import BaseModel


class ScenarioResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    scenario_type: str
    difficulty: int
    estimated_duration_minutes: int

    model_config = {"from_attributes": True}


class SessionStartRequest(BaseModel):
    scenario_id: uuid.UUID


class SessionResponse(BaseModel):
    id: uuid.UUID
    scenario_id: uuid.UUID
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    score_total: float | None = None
    scoring_details: dict | None = None
    feedback_text: str | None = None

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    emotion_state: str | None = None
    sequence_number: int
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionResultResponse(BaseModel):
    session: SessionResponse
    messages: list[MessageResponse]
    score_breakdown: dict | None = None
