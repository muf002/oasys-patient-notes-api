import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient


class PatientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, provider_id: uuid.UUID, first_name: str, last_name: str) -> Patient:
        patient = Patient(
            id=uuid.uuid4(),
            provider_id=provider_id,
            first_name=first_name,
            last_name=last_name,
        )
        self._session.add(patient)
        await self._session.flush()
        await self._session.refresh(patient)
        return patient

    async def get_by_id(self, patient_id: uuid.UUID, provider_id: uuid.UUID) -> Patient | None:
        result = await self._session.execute(
            select(Patient).where(
                Patient.id == patient_id,
                Patient.provider_id == provider_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_provider(
        self, provider_id: uuid.UUID, limit: int = 10, offset: int = 0
    ) -> list[Patient]:
        result = await self._session.execute(
            select(Patient)
            .where(Patient.provider_id == provider_id)
            .order_by(Patient.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_ids_for_provider(self, provider_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self._session.execute(
            select(Patient.id).where(Patient.provider_id == provider_id)
        )
        return list(result.scalars().all())

