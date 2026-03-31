import asyncio
from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from app.core.database import Base, get_async_session
from app.main import create_app

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
