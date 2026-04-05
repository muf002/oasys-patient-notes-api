"""Unit tests for NoteService — mocked repos, no DB, no HTTP."""

import csv
import io
import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import InvalidCSVError, NoteNotFoundError, PatientNotFoundError
from app.models.note import Note, NoteType
from app.models.patient import Patient
from app.schemas.note import NoteCreate
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


def _make_csv(*rows: dict) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["note_type", "session_date", "content"])
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode()


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

        csv_bytes = _make_csv(
            {"note_type": "intake", "session_date": "2024-01-01", "content": "Intake note."},
            {"note_type": "progress_note", "session_date": "2024-02-01", "content": "Progress note."},
        )
        result = await service.bulk_create_notes(provider_id, patient_id, csv_bytes)

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

        csv_bytes = _make_csv(
            {"note_type": "progress_note", "session_date": "2024-01-01", "content": "Valid note."},
            {"note_type": "bad_type", "session_date": "2024-01-02", "content": "Invalid."},
        )
        result = await service.bulk_create_notes(provider_id, patient_id, csv_bytes)

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

        csv_bytes = _make_csv(
            {"note_type": "intake", "session_date": "2024-01-01", "content": "Note content."}
        )
        with pytest.raises(PatientNotFoundError):
            await service.bulk_create_notes(provider_id, patient_id, csv_bytes)

    async def test_missing_headers_raises_invalid_csv(
        self,
        service: NoteService,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> None:
        patient_repo.get_by_id.return_value = _make_patient(provider_id)
        bad_csv = b"note_type,content\nintake,Missing session_date column.\n"

        with pytest.raises(InvalidCSVError):
            await service.bulk_create_notes(provider_id, patient_id, bad_csv)

    async def test_non_utf8_bytes_raises_invalid_csv(
        self,
        service: NoteService,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> None:
        patient_repo.get_by_id.return_value = _make_patient(provider_id)

        with pytest.raises(InvalidCSVError):
            await service.bulk_create_notes(provider_id, patient_id, b"\xff\xfe bad bytes")

    async def test_empty_csv_raises_invalid_csv(
        self,
        service: NoteService,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> None:
        patient_repo.get_by_id.return_value = _make_patient(provider_id)
        headers_only = b"note_type,session_date,content\n"

        with pytest.raises(InvalidCSVError):
            await service.bulk_create_notes(provider_id, patient_id, headers_only)

    async def test_content_with_commas_and_newlines_parsed_correctly(
        self,
        service: NoteService,
        note_repo: AsyncMock,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> None:
        patient_repo.get_by_id.return_value = _make_patient(provider_id)
        note_repo.bulk_create.return_value = [_make_note(patient_id)]

        # RFC 4180: fields with commas/newlines are wrapped in double-quotes
        csv_bytes = (
            b"note_type,session_date,content\n"
            b'progress_note,2024-01-01,"Patient noted improvement, follow up in 2 weeks.\n'
            b'Mood stable."\n'
        )
        result = await service.bulk_create_notes(provider_id, patient_id, csv_bytes)

        assert len(result.created) == 1
        assert len(result.failed) == 0
