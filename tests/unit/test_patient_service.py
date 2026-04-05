"""Unit tests for PatientService — mocked repos, no DB, no HTTP."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import PatientNotFoundError
from app.models.patient import Patient
from app.schemas.patient import PatientResponse
from app.services.patient import PatientService


def _make_patient(provider_id: uuid.UUID | None = None) -> Patient:
    p = Patient()
    p.id = uuid.uuid4()
    p.provider_id = provider_id or uuid.uuid4()
    p.first_name = "Jane"
    p.last_name = "Smith"
    p.created_at = datetime.now(UTC)
    return p


@pytest.fixture
def provider_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def patient_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(patient_repo: AsyncMock) -> PatientService:
    return PatientService(patient_repo=patient_repo)


class TestCreatePatient:
    async def test_creates_patient_and_returns_response(
        self,
        service: PatientService,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
    ) -> None:
        expected = _make_patient(provider_id)
        patient_repo.create.return_value = expected

        result = await service.create_patient(provider_id, "Jane", "Smith")

        patient_repo.create.assert_awaited_once_with(
            provider_id=provider_id,
            first_name="Jane",
            last_name="Smith",
        )
        assert isinstance(result, PatientResponse)
        assert result.id == expected.id
        assert result.first_name == expected.first_name
        assert result.last_name == expected.last_name

    async def test_returns_patient_response_type(
        self,
        service: PatientService,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
    ) -> None:
        patient_repo.create.return_value = _make_patient(provider_id)

        result = await service.create_patient(provider_id, "Jane", "Smith")

        assert isinstance(result, PatientResponse)


class TestGetPatient:
    async def test_returns_patient_for_owned_provider(
        self,
        service: PatientService,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
    ) -> None:
        expected = _make_patient(provider_id)
        patient_repo.get_by_id.return_value = expected

        result = await service.get_patient(expected.id, provider_id)

        patient_repo.get_by_id.assert_awaited_once_with(expected.id, provider_id)
        assert result.id == expected.id

    async def test_raises_patient_not_found_when_repo_returns_none(
        self,
        service: PatientService,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
    ) -> None:
        patient_repo.get_by_id.return_value = None

        with pytest.raises(PatientNotFoundError):
            await service.get_patient(uuid.uuid4(), provider_id)

    async def test_raises_not_found_for_other_providers_patient(
        self,
        service: PatientService,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
    ) -> None:
        """Repo returns None when provider_id doesn't match — service must raise."""
        patient_repo.get_by_id.return_value = None
        other_patient_id = uuid.uuid4()

        with pytest.raises(PatientNotFoundError):
            await service.get_patient(other_patient_id, provider_id)


class TestListPatients:
    async def test_returns_all_patients_for_provider(
        self,
        service: PatientService,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
    ) -> None:
        patients = [_make_patient(provider_id), _make_patient(provider_id)]
        patient_repo.list_for_provider.return_value = patients

        result = await service.list_patients(provider_id)

        patient_repo.list_for_provider.assert_awaited_once_with(provider_id, 10, 0)
        assert len(result) == 2
        assert all(isinstance(r, PatientResponse) for r in result)

    async def test_returns_empty_list_when_no_patients(
        self,
        service: PatientService,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
    ) -> None:
        patient_repo.list_for_provider.return_value = []

        result = await service.list_patients(provider_id)

        assert result == []

    async def test_passes_pagination_params_to_repo(
        self,
        service: PatientService,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
    ) -> None:
        patient_repo.list_for_provider.return_value = []

        await service.list_patients(provider_id, limit=5, offset=20)

        patient_repo.list_for_provider.assert_awaited_once_with(provider_id, 5, 20)

    async def test_default_pagination_is_limit_10_offset_0(
        self,
        service: PatientService,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
    ) -> None:
        patient_repo.list_for_provider.return_value = []

        await service.list_patients(provider_id)

        _, limit, offset = patient_repo.list_for_provider.call_args.args
        assert limit == 10
        assert offset == 0
