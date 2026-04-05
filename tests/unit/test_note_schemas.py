"""Unit tests for Pydantic note schemas — no DB, no HTTP."""

from datetime import date

import pytest

from app.models.note import NoteType
from app.schemas.note import NoteCreate, NoteUpdate


class TestNoteCreate:
    def test_valid_note(self) -> None:
        note = NoteCreate(
            note_type=NoteType.PROGRESS_NOTE,
            content="Session went well.",
            session_date=date(2024, 1, 15),
        )
        assert note.note_type == NoteType.PROGRESS_NOTE
        assert note.content == "Session went well."

    def test_invalid_note_type_rejected(self) -> None:
        with pytest.raises(ValueError):
            NoteCreate(
                note_type="invalid_type",  # type: ignore[arg-type]
                content="Some content",
                session_date=date(2024, 1, 15),
            )

    def test_empty_content_rejected(self) -> None:
        with pytest.raises(ValueError):
            NoteCreate(
                note_type=NoteType.INTAKE,
                content="",
                session_date=date(2024, 1, 15),
            )

    def test_all_note_types_accepted(self) -> None:
        for note_type in NoteType:
            note = NoteCreate(
                note_type=note_type,
                content="Content here.",
                session_date=date(2024, 3, 1),
            )
            assert note.note_type == note_type

    def test_missing_session_date_rejected(self) -> None:
        with pytest.raises(ValueError):
            NoteCreate(
                note_type=NoteType.PROGRESS_NOTE,
                content="Some content",
                session_date=None,  # type: ignore[arg-type]
            )


class TestNoteUpdate:
    def test_all_fields_optional(self) -> None:
        update = NoteUpdate()
        assert update.note_type is None
        assert update.content is None
        assert update.session_date is None

    def test_partial_update_allowed(self) -> None:
        update = NoteUpdate(content="Updated content.")
        assert update.content == "Updated content."
        assert update.note_type is None

    def test_empty_content_rejected_on_update(self) -> None:
        with pytest.raises(ValueError):
            NoteUpdate(content="")


