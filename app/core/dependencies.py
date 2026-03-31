from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session

# Stub: will be replaced with real provider lookup in the auth phase
_STATIC_TOKENS: dict[str, str] = {}

security = HTTPBearer()


async def get_db(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AsyncGenerator[AsyncSession, None]:
    yield session


async def get_current_provider(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> str:
    """Stub: returns provider_id from token. Full implementation in auth phase."""
    token = credentials.credentials
    provider_id = _STATIC_TOKENS.get(token)
    if provider_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )
    return provider_id
