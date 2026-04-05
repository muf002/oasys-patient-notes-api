"""Unit tests for JWT authentication — no HTTP, no database."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.dependencies import get_current_provider
from app.models.provider import Provider

_SECRET = "test-secret-key"
_ALGORITHM = "HS256"


def _make_token(payload: dict, secret: str = _SECRET) -> str:
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def _make_credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _make_provider() -> Provider:
    p = Provider()
    p.id = uuid.uuid4()
    p.name = "Dr. Alice"
    p.email = "alice@test.com"
    p.created_at = datetime.now(UTC)
    return p


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


class TestGetCurrentProvider:
    async def test_valid_token_returns_provider(self, mock_db: AsyncMock) -> None:
        provider = _make_provider()
        token = _make_token({"sub": str(provider.id)})

        with (
            patch("app.core.dependencies.settings") as mock_settings,
            patch("app.core.dependencies.ProviderRepository") as mock_repo_class,
        ):
            mock_settings.SECRET_KEY = _SECRET
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_id.return_value = provider

            result = await get_current_provider(_make_credentials(token), mock_db)

        assert result.id == provider.id
        mock_repo.get_by_id.assert_awaited_once_with(provider.id)

    async def test_malformed_token_raises_401(self, mock_db: AsyncMock) -> None:
        with (
            patch("app.core.dependencies.settings") as mock_settings,
            pytest.raises(HTTPException) as exc_info,
        ):
            mock_settings.SECRET_KEY = _SECRET
            await get_current_provider(_make_credentials("not.a.valid.token"), mock_db)

        assert exc_info.value.status_code == 401

    async def test_valid_token_but_provider_not_in_db_raises_401(self, mock_db: AsyncMock) -> None:
        token = _make_token({"sub": str(uuid.uuid4())})

        with (
            patch("app.core.dependencies.settings") as mock_settings,
            patch("app.core.dependencies.ProviderRepository") as mock_repo_class,
        ):
            mock_settings.SECRET_KEY = _SECRET
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_id.return_value = None  # provider deleted / unknown

            with pytest.raises(HTTPException) as exc_info:
                await get_current_provider(_make_credentials(token), mock_db)

        assert exc_info.value.status_code == 401
