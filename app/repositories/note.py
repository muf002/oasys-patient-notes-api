import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note, NoteType
from app.schemas.note import NoteCreate


class NoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        patient_id: uuid.UUID,
        note_type: NoteType,
        content: str,
        session_date: date,
    ) -> Note:
        note = Note(
            id=uuid.uuid4(),
            patient_id=patient_id,
            note_type=note_type,
            content=content,
            session_date=session_date,
        )
        self._session.add(note)
        await self._session.flush()
        await self._session.refresh(note)
        return note

    async def get_by_id(self, note_id: uuid.UUID, patient_id: uuid.UUID) -> Note | None:
        result = await self._session.execute(
            select(Note).where(
                Note.id == note_id,
                Note.patient_id == patient_id,
                Note.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_patient(
        self,
        patient_id: uuid.UUID,
        note_type: NoteType | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[Note]:
        query = select(Note).where(
            Note.patient_id == patient_id,
            Note.deleted_at.is_(None),
        )
        if note_type is not None:
            query = query.where(Note.note_type == note_type)
        query = query.order_by(Note.session_date.desc()).limit(limit).offset(offset)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def update(
        self,
        note: Note,
        note_type: NoteType | None,
        content: str | None,
        session_date: date | None,
    ) -> Note:
        if note_type is not None:
            note.note_type = note_type
        if content is not None:
            note.content = content
        if session_date is not None:
            note.session_date = session_date
        await self._session.flush()
        await self._session.refresh(note)
        return note

    async def soft_delete(self, note: Note) -> None:
        note.deleted_at = datetime.now(UTC)
        await self._session.flush()

    async def bulk_create(
        self,
        patient_id: uuid.UUID,
        items: list[NoteCreate],
    ) -> list[Note]:
        notes = [
            Note(
                id=uuid.uuid4(),
                patient_id=patient_id,
                note_type=item.note_type,
                content=item.content,
                session_date=item.session_date,
            )
            for item in items
        ]
        self._session.add_all(notes)
        await self._session.flush()
        for note in notes:
            await self._session.refresh(note)
        return notes

    async def count_for_provider_patients(self, patient_ids: list[uuid.UUID]) -> int:
        if not patient_ids:
            return 0
        result = await self._session.execute(
            select(func.count())
            .select_from(Note)
            .where(
                Note.patient_id.in_(patient_ids),
                Note.deleted_at.is_(None),
            )
        )
        return result.scalar_one()
