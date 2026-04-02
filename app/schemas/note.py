import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.note import NoteType


class NoteCreate(BaseModel):
    note_type: NoteType
    content: str = Field(min_length=1)
    session_date: date


class NoteUpdate(BaseModel):
    note_type: NoteType | None = None
    content: str | None = Field(default=None, min_length=1)
    session_date: date | None = None


class NoteResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    note_type: NoteType
    content: str
    session_date: date
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BulkNoteCreate(BaseModel):
    notes: list[dict[str, Any]] = Field(min_length=1)


class BulkNoteFailure(BaseModel):
    index: int
    errors: str


class BulkNoteCreateResponse(BaseModel):
    created: list[NoteResponse]
    failed: list[BulkNoteFailure]
