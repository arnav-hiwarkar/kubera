"""
Test Group (a) — seed/creation of a CompanyAdmin.

Tests the internal endpoint POST /api/v1/internal/admins:
  - Creates Company + CompanyAdmin atomically
  - Returns correct IDs
  - Rows actually exist in the DB
  - Rejects duplicate CIN
  - Rejects duplicate email
  - Rejects missing/wrong internal API key
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.company import Company
from app.db.models.company_admin import CompanyAdmin


ENDPOINT = "/api/v1/internal/admins"


@pytest.mark.asyncio
async def test_create_company_admin_success(
    client: AsyncClient,
    db_session: AsyncSession,
    internal_key: str,
) -> None:
    """
    (a) Seed/creation: internal endpoint creates Company + CompanyAdmin.
    Rows must exist in the DB with correct FK linkage.
    """
    payload = {
        "company_name": "Acme Pvt Ltd",
        "cin": "U11111MH2020PTC111111",
        "admin_email": "admin@acme.com",
        "admin_password": "strongpass1",
    }
    response = await client.post(
        ENDPOINT,
        json=payload,
        headers={"X-Internal-Key": internal_key},
    )
    assert response.status_code == 201, response.text
    data = response.json()

    assert "company_id" in data
    assert "admin_id" in data
    company_id = uuid.UUID(data["company_id"])
    admin_id = uuid.UUID(data["admin_id"])

    # Verify Company row in DB
    company = await db_session.get(Company, company_id)
    assert company is not None
    assert company.name == "Acme Pvt Ltd"
    assert company.cin == "U11111MH2020PTC111111"
    assert company.is_active is True

    # Verify CompanyAdmin row in DB
    admin = await db_session.get(CompanyAdmin, admin_id)
    assert admin is not None
    assert admin.email == "admin@acme.com"
    assert admin.company_id == company_id
    # Password must be hashed — never plain
    assert admin.hashed_password != "strongpass1"
    assert admin.hashed_password.startswith("$2b$")


@pytest.mark.asyncio
async def test_create_company_admin_rejects_duplicate_cin(
    client: AsyncClient,
    db_session: AsyncSession,
    internal_key: str,
) -> None:
    """Duplicate CIN must return 409."""
    payload = {
        "company_name": "Dupe CIN Co",
        "cin": "U22222MH2020PTC222222",
        "admin_email": "first@dupe.com",
        "admin_password": "pass1",
    }
    r1 = await client.post(ENDPOINT, json=payload, headers={"X-Internal-Key": internal_key})
    assert r1.status_code == 201

    payload2 = {**payload, "admin_email": "second@dupe.com"}
    r2 = await client.post(ENDPOINT, json=payload2, headers={"X-Internal-Key": internal_key})
    assert r2.status_code == 409
    assert "CIN" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_create_company_admin_rejects_duplicate_email(
    client: AsyncClient,
    db_session: AsyncSession,
    internal_key: str,
) -> None:
    """Duplicate admin email must return 409."""
    payload = {
        "company_name": "Co A",
        "cin": "U33333MH2020PTC333333",
        "admin_email": "shared@email.com",
        "admin_password": "pass1",
    }
    r1 = await client.post(ENDPOINT, json=payload, headers={"X-Internal-Key": internal_key})
    assert r1.status_code == 201

    payload2 = {**payload, "cin": "U44444MH2020PTC444444", "company_name": "Co B"}
    r2 = await client.post(ENDPOINT, json=payload2, headers={"X-Internal-Key": internal_key})
    assert r2.status_code == 409
    assert "email" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_create_company_admin_rejects_wrong_key(
    client: AsyncClient,
) -> None:
    """Wrong internal API key must return 403."""
    payload = {
        "company_name": "X",
        "cin": "U55555MH2020PTC555555",
        "admin_email": "x@x.com",
        "admin_password": "pass",
    }
    response = await client.post(
        ENDPOINT,
        json=payload,
        headers={"X-Internal-Key": "wrong-key"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_company_admin_rejects_missing_key(
    client: AsyncClient,
) -> None:
    """Missing internal API key must return 422 (header required)."""
    payload = {
        "company_name": "X",
        "cin": "U66666MH2020PTC666666",
        "admin_email": "y@y.com",
        "admin_password": "pass",
    }
    response = await client.post(ENDPOINT, json=payload)
    assert response.status_code == 422
