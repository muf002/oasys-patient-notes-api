# ── base ──────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONPATH=. \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# ── dev ───────────────────────────────────────────────────────────────────────
FROM base AS dev

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock* ./

# Install all dependencies including dev group
RUN uv sync --frozen

COPY . .

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── prod ──────────────────────────────────────────────────────────────────────
FROM base AS prod

COPY pyproject.toml uv.lock* ./

# Install only runtime dependencies (no dev group)
RUN uv sync --frozen --no-dev

COPY . .

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
