import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin


class LedgerGroup(Base):
    __tablename__ = "ledger_group"
    
    # Not tenant-scoped; this is shared seed data (Schedule III)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ledger_group.id"), nullable=True
    )
    schedule_iii_category: Mapped[str | None] = mapped_column(String, nullable=True)


class Ledger(TenantScopedMixin, Base):
    __tablename__ = "ledger"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ledger_code: Mapped[str | None] = mapped_column(String, nullable=True)
    ledger_name: Mapped[str] = mapped_column(String, nullable=False)
    opening_balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    debit: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    credit: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    closing_balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ledger_group.id"), nullable=True
    )


class AuditEngagement(TenantScopedMixin, Base):
    __tablename__ = "audit_engagement"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    period_label: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="invited", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AuditEntry(TenantScopedMixin, Base):
    __tablename__ = "audit_entry"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audit_engagement.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auditor.id"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, default="proposed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AuditEntryLine(TenantScopedMixin, Base):
    __tablename__ = "audit_entry_line"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audit_entry.id", ondelete="CASCADE"), nullable=False
    )
    ledger_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ledger.id"), nullable=False
    )
    side: Mapped[str] = mapped_column(String, nullable=False) # debit or credit
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)


class ReportTemplate(TenantScopedMixin, Base):
    __tablename__ = "report_template"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    json_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
