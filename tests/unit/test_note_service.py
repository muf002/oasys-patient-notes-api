"""Unit tests for NoteService — mocked repos, no DB, no HTTP."""

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import NoteNotFoundError, PatientNotFoundError
from app.models.note import Note, NoteType
from app.models.patient import Patient
from app.schemas.note import BulkNoteCreate, NoteCreate
from app.services.note import NoteService


def _make_patient(provider_id: uuid.UUID | None = None) -> Patient:
    p = Patient()
    p.id = uuid.uuid4()
    p.provider_id = provider_id or uuid.uuid4()
    p.first_name = "John"
    p.last_name = "Doe"
    p.created_at = datetime.now(UTC)
    return p


def _make_note(patient_id: uuid.UUID | None = None) -> Note:
    n = Note()
    n.id = uuid.uuid4()
    n.patient_id = patient_id or uuid.uuid4()
    n.note_type = NoteType.PROGRESS_NOTE
    n.content = "Session notes here."
    n.session_date = date(2024, 1, 15)
    n.created_at = datetime.now(UTC)
    n.updated_at = datetime.now(UTC)
    n.deleted_at = None
    return n


@pytest.fixture
def provider_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def patient_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def note_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def patient_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(note_repo: AsyncMock, patient_repo: AsyncMock) -> NoteService:
    return NoteService(note_repo=note_repo, patient_repo=patient_repo)


class TestCreateNote:
    async def test_creates_note_for_owned_patient(
        self,
        service: NoteService,
        note_repo: AsyncMock,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> None:
        patient_repo.get_by_id.return_value = _make_patient(provider_id)
        expected_note = _make_note(patient_id)
        note_repo.create.return_value = expected_note

        data = NoteCreate(
            note_type=NoteType.INTAKE,
            content="First intake.",
            session_date=date(2024, 1, 1),
        )
        result = await service.create_note(provider_id, patient_id, data)

        patient_repo.get_by_id.assert_awaited_once_with(patient_id, provider_id)
        note_repo.create.assert_awaited_once()
        assert result.id == expected_note.id

    async def test_raises_404_when_patient_not_owned(
        self,
        service: NoteService,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> None:
        patient_repo.get_by_id.return_value = None

        data = NoteCreate(
            note_type=NoteType.PROGRESS_NOTE,
            content="Some content.",
            session_date=date(2024, 1, 1),
        )
        with pytest.raises(PatientNotFoundError):
            await service.create_note(provider_id, patient_id, data)


class TestGetNote:
    async def test_returns_note_for_owned_patient(
        self,
        service: NoteService,
        note_repo: AsyncMock,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> None:
        patient_repo.get_by_id.return_value = _make_patient(provider_id)
        expected_note = _make_note(patient_id)
        note_repo.get_by_id.return_value = expected_note

        result = await service.get_note(provider_id, patient_id, expected_note.id)
        assert result.id == expected_note.id

    async def test_raises_404_when_note_not_found(
        self,
        service: NoteService,
        note_repo: AsyncMock,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> None:
        patient_repo.get_by_id.return_value = _make_patient(provider_id)
        note_repo.get_by_id.return_value = None

        with pytest.raises(NoteNotFoundError):
            await service.get_note(provider_id, patient_id, uuid.uuid4())


class TestDeleteNote:
    async def test_soft_deletes_note(
        self,
        service: NoteService,
        note_repo: AsyncMock,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> None:
        patient_repo.get_by_id.return_value = _make_patient(provider_id)
        note = _make_note(patient_id)
        note_repo.get_by_id.return_value = note

        await service.delete_note(provider_id, patient_id, note.id)
        note_repo.soft_delete.assert_awaited_once_with(note)

    async def test_raises_404_if_note_missing(
        self,
        service: NoteService,
        note_repo: AsyncMock,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> None:
        patient_repo.get_by_id.return_value = _make_patient(provider_id)
        note_repo.get_by_id.return_value = None

        with pytest.raises(NoteNotFoundError):
            await service.delete_note(provider_id, patient_id, uuid.uuid4())


class TestBulkCreateNotes:
    async def test_all_valid_items_created(
        self,
        service: NoteService,
        note_repo: AsyncMock,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> None:
        patient_repo.get_by_id.return_value = _make_patient(provider_id)
        note1 = _make_note(patient_id)
        note2 = _make_note(patient_id)
        note_repo.bulk_create.return_value = [note1, note2]

        data = BulkNoteCreate(
            notes=[
                {"note_type": "intake", "content": "Intake note.", "session_date": "2024-01-01"},
                {"note_type": "progress_note", "content": "Progress note.", "session_date": "2024-02-01"},
            ]
        )
        result = await service.bulk_create_notes(provider_id, patient_id, data)

        assert len(result.created) == 2
        assert len(result.failed) == 0

    async def test_partial_failure_returns_created_and_failed(
        self,
        service: NoteService,
        note_repo: AsyncMock,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> None:
        patient_repo.get_by_id.return_value = _make_patient(provider_id)
        valid_note = _make_note(patient_id)
        note_repo.bulk_create.return_value = [valid_note]

        data = BulkNoteCreate(
            notes=[
                {"note_type": "progress_note", "content": "Valid note.", "session_date": "2024-01-01"},
                {"note_type": "bad_type", "content": "Invalid.", "session_date": "2024-01-02"},
            ]
        )
        result = await service.bulk_create_notes(provider_id, patient_id, data)

        assert len(result.created) == 1
        assert len(result.failed) == 1
        assert result.failed[0].index == 1

    async def test_raises_404_if_patient_not_owned(
        self,
        service: NoteService,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> None:
        patient_repo.get_by_id.return_value = None

        data = BulkNoteCreate(
            notes=[
                {"note_type": "intake", "content": "Note content.", "session_date": "2024-01-01"}
            ]
        )
        with pytest.raises(PatientNotFoundError):
            await service.bulk_create_notes(provider_id, patient_id, data)
