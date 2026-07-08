import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base, TenantScopedMixin


class DocumentType(Base):
    __tablename__ = "document_type"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document.id", ondelete="SET NULL"), nullable=True)
    metadata_schema: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    template_document: Mapped["Document"] = relationship("Document", foreign_keys=[template_file_id])


class MeetingRecord(TenantScopedMixin, Base):
    __tablename__ = "meeting_record"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    doc_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_type.id", ondelete="RESTRICT"), nullable=False, index=True)
    structured_metadata: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    linked_document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document.id", ondelete="SET NULL"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    document_type: Mapped["DocumentType"] = relationship("DocumentType")
    linked_document: Mapped["Document"] = relationship("Document", foreign_keys=[linked_document_id])
