"""
Auth router — /api/v1/auth

Endpoints:
  POST /login   — email + password → access + refresh tokens
  POST /refresh — refresh token → new access token
  GET  /me      — returns current admin profile (protected, for testing)
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_admin
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    verify_password,
)
from app.db.models.company_admin import CompanyAdmin
from app.db.session import get_db

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AdminProfile(BaseModel):
    id: uuid.UUID
    email: str
    company_id: uuid.UUID
    is_active: bool

    model_config = {"from_attributes": True}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Authenticate a CompanyAdmin with email + password.
    Returns access + refresh tokens on success.
    """
    result = await db.execute(
        select(CompanyAdmin).where(CompanyAdmin.email == form_data.username)
    )
    admin = result.scalar_one_or_none()

    if admin is None or not verify_password(form_data.password, admin.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    return TokenResponse(
        access_token=create_access_token(str(admin.id), str(admin.company_id)),
        refresh_token=create_refresh_token(str(admin.id)),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Exchange a valid refresh token for a new access token.
    The refresh token must have been signed with REFRESH_SECRET_KEY.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_refresh_token(body.refresh_token)
        admin_id: str | None = payload.get("sub")
        if admin_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(
        select(CompanyAdmin).where(CompanyAdmin.id == uuid.UUID(admin_id))
    )
    admin = result.scalar_one_or_none()
    if admin is None or not admin.is_active:
        raise credentials_exception

    return TokenResponse(
        access_token=create_access_token(str(admin.id), str(admin.company_id)),
        refresh_token=create_refresh_token(str(admin.id)),
    )


@router.get("/me", response_model=AdminProfile)
async def me(current_admin: CompanyAdmin = Depends(get_current_admin)) -> AdminProfile:
    """Return the currently authenticated admin's profile."""
    return AdminProfile.model_validate(current_admin)
