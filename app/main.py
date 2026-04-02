from fastapi import FastAPI, HTTPException, Request, status

from app.api.v1.router import router as v1_router
from app.core.exceptions import NoteNotFoundError, PatientNotFoundError, ProviderEmailConflictError


def create_app() -> FastAPI:
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

    @app.exception_handler(ProviderEmailConflictError)
    async def provider_email_conflict_handler(
        request: Request, exc: ProviderEmailConflictError
    ) -> None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(v1_router, prefix="/api/v1")

    return app


app = create_app()
