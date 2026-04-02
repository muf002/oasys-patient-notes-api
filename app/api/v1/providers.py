from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_provider, get_provider_service
from app.models.provider import Provider
from app.schemas.provider import ProviderCreate, ProviderResponse, ProviderStatsResponse
from app.services.provider import ProviderService

router = APIRouter(prefix="/providers", tags=["providers"])


@router.post("", response_model=ProviderResponse, status_code=201)
async def create_provider(
    body: ProviderCreate,
    service: Annotated[ProviderService, Depends(get_provider_service)],
) -> ProviderResponse:
    """Bootstrap endpoint: create a provider and receive a lifetime JWT."""
    return await service.create_provider(name=body.name, email=body.email)


@router.get("/stats", response_model=ProviderStatsResponse)
async def get_provider_stats(
    service: Annotated[ProviderService, Depends(get_provider_service)],
    current_provider: Annotated[Provider, Depends(get_current_provider)],
) -> ProviderStatsResponse:
    return await service.get_stats(current_provider.id)
