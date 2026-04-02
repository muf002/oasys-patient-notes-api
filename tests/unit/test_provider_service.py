"""Unit tests for ProviderService — mocked repos, no DB, no HTTP."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ProviderEmailConflictError
from app.models.patient import Patient
from app.models.provider import Provider
from app.services.provider import ProviderService


def _make_provider() -> Provider:
    p = Provider()
    p.id = uuid.uuid4()
    p.name = "Dr. Alice"
    p.email = "alice@test.com"
    p.created_at = datetime.now(UTC)
    return p


def _make_patient() -> Patient:
    p = Patient()
    p.id = uuid.uuid4()
    p.provider_id = uuid.uuid4()
    p.first_name = "John"
    p.last_name = "Doe"
    p.created_at = datetime.now(UTC)
    return p


@pytest.fixture
def provider_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def patient_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def note_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    provider_repo: AsyncMock, patient_repo: AsyncMock, note_repo: AsyncMock
) -> ProviderService:
    return ProviderService(
        provider_repo=provider_repo,
        patient_repo=patient_repo,
        note_repo=note_repo,
    )


class TestCreateProvider:
    async def test_creates_provider_and_returns_token(
        self, service: ProviderService, provider_repo: AsyncMock
    ) -> None:
        provider = _make_provider()
        provider_repo.create.return_value = provider

        with patch("app.services.provider._write_token"):
            result = await service.create_provider(provider.name, provider.email)

        assert result.id == provider.id
        assert result.email == provider.email
        assert result.api_token != ""

    async def test_write_token_called_on_create(
        self, service: ProviderService, provider_repo: AsyncMock
    ) -> None:
        provider = _make_provider()
        provider_repo.create.return_value = provider

        with patch("app.services.provider._write_token") as mock_write:
            await service.create_provider(provider.name, provider.email)

        mock_write.assert_called_once()

    async def test_duplicate_email_raises_conflict(
        self, service: ProviderService, provider_repo: AsyncMock
    ) -> None:
        provider_repo.create.side_effect = IntegrityError(None, None, Exception())

        with pytest.raises(ProviderEmailConflictError):
            await service.create_provider("Dr. Alice", "alice@test.com")


class TestGetStats:
    async def test_returns_correct_counts(
        self,
        service: ProviderService,
        patient_repo: AsyncMock,
        note_repo: AsyncMock,
    ) -> None:
        patient_ids = [uuid.uuid4(), uuid.uuid4()]
        patient_repo.get_ids_for_provider.return_value = patient_ids
        note_repo.count_for_provider_patients.return_value = 5

        result = await service.get_stats(uuid.uuid4())

        assert result.total_patients == 2
        assert result.total_notes == 5

    async def test_stats_with_no_patients(
        self,
        service: ProviderService,
        patient_repo: AsyncMock,
        note_repo: AsyncMock,
    ) -> None:
        patient_repo.get_ids_for_provider.return_value = []
        note_repo.count_for_provider_patients.return_value = 0

        result = await service.get_stats(uuid.uuid4())

        assert result.total_patients == 0
        assert result.total_notes == 0
