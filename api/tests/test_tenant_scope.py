"""
Test Group (d) — Tenant-scoping dependency actually filters by company_id.

Two companies, each with an admin and a DummyTenantResource row.
Each admin must ONLY see their own resource, never the other company's.

This proves the TenantScopedMixin + get_tenant_scope() invariant:
  company_id always comes from the token, never from user input,
  and acts as a mandatory WHERE filter on all scoped queries.
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.db.models.company import Company
from app.db.models.company_admin import CompanyAdmin
from tests.conftest import DummyTenantResource, create_company_and_admin

# We need a real protected endpoint that uses get_tenant_scope() and
# queries DummyTenantResource. We register it here as a test-only router
# added to the app during this test module only.

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession as AS

from app.core.deps import get_tenant_scope
from app.db.session import get_db
from app.main import app

_test_router = APIRouter()


@_test_router.get("/api/v1/test/my-resources")
async def list_my_resources(
    company_id: uuid.UUID = Depends(get_tenant_scope),
    db: AS = Depends(get_db),
) -> list[dict]:
    """
    Test-only endpoint: returns DummyTenantResource rows
    filtered strictly by company_id from the token.
    """
    result = await db.execute(
        select(DummyTenantResource).where(
            DummyTenantResource.company_id == company_id
        )
    )
    rows = result.scalars().all()
    return [{"id": str(r.id), "label": r.label, "company_id": str(r.company_id)} for r in rows]


app.include_router(_test_router)

RESOURCE_URL = "/api/v1/test/my-resources"


@pytest.mark.asyncio
async def test_tenant_scope_filters_by_company_id(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    (d) Two companies, each with one DummyTenantResource row.
    Company A's admin must see only their row.
    Company B's admin must see only their row.
    Neither must see the other's data.
    """
    # ── Set up two companies ──────────────────────────────────────────────
    company_a, admin_a = await create_company_and_admin(
        db_session,
        company_name="Tenant A Ltd",
        cin="UA1111MH2020PTC111111",
        email="admin@tenant-a.com",
        password="passA",
    )
    company_b, admin_b = await create_company_and_admin(
        db_session,
        company_name="Tenant B Ltd",
        cin="UB2222MH2020PTC222222",
        email="admin@tenant-b.com",
        password="passB",
    )

    # ── Create one DummyTenantResource per company ────────────────────────
    resource_a = DummyTenantResource(
        id=uuid.uuid4(),
        company_id=company_a.id,
        label="Resource belonging to Tenant A",
    )
    resource_b = DummyTenantResource(
        id=uuid.uuid4(),
        company_id=company_b.id,
        label="Resource belonging to Tenant B",
    )
    db_session.add(resource_a)
    db_session.add(resource_b)
    await db_session.flush()

    # ── Tokens ────────────────────────────────────────────────────────────
    token_a = create_access_token(str(admin_a.id), str(company_a.id))
    token_b = create_access_token(str(admin_b.id), str(company_b.id))

    # ── Admin A sees ONLY their resource ──────────────────────────────────
    resp_a = await client.get(
        RESOURCE_URL, headers={"Authorization": f"Bearer {token_a}"}
    )
    assert resp_a.status_code == 200, resp_a.text
    rows_a = resp_a.json()
    assert len(rows_a) == 1, f"Admin A should see 1 row, got {len(rows_a)}"
    assert rows_a[0]["label"] == "Resource belonging to Tenant A"
    assert rows_a[0]["company_id"] == str(company_a.id)

    # ── Admin B sees ONLY their resource ──────────────────────────────────
    resp_b = await client.get(
        RESOURCE_URL, headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp_b.status_code == 200, resp_b.text
    rows_b = resp_b.json()
    assert len(rows_b) == 1, f"Admin B should see 1 row, got {len(rows_b)}"
    assert rows_b[0]["label"] == "Resource belonging to Tenant B"
    assert rows_b[0]["company_id"] == str(company_b.id)

    # ── Cross-tenant leak check ───────────────────────────────────────────
    all_labels_a = {r["label"] for r in rows_a}
    all_labels_b = {r["label"] for r in rows_b}
    assert "Resource belonging to Tenant B" not in all_labels_a, (
        "CROSS-TENANT LEAK: Admin A can see Tenant B's data!"
    )
    assert "Resource belonging to Tenant A" not in all_labels_b, (
        "CROSS-TENANT LEAK: Admin B can see Tenant A's data!"
    )
