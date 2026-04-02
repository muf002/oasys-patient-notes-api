import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class PatientCreate(BaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


class PatientResponse(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    created_at: datetime

    model_config = {"from_attributes": True}
