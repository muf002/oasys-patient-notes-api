import logging

from fastapi import FastAPI, HTTPException, Request, status

from app.api.v1.router import router as v1_router
from app.core.exceptions import (
    InvalidCSVError,
    NoteNotFoundError,
    PatientNotFoundError,
    ProviderEmailConflictError,
    SessionNotFoundError,
)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:     %(name)s - %(message)s",
    )
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def create_app() -> FastAPI:
    _configure_logging()
    app = FastAPI(
        title="Oasys Patient Notes API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @app.exception_handler(PatientNotFoundError)
    async def patient_not_found_handler(request: Request, exc: PatientNotFoundError) -> None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    @app.exception_handler(NoteNotFoundError)
    async def note_not_found_handler(request: Request, exc: NoteNotFoundError) -> None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    @app.exception_handler(SessionNotFoundError)
    async def session_not_found_handler(request: Request, exc: SessionNotFoundError) -> None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    @app.exception_handler(ProviderEmailConflictError)
    async def provider_email_conflict_handler(
        request: Request, exc: ProviderEmailConflictError
    ) -> None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    @app.exception_handler(InvalidCSVError)
    async def invalid_csv_handler(request: Request, exc: InvalidCSVError) -> None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(v1_router, prefix="/api/v1")

    return app


app = create_app()
