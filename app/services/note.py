import csv
import io
import logging
import uuid

from pydantic import ValidationError

from app.core.constants import (
    CSV_REQUIRED_HEADERS,
    DEFAULT_PAGE_LIMIT,
    DEFAULT_PAGE_OFFSET,
    ERR_CSV_MISSING_HEADERS,
    ERR_CSV_NO_DATA,
)
from app.core.exceptions import InvalidCSVError, NoteNotFoundError, PatientNotFoundError
from app.models.note import NoteType
from app.repositories.note import NoteRepository
from app.repositories.patient import PatientRepository
from app.schemas.note import (
    BulkNoteCreateResponse,
    BulkNoteFailure,
    NoteCreate,
    NoteResponse,
    NoteUpdate,
)

logger = logging.getLogger(__name__)


class NoteService:
    def __init__(self, note_repo: NoteRepository, patient_repo: PatientRepository) -> None:
        self._note_repo = note_repo
        self._patient_repo = patient_repo

    async def _require_patient(self, patient_id: uuid.UUID, provider_id: uuid.UUID) -> None:
        """Raise PatientNotFoundError if patient doesn't belong to this provider."""
        patient = await self._patient_repo.get_by_id(patient_id, provider_id)
        if patient is None:
            raise PatientNotFoundError()

    async def create_note(
        self, provider_id: uuid.UUID, patient_id: uuid.UUID, data: NoteCreate
    ) -> NoteResponse:
        await self._require_patient(patient_id, provider_id)
        note = await self._note_repo.create(
            patient_id=patient_id,
            note_type=data.note_type,
            content=data.content,
            session_date=data.session_date,
        )
        logger.info("Note %s created for patient %s", note.id, patient_id)
        return NoteResponse.model_validate(note)

    async def get_note(
        self, provider_id: uuid.UUID, patient_id: uuid.UUID, note_id: uuid.UUID
    ) -> NoteResponse:
        await self._require_patient(patient_id, provider_id)
        note = await self._note_repo.get_by_id(note_id, patient_id)
        if note is None:
            raise NoteNotFoundError()
        return NoteResponse.model_validate(note)

    async def list_notes(
        self,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
        note_type: NoteType | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = DEFAULT_PAGE_OFFSET,
    ) -> list[NoteResponse]:
        await self._require_patient(patient_id, provider_id)
        notes = await self._note_repo.list_for_patient(patient_id, note_type, limit, offset)
        return [NoteResponse.model_validate(n) for n in notes]

    async def update_note(
        self,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
        note_id: uuid.UUID,
        data: NoteUpdate,
    ) -> NoteResponse:
        await self._require_patient(patient_id, provider_id)
        note = await self._note_repo.get_by_id(note_id, patient_id)
        if note is None:
            raise NoteNotFoundError()
        updated = await self._note_repo.update(
            note,
            note_type=data.note_type,
            content=data.content,
            session_date=data.session_date,
        )
        logger.info("Note %s updated for patient %s", note_id, patient_id)
        return NoteResponse.model_validate(updated)

    async def delete_note(
        self, provider_id: uuid.UUID, patient_id: uuid.UUID, note_id: uuid.UUID
    ) -> None:
        await self._require_patient(patient_id, provider_id)
        note = await self._note_repo.get_by_id(note_id, patient_id)
        if note is None:
            raise NoteNotFoundError()
        await self._note_repo.soft_delete(note)
        logger.info("Note %s deleted for patient %s", note_id, patient_id)

    async def bulk_create_notes(
        self, provider_id: uuid.UUID, patient_id: uuid.UUID, csv_bytes: bytes
    ) -> BulkNoteCreateResponse:
        await self._require_patient(patient_id, provider_id)

        try:
            text = csv_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidCSVError("File must be UTF-8 encoded") from exc

        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None or not CSV_REQUIRED_HEADERS.issubset(set(reader.fieldnames)):
            raise InvalidCSVError(ERR_CSV_MISSING_HEADERS)

        valid_items: list[NoteCreate] = []
        failed: list[BulkNoteFailure] = []

        for i, row in enumerate(reader):
            try:
                item = NoteCreate.model_validate(
                    {
                        "note_type": row["note_type"].strip(),
                        "content": row["content"].strip(),
                        "session_date": row["session_date"].strip(),
                    }
                )
                valid_items.append(item)
            except ValidationError as exc:
                failed.append(BulkNoteFailure(index=i, errors=str(exc)))

        if not valid_items and not failed:
            raise InvalidCSVError(ERR_CSV_NO_DATA)

        created_notes: list[NoteResponse] = []
        if valid_items:
            db_notes = await self._note_repo.bulk_create(
                patient_id=patient_id,
                items=valid_items,
            )
            created_notes = [NoteResponse.model_validate(n) for n in db_notes]

        logger.info(
            "Bulk note import for patient %s: %d created, %d failed",
            patient_id,
            len(created_notes),
            len(failed),
        )
        return BulkNoteCreateResponse(created=created_notes, failed=failed)
