import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.integrations.insights import ClinicalInsights
from app.models.session import SessionStatus


class SessionCreate(BaseModel):
    session_date: date = Field(..., description="Must not be in the future")

    @field_validator("session_date")
    @classmethod
    def session_date_not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("session_date cannot be in the future")
        return v


class SessionResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    session_date: date
    original_filename: str
    status: SessionStatus
    transcript: str | None
    insights: ClinicalInsights | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
