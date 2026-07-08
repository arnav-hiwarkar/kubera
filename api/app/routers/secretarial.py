import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_tenant_scope
from app.db.models.secretarial import DocumentType, MeetingRecord
from app.db.session import get_db
from app.schemas.secretarial import (
    DocumentTypeCreate,
    DocumentTypeResponse,
    MeetingRecordCreate,
    MeetingRecordResponse,
)

router = APIRouter(prefix="/api/v1/secretarial", tags=["secretarial"])


@router.post(
    "/document-types",
    response_model=DocumentTypeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_document_type(
    payload: DocumentTypeCreate,
    company_id: uuid.UUID = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a new custom DocumentType for the company."""
    doc_type = DocumentType(
        company_id=company_id,
        name=payload.name,
        metadata_schema=payload.metadata_schema,
        template_file_id=payload.template_file_id,
    )
    db.add(doc_type)
    await db.commit()
    await db.refresh(doc_type)
    return doc_type


@router.get("/document-types", response_model=list[DocumentTypeResponse])
async def list_document_types(
    company_id: uuid.UUID = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List all DocumentTypes available to the company (system + custom)."""
    result = await db.execute(
        select(DocumentType).where(
            or_(
                DocumentType.company_id == company_id,
                DocumentType.company_id.is_(None),
            )
        )
    )
    return result.scalars().all()


@router.post(
    "/meeting-records",
    response_model=MeetingRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_meeting_record(
    payload: MeetingRecordCreate,
    company_id: uuid.UUID = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a new MeetingRecord."""
    # Validate that the doc_type_id is accessible
    dt_result = await db.execute(
        select(DocumentType).where(
            DocumentType.id == payload.doc_type_id,
            or_(
                DocumentType.company_id == company_id,
                DocumentType.company_id.is_(None),
            )
        )
    )
    doc_type = dt_result.scalar_one_or_none()
    if not doc_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document type not found or inaccessible",
        )

    record = MeetingRecord(
        company_id=company_id,
        doc_type_id=payload.doc_type_id,
        structured_metadata=payload.structured_metadata,
        linked_document_id=payload.linked_document_id,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.get("/meeting-records", response_model=list[MeetingRecordResponse])
async def list_meeting_records(
    company_id: uuid.UUID = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List all MeetingRecords for the company."""
    result = await db.execute(
        select(MeetingRecord).where(MeetingRecord.company_id == company_id)
    )
    return result.scalars().all()
