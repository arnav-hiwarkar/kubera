import uuid
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import json

from app.core.deps import get_current_admin, get_tenant_scope
from app.db.models.company_admin import CompanyAdmin
from app.db.models.docvault import Bucket, Document, DocumentVersion, DocumentStatus
from app.db.session import get_db
from app.services.storage import save_document, load_document, delete_document_file

router = APIRouter(prefix="/api/v1/docvault", tags=["docvault"])

# ── Schemas ───────────────────────────────────────────────────────────────────

class BucketCreate(BaseModel):
    name: str

class BucketResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    created_by: Optional[uuid.UUID]

    model_config = {"from_attributes": True}

class DocumentResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    current_version_id: Optional[uuid.UUID]
    bucket_id: Optional[uuid.UUID]
    status: DocumentStatus
    title: str
    doc_type: Optional[str]
    tags: Optional[list[str]]
    created_by: Optional[uuid.UUID]

    model_config = {"from_attributes": True}

class DocumentVersionResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    original_filename: str
    mime_type: str
    size_bytes: int
    version_number: int
    uploaded_by: Optional[uuid.UUID]

    model_config = {"from_attributes": True}

class DocumentUpdate(BaseModel):
    status: Optional[DocumentStatus] = None
    bucket_id: Optional[uuid.UUID] = None
    tags: Optional[list[str]] = None


# ── Buckets ───────────────────────────────────────────────────────────────────

@router.post("/buckets", response_model=BucketResponse)
async def create_bucket(
    body: BucketCreate,
    current_admin: CompanyAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    bucket = Bucket(
        company_id=current_admin.company_id,
        name=body.name,
        created_by=current_admin.id,
    )
    db.add(bucket)
    await db.commit()
    await db.refresh(bucket)
    return bucket

@router.get("/buckets", response_model=List[BucketResponse])
async def list_buckets(
    company_id: uuid.UUID = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Bucket).where(Bucket.company_id == company_id))
    return result.scalars().all()

@router.delete("/buckets/{bucket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bucket(
    bucket_id: uuid.UUID,
    company_id: uuid.UUID = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Bucket).where(and_(Bucket.id == bucket_id, Bucket.company_id == company_id))
    )
    bucket = result.scalar_one_or_none()
    if not bucket:
        raise HTTPException(status_code=404, detail="Bucket not found")
    
    await db.delete(bucket)
    await db.commit()

# ── Documents ─────────────────────────────────────────────────────────────────

@router.post("/documents", response_model=DocumentResponse)
async def upload_document(
    title: Annotated[str, Form()],
    file: UploadFile,
    bucket_id: Annotated[Optional[uuid.UUID], Form()] = None,
    doc_type: Annotated[Optional[str], Form()] = None,
    tags: Annotated[Optional[str], Form()] = None, # JSON list as string
    current_admin: CompanyAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    parsed_tags = None
    if tags:
        try:
            parsed_tags = json.loads(tags)
            if not isinstance(parsed_tags, list):
                raise ValueError()
        except Exception:
            raise HTTPException(status_code=422, detail="tags must be a valid JSON list of strings")

    storage_path, size_bytes, checksum, encrypted_dek = await save_document(current_admin.company_id, file)

    doc = Document(
        company_id=current_admin.company_id,
        title=title,
        bucket_id=bucket_id,
        doc_type=doc_type,
        tags=parsed_tags,
        created_by=current_admin.id,
    )
    db.add(doc)
    await db.flush() # get doc.id

    doc_version = DocumentVersion(
        document_id=doc.id,
        storage_path=storage_path,
        original_filename=file.filename or "unknown",
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=size_bytes,
        checksum=checksum,
        encrypted_dek=encrypted_dek,
        uploaded_by=current_admin.id,
        version_number=1,
    )
    db.add(doc_version)
    await db.flush()

    doc.current_version_id = doc_version.id
    await db.commit()
    await db.refresh(doc)
    return doc

@router.post("/documents/{document_id}/versions", response_model=DocumentVersionResponse)
async def upload_document_version(
    document_id: uuid.UUID,
    file: UploadFile,
    current_admin: CompanyAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(and_(Document.id == document_id, Document.company_id == current_admin.company_id))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # get latest version number
    version_result = await db.execute(
        select(DocumentVersion.version_number)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    )
    latest_version = version_result.scalar_one_or_none() or 0

    storage_path, size_bytes, checksum, encrypted_dek = await save_document(current_admin.company_id, file)

    doc_version = DocumentVersion(
        document_id=doc.id,
        storage_path=storage_path,
        original_filename=file.filename or "unknown",
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=size_bytes,
        checksum=checksum,
        encrypted_dek=encrypted_dek,
        uploaded_by=current_admin.id,
        version_number=latest_version + 1,
    )
    db.add(doc_version)
    await db.flush()

    doc.current_version_id = doc_version.id
    await db.commit()
    await db.refresh(doc_version)
    return doc_version

@router.get("/documents", response_model=List[DocumentResponse])
async def list_documents(
    bucket_id: Optional[uuid.UUID] = None,
    status: Optional[DocumentStatus] = None,
    company_id: uuid.UUID = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    query = select(Document).where(Document.company_id == company_id)
    if bucket_id:
        query = query.where(Document.bucket_id == bucket_id)
    if status:
        query = query.where(Document.status == status)
    
    result = await db.execute(query)
    return result.scalars().all()

@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    company_id: uuid.UUID = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(and_(Document.id == document_id, Document.company_id == company_id))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc

@router.patch("/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: uuid.UUID,
    body: DocumentUpdate,
    company_id: uuid.UUID = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(and_(Document.id == document_id, Document.company_id == company_id))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if body.status is not None:
        doc.status = body.status
    if body.bucket_id is not None:
        doc.bucket_id = body.bucket_id
    if body.tags is not None:
        doc.tags = body.tags
        
    await db.commit()
    await db.refresh(doc)
    return doc

@router.delete("/documents/{document_id}", response_model=DocumentResponse)
async def delete_document(
    document_id: uuid.UUID,
    company_id: uuid.UUID = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(and_(Document.id == document_id, Document.company_id == company_id))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc.status = DocumentStatus.archived
    await db.commit()
    await db.refresh(doc)
    return doc

@router.get("/documents/{document_id}/versions", response_model=List[DocumentVersionResponse])
async def list_document_versions(
    document_id: uuid.UUID,
    company_id: uuid.UUID = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    # Ensure document belongs to company
    result = await db.execute(
        select(Document).where(and_(Document.id == document_id, Document.company_id == company_id))
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Document not found")

    versions_result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == document_id)
    )
    return versions_result.scalars().all()

@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    version_id: Optional[uuid.UUID] = None,
    company_id: uuid.UUID = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    # Check access to the document
    result = await db.execute(
        select(Document).where(and_(Document.id == document_id, Document.company_id == company_id))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    target_version_id = version_id or doc.current_version_id
    if not target_version_id:
        raise HTTPException(status_code=404, detail="No versions available")
        
    version_result = await db.execute(
        select(DocumentVersion).where(and_(
            DocumentVersion.id == target_version_id,
            DocumentVersion.document_id == document_id
        ))
    )
    doc_version = version_result.scalar_one_or_none()
    if not doc_version:
        raise HTTPException(status_code=404, detail="Version not found")
        
    try:
        decrypted_bytes = load_document(doc_version.storage_path, doc_version.encrypted_dek)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to decrypt document")
        
    def iterfile():
        yield decrypted_bytes
        
    return StreamingResponse(
        iterfile(),
        media_type=doc_version.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{doc_version.original_filename}"'
        }
    )
