"""Integration tests for note endpoints (CRUD, bulk, filtering, soft-delete)."""

import uuid

from httpx import AsyncClient


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
        resp = await auth_client_a.post(
            f"/api/v1/patients/{patient['id']}/notes/bulk",
            json={
                "notes": [
                    {"note_type": "intake", "content": "Intake.", "session_date": "2024-01-01"},
                    {
                        "note_type": "progress_note",
                        "content": "Progress.",
                        "session_date": "2024-02-01",
                    },  # noqa: E501
                ]
            },
        )
        assert resp.status_code == 207
        body = resp.json()
        assert len(body["created"]) == 2
        assert len(body["failed"]) == 0

    async def test_partial_failure_returns_207_with_created_and_failed(
        self, auth_client_a: AsyncClient
    ) -> None:
        patient = await _create_patient(auth_client_a)
        resp = await auth_client_a.post(
            f"/api/v1/patients/{patient['id']}/notes/bulk",
            json={
                "notes": [
                    {"note_type": "intake", "content": "Valid note.", "session_date": "2024-01-01"},
                    {"note_type": "bad_type", "content": "Invalid.", "session_date": "2024-01-02"},
                ]
            },
        )
        assert resp.status_code == 207
        body = resp.json()
        assert len(body["created"]) == 1
        assert len(body["failed"]) == 1
        assert body["failed"][0]["index"] == 1

    async def test_empty_notes_list_returns_422(self, auth_client_a: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a)
        resp = await auth_client_a.post(
            f"/api/v1/patients/{patient['id']}/notes/bulk",
            json={"notes": []},
        )
        assert resp.status_code == 422

    async def test_bulk_unknown_patient_returns_404(self, auth_client_a: AsyncClient) -> None:
        resp = await auth_client_a.post(
            f"/api/v1/patients/{uuid.uuid4()}/notes/bulk",
            json={
                "notes": [{"note_type": "intake", "content": "Note.", "session_date": "2024-01-01"}]
            },
        )
        assert resp.status_code == 404
