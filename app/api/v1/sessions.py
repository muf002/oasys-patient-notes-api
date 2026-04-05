import logging
import uuid
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import ValidationError

from app.core.config import settings
from app.core.dependencies import get_current_provider, get_session_service
from app.models.provider import Provider
from app.models.session import SessionStatus
from app.schemas.session import SessionCreate, SessionResponse
from app.services.session import SessionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/patients", tags=["sessions"])

_ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a"}
_CHUNK_SIZE = 1024 * 1024  # 1 MB


async def _read_audio_with_size_limit(audio_file: UploadFile, max_size_mb: int) -> bytes:
    max_bytes = max_size_mb * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while chunk := await audio_file.read(_CHUNK_SIZE):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Audio file exceeds {max_size_mb}MB limit",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/{patient_id}/sessions", response_model=SessionResponse, status_code=202)
async def upload_session(
    patient_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    audio_file: Annotated[UploadFile, File()],
    session_date: Annotated[date, Form()],
    service: Annotated[SessionService, Depends(get_session_service)],
    current_provider: Annotated[Provider, Depends(get_current_provider)],
) -> SessionResponse:
    logger.info("Uploading session for patient %s", patient_id)
    suffix = Path(audio_file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported audio format. Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )

    audio_bytes = await _read_audio_with_size_limit(audio_file, settings.AUDIO_MAX_SIZE_MB)

    try:
        data = SessionCreate(session_date=session_date)
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="session_date cannot be in the future",
        )

    response = await service.create_session(
        provider_id=current_provider.id,
        patient_id=patient_id,
        data=data,
        filename=audio_file.filename or "upload",
    )

    background_tasks.add_task(service.run_pipeline, response.id, audio_bytes)

    return response


@router.get("/{patient_id}/sessions", response_model=list[SessionResponse])
async def list_sessions(
    patient_id: uuid.UUID,
    service: Annotated[SessionService, Depends(get_session_service)],
    current_provider: Annotated[Provider, Depends(get_current_provider)],
    session_status: Annotated[SessionStatus | None, Query(alias="status")] = None,
) -> list[SessionResponse]:
    return await service.list_sessions(current_provider.id, patient_id, session_status)


@router.get("/{patient_id}/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    patient_id: uuid.UUID,
    session_id: uuid.UUID,
    service: Annotated[SessionService, Depends(get_session_service)],
    current_provider: Annotated[Provider, Depends(get_current_provider)],
) -> SessionResponse:
    return await service.get_session(current_provider.id, patient_id, session_id)
