import asyncio
import json
import logging
import uuid
from pathlib import Path

import jwt
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.constants import JWT_ALGORITHM
from app.core.exceptions import ProviderEmailConflictError
from app.models.provider import Provider
from app.repositories.note import NoteRepository
from app.repositories.patient import PatientRepository
from app.repositories.provider import ProviderRepository
from app.schemas.provider import ProviderResponse, ProviderStatsResponse

logger = logging.getLogger(__name__)

TOKENS_FILE = Path("data/tokens.json")


def _generate_token(provider_id: uuid.UUID) -> str:
    """Generate a lifetime JWT for the given provider (no expiry)."""
    return jwt.encode(
        {"sub": str(provider_id)},
        settings.SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def _write_token(provider_name: str, provider_id: uuid.UUID, token: str) -> None:
    """Append or update a provider token in tokens.json."""
    TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, str] = {}
    if TOKENS_FILE.exists():
        try:
            data = json.loads(TOKENS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read existing tokens file %s — starting fresh", TOKENS_FILE)
            data = {}
    key = f"{provider_name} ({provider_id})"
    data[key] = token
    TOKENS_FILE.write_text(json.dumps(data, indent=2))


class ProviderService:
    def __init__(
        self,
        provider_repo: ProviderRepository,
        patient_repo: PatientRepository,
        note_repo: NoteRepository,
    ) -> None:
        self._provider_repo = provider_repo
        self._patient_repo = patient_repo
        self._note_repo = note_repo

    async def create_provider(self, name: str, email: str) -> ProviderResponse:
        try:
            provider: Provider = await self._provider_repo.create(name=name, email=email)
        except IntegrityError as err:
            logger.warning("Provider creation failed — email already registered: %s", email)
            raise ProviderEmailConflictError() from err
        token = _generate_token(provider.id)
        await asyncio.to_thread(_write_token, provider.name, provider.id, token)
        logger.info("Provider created: %s (%s)", provider.name, provider.id)
        return ProviderResponse(
            id=provider.id,
            name=provider.name,
            email=provider.email,
            api_token=token,
            created_at=provider.created_at,
        )

    async def get_stats(self, provider_id: uuid.UUID) -> ProviderStatsResponse:
        patient_ids = await self._patient_repo.get_ids_for_provider(provider_id)
        total_notes = await self._note_repo.count_for_provider_patients(patient_ids)
        return ProviderStatsResponse(
            total_patients=len(patient_ids),
            total_notes=total_notes,
        )
