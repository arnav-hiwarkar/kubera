"""
Test Groups (b) and (c) — JWT auth.

(b) Login with correct credentials returns a valid, decodable JWT
    with correct claims (sub, company_id, principal_type, type).

(c) A protected endpoint rejects:
    - missing token
    - expired token
    - token signed with wrong secret
    - refresh token used as access token
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import (
    PRINCIPAL_TYPE_COMPANY_ADMIN,
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
    create_refresh_token,
)
from tests.conftest import create_company_and_admin

settings = get_settings()
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"


# ── (b) Login returns a valid JWT ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_returns_valid_jwt(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    (b) Login with correct credentials returns access + refresh tokens.
    Access token must decode with correct claims.
    """
    company, admin = await create_company_and_admin(
        db_session,
        cin="U77777MH2020PTC777777",
        email="auth_test@co.com",
        password="correctpass",
    )

    response = await client.post(
        LOGIN_URL,
        data={"username": "auth_test@co.com", "password": "correctpass"},
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    # Decode and validate access token claims
    access_payload = jwt.decode(
        data["access_token"],
        settings.secret_key,
        algorithms=[settings.algorithm],
    )
    assert access_payload["sub"] == str(admin.id)
    assert access_payload["company_id"] == str(company.id)
    assert access_payload["principal_type"] == PRINCIPAL_TYPE_COMPANY_ADMIN
    assert access_payload["type"] == TOKEN_TYPE_ACCESS

    # Decode and validate refresh token claims
    refresh_payload = jwt.decode(
        data["refresh_token"],
        settings.refresh_secret_key,
        algorithms=[settings.algorithm],
    )
    assert refresh_payload["sub"] == str(admin.id)
    assert refresh_payload["principal_type"] == PRINCIPAL_TYPE_COMPANY_ADMIN
    assert refresh_payload["type"] == TOKEN_TYPE_REFRESH


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Wrong password must return 401."""
    await create_company_and_admin(
        db_session,
        cin="U88888MH2020PTC888888",
        email="wrongpass@co.com",
        password="correctpass",
    )
    response = await client.post(
        LOGIN_URL,
        data={"username": "wrongpass@co.com", "password": "wrongpass"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401(client: AsyncClient) -> None:
    """Unknown email must return 401."""
    response = await client.post(
        LOGIN_URL,
        data={"username": "nobody@nowhere.com", "password": "anything"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_returns_new_access_token(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Valid refresh token must yield a new access token."""
    company, admin = await create_company_and_admin(
        db_session,
        cin="U99999MH2020PTC999999",
        email="refresh@co.com",
        password="pass",
    )
    refresh_token = create_refresh_token(str(admin.id))

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    new_data = response.json()
    assert "access_token" in new_data

    # New access token must be valid
    payload = jwt.decode(
        new_data["access_token"],
        settings.secret_key,
        algorithms=[settings.algorithm],
    )
    assert payload["sub"] == str(admin.id)


# ── (c) Protected endpoint rejects invalid/missing token ─────────────────────

@pytest.mark.asyncio
async def test_protected_endpoint_rejects_missing_token(
    client: AsyncClient,
) -> None:
    """(c) No Authorization header → 401."""
    response = await client.get(ME_URL)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_rejects_malformed_token(
    client: AsyncClient,
) -> None:
    """(c) Garbage token string → 401."""
    response = await client.get(
        ME_URL, headers={"Authorization": "Bearer not.a.real.token"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_rejects_wrong_secret(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """(c) Token signed with a different secret → 401."""
    company, admin = await create_company_and_admin(
        db_session,
        cin="U10101MH2020PTC101010",
        email="wrongsecret@co.com",
        password="pass",
    )
    # Sign with a completely different key
    bad_token = jwt.encode(
        {
            "sub": str(admin.id),
            "company_id": str(company.id),
            "principal_type": PRINCIPAL_TYPE_COMPANY_ADMIN,
            "type": TOKEN_TYPE_ACCESS,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        },
        key="totally-wrong-secret",
        algorithm=settings.algorithm,
    )
    response = await client.get(
        ME_URL, headers={"Authorization": f"Bearer {bad_token}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_rejects_expired_token(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """(c) Expired access token → 401."""
    company, admin = await create_company_and_admin(
        db_session,
        cin="U20202MH2020PTC202020",
        email="expired@co.com",
        password="pass",
    )
    expired_token = jwt.encode(
        {
            "sub": str(admin.id),
            "company_id": str(company.id),
            "principal_type": PRINCIPAL_TYPE_COMPANY_ADMIN,
            "type": TOKEN_TYPE_ACCESS,
            # exp in the past
            "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
        },
        key=settings.secret_key,
        algorithm=settings.algorithm,
    )
    response = await client.get(
        ME_URL, headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_rejects_refresh_token_as_access(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """(c) Refresh token must NOT be accepted as an access token."""
    company, admin = await create_company_and_admin(
        db_session,
        cin="U30303MH2020PTC303030",
        email="refreshasaccess@co.com",
        password="pass",
    )
    refresh_token = create_refresh_token(str(admin.id))
    response = await client.get(
        ME_URL, headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert response.status_code == 401
