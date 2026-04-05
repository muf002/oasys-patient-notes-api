import asyncio
import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Annotated
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from app.core.database import Base, get_async_session
from app.core.dependencies import get_current_provider, get_session_service
from app.integrations.insights import StubInsightsGenerator
from app.integrations.transcription import StubTranscriber
from app.main import create_app
from app.models.provider import Provider
from app.repositories.patient import PatientRepository
from app.repositories.session import SessionRepository
from app.services.session import SessionService

# ---------------------------------------------------------------------------
# Session-scoped: spin up a real PostgreSQL 16 container once per test session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    with PostgresContainer("postgres:16-alpine") as container:
        yield container


@pytest.fixture(scope="session")
def db_engine(postgres_container: PostgresContainer):  # type: ignore[no-untyped-def]
    """Create async engine from the testcontainer URL and run create_all once.

    NullPool is required here: the session-scoped engine uses asyncio.run() for
    setup/teardown which creates its own event loop. NullPool prevents connections
    from being held across different event loops (setup loop vs per-test loop).
    """
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    user = postgres_container.username
    password = postgres_container.password
    dbname = postgres_container.dbname

    url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}"
    async_engine = create_async_engine(url, echo=False, poolclass=NullPool)

    async def _create_tables() -> None:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create_tables())
    yield async_engine

    async def _dispose() -> None:
        await async_engine.dispose()

    asyncio.run(_dispose())


# ---------------------------------------------------------------------------
# Function-scoped: each test gets a fresh session that rolls back on teardown
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:  # type: ignore[no-untyped-def]
    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session, session.begin():
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Provider fixtures — create real Provider rows, no JWT involved
# ---------------------------------------------------------------------------


@pytest.fixture
async def provider_a(db_session: AsyncSession) -> Provider:
    provider = Provider(
        id=uuid.uuid4(),
        name="Dr. Alice",
        email=f"alice-{uuid.uuid4()}@test.com",
    )
    db_session.add(provider)
    await db_session.flush()
    await db_session.refresh(provider)
    return provider


@pytest.fixture
async def provider_b(db_session: AsyncSession) -> Provider:
    provider = Provider(
        id=uuid.uuid4(),
        name="Dr. Bob",
        email=f"bob-{uuid.uuid4()}@test.com",
    )
    db_session.add(provider)
    await db_session.flush()
    await db_session.refresh(provider)
    return provider


# ---------------------------------------------------------------------------
# Auth clients — bypass JWT entirely; inject Provider directly via DI override
# ---------------------------------------------------------------------------


def _make_auth_client(
    db_session: AsyncSession, provider: Provider
) -> AsyncGenerator[AsyncClient, None]:
    async def _gen() -> AsyncGenerator[AsyncClient, None]:
        app = create_app()

        async def _override_db() -> AsyncGenerator[AsyncSession, None]:
            yield db_session

        app.dependency_overrides[get_async_session] = _override_db
        app.dependency_overrides[get_current_provider] = lambda: provider

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client

        app.dependency_overrides.clear()

    return _gen()


@pytest.fixture
async def auth_client_a(
    db_session: AsyncSession, provider_a: Provider
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _make_auth_client(db_session, provider_a):
        yield client


@pytest.fixture
async def auth_client_b(
    db_session: AsyncSession, provider_b: Provider
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _make_auth_client(db_session, provider_b):
        yield client


# ---------------------------------------------------------------------------
# Stub fixtures — deterministic providers for integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_transcriber() -> StubTranscriber:
    return StubTranscriber()


@pytest.fixture
def stub_insights_generator() -> StubInsightsGenerator:
    return StubInsightsGenerator()


# ---------------------------------------------------------------------------
# auth_client_a_with_stubs — real SessionService with stubs + suppressed pipeline
# ---------------------------------------------------------------------------


@pytest.fixture
async def auth_client_a_with_stubs(
    db_session: AsyncSession,
    db_engine,
    provider_a: Provider,  # type: ignore[no-untyped-def]
) -> AsyncGenerator[AsyncClient, None]:
    """Provider A client with stub providers and run_pipeline suppressed via AsyncMock.

    Background task execution is suppressed so integration tests verify HTTP contracts
    only (202, PENDING state, list/get responses) without pipeline side effects.
    """
    test_session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    def _override_session_service(
        db: Annotated[AsyncSession, Depends(get_async_session)],
    ) -> SessionService:
        session_repo = SessionRepository(db)
        session_repo.commit = AsyncMock()  # type: ignore[method-assign]
        service = SessionService(
            session_repo=session_repo,
            patient_repo=PatientRepository(db),
            transcription_provider=StubTranscriber(),
            insights_provider=StubInsightsGenerator(),
            session_factory=test_session_factory,
        )
        service.run_pipeline = AsyncMock()  # type: ignore[method-assign]
        return service

    app.dependency_overrides[get_async_session] = _override_db
    app.dependency_overrides[get_current_provider] = lambda: provider_a
    app.dependency_overrides[get_session_service] = _override_session_service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Generic unauthenticated client (for health check, provider creation tests)
# ---------------------------------------------------------------------------


@pytest.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_async_session] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()
