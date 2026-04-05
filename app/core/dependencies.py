import logging
import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.constants import (
    ERR_INVALID_TOKEN,
    ERR_PROVIDER_NOT_FOUND,
    JWT_ALGORITHM,
    JWT_SUBJECT_CLAIM,
)
from app.core.database import AsyncSessionFactory, get_async_session
from app.integrations.insights import GroqInsightsGenerator, InsightsProvider, StubInsightsGenerator
from app.integrations.transcription import (
    GroqWhisperTranscriber,
    StubTranscriber,
    TranscriptionProvider,
)
from app.models.provider import Provider
from app.repositories.note import NoteRepository
from app.repositories.patient import PatientRepository
from app.repositories.provider import ProviderRepository
from app.repositories.session import SessionRepository
from app.services.note import NoteService
from app.services.patient import PatientService
from app.services.provider import ProviderService
from app.services.session import SessionService

logger = logging.getLogger(__name__)

security = HTTPBearer()


async def get_current_provider(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> Provider:
    """Decode Bearer JWT, extract provider_id, return Provider from DB."""
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
        provider_id = uuid.UUID(payload[JWT_SUBJECT_CLAIM])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        logger.warning("JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_INVALID_TOKEN,
        ) from exc

    provider = await ProviderRepository(db).get_by_id(provider_id)
    if provider is None:
        logger.warning("Token references unknown provider %s", provider_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_PROVIDER_NOT_FOUND,
        )
    return provider


def get_patient_service(db: Annotated[AsyncSession, Depends(get_async_session)]) -> PatientService:
    return PatientService(patient_repo=PatientRepository(db))


def get_note_service(db: Annotated[AsyncSession, Depends(get_async_session)]) -> NoteService:
    return NoteService(
        note_repo=NoteRepository(db),
        patient_repo=PatientRepository(db),
    )


def get_provider_service(
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> ProviderService:
    return ProviderService(
        provider_repo=ProviderRepository(db),
        patient_repo=PatientRepository(db),
        note_repo=NoteRepository(db),
    )


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return AsyncSessionFactory


def get_transcription_provider() -> TranscriptionProvider:
    if settings.GROQ_API_KEY:
        return GroqWhisperTranscriber(api_key=settings.GROQ_API_KEY)
    return StubTranscriber()


def get_insights_provider() -> InsightsProvider:
    if settings.GROQ_API_KEY:
        return GroqInsightsGenerator(api_key=settings.GROQ_API_KEY)
    return StubInsightsGenerator()


def get_session_service(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    transcription_provider: Annotated[TranscriptionProvider, Depends(get_transcription_provider)],
    insights_provider: Annotated[InsightsProvider, Depends(get_insights_provider)],
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> SessionService:
    return SessionService(
        session_repo=SessionRepository(db),
        patient_repo=PatientRepository(db),
        transcription_provider=transcription_provider,
        insights_provider=insights_provider,
        session_factory=session_factory,
    )
