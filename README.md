# Oasys Patient Notes API

A Python backend that models a simplified patient notes system with provider-scoped access, and includes an audio-to-insights pipeline that transcribes session recordings and generates AI-powered clinical analysis.

---

## Setup Guide

### Prerequisites

- Docker and Docker Compose

### Running the project

1. Copy the example environment file and fill in your values:
   ```bash
   cp .env.example .env
   ```

2. Start the app and database:
   ```bash
   make run
   ```

   The API will be available at `http://localhost:8000`.
   Interactive docs at `http://localhost:8000/docs`.

3. Run database migrations (requires the stack to be running):
   ```bash
   make migrate
   ```

4. To stop the stack:
   ```bash
   make down
   ```

---

## Available Commands

| Command | Description |
|---|---|
| `make run` | Start app + database via Docker Compose |
| `make down` | Stop and remove containers |
| `make shell` | Open a shell inside the app container |
| `make test` | Run the test suite |
| `make lint` | Check code style with ruff |
| `make format` | Auto-format code with ruff |
| `make typecheck` | Run mypy static analysis |
| `make migrate` | Apply pending Alembic migrations |
| `make migration name=<msg>` | Generate a new Alembic migration |

---

## Architecture Overview

The codebase is organized into four explicit layers, each with a single responsibility:

```
HTTP Request
    → Router (app/api/v1/)       — parse input, call service, return response
    → Service (app/services/)    — business logic, owns cross-entity rules
    → Repository (app/repositories/) — DB access only, no business logic
    → ORM Model (app/models/)    — schema definition
```

**Request flow example — `PATCH /api/v1/patients/{patient_id}/notes/{note_id}`:**

1. FastAPI parses the request body into a `NoteUpdate` Pydantic model (validation happens here)
2. `get_current_provider` dependency decodes the Bearer JWT, looks up the `Provider` row, and injects it
3. The router calls `NoteService.update_note(provider_id, patient_id, note_id, data)`
4. The service first calls `PatientRepository.get_by_id(patient_id, provider_id)` — if the patient doesn't belong to this provider, it raises `PatientNotFoundError` (translated to 404 by a global exception handler in `main.py`). This is the cross-provider isolation gate.
5. The service calls `NoteRepository.get_by_id(note_id, patient_id)` — raises `NoteNotFoundError` if not found
6. The service calls `NoteRepository.update(note, ...)` which applies only the non-None fields and flushes
7. The session's `begin()` context manager in `get_async_session` commits on clean exit
8. The router returns the updated `NoteResponse`

**Key design decisions:**

- **Explicit dependencies** — services receive repos via constructor injection; routers receive services via FastAPI `Depends`. Nothing is imported globally or looked up.
- **Domain exceptions** — services raise `PatientNotFoundError` / `NoteNotFoundError` (plain Python exceptions). Global handlers in `main.py` translate these to HTTP responses. The service layer has no FastAPI imports.
- **Cross-provider isolation** — every patient lookup includes `provider_id` as a WHERE condition. A provider can never retrieve, modify, or delete another provider's data — even if they know the UUID — because the query simply returns nothing.
- **Soft delete** — `Note.deleted_at` is set to the current timestamp rather than physically deleting the row. All queries filter `deleted_at IS NULL`.
- **Bulk partial failure** — `POST /notes/bulk` accepts `list[dict]` rather than `list[NoteCreate]`, so Pydantic does not validate individual items at the HTTP boundary. The service validates each item individually and returns a 207 with separate `created` and `failed` lists.
- **Async throughout** — SQLAlchemy async engine with `asyncpg`, all repository and service methods are `async def`.
- **Token management** — `POST /api/v1/providers` is an unauthenticated bootstrap endpoint. It creates a provider and returns a lifetime JWT signed with `SECRET_KEY`. Tokens are also persisted to `data/tokens.json` for local development convenience.

---

## API Documentation

Auto-generated docs are available at `/docs` (Swagger UI) and `/redoc` when the server is running.

---

## AI & Audio Pipeline Details

_To be completed in Feature 2._

---

## Testing Strategy

Tests are split into two layers:

- **Unit tests** (`tests/unit/`) — test service/business logic in isolation using mocked repositories. No database, no HTTP.
- **Integration tests** (`tests/integration/`) — test full request/response cycles against a real PostgreSQL 16 instance spun up automatically via `testcontainers`.

Run all tests with:
```bash
make test
```

---

## Challenges & Trade-offs

**Bulk partial failure and Pydantic validation boundary**
The natural instinct is to use `list[NoteCreate]` in `BulkNoteCreate`, which gives clean OpenAPI docs and automatic validation. But Pydantic validates the entire list atomically — one invalid item rejects the whole request with 422, making 207 partial success unreachable. The fix is to accept `list[dict[str, Any]]` at the HTTP boundary and validate each item individually in the service. The trade-off is a less descriptive OpenAPI schema for the bulk endpoint's input; documented via `json_schema_extra` to compensate.

**Transaction commit placement**
SQLAlchemy's async session context manager calls `session.close()` on exit, which rolls back any uncommitted transaction. Repositories use `flush()` (not `commit()`) to write within the current transaction and get server-generated values back. The commit must happen at the request boundary, not inside individual repo methods — otherwise a multi-step service operation (e.g. verify patient → create note) would commit after the first step. The solution is wrapping the yielded session in `async with session.begin()` inside `get_async_session`, which auto-commits on clean exit and auto-rolls back on exception.

**Timezone-aware datetimes**
All timestamp columns use `TIMESTAMP WITH TIME ZONE` (`DateTime(timezone=True)` in SQLAlchemy). This avoids the common bug of storing timezone-naive datetimes and later being unable to reason about them in a multi-timezone context. The `onupdate` on `Note.updated_at` uses a Python-side callable (`lambda: datetime.now(UTC)`) rather than a server-side `func.now()`, so the ORM fires it automatically on attribute mutations and the updated value is reflected in the Python object without an extra `refresh()`.

**Testing without a real auth flow**
Integration tests bypass JWT entirely by overriding `get_current_provider` via `app.dependency_overrides`. This keeps tests fast and isolated from token generation details, but means the real JWT decode path is not exercised by the integration suite. A dedicated auth integration test (valid token, malformed token, unknown provider) covers that gap separately.

**`data/tokens.json` as a dev convenience**
Storing tokens in a file is intentionally a development convenience, not a production auth store. In production, providers would authenticate through a proper identity system and tokens would not be written to disk. The file is excluded from git via `.gitignore`.
