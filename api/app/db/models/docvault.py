import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base, TenantScopedMixin


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    pending_approval = "pending_approval"
    action_required = "action_required"
    verified = "verified"
    submitted = "submitted"
    overdue = "overdue"
    archived = "archived"


class Bucket(TenantScopedMixin, Base):
    __tablename__ = "bucket"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("company_admin.id"), nullable=True)

    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="bucket",
        cascade="all, delete-orphan",
    )


class Document(TenantScopedMixin, Base):
    __tablename__ = "document"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    current_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_version.id", use_alter=True), nullable=True)
    bucket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bucket.id"), nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus, name="document_status_enum"), default=DocumentStatus.uploaded, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(255), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("company_admin.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    bucket: Mapped["Bucket"] = relationship("Bucket", back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(
        "DocumentVersion",
        back_populates="document",
        foreign_keys="DocumentVersion.document_id",
        cascade="all, delete-orphan",
    )
    current_version: Mapped["DocumentVersion"] = relationship(
        "DocumentVersion",
        foreign_keys=[current_version_id],
        post_update=True,
    )


class DocumentVersion(Base):
    __tablename__ = "document_version"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_dek: Mapped[str] = mapped_column(String(512), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("company_admin.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    document: Mapped["Document"] = relationship("Document", back_populates="versions", foreign_keys=[document_id])


class DocumentAccessOverride(Base):
    __tablename__ = "document_access_override"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True)
    principal: Mapped[str] = mapped_column(String(255), nullable=False)
    permission_level: Mapped[str] = mapped_column(String(50), nullable=False)
