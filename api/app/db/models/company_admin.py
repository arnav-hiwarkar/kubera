"""
CompanyAdmin model.

One admin per company in v1 (enforced at the application layer, not
as a DB UNIQUE constraint — so the schema doesn't preclude adding
multi-user support in a later phase without a migration).

CompanyAdmin is NOT a TenantScopedMixin table — it lives above the
tenant boundary. It has a plain FK to company.id.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CompanyAdmin(Base):
    __tablename__ = "company_admin"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(254),
        unique=True,
        nullable=False,
        index=True,
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────
    company: Mapped["Company"] = relationship(  # noqa: F821
        "Company",
        back_populates="admins",
    )

    def __repr__(self) -> str:
        return f"<CompanyAdmin id={self.id} email={self.email!r} company_id={self.company_id}>"
