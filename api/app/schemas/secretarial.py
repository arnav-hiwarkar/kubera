import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DocumentTypeBase(BaseModel):
    name: str
    metadata_schema: dict[str, Any]
    template_file_id: uuid.UUID | None = None


class DocumentTypeCreate(DocumentTypeBase):
    pass


class DocumentTypeResponse(DocumentTypeBase):
    id: uuid.UUID
    company_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MeetingRecordBase(BaseModel):
    doc_type_id: uuid.UUID
    structured_metadata: dict[str, Any]
    linked_document_id: uuid.UUID | None = None


class MeetingRecordCreate(MeetingRecordBase):
    pass


class MeetingRecordResponse(MeetingRecordBase):
    id: uuid.UUID
    company_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
