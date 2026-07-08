"""
Company model.

Company is the root tenant entity. Every company-owned table
references this via TenantScopedMixin.company_id.

One row per client company. Created by internal Kubera staff only
(no self-serve signup in v1).
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Company(Base):
    __tablename__ = "company"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cin: Mapped[str] = mapped_column(
        String(21),
        unique=True,
        nullable=False,
        comment="Corporate Identity Number (21-char Indian CIN)",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────
    admins: Mapped[list["CompanyAdmin"]] = relationship(  # noqa: F821
        "CompanyAdmin",
        back_populates="company",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Company id={self.id} name={self.name!r} cin={self.cin!r}>"
