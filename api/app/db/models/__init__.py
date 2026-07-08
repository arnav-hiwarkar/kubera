"""
Model registry — import all models here so Alembic autogenerate
can see them all when it inspects Base.metadata.
"""
from app.db.models.company import Company  # noqa: F401
from app.db.models.company_admin import CompanyAdmin  # noqa: F401
from app.db.models.docvault import Bucket, Document, DocumentAccessOverride, DocumentVersion  # noqa: F401

__all__ = ["Company", "CompanyAdmin", "Bucket", "Document", "DocumentVersion", "DocumentAccessOverride"]
