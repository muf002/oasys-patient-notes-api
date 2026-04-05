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

### Model choices

**Transcription: Groq Whisper (`whisper-large-v3-turbo`)** — free-tier Groq platform, OpenAI-compatible SDK, 25 MB file size limit, fast inference. **LLM: Groq LLaMA 3.3 70B (`llama-3.3-70b-versatile`)** — same free-tier Groq account, supports `response_format={"type": "json_object"}` for guaranteed JSON output, sufficient context window for long transcripts. A single `GROQ_API_KEY` covers both services. The Protocol abstraction (`TranscriptionProvider`, `InsightsProvider`) means swapping to OpenAI Whisper + GPT-4o later is a one-file change.

### Prompt design

The system prompt forces clinically specific output, not generic summaries. Key rules baked into the prompt:
- `key_themes`: must be specific (e.g. `"occupational stressor: hostile manager"`, not `"work stress"`)
- `risk_indicators`: evidence-based only — conservative flagging, no speculation from ambiguous statements; empty array if none found
- `recommended_followups`: concrete and actionable (e.g. `"Explore avoidance behaviors around family conflict"`), not `"continue therapy"`
- `session_summary`: third-person clinical narrative, no diagnosis

JSON mode at the API call level (`response_format={"type": "json_object"}`) combined with `ClinicalInsights.model_validate_json()` guarantees parseable structured output. Tenacity retries on `RateLimitError` or `ValidationError` (up to 3 attempts, exponential backoff 2–10 s).

### Async pipeline with 202 polling

`POST /sessions` → immediately returns 202 with `status=pending`. FastAPI `BackgroundTasks` runs the pipeline after the response is sent. Clients poll `GET /sessions/{id}` for status changes (`pending → transcribing → analyzing → completed` or `failed`).

**Trade-off:** `BackgroundTasks` has no built-in retry — if the server restarts mid-pipeline, the task is lost and the session stays stuck in `transcribing`/`analyzing`. Production would use Celery + Redis or ARQ. For this assessment, `BackgroundTasks` is the right call: zero extra infrastructure, no broker, and the pipeline completes in seconds. Transient rate limits are handled by `tenacity` retries inside the provider before any exception reaches the pipeline.

### Pipeline state machine and transcript preservation

```
PENDING → TRANSCRIBING → [Groq Whisper] → ANALYZING → [Groq LLaMA] → COMPLETED
                       ↘ FAILED                     ↘ FAILED (transcript already committed)
```

Each state transition is its own DB transaction, committed and closed **before** the next external API call. No DB transaction is ever held open during a Groq API call. If the LLM step fails, `FAILED` is recorded but the transcript from Tx 2 is already committed and preserved in the database — the client can still read it.

### No audio file persistence

Audio bytes are read in the route handler, passed to the background task as `bytes`, then discarded. Only the transcript and insights are stored. **Trade-off:** if transcription fails, the client must re-upload. For a production clinical system, audio would be stored durably since session recordings are irreproducible. For this assessment, the simpler approach keeps the focus on pipeline architecture.

### Content-type validation

Only the file extension is validated (`.wav`, `.mp3`, `.m4a`) — not the `Content-Type` header. Extension spoofing is therefore possible. Accepted as a simplification trade-off.

### Stub providers and auto-fallback

`StubTranscriber` and `StubInsightsGenerator` are deterministic stubs used in two ways:
1. **Auto-fallback** — when `GROQ_API_KEY` is absent, `get_transcription_provider` and `get_insights_provider` return the stubs automatically. The app runs in any environment without a Groq account.
2. **Integration tests** — stubs are injected directly, and `run_pipeline` is replaced with `AsyncMock()` to suppress background task execution entirely. Integration tests verify only HTTP contracts; pipeline logic is covered by unit tests with mocked repos.

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
