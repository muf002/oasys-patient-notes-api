import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import AudioSession, SessionStatus


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        patient_id: uuid.UUID,
        session_date: date,
        original_filename: str,
    ) -> AudioSession:
        audio_session = AudioSession(
            id=uuid.uuid4(),
            patient_id=patient_id,
            session_date=session_date,
            original_filename=original_filename,
            status=SessionStatus.PENDING,
        )
        self._session.add(audio_session)
        await self._session.flush()
        await self._session.refresh(audio_session)
        return audio_session

    async def get_by_id(
        self, session_id: uuid.UUID, patient_id: uuid.UUID
    ) -> AudioSession | None:
        result = await self._session.execute(
            select(AudioSession).where(
                AudioSession.id == session_id,
                AudioSession.patient_id == patient_id,
                AudioSession.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id_internal(self, session_id: uuid.UUID) -> AudioSession | None:
        """Unscoped lookup for background task use — no patient_id filter."""
        result = await self._session.execute(
            select(AudioSession).where(AudioSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_for_patient(
        self, patient_id: uuid.UUID, status: SessionStatus | None = None
    ) -> list[AudioSession]:
        query = select(AudioSession).where(
            AudioSession.patient_id == patient_id,
            AudioSession.deleted_at.is_(None),
        )
        if status is not None:
            query = query.where(AudioSession.status == status)
        query = query.order_by(AudioSession.session_date.desc())
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def update_status(
        self, audio_session: AudioSession, status: SessionStatus
    ) -> AudioSession:
        audio_session.status = status
        await self._session.flush()
        await self._session.refresh(audio_session)
        return audio_session

    async def update_transcript(
        self, audio_session: AudioSession, transcript: str
    ) -> AudioSession:
        audio_session.transcript = transcript
        await self._session.flush()
        await self._session.refresh(audio_session)
        return audio_session

    async def update_insights(
        self, audio_session: AudioSession, insights_dict: dict[str, Any]
    ) -> AudioSession:
        audio_session.insights = insights_dict
        await self._session.flush()
        await self._session.refresh(audio_session)
        return audio_session

    async def set_failed(
        self, audio_session: AudioSession, error_message: str
    ) -> AudioSession:
        audio_session.status = SessionStatus.FAILED
        audio_session.error_message = error_message
        await self._session.flush()
        await self._session.refresh(audio_session)
        return audio_session

    async def soft_delete(self, audio_session: AudioSession) -> None:
        audio_session.deleted_at = datetime.now(UTC)
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()
