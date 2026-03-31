# Oasys Patient Notes API — Initial Architecture Plan

## Context
This is a take-home assessment for Oasys Health. The goal of this phase is to establish the full project foundation before building any features. This includes project structure, tooling, Docker setup, database setup, Alembic migrations, testing infrastructure, and GitHub repository initialization. No feature code is written in this phase.

---

## Stack Decisions
| Concern | Choice | Reason |
|---|---|---|
| Python | 3.12 | Stable, better perf than 3.11, good library support |
| Package manager | `uv` | Used internally at Oasys, fastest, modern |
| Web framework | FastAPI | Required |
| Validation | Pydantic v2 | Required |
| Database | PostgreSQL 16 | Required |
| ORM | SQLAlchemy 2.0 (async) + asyncpg | First-class async, industry standard, repo pattern fits well |
| Server | uvicorn | ASGI server for FastAPI; `uvicorn[standard]` for hot reload support |
| Migrations | Alembic | Production best practice, bonus credit |
| Test DB | testcontainers[postgres] | Real PostgreSQL 16 for integration tests; spins up via Docker (already a project dependency), tears down automatically; required for JSONB fidelity on LLM insights storage |
| Testing | pytest + pytest-asyncio + pytest-mock + httpx + testcontainers[postgres] | Standard, composable; httpx required for AsyncClient in conftest; testcontainers for real PG integration tests |
| Lint/Format | ruff | Replaces black + isort + flake8 in one tool |
| Type checking | mypy | Required for type safety signal |
| Config | pydantic-settings | Type-safe env var management, integrates with Pydantic |

**pytest-asyncio config:** `asyncio_mode = "auto"` must be set under `[tool.pytest.ini_options]` in `pyproject.toml`. Without it, async test functions and async fixtures in conftest silently fail or require manual `@pytest.mark.asyncio` decorators on every test.

**Trade-off to document in README:** `testcontainers` requires Docker to run tests, but Docker is already a project dependency for `make run`. The container starts once per session (~3–5s overhead), and per-test isolation is achieved via transaction rollbacks rather than truncation — keeping individual tests fast. This gives full PostgreSQL 16 fidelity including JSONB, which is required for LLM insights storage.

---

## Project Structure

```
oasys-patient-notes-api/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app factory (create_app())
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py            # pydantic-settings: Settings class
│   │   ├── database.py          # Async engine, session factory, Base
│   │   └── dependencies.py      # FastAPI DI: get_db, get_current_provider
│   ├── models/                  # SQLAlchemy ORM models (DB layer)
│   │   └── __init__.py
│   ├── schemas/                 # Pydantic request/response schemas (API layer)
│   │   └── __init__.py
│   ├── repositories/            # Async DB access (no business logic)
│   │   └── __init__.py
│   ├── services/                # Business logic (no HTTP, no DB)
│   │   └── __init__.py
│   └── api/
│       ├── __init__.py
│       └── v1/
│           ├── __init__.py
│           └── router.py        # Mounts all v1 endpoint routers
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Shared fixtures: app, async client, test DB session
│   ├── unit/                    # Service logic tests (mocked repos, no DB)
│   │   └── __init__.py
│   └── integration/             # API endpoint tests (real PostgreSQL 16 via testcontainers)
│       └── __init__.py
├── alembic/
│   ├── env.py                   # Alembic async env config
│   ├── script.py.mako
│   └── versions/                # Migration files
├── alembic.ini
├── docker-compose.yml           # app + postgres services
├── Dockerfile                   # Multi-stage: dev + prod targets
├── pyproject.toml               # All deps, ruff config, mypy config, pytest config
├── Makefile                     # test, lint, typecheck, run, migrate commands
├── .env.example                 # Template for required env vars
├── .gitignore
└── README.md
```

---

## Layer Responsibilities

| Layer | Location | Responsibility |
|---|---|---|
| API | `app/api/` | HTTP routing, request parsing, response serialization |
| Service | `app/services/` | Business logic, orchestration, domain rules |
| Repository | `app/repositories/` | All DB queries via SQLAlchemy AsyncSession |
| Models | `app/models/` | SQLAlchemy ORM table definitions |
| Schemas | `app/schemas/` | Pydantic input/output models (separate from ORM models) |
| Core | `app/core/` | Config, DB setup, shared dependencies |

**Import style:** `from app.core.config import settings` — clean, no `src.` prefix.

**`PYTHONPATH` requirement:** Bare `app.` imports only resolve if the project root is on the Python path. Set `pythonpath = ["."]` under `[tool.pytest.ini_options]` in `pyproject.toml` for tests, and ensure `PYTHONPATH=.` is set in the Docker environment and Makefile where needed.

**Key principle:** Services depend on repository interfaces (not implementations) — this is what makes unit testing possible without a real DB.

---

## Database Setup

- `app/core/database.py` — creates async engine from `DATABASE_URL` env var, provides `AsyncSession` factory, exposes `Base` (declarative base for all models)
- Alembic configured to use async engine (`run_async_migrations` pattern)
- `alembic/env.py` imports `Base.metadata` from `app/core/database.py` for autogenerate support
- Initial migration created for the base schema (empty, just proves the pipeline works)

---

## Configuration (`app/core/config.py`)

```python
# pydantic-settings Settings class
class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ENVIRONMENT: str = "development"
    # AI/audio keys added later
    # Note: test DATABASE_URL is injected dynamically by testcontainers — no static TEST_DATABASE_URL needed

    model_config = SettingsConfig(env_file=".env")
```

---

## Docker Setup

**`Dockerfile`** — multi-stage:
- `base` stage: Python 3.12-slim, installs uv; sets `ENV PYTHONPATH=.`
- `dev` stage: installs all deps including dev, mounts source via volume, runs with `--reload`
- `prod` stage: installs only runtime deps, runs with uvicorn

**`docker-compose.yml`:**
- `db` service: `postgres:16-alpine`, persistent volume, healthcheck
- `app` service: builds from `Dockerfile` dev target, depends on `db` healthcheck, mounts `app/` as volume for hot reload, reads `.env` file

`docker compose up` → app running at `http://localhost:8000`, Postgres at `localhost:5432`

---

## Testing Infrastructure (`tests/conftest.py`)

```
Fixtures:
- postgres_container  — session-scoped; spins up PostgreSQL 16 via testcontainers, tears down after session
- engine              — session-scoped; creates async engine from container URL, runs create_all once
- db_session          — function-scoped; AsyncSession per test, rolls back after each test (no truncation needed)
- async_client        — httpx AsyncClient with app mounted, injects test db_session via dependency_overrides
```

Container starts once per test session (~3–5s), each test rolls back its transaction — fast and fully isolated.

**Schema strategy:** `engine` fixture uses `create_all` (SQLAlchemy models directly), not Alembic migrations. Tests verify behavior, not migration history. A dedicated `test_migrations_in_sync` test runs `alembic check` to catch any drift between models and migration files — this is the only place migrations are verified, keeping the rest of the test suite fast.

Unit tests: import service classes directly, inject mock repositories via pytest-mock — no DB, no HTTP.

Integration tests: use `async_client` fixture — full request/response cycle against real PostgreSQL 16.

---

## Makefile Commands

```makefile
make run         # docker compose up
make down        # docker compose down
make shell       # docker compose exec app bash
make test        # pytest tests/
make lint        # ruff check . && ruff format --check .
make format      # ruff format .
make typecheck   # mypy app/
make migrate     # alembic upgrade head
make migration   # alembic revision --autogenerate -m "$(name)"
```

---

## GitHub Repository Setup

Steps:
1. `git init` in project root
2. Create `.gitignore` (Python, uv, .env, __pycache__, .mypy_cache, etc.)
3. Initial commit: "chore: initial project scaffold"
4. Create public repo `oasys-patient-notes-api` on GitHub
5. Push with `git remote add origin` + `git push -u origin main`
6. Commit strategy going forward: incremental, feature-scoped commits

---

## Environment Variables (`.env.example`)

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/oasys
SECRET_KEY=changeme
ENVIRONMENT=development
# Added in Feature 2:
# OPENAI_API_KEY=
# ANTHROPIC_API_KEY=
```

---

## What IS Done in This Phase
- Project scaffold: all directories, `__init__.py` files, `pyproject.toml`, `Makefile`, `.gitignore`, `.env.example`
- `app/core/config.py` — `Settings` class with `DATABASE_URL`, `SECRET_KEY`, `ENVIRONMENT`
- `app/core/database.py` — async engine, `AsyncSession` factory, `Base`
- `app/core/dependencies.py` — skeleton `get_db` and `get_current_provider` stubs
- `app/main.py` — `create_app()` factory, mounts v1 router, includes `/health` endpoint returning `{"status": "ok"}`
- `Dockerfile` — multi-stage dev/prod with `PYTHONPATH=.`
- `docker-compose.yml` — `app` + `db` services
- Alembic init — `alembic.ini`, `alembic/env.py` wired to async engine, first empty migration
- `tests/conftest.py` — all fixtures: `postgres_container`, `engine` (create_all), `db_session`, `async_client`
- `tests/test_migrations_in_sync.py` — runs `alembic check` to catch model/migration drift
- GitHub repo created, initial commit pushed

## What Is NOT Done in This Phase
- No feature endpoints (patients, notes, sessions)
- No ORM models beyond what's needed to verify Alembic works
- No auth logic (just skeleton stubs)
- No AI/audio pipeline

---

## Verification Steps
1. `docker compose up` — app boots, hits `/health` endpoint, returns 200
2. `make migrate` — Alembic runs successfully against the Postgres container
3. `make test` — pytest discovers and runs (0 tests, no failures)
4. `make lint` — ruff passes with no errors
5. `make typecheck` — mypy passes with no errors
6. GitHub repo created, initial commit pushed
