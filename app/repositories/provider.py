import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider import Provider


class ProviderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, name: str, email: str) -> Provider:
        provider = Provider(id=uuid.uuid4(), name=name, email=email)
        self._session.add(provider)
        await self._session.flush()
        await self._session.refresh(provider)
        return provider

    async def get_by_id(self, provider_id: uuid.UUID) -> Provider | None:
        result = await self._session.execute(select(Provider).where(Provider.id == provider_id))
        return result.scalar_one_or_none()

    async def get_all(self) -> list[Provider]:
        result = await self._session.execute(select(Provider))
        return list(result.scalars().all())
