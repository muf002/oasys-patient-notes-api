"""Integration tests for note endpoints (CRUD, bulk, filtering, soft-delete)."""

import uuid

from httpx import AsyncClient


def _make_csv(*rows: tuple[str, str, str]) -> bytes:
    """Build a minimal valid CSV from (note_type, session_date, content) tuples."""
    lines = ["note_type,session_date,content"]
    for note_type, session_date, content in rows:
        # Wrap content in quotes to handle embedded commas/newlines
        lines.append(f'{note_type},{session_date},"{content}"')
    return "\n".join(lines).encode()


async def _create_patient(client: AsyncClient) -> dict:
    resp = await client.post("/api/v1/patients", json={"first_name": "Test", "last_name": "User"})
    assert resp.status_code == 201
    return resp.json()


async def _create_note(
    client: AsyncClient,
    patient_id: str,
    note_type: str = "progress_note",
    content: str = "Some clinical notes.",
    session_date: str = "2024-03-01",
) -> dict:
    resp = await client.post(
        f"/api/v1/patients/{patient_id}/notes",
        json={"note_type": note_type, "content": content, "session_date": session_date},
    )
    assert resp.status_code == 201
    return resp.json()


class TestCreateNote:
    async def test_creates_note_successfully(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        resp = await auth_client_a.post(
            f"/api/v1/patients/{patient['id']}/notes",
            json={
                "note_type": "intake",
                "content": "Initial intake session.",
                "session_date": "2024-01-10",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["note_type"] == "intake"
        assert body["content"] == "Initial intake session."
        assert body["patient_id"] == patient["id"]

    async def test_invalid_note_type_returns_422(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        resp = await auth_client_a.post(
            f"/api/v1/patients/{patient['id']}/notes",
            json={"note_type": "bad_type", "content": "X", "session_date": "2024-01-01"},
        )
        assert resp.status_code == 422

    async def test_blank_content_returns_422(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        resp = await auth_client_a.post(
            f"/api/v1/patients/{patient['id']}/notes",
            json={"note_type": "progress_note", "content": "", "session_date": "2024-01-01"},
        )
        assert resp.status_code == 422

    async def test_unknown_patient_returns_404(self, auth_client_a: AsyncClient) -> None:
        resp = await auth_client_a.post(
            f"/api/v1/patients/{uuid.uuid4()}/notes",
            json={"note_type": "intake", "content": "Content.", "session_date": "2024-01-01"},
        )
        assert resp.status_code == 404


class TestGetNote:
    async def test_gets_existing_note(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        note = await _create_note(auth_client_a, patient["id"])
        resp = await auth_client_a.get(f"/api/v1/patients/{patient['id']}/notes/{note['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == note["id"]

    async def test_unknown_note_returns_404(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        resp = await auth_client_a.get(f"/api/v1/patients/{patient['id']}/notes/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestListNotes:
    async def test_lists_all_notes_for_patient(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        await _create_note(auth_client_a, patient["id"], note_type="intake")
        await _create_note(auth_client_a, patient["id"], note_type="progress_note")

        resp = await auth_client_a.get(f"/api/v1/patients/{patient['id']}/notes")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_filters_by_note_type(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        await _create_note(auth_client_a, patient["id"], note_type="intake")
        await _create_note(auth_client_a, patient["id"], note_type="progress_note")
        await _create_note(auth_client_a, patient["id"], note_type="progress_note")

        resp = await auth_client_a.get(
            f"/api/v1/patients/{patient['id']}/notes?note_type=progress_note"
        )
        assert resp.status_code == 200
        notes = resp.json()
        assert len(notes) == 2
        assert all(n["note_type"] == "progress_note" for n in notes)

    async def test_soft_deleted_notes_excluded_from_list(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        note = await _create_note(auth_client_a, patient["id"])

        await auth_client_a.delete(f"/api/v1/patients/{patient['id']}/notes/{note['id']}")

        resp = await auth_client_a.get(f"/api/v1/patients/{patient['id']}/notes")
        assert resp.status_code == 200
        assert resp.json() == []


class TestUpdateNote:
    async def test_partial_update_only_changes_provided_fields(
        self, auth_client_a: AsyncClient
    ) -> None:
        patient = await _create_patient(auth_client_a)
        note = await _create_note(auth_client_a, patient["id"], note_type="intake")

        resp = await auth_client_a.patch(
            f"/api/v1/patients/{patient['id']}/notes/{note['id']}",
            json={"content": "Updated content."},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["content"] == "Updated content."
        assert body["note_type"] == "intake"  # unchanged

    async def test_update_note_type(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        note = await _create_note(auth_client_a, patient["id"], note_type="intake")

        resp = await auth_client_a.patch(
            f"/api/v1/patients/{patient['id']}/notes/{note['id']}",
            json={"note_type": "discharge_summary"},
        )
        assert resp.status_code == 200
        assert resp.json()["note_type"] == "discharge_summary"

    async def test_update_nonexistent_note_returns_404(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        resp = await auth_client_a.patch(
            f"/api/v1/patients/{patient['id']}/notes/{uuid.uuid4()}",
            json={"content": "New content."},
        )
        assert resp.status_code == 404


class TestDeleteNote:
    async def test_soft_delete_returns_204(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        note = await _create_note(auth_client_a, patient["id"])

        resp = await auth_client_a.delete(f"/api/v1/patients/{patient['id']}/notes/{note['id']}")
        assert resp.status_code == 204

    async def test_deleted_note_not_accessible(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        note = await _create_note(auth_client_a, patient["id"])

        await auth_client_a.delete(f"/api/v1/patients/{patient['id']}/notes/{note['id']}")

        resp = await auth_client_a.get(f"/api/v1/patients/{patient['id']}/notes/{note['id']}")
        assert resp.status_code == 404

    async def test_delete_nonexistent_note_returns_404(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        resp = await auth_client_a.delete(f"/api/v1/patients/{patient['id']}/notes/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestBulkCreateNotes:
    async def test_all_valid_returns_207_all_created(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        csv_bytes = _make_csv(
            ("intake", "2024-01-01", "Intake note."),
            ("progress_note", "2024-02-01", "Progress note."),
        )
        resp = await auth_client_a.post(
            f"/api/v1/patients/{patient['id']}/notes/bulk",
            files={"file": ("notes.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 207
        body = resp.json()
        assert len(body["created"]) == 2
        assert len(body["failed"]) == 0

    async def test_partial_failure_returns_207_with_created_and_failed(
        self, auth_client_a: AsyncClient
    ) -> None:
        patient = await _create_patient(auth_client_a)
        csv_bytes = _make_csv(
            ("intake", "2024-01-01", "Valid note."),
            ("bad_type", "2024-01-02", "Invalid."),
        )
        resp = await auth_client_a.post(
            f"/api/v1/patients/{patient['id']}/notes/bulk",
            files={"file": ("notes.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 207
        body = resp.json()
        assert len(body["created"]) == 1
        assert len(body["failed"]) == 1
        assert body["failed"][0]["index"] == 1

    async def test_wrong_file_extension_returns_400(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        resp = await auth_client_a.post(
            f"/api/v1/patients/{patient['id']}/notes/bulk",
            files={"file": ("notes.json", b'{"notes":[]}', "application/json")},
        )
        assert resp.status_code == 400

    async def test_missing_headers_returns_400(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        bad_csv = b"note_type,content\nintake,Missing session_date.\n"
        resp = await auth_client_a.post(
            f"/api/v1/patients/{patient['id']}/notes/bulk",
            files={"file": ("notes.csv", bad_csv, "text/csv")},
        )
        assert resp.status_code == 400

    async def test_empty_csv_returns_400(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        headers_only = b"note_type,session_date,content\n"
        resp = await auth_client_a.post(
            f"/api/v1/patients/{patient['id']}/notes/bulk",
            files={"file": ("notes.csv", headers_only, "text/csv")},
        )
        assert resp.status_code == 400

    async def test_bulk_unknown_patient_returns_404(self, auth_client_a: AsyncClient) -> None:
        csv_bytes = _make_csv(("intake", "2024-01-01", "Note."))
        resp = await auth_client_a.post(
            f"/api/v1/patients/{uuid.uuid4()}/notes/bulk",
            files={"file": ("notes.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 404

    async def test_content_with_commas_parsed_correctly(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        csv_bytes = (
            b"note_type,session_date,content\n"
            b'progress_note,2024-03-01,"Patient noted improvement, follow up in 2 weeks."\n'
        )
        resp = await auth_client_a.post(
            f"/api/v1/patients/{patient['id']}/notes/bulk",
            files={"file": ("notes.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 207
        body = resp.json()
        assert len(body["created"]) == 1
        assert body["created"][0]["content"] == "Patient noted improvement, follow up in 2 weeks."
