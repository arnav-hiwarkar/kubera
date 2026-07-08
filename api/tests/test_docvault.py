import io
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from tests.conftest import create_company_and_admin

@pytest.fixture
async def company_a_setup(db_session: AsyncSession):
    uid = str(uuid.uuid4())[:8]
    company, admin = await create_company_and_admin(
        db_session, cin=f"U{uid}MH2020PTC000001", email=f"admin_a_{uid}@co.com", password="pass"
    )
    token = create_access_token(str(admin.id), str(company.id))
    return company, admin, token

@pytest.fixture
async def company_b_setup(db_session: AsyncSession):
    uid = str(uuid.uuid4())[:8]
    company, admin = await create_company_and_admin(
        db_session, cin=f"U{uid}MH2020PTC000002", email=f"admin_b_{uid}@co.com", password="pass"
    )
    token = create_access_token(str(admin.id), str(company.id))
    return company, admin, token


@pytest.mark.asyncio
async def test_docvault_upload_and_download(client: AsyncClient, company_a_setup):
    _, _, token = company_a_setup
    headers = {"Authorization": f"Bearer {token}"}
    
    file_content = b"Hello, secure vault!"
    
    # Upload
    response = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Test Document"},
        files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Test Document"
    assert data["status"] == "uploaded"
    doc_id = data["id"]
    
    # Get metadata
    res_get = await client.get(f"/api/v1/docvault/documents/{doc_id}", headers=headers)
    assert res_get.status_code == 200
    
    # Download
    res_down = await client.get(f"/api/v1/docvault/documents/{doc_id}/download", headers=headers)
    assert res_down.status_code == 200
    assert res_down.content == file_content

@pytest.mark.asyncio
async def test_docvault_reupload_version_increment(client: AsyncClient, company_a_setup):
    _, _, token = company_a_setup
    headers = {"Authorization": f"Bearer {token}"}
    
    # Upload initial
    res1 = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Versioned Doc"},
        files={"file": ("v1.txt", io.BytesIO(b"v1"), "text/plain")},
        headers=headers,
    )
    doc_id = res1.json()["id"]
    
    # Re-upload
    res2 = await client.post(
        f"/api/v1/docvault/documents/{doc_id}/versions",
        files={"file": ("v2.txt", io.BytesIO(b"v2"), "text/plain")},
        headers=headers,
    )
    assert res2.status_code == 200
    v2_data = res2.json()
    assert v2_data["version_number"] == 2
    assert v2_data["document_id"] == doc_id
    
    # Download latest
    res_down = await client.get(f"/api/v1/docvault/documents/{doc_id}/download", headers=headers)
    assert res_down.content == b"v2"
    
    # Download v1 specifically
    res_versions = await client.get(f"/api/v1/docvault/documents/{doc_id}/versions", headers=headers)
    versions = res_versions.json()
    assert len(versions) == 2
    v1_id = next(v["id"] for v in versions if v["version_number"] == 1)
    
    res_down_v1 = await client.get(f"/api/v1/docvault/documents/{doc_id}/download?version_id={v1_id}", headers=headers)
    assert res_down_v1.content == b"v1"

@pytest.mark.asyncio
async def test_docvault_status_bucket_updates(client: AsyncClient, company_a_setup):
    _, _, token = company_a_setup
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create bucket
    res_bucket = await client.post("/api/v1/docvault/buckets", json={"name": "Tax Bucket"}, headers=headers)
    bucket_id = res_bucket.json()["id"]
    
    # Upload
    res_doc = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Updatable Doc"},
        files={"file": ("file.txt", io.BytesIO(b"data"), "text/plain")},
        headers=headers,
    )
    doc_id = res_doc.json()["id"]
    
    # Update status and bucket
    res_patch = await client.patch(
        f"/api/v1/docvault/documents/{doc_id}",
        json={"status": "verified", "bucket_id": bucket_id, "tags": ["tag1"]},
        headers=headers,
    )
    assert res_patch.status_code == 200
    updated_data = res_patch.json()
    assert updated_data["status"] == "verified"
    assert updated_data["bucket_id"] == bucket_id
    assert updated_data["tags"] == ["tag1"]

@pytest.mark.asyncio
async def test_cross_tenant_isolation(client: AsyncClient, company_a_setup, company_b_setup):
    comp_a, _, token_a = company_a_setup
    comp_b, _, token_b = company_b_setup
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    
    # A creates bucket and document
    res_bucket = await client.post("/api/v1/docvault/buckets", json={"name": "A Bucket"}, headers=headers_a)
    bucket_id_a = res_bucket.json()["id"]
    
    res_doc = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "A Document", "bucket_id": bucket_id_a},
        files={"file": ("a.txt", io.BytesIO(b"A data"), "text/plain")},
        headers=headers_a,
    )
    doc_id_a = res_doc.json()["id"]
    
    # B tries to list A's buckets
    res_buckets_b = await client.get("/api/v1/docvault/buckets", headers=headers_b)
    bucket_ids_b = [b["id"] for b in res_buckets_b.json()]
    assert bucket_id_a not in bucket_ids_b
    
    # B tries to delete A's bucket
    res_del_b = await client.delete(f"/api/v1/docvault/buckets/{bucket_id_a}", headers=headers_b)
    assert res_del_b.status_code == 404
    
    # B tries to get A's document metadata
    res_get_b = await client.get(f"/api/v1/docvault/documents/{doc_id_a}", headers=headers_b)
    assert res_get_b.status_code == 404
    
    # B tries to download A's document
    res_down_b = await client.get(f"/api/v1/docvault/documents/{doc_id_a}/download", headers=headers_b)
    assert res_down_b.status_code == 404
    
    # B tries to update A's document
    res_patch_b = await client.patch(f"/api/v1/docvault/documents/{doc_id_a}", json={"status": "archived"}, headers=headers_b)
    assert res_patch_b.status_code == 404
