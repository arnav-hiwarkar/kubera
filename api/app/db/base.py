"""
SQLAlchemy 2.0 declarative base + TenantScopedMixin.

TenantScopedMixin is the single highest-risk primitive in Kubera.
Every table that holds company-owned data MUST inherit from it.
The get_tenant_scope() dependency (app/core/deps.py) enforces
that all queries against these tables are filtered by company_id.

Rules:
  1. Inherit TenantScopedMixin BEFORE any other mixin.
  2. Never read company_id from request body — always from the token
     via get_tenant_scope().
  3. company_id is non-nullable, indexed, with RESTRICT FK so a company
     cannot be deleted while any of its data rows exist.
"""
import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Project-wide declarative base. All models inherit from this."""
    pass


class TenantScopedMixin:
    """
    Mixin that adds a non-nullable, indexed company_id FK to any model.

    Usage:
        class MyModel(TenantScopedMixin, Base):
            __tablename__ = "my_model"
            id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
            ...

    The FK references company.id with ondelete=RESTRICT.
    All queries against TenantScoped tables MUST be scoped with:
        .where(MyModel.company_id == company_id)
    where company_id comes from get_tenant_scope(), never from user input.
    """

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("company.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
