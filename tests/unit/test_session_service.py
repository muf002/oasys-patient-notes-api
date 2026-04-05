"""Unit tests for SessionService — mocked repos, no DB, no HTTP."""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import PatientNotFoundError, SessionNotFoundError
from app.integrations.insights import StubInsightsGenerator
from app.integrations.transcription import StubTranscriber
from app.models.patient import Patient
from app.models.session import AudioSession, SessionStatus
from app.schemas.session import SessionCreate
from app.services.session import SessionService


def _make_patient(provider_id: uuid.UUID | None = None) -> Patient:
    p = Patient()
    p.id = uuid.uuid4()
    p.provider_id = provider_id or uuid.uuid4()
    p.first_name = "John"
    p.last_name = "Doe"
    p.created_at = datetime.now(UTC)
    return p


def _make_audio_session(patient_id: uuid.UUID | None = None) -> AudioSession:
    s = AudioSession()
    s.id = uuid.uuid4()
    s.patient_id = patient_id or uuid.uuid4()
    s.session_date = date(2024, 1, 15)
    s.original_filename = "recording.wav"
    s.status = SessionStatus.PENDING
    s.transcript = None
    s.insights = None
    s.error_message = None
    s.created_at = datetime.now(UTC)
    s.updated_at = datetime.now(UTC)
    s.deleted_at = None
    return s


@pytest.fixture
def provider_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def patient_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def session_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def patient_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_repo() -> AsyncMock:
    """Shared repo mock — returned by patched SessionRepository inside _execute_pipeline."""
    return AsyncMock()


@pytest.fixture
def mock_session_factory(mock_repo: AsyncMock):  # type: ignore[no-untyped-def]
    """Async context manager factory whose db.begin() is also an async context manager."""
    mock_db = MagicMock()

    @asynccontextmanager  # type: ignore[arg-type]
    async def _begin():  # type: ignore[no-untyped-def]
        yield

    mock_db.begin = _begin

    @asynccontextmanager  # type: ignore[arg-type]
    async def _factory():  # type: ignore[no-untyped-def]
        yield mock_db

    return _factory


def _make_pipeline_session_mock() -> MagicMock:
    m = MagicMock()
    m.original_filename = "test.wav"
    return m


class TestCreateSession:
    async def test_creates_session_for_owned_patient(
        self,
        session_repo: AsyncMock,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> None:
        patient_repo.get_by_id.return_value = _make_patient(provider_id)
        expected = _make_audio_session(patient_id)
        session_repo.create.return_value = expected

        service = SessionService(
            session_repo=session_repo,
            patient_repo=patient_repo,
            transcription_provider=StubTranscriber(),
            insights_provider=StubInsightsGenerator(),
            session_factory=MagicMock(),
        )
        data = SessionCreate(session_date=date(2024, 1, 15))
        result = await service.create_session(provider_id, patient_id, data, "recording.wav")

        patient_repo.get_by_id.assert_awaited_once_with(patient_id, provider_id)
        session_repo.create.assert_awaited_once()
        assert result.id == expected.id

    async def test_raises_patient_not_found_for_unowned_patient(
        self,
        session_repo: AsyncMock,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> None:
        patient_repo.get_by_id.return_value = None

        service = SessionService(
            session_repo=session_repo,
            patient_repo=patient_repo,
            transcription_provider=StubTranscriber(),
            insights_provider=StubInsightsGenerator(),
            session_factory=MagicMock(),
        )
        data = SessionCreate(session_date=date(2024, 1, 15))
        with pytest.raises(PatientNotFoundError):
            await service.create_session(provider_id, patient_id, data, "recording.wav")


class TestGetSession:
    async def test_returns_session(
        self,
        session_repo: AsyncMock,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> None:
        patient_repo.get_by_id.return_value = _make_patient(provider_id)
        expected = _make_audio_session(patient_id)
        session_repo.get_by_id.return_value = expected

        service = SessionService(
            session_repo=session_repo,
            patient_repo=patient_repo,
            transcription_provider=StubTranscriber(),
            insights_provider=StubInsightsGenerator(),
            session_factory=MagicMock(),
        )
        result = await service.get_session(provider_id, patient_id, expected.id)
        assert result.id == expected.id

    async def test_raises_session_not_found(
        self,
        session_repo: AsyncMock,
        patient_repo: AsyncMock,
        provider_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> None:
        patient_repo.get_by_id.return_value = _make_patient(provider_id)
        session_repo.get_by_id.return_value = None

        service = SessionService(
            session_repo=session_repo,
            patient_repo=patient_repo,
            transcription_provider=StubTranscriber(),
            insights_provider=StubInsightsGenerator(),
            session_factory=MagicMock(),
        )
        with pytest.raises(SessionNotFoundError):
            await service.get_session(provider_id, patient_id, uuid.uuid4())


class TestExecutePipeline:
    async def test_successful_pipeline_reaches_completed(
        self,
        mock_repo: AsyncMock,
        mock_session_factory: MagicMock,
    ) -> None:
        mock_repo.get_by_id_internal.return_value = _make_pipeline_session_mock()

        service = SessionService(
            session_repo=AsyncMock(),
            patient_repo=AsyncMock(),
            transcription_provider=StubTranscriber(),
            insights_provider=StubInsightsGenerator(),
            session_factory=mock_session_factory,
        )
        with patch("app.services.session.SessionRepository", return_value=mock_repo):
            await service._execute_pipeline(uuid.uuid4(), b"audio data")

        statuses = [call.args[1] for call in mock_repo.update_status.call_args_list]
        assert statuses == [
            SessionStatus.TRANSCRIBING,
            SessionStatus.ANALYZING,
            SessionStatus.COMPLETED,
        ]

    async def test_transcription_failure_sets_failed_status(
        self,
        mock_repo: AsyncMock,
        mock_session_factory: MagicMock,
    ) -> None:
        mock_repo.get_by_id_internal.return_value = _make_pipeline_session_mock()

        failing_transcriber = AsyncMock()
        failing_transcriber.transcribe.side_effect = ValueError("network error")

        service = SessionService(
            session_repo=AsyncMock(),
            patient_repo=AsyncMock(),
            transcription_provider=failing_transcriber,
            insights_provider=StubInsightsGenerator(),
            session_factory=mock_session_factory,
        )
        with patch("app.services.session.SessionRepository", return_value=mock_repo):
            await service._execute_pipeline(uuid.uuid4(), b"audio data")

        mock_repo.set_failed.assert_awaited_once()
        error_msg = mock_repo.set_failed.call_args.args[1]
        assert error_msg.startswith("Transcription failed:")

    async def test_insights_failure_preserves_transcript(
        self,
        mock_repo: AsyncMock,
        mock_session_factory: MagicMock,
    ) -> None:
        mock_repo.get_by_id_internal.return_value = _make_pipeline_session_mock()

        service = SessionService(
            session_repo=AsyncMock(),
            patient_repo=AsyncMock(),
            transcription_provider=StubTranscriber(),
            insights_provider=StubInsightsGenerator(raises=ValueError("rate limited")),
            session_factory=mock_session_factory,
        )
        with patch("app.services.session.SessionRepository", return_value=mock_repo):
            await service._execute_pipeline(uuid.uuid4(), b"audio data")

        # Tx 2 committed the transcript before LLM failure
        mock_repo.update_transcript.assert_awaited()
        mock_repo.set_failed.assert_awaited_once()
        error_msg = mock_repo.set_failed.call_args.args[1]
        assert error_msg.startswith("Insights generation failed:")

    async def test_insights_failure_records_specific_error_message(
        self,
        mock_repo: AsyncMock,
        mock_session_factory: MagicMock,
    ) -> None:
        mock_repo.get_by_id_internal.return_value = _make_pipeline_session_mock()

        service = SessionService(
            session_repo=AsyncMock(),
            patient_repo=AsyncMock(),
            transcription_provider=StubTranscriber(),
            insights_provider=StubInsightsGenerator(raises=ValueError("quota exceeded")),
            session_factory=mock_session_factory,
        )
        with patch("app.services.session.SessionRepository", return_value=mock_repo):
            await service._execute_pipeline(uuid.uuid4(), b"audio data")

        error_msg = mock_repo.set_failed.call_args.args[1]
        assert "quota exceeded" in error_msg
