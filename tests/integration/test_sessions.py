"""Integration tests for session endpoints — HTTP contracts, no real Groq calls."""

import uuid

import pytest
from httpx import AsyncClient

import app.api.v1.sessions as sessions_module


async def _create_patient(client: AsyncClient) -> dict:
    resp = await client.post("/api/v1/patients", json={"first_name": "Test", "last_name": "User"})
    assert resp.status_code == 201
    return resp.json()


async def _upload_session(
    client: AsyncClient,
    patient_id: str,
    filename: str = "test.wav",
    session_date: str = "2024-01-15",
) -> dict:
    resp = await client.post(
        f"/api/v1/patients/{patient_id}/sessions",
        data={"session_date": session_date},
        files={"audio_file": (filename, b"fake audio content", "audio/wav")},
    )
    assert resp.status_code == 202
    return resp.json()


class TestSessionUpload:
    async def test_upload_valid_audio_returns_202_with_pending_status(
        self, auth_client_a_with_stubs: AsyncClient
    ) -> None:
        patient = await _create_patient(auth_client_a_with_stubs)
        resp = await auth_client_a_with_stubs.post(
            f"/api/v1/patients/{patient['id']}/sessions",
            data={"session_date": "2024-01-15"},
            files={"audio_file": ("recording.wav", b"fake audio content", "audio/wav")},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "pending"
        assert body["patient_id"] == patient["id"]
        assert body["original_filename"] == "recording.wav"
        assert body["transcript"] is None
        assert body["insights"] is None

    async def test_upload_unsupported_format_returns_422(
        self, auth_client_a_with_stubs: AsyncClient
    ) -> None:
        patient = await _create_patient(auth_client_a_with_stubs)
        resp = await auth_client_a_with_stubs.post(
            f"/api/v1/patients/{patient['id']}/sessions",
            data={"session_date": "2024-01-15"},
            files={"audio_file": ("notes.pdf", b"pdf content", "application/pdf")},
        )
        assert resp.status_code == 422

    async def test_upload_exceeds_size_limit_returns_413(
        self, auth_client_a_with_stubs: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        patient = await _create_patient(auth_client_a_with_stubs)
        # Temporarily set limit to 0 bytes so any non-empty file exceeds it
        monkeypatch.setattr(sessions_module.settings, "AUDIO_MAX_SIZE_MB", 0)
        resp = await auth_client_a_with_stubs.post(
            f"/api/v1/patients/{patient['id']}/sessions",
            data={"session_date": "2024-01-15"},
            files={"audio_file": ("test.wav", b"x", "audio/wav")},
        )
        assert resp.status_code == 413

    async def test_upload_unknown_patient_returns_404(
        self, auth_client_a_with_stubs: AsyncClient
    ) -> None:
        resp = await auth_client_a_with_stubs.post(
            f"/api/v1/patients/{uuid.uuid4()}/sessions",
            data={"session_date": "2024-01-15"},
            files={"audio_file": ("test.wav", b"audio", "audio/wav")},
        )
        assert resp.status_code == 404

    async def test_upload_future_session_date_returns_422(
        self, auth_client_a_with_stubs: AsyncClient
    ) -> None:
        patient = await _create_patient(auth_client_a_with_stubs)
        resp = await auth_client_a_with_stubs.post(
            f"/api/v1/patients/{patient['id']}/sessions",
            data={"session_date": "2099-01-01"},
            files={"audio_file": ("test.wav", b"audio", "audio/wav")},
        )
        assert resp.status_code == 422


class TestGetSession:
    async def test_get_session_returns_pending_session(
        self, auth_client_a_with_stubs: AsyncClient
    ) -> None:
        patient = await _create_patient(auth_client_a_with_stubs)
        uploaded = await _upload_session(auth_client_a_with_stubs, patient["id"])

        resp = await auth_client_a_with_stubs.get(
            f"/api/v1/patients/{patient['id']}/sessions/{uploaded['id']}"
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == uploaded["id"]
        assert resp.json()["status"] == "pending"

    async def test_get_unknown_session_returns_404(
        self, auth_client_a_with_stubs: AsyncClient
    ) -> None:
        patient = await _create_patient(auth_client_a_with_stubs)
        resp = await auth_client_a_with_stubs.get(
            f"/api/v1/patients/{patient['id']}/sessions/{uuid.uuid4()}"
        )
        assert resp.status_code == 404

    async def test_provider_b_cannot_get_provider_a_session(
        self, auth_client_a_with_stubs: AsyncClient, auth_client_b: AsyncClient
    ) -> None:
        patient = await _create_patient(auth_client_a_with_stubs)
        uploaded = await _upload_session(auth_client_a_with_stubs, patient["id"])

        resp = await auth_client_b.get(
            f"/api/v1/patients/{patient['id']}/sessions/{uploaded['id']}"
        )
        assert resp.status_code == 404


class TestListSessions:
    async def test_lists_sessions_for_owned_patient(
        self, auth_client_a_with_stubs: AsyncClient
    ) -> None:
        patient = await _create_patient(auth_client_a_with_stubs)
        await _upload_session(auth_client_a_with_stubs, patient["id"])
        await _upload_session(auth_client_a_with_stubs, patient["id"])

        resp = await auth_client_a_with_stubs.get(f"/api/v1/patients/{patient['id']}/sessions")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_filters_by_status(self, auth_client_a_with_stubs: AsyncClient) -> None:
        patient = await _create_patient(auth_client_a_with_stubs)
        await _upload_session(auth_client_a_with_stubs, patient["id"])

        resp = await auth_client_a_with_stubs.get(
            f"/api/v1/patients/{patient['id']}/sessions?status=pending"
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["status"] == "pending"

        resp_none = await auth_client_a_with_stubs.get(
            f"/api/v1/patients/{patient['id']}/sessions?status=completed"
        )
        assert resp_none.status_code == 200
        assert resp_none.json() == []

    async def test_provider_b_cannot_list_provider_a_sessions(
        self, auth_client_a_with_stubs: AsyncClient, auth_client_b: AsyncClient
    ) -> None:
        patient = await _create_patient(auth_client_a_with_stubs)
        await _upload_session(auth_client_a_with_stubs, patient["id"])

        resp = await auth_client_b.get(f"/api/v1/patients/{patient['id']}/sessions")
        assert resp.status_code == 404

    async def test_invalid_status_param_returns_422(
        self, auth_client_a_with_stubs: AsyncClient
    ) -> None:
        patient = await _create_patient(auth_client_a_with_stubs)
        resp = await auth_client_a_with_stubs.get(
            f"/api/v1/patients/{patient['id']}/sessions?status=invalid"
        )
        assert resp.status_code == 422
