import uuid

from app.core.exceptions import PatientNotFoundError
from app.repositories.patient import PatientRepository
from app.schemas.patient import PatientResponse


class PatientService:
    def __init__(self, patient_repo: PatientRepository) -> None:
        self._patient_repo = patient_repo

    async def create_patient(
        self, provider_id: uuid.UUID, first_name: str, last_name: str
    ) -> PatientResponse:
        patient = await self._patient_repo.create(
            provider_id=provider_id,
            first_name=first_name,
            last_name=last_name,
        )
        return PatientResponse.model_validate(patient)

    async def get_patient(
        self, patient_id: uuid.UUID, provider_id: uuid.UUID
    ) -> PatientResponse:
        patient = await self._patient_repo.get_by_id(patient_id, provider_id)
        if patient is None:
            raise PatientNotFoundError()
        return PatientResponse.model_validate(patient)

    async def list_patients(self, provider_id: uuid.UUID) -> list[PatientResponse]:
        patients = await self._patient_repo.list_for_provider(provider_id)
        return [PatientResponse.model_validate(p) for p in patients]
