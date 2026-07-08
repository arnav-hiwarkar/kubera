"""
Internal router — /api/v1/internal

These endpoints are NOT exposed to the public or to company admins.
They are guarded by the INTERNAL_API_KEY (X-Internal-Key header).
Use them for Kubera team operations: creating companies + first admins.

No JWT auth here — this is the bootstrap path that creates the
entities that JWT auth depends on.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_internal_key
from app.core.security import hash_password
from app.db.models.company import Company
from app.db.models.company_admin import CompanyAdmin
from app.db.session import get_db

router = APIRouter(
    prefix="/api/v1/internal",
    tags=["internal"],
    dependencies=[Depends(require_internal_key)],
)


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreateAdminRequest(BaseModel):
    company_name: str
    cin: str
    admin_email: EmailStr
    admin_password: str


class CreateAdminResponse(BaseModel):
    company_id: uuid.UUID
    admin_id: uuid.UUID
    message: str = "Company and admin created successfully"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/admins",
    response_model=CreateAdminResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_company_admin(
    body: CreateAdminRequest,
    db: AsyncSession = Depends(get_db),
) -> CreateAdminResponse:
    """
    Create a Company and its first CompanyAdmin atomically.

    This is the ONLY way to provision a new tenant in v1.
    No public signup. Requires X-Internal-Key header.

    Idempotency: rejects duplicate CIN or duplicate admin email.
    """
    # Check for duplicate CIN
    existing_company = await db.execute(
        select(Company).where(Company.cin == body.cin)
    )
    if existing_company.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Company with CIN {body.cin!r} already exists",
        )

    # Check for duplicate email
    existing_admin = await db.execute(
        select(CompanyAdmin).where(CompanyAdmin.email == body.admin_email)
    )
    if existing_admin.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Admin with email {body.admin_email!r} already exists",
        )

    # Create company + admin in one transaction
    company = Company(
        id=uuid.uuid4(),
        name=body.company_name,
        cin=body.cin,
    )
    db.add(company)
    await db.flush()  # get company.id before creating admin

    admin = CompanyAdmin(
        id=uuid.uuid4(),
        company_id=company.id,
        email=body.admin_email,
        hashed_password=hash_password(body.admin_password),
    )
    db.add(admin)
    # Session commits in get_db() after the request completes

    return CreateAdminResponse(company_id=company.id, admin_id=admin.id)
