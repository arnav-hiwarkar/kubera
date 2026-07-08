import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import create_company_and_admin
from app.core.security import create_access_token

@pytest.fixture
async def company_b_setup(db_session: AsyncSession):
    uid = str(uuid.uuid4())[:5]
    company, admin = await create_company_and_admin(
        db_session, cin=f"U{uid}MH2020PTC000002", email=f"admin_b_{uid}@co.com", password="pass"
    )
    token = create_access_token(str(admin.id), str(company.id))
    return company, admin, token


@pytest.mark.asyncio
async def test_create_and_list_document_type(
    client: AsyncClient,
    company_a_setup: tuple,
):
    _, _, token = company_a_setup
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create
    resp = await client.post(
        "/api/v1/secretarial/document-types",
        headers=headers,
        json={
            "name": "Custom MoM",
            "metadata_schema": {"type": "object", "properties": {"date": {"type": "string"}}},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Custom MoM"
    doc_type_id = data["id"]
    
    # List
    resp2 = await client.get("/api/v1/secretarial/document-types", headers=headers)
    assert resp2.status_code == 200
    docs = resp2.json()
    assert len(docs) >= 1
    assert any(d["id"] == doc_type_id for d in docs)


@pytest.mark.asyncio
async def test_tenant_isolation_document_type(
    client: AsyncClient,
    company_a_setup: tuple,
    company_b_setup: tuple,
):
    _, _, token_a = company_a_setup
    _, _, token_b = company_b_setup
    # A creates
    resp = await client.post(
        "/api/v1/secretarial/document-types",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "name": "Company A Private Type",
            "metadata_schema": {},
        },
    )
    doc_a_id = resp.json()["id"]

    # B lists
    resp_b = await client.get(
        "/api/v1/secretarial/document-types",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    docs_b = resp_b.json()
    assert not any(d["id"] == doc_a_id for d in docs_b)


@pytest.mark.asyncio
async def test_create_and_list_meeting_record(
    client: AsyncClient,
    company_a_setup: tuple,
):
    _, _, token = company_a_setup
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create doc type
    dt_resp = await client.post(
        "/api/v1/secretarial/document-types",
        headers=headers,
        json={"name": "Type for record", "metadata_schema": {}},
    )
    dt_id = dt_resp.json()["id"]

    # Create meeting record
    mr_resp = await client.post(
        "/api/v1/secretarial/meeting-records",
        headers=headers,
        json={
            "doc_type_id": dt_id,
            "structured_metadata": {"foo": "bar"},
        },
    )
    assert mr_resp.status_code == 201
    mr_data = mr_resp.json()
    mr_id = mr_data["id"]
    assert mr_data["doc_type_id"] == dt_id
    assert mr_data["structured_metadata"] == {"foo": "bar"}

    # List
    list_resp = await client.get("/api/v1/secretarial/meeting-records", headers=headers)
    assert list_resp.status_code == 200
    mrs = list_resp.json()
    assert any(m["id"] == mr_id for m in mrs)


@pytest.mark.asyncio
async def test_meeting_record_rejects_inaccessible_doc_type(
    client: AsyncClient,
    company_a_setup: tuple,
    company_b_setup: tuple,
):
    _, _, token_a = company_a_setup
    _, _, token_b = company_b_setup
    # A creates doc type
    dt_resp = await client.post(
        "/api/v1/secretarial/document-types",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "A type", "metadata_schema": {}},
    )
    dt_id = dt_resp.json()["id"]

    # B tries to use A's doc type
    mr_resp = await client.post(
        "/api/v1/secretarial/meeting-records",
        headers={"Authorization": f"Bearer {token_b}"},
        json={
            "doc_type_id": dt_id,
            "structured_metadata": {},
        },
    )
    assert mr_resp.status_code == 404
