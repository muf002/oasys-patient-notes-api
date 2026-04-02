import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr


class ProviderResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    api_token: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ProviderStatsResponse(BaseModel):
    total_patients: int
    total_notes: int
