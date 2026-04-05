"""
Cross-provider data isolation tests.

A provider must never be able to read, modify, or delete another provider's
patients or notes — even if they know the UUID.
"""

from httpx import AsyncClient

from app.models.provider import Provider


async def _create_patient(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/patients", json={"first_name": "Owned", "last_name": "Patient"}
    )
    assert resp.status_code == 201
    return resp.json()


async def _create_note(client: AsyncClient, patient_id: str) -> dict:
    resp = await client.post(
        f"/api/v1/patients/{patient_id}/notes",
        json={
            "note_type": "progress_note",
            "content": "Private clinical notes.",
            "session_date": "2024-06-01",
        },
    )
    assert resp.status_code == 201
    return resp.json()


class TestCrossProviderPatientIsolation:
    async def test_provider_b_cannot_get_provider_a_patient(
        self,
        auth_client_a: AsyncClient,
        auth_client_b: AsyncClient,
    ) -> None:
        patient_a = await _create_patient(auth_client_a)

        resp = await auth_client_b.get(f"/api/v1/patients/{patient_a['id']}")
        assert resp.status_code == 404

    async def test_provider_b_cannot_list_provider_a_patients(
        self,
        auth_client_a: AsyncClient,
        auth_client_b: AsyncClient,
    ) -> None:
        await _create_patient(auth_client_a)

        resp = await auth_client_b.get("/api/v1/patients")
        assert resp.status_code == 200
        # Provider B has no patients — must not see A's
        assert resp.json() == []

    async def test_provider_b_cannot_create_patient_for_provider_a(
        self,
        auth_client_a: AsyncClient,
        auth_client_b: AsyncClient,
        provider_a: Provider,
    ) -> None:
        # Patient creation always scopes to the authenticated provider —
        # there's no way to pass a different provider_id via the API.
        resp = await auth_client_b.post(
            "/api/v1/patients", json={"first_name": "Hijack", "last_name": "Attempt"}
        )
        assert resp.status_code == 201
        patient_id = resp.json()["id"]

        # Patient is visible to B but invisible to A — confirms correct scoping
        assert (await auth_client_b.get(f"/api/v1/patients/{patient_id}")).status_code == 200
        assert (await auth_client_a.get(f"/api/v1/patients/{patient_id}")).status_code == 404


class TestCrossProviderNoteIsolation:
    async def test_provider_b_cannot_get_provider_a_note(
        self,
        auth_client_a: AsyncClient,
        auth_client_b: AsyncClient,
    ) -> None:
        patient_a = await _create_patient(auth_client_a)
        note_a = await _create_note(auth_client_a, patient_a["id"])

        resp = await auth_client_b.get(f"/api/v1/patients/{patient_a['id']}/notes/{note_a['id']}")
        assert resp.status_code == 404

    async def test_provider_b_cannot_list_provider_a_notes(
        self,
        auth_client_a: AsyncClient,
        auth_client_b: AsyncClient,
    ) -> None:
        patient_a = await _create_patient(auth_client_a)
        await _create_note(auth_client_a, patient_a["id"])

        resp = await auth_client_b.get(f"/api/v1/patients/{patient_a['id']}/notes")
        assert resp.status_code == 404

    async def test_provider_b_cannot_update_provider_a_note(
        self,
        auth_client_a: AsyncClient,
        auth_client_b: AsyncClient,
    ) -> None:
        patient_a = await _create_patient(auth_client_a)
        note_a = await _create_note(auth_client_a, patient_a["id"])

        resp = await auth_client_b.patch(
            f"/api/v1/patients/{patient_a['id']}/notes/{note_a['id']}",
            json={"content": "Tampered content."},
        )
        assert resp.status_code == 404

    async def test_provider_b_cannot_delete_provider_a_note(
        self,
        auth_client_a: AsyncClient,
        auth_client_b: AsyncClient,
    ) -> None:
        patient_a = await _create_patient(auth_client_a)
        note_a = await _create_note(auth_client_a, patient_a["id"])

        resp = await auth_client_b.delete(
            f"/api/v1/patients/{patient_a['id']}/notes/{note_a['id']}"
        )
        assert resp.status_code == 404

    async def test_provider_b_cannot_bulk_create_on_provider_a_patient(
        self,
        auth_client_a: AsyncClient,
        auth_client_b: AsyncClient,
    ) -> None:
        patient_a = await _create_patient(auth_client_a)

        resp = await auth_client_b.post(
            f"/api/v1/patients/{patient_a['id']}/notes/bulk",
            json={
                "notes": [
                    {
                        "note_type": "intake",
                        "content": "Unauthorized note.",
                        "session_date": "2024-01-01",
                    }
                ]
            },
        )
        assert resp.status_code == 404


class TestProviderStats:
    async def test_stats_only_count_own_patients_and_notes(
        self,
        auth_client_a: AsyncClient,
        auth_client_b: AsyncClient,
    ) -> None:
        patient_a = await _create_patient(auth_client_a)
        await _create_note(auth_client_a, patient_a["id"])
        await _create_note(auth_client_a, patient_a["id"])

        # Provider B has no data
        resp_b = await auth_client_b.get("/api/v1/providers/stats")
        assert resp_b.status_code == 200
        stats_b = resp_b.json()
        assert stats_b["total_patients"] == 0
        assert stats_b["total_notes"] == 0

        # Provider A has 1 patient, 2 notes
        resp_a = await auth_client_a.get("/api/v1/providers/stats")
        assert resp_a.status_code == 200
        stats_a = resp_a.json()
        assert stats_a["total_patients"] == 1
        assert stats_a["total_notes"] == 2
