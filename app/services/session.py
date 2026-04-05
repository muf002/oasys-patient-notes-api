import logging
import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import PatientNotFoundError, SessionNotFoundError
from app.integrations.insights import InsightsProvider
from app.integrations.transcription import TranscriptionProvider
from app.models.session import SessionStatus
from app.repositories.patient import PatientRepository
from app.repositories.session import SessionRepository
from app.schemas.session import SessionCreate, SessionResponse

logger = logging.getLogger(__name__)


class SessionService:
    def __init__(
        self,
        session_repo: SessionRepository,
        patient_repo: PatientRepository,
        transcription_provider: TranscriptionProvider,
        insights_provider: InsightsProvider,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_repo = session_repo
        self._patient_repo = patient_repo
        self._transcription_provider = transcription_provider
        self._insights_provider = insights_provider
        self._session_factory = session_factory

    async def _require_patient(self, patient_id: uuid.UUID, provider_id: uuid.UUID) -> None:
        """Raise PatientNotFoundError if patient doesn't belong to this provider."""
        patient = await self._patient_repo.get_by_id(patient_id, provider_id)
        if patient is None:
            raise PatientNotFoundError()

    async def create_session(
        self,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
        data: SessionCreate,
        filename: str,
    ) -> SessionResponse:
        await self._require_patient(patient_id, provider_id)
        audio_session = await self._session_repo.create(
            patient_id=patient_id,
            session_date=data.session_date,
            original_filename=filename,
        )
        # Commit immediately so the row is visible to the pipeline's own DB
        # connections (READ COMMITTED). BackgroundTasks run inside the request
        # lifecycle before the dependency-managed transaction commits.
        await self._session_repo.commit()
        return SessionResponse.model_validate(audio_session)

    async def get_session(
        self,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> SessionResponse:
        await self._require_patient(patient_id, provider_id)
        audio_session = await self._session_repo.get_by_id(session_id, patient_id)
        if audio_session is None:
            raise SessionNotFoundError()
        return SessionResponse.model_validate(audio_session)

    async def list_sessions(
        self,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
        status: SessionStatus | None = None,
    ) -> list[SessionResponse]:
        await self._require_patient(patient_id, provider_id)
        sessions = await self._session_repo.list_for_patient(patient_id, status)
        return [SessionResponse.model_validate(s) for s in sessions]

    async def run_pipeline(self, session_id: uuid.UUID, audio_bytes: bytes) -> None:
        await self._execute_pipeline(session_id, audio_bytes)

    async def _execute_pipeline(self, session_id: uuid.UUID, audio_bytes: bytes) -> None:
        # Tx 1: fetch session, PENDING → TRANSCRIBING
        logger.info("Executing pipeline for session %s", session_id)
        original_filename: str | None = None
        async with self._session_factory() as db:
            async with db.begin():
                repo = SessionRepository(db)
                session = await repo.get_by_id_internal(session_id)
                if session is None:
                    logger.error("Session not found for session %s", session_id)
                    return
                original_filename = session.original_filename
                await repo.update_status(session, SessionStatus.TRANSCRIBING)
        # ── no DB transaction held ──────────────────────────────────────────
        if original_filename is None:
            logger.error("Session %s has no original_filename — aborting pipeline", session_id)
            async with self._session_factory() as db:
                async with db.begin():
                    repo = SessionRepository(db)
                    session = await repo.get_by_id_internal(session_id)
                    if session:
                        await repo.set_failed(session, "Pipeline aborted: missing original filename")
            return
        try:
            transcript = await self._transcription_provider.transcribe(
                audio_bytes, original_filename
            )
            logger.info("Transcription successful for session %s", session_id)
        except Exception as exc:
            logger.exception("Transcription failed for session %s", session_id)
            async with self._session_factory() as db:
                async with db.begin():
                    repo = SessionRepository(db)
                    session = await repo.get_by_id_internal(session_id)
                    if session:
                        await repo.set_failed(session, f"Transcription failed: {exc}")
            return

        # Tx 2: save transcript → ANALYZING (single atomic write; transcript preserved even if LLM later fails)
        async with self._session_factory() as db:
            async with db.begin():
                repo = SessionRepository(db)
                session = await repo.get_by_id_internal(session_id)
                if session is None:
                    return
                await repo.update_transcript(session, transcript)
                await repo.update_status(session, SessionStatus.ANALYZING)
                logger.info("Transcript saved and status updated to ANALYZING for session %s", session_id)
        # ── no DB transaction held ──────────────────────────────────────────
        try:
            insights = await self._insights_provider.generate_insights(transcript)
        except Exception as exc:
            logger.exception("Insights generation failed for session %s", session_id)
            async with self._session_factory() as db:
                async with db.begin():
                    repo = SessionRepository(db)
                    session = await repo.get_by_id_internal(session_id)
                    if session:
                        # transcript already committed in Tx 2 — preserved
                        await repo.set_failed(session, f"Insights generation failed: {exc}")
            return

        # Tx 3: save insights, ANALYZING → COMPLETED
        async with self._session_factory() as db:
            async with db.begin():
                repo = SessionRepository(db)
                session = await repo.get_by_id_internal(session_id)
                if session is None:
                    return
                await repo.update_insights(session, insights.model_dump())
                await repo.update_status(session, SessionStatus.COMPLETED)
