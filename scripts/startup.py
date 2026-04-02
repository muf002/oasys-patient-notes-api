"""
Startup script — runs before uvicorn on every container start.

Steps:
  1. Run Alembic migrations (upgrade head) programmatically.
  2. Check if the providers table already has data.
     - If seeded and tokens.json exists  → skip.
     - If seeded but tokens.json missing → regenerate tokens from existing providers.
     - If empty                          → insert seed data + generate tokens.
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path

# Ensure project root is on sys.path when run directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt  # noqa: E402, I001
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

# Use a dedicated handler with propagate=False so that alembic's fileConfig
# (which sets the root logger level to WARN) doesn't silence our INFO logs.
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
log.addHandler(_handler)
log.propagate = False

TOKENS_FILE = Path("data/tokens.json")

SEED_PROVIDERS = [
    {"name": "Dr. Alice Smith", "email": "alice@oasys.health"},
    {"name": "Dr. Bob Jones", "email": "bob@oasys.health"},
]

SEED_PATIENTS: dict[str, list[dict[str, str]]] = {
    "alice@oasys.health": [
        {"first_name": "John", "last_name": "Doe"},
        {"first_name": "Jane", "last_name": "Smith"},
    ],
    "bob@oasys.health": [
        {"first_name": "Charlie", "last_name": "Brown"},
    ],
}


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------


def run_migrations() -> None:
    log.info("Running Alembic migrations…")
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    log.info("Migrations complete.")


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


def _generate_token(provider_id: uuid.UUID, secret_key: str) -> str:
    return jwt.encode({"sub": str(provider_id)}, secret_key, algorithm="HS256")


def _write_tokens(entries: dict[str, str]) -> None:
    TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKENS_FILE.write_text(json.dumps(entries, indent=2))
    log.info("tokens.json written with %d provider(s).", len(entries))


async def _seed(session: AsyncSession, secret_key: str) -> None:
    from app.models.note import Note  # noqa: F401 — ensure tables are mapped
    from app.models.patient import Patient
    from app.models.provider import Provider

    token_map: dict[str, str] = {}

    for p_data in SEED_PROVIDERS:
        provider = Provider(
            id=uuid.uuid4(),
            name=p_data["name"],
            email=p_data["email"],
        )
        session.add(provider)
        await session.flush()
        await session.refresh(provider)

        token = _generate_token(provider.id, secret_key)
        token_map[f"{provider.name} ({provider.id})"] = token

        for pat_data in SEED_PATIENTS.get(p_data["email"], []):
            patient = Patient(
                id=uuid.uuid4(),
                provider_id=provider.id,
                first_name=pat_data["first_name"],
                last_name=pat_data["last_name"],
            )
            session.add(patient)

    await session.commit()
    _write_tokens(token_map)
    log.info("Seed data inserted: %d providers.", len(SEED_PROVIDERS))


async def _regenerate_tokens(session: AsyncSession, secret_key: str) -> None:
    from app.models.provider import Provider

    result = await session.execute(select(Provider))
    providers = list(result.scalars().all())
    token_map = {f"{p.name} ({p.id})": _generate_token(p.id, secret_key) for p in providers}
    _write_tokens(token_map)
    log.info("Regenerated tokens for %d existing provider(s).", len(providers))


async def run_seed() -> None:
    database_url = os.environ["DATABASE_URL"]
    secret_key = os.environ["SECRET_KEY"]

    engine = create_async_engine(database_url, echo=False)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM providers"))
        count: int = result.scalar_one()

        if count > 0 and TOKENS_FILE.exists():
            log.info("Database already seeded and tokens.json present — skipping.")
        elif count > 0:
            log.info("Database already seeded but tokens.json missing — regenerating.")
            await _regenerate_tokens(session, secret_key)
        else:
            log.info("Database empty — inserting seed data.")
            await _seed(session, secret_key)

    await engine.dispose()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    run_migrations()
    asyncio.run(run_seed())
    log.info("Startup complete.")


if __name__ == "__main__":
    main()
