"""Integration tests for patient endpoints."""

import uuid

from httpx import AsyncClient

from app.models.provider import Provider


async def _create_patient(client: AsyncClient, first: str = "John", last: str = "Doe") -> dict:
    resp = await client.post("/api/v1/patients", json={"first_name": first, "last_name": last})
    assert resp.status_code == 201
    return resp.json()


class TestCreatePatient:
    async def test_creates_patient_successfully(
        self, auth_client_a: AsyncClient, provider_a: Provider
    ) -> None:
        resp = await auth_client_a.post(
            "/api/v1/patients", json={"first_name": "Alice", "last_name": "Wonder"}
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["first_name"] == "Alice"
        assert body["last_name"] == "Wonder"
        assert "id" in body
        assert "provider_id" not in body

    async def test_missing_first_name_returns_422(self, auth_client_a: AsyncClient) -> None:
        resp = await auth_client_a.post("/api/v1/patients", json={"last_name": "Doe"})
        assert resp.status_code == 422

    async def test_requires_auth(self, async_client: AsyncClient) -> None:
        resp = await async_client.post(
            "/api/v1/patients", json={"first_name": "John", "last_name": "Doe"}
        )
        assert resp.status_code in (401, 403)


class TestListPatients:
    async def test_returns_only_providers_patients(
        self, auth_client_a: AsyncClient, auth_client_b: AsyncClient
    ) -> None:
        await _create_patient(auth_client_a, "Alice", "A")
        await _create_patient(auth_client_b, "Bob", "B")

        resp_a = await auth_client_a.get("/api/v1/patients")
        assert resp_a.status_code == 200
        names = [p["first_name"] for p in resp_a.json()]
        assert "Alice" in names
        assert "Bob" not in names

    async def test_empty_list_for_new_provider(self, auth_client_a: AsyncClient) -> None:
        resp = await auth_client_a.get("/api/v1/patients")
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetPatient:
    async def test_get_own_patient(self, auth_client_a: AsyncClient) -> None:
        created = await _create_patient(auth_client_a)
        resp = await auth_client_a.get(f"/api/v1/patients/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    async def test_get_nonexistent_patient_returns_404(self, auth_client_a: AsyncClient) -> None:
        resp = await auth_client_a.get(f"/api/v1/patients/{uuid.uuid4()}")
        assert resp.status_code == 404
