from fastapi import FastAPI

from app.api.v1.router import router as v1_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Oasys Patient Notes API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(v1_router, prefix="/api/v1")

    return app


app = create_app()
