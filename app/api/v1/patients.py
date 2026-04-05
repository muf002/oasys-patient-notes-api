import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_provider, get_note_service, get_patient_service
from app.models.note import NoteType
from app.models.provider import Provider
from app.schemas.note import (
    BulkNoteCreate,
    BulkNoteCreateResponse,
    NoteCreate,
    NoteResponse,
    NoteUpdate,
)
from app.schemas.patient import PatientCreate, PatientResponse
from app.services.note import NoteService
from app.services.patient import PatientService

router = APIRouter(prefix="/patients", tags=["patients"])


# ---------------------------------------------------------------------------
# Patient endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=PatientResponse, status_code=201)
async def create_patient(
    body: PatientCreate,
    service: Annotated[PatientService, Depends(get_patient_service)],
    current_provider: Annotated[Provider, Depends(get_current_provider)],
) -> PatientResponse:
    return await service.create_patient(
        provider_id=current_provider.id,
        first_name=body.first_name,
        last_name=body.last_name,
    )


@router.get("", response_model=list[PatientResponse])
async def list_patients(
    service: Annotated[PatientService, Depends(get_patient_service)],
    current_provider: Annotated[Provider, Depends(get_current_provider)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PatientResponse]:
    return await service.list_patients(current_provider.id, limit, offset)


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: uuid.UUID,
    service: Annotated[PatientService, Depends(get_patient_service)],
    current_provider: Annotated[Provider, Depends(get_current_provider)],
) -> PatientResponse:
    return await service.get_patient(patient_id, current_provider.id)


# ---------------------------------------------------------------------------
# Note endpoints (nested under /patients/{patient_id}/notes)
# ---------------------------------------------------------------------------


@router.post("/{patient_id}/notes", response_model=NoteResponse, status_code=201)
async def create_note(
    patient_id: uuid.UUID,
    body: NoteCreate,
    service: Annotated[NoteService, Depends(get_note_service)],
    current_provider: Annotated[Provider, Depends(get_current_provider)],
) -> NoteResponse:
    return await service.create_note(current_provider.id, patient_id, body)


@router.get("/{patient_id}/notes", response_model=list[NoteResponse])
async def list_notes(
    patient_id: uuid.UUID,
    service: Annotated[NoteService, Depends(get_note_service)],
    current_provider: Annotated[Provider, Depends(get_current_provider)],
    note_type: Annotated[NoteType | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[NoteResponse]:
    return await service.list_notes(current_provider.id, patient_id, note_type, limit, offset)


@router.post("/{patient_id}/notes/bulk", response_model=BulkNoteCreateResponse, status_code=207)
async def bulk_create_notes(
    patient_id: uuid.UUID,
    body: BulkNoteCreate,
    service: Annotated[NoteService, Depends(get_note_service)],
    current_provider: Annotated[Provider, Depends(get_current_provider)],
) -> BulkNoteCreateResponse:
    return await service.bulk_create_notes(current_provider.id, patient_id, body)


@router.get("/{patient_id}/notes/{note_id}", response_model=NoteResponse)
async def get_note(
    patient_id: uuid.UUID,
    note_id: uuid.UUID,
    service: Annotated[NoteService, Depends(get_note_service)],
    current_provider: Annotated[Provider, Depends(get_current_provider)],
) -> NoteResponse:
    return await service.get_note(current_provider.id, patient_id, note_id)


@router.patch("/{patient_id}/notes/{note_id}", response_model=NoteResponse)
async def update_note(
    patient_id: uuid.UUID,
    note_id: uuid.UUID,
    body: NoteUpdate,
    service: Annotated[NoteService, Depends(get_note_service)],
    current_provider: Annotated[Provider, Depends(get_current_provider)],
) -> NoteResponse:
    return await service.update_note(current_provider.id, patient_id, note_id, body)


@router.delete("/{patient_id}/notes/{note_id}", status_code=204)
async def delete_note(
    patient_id: uuid.UUID,
    note_id: uuid.UUID,
    service: Annotated[NoteService, Depends(get_note_service)],
    current_provider: Annotated[Provider, Depends(get_current_provider)],
) -> None:
    await service.delete_note(current_provider.id, patient_id, note_id)
