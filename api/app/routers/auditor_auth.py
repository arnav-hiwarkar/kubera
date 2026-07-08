import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_auditor
from app.core.security import (
    create_auditor_access_token,
    create_auditor_refresh_token,
    decode_auditor_refresh_token,
    hash_password,
    verify_password,
)
from app.db.models.auditor import Auditor, AuditorEngagementGrant, AuditorInvite
from app.db.session import get_db

router = APIRouter(prefix="/api/v1/auditor/auth", tags=["auditor-auth"])


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AcceptInviteRequest(BaseModel):
    token: str
    password: Optional[str] = None


class AuditorProfile(BaseModel):
    id: uuid.UUID
    email: str
    is_active: bool
    model_config = {"from_attributes": True}


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await db.execute(
        select(Auditor).where(Auditor.email == form_data.username)
    )
    auditor = result.scalar_one_or_none()

    if auditor is None or not verify_password(form_data.password, auditor.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not auditor.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    return TokenResponse(
        access_token=create_auditor_access_token(str(auditor.id)),
        refresh_token=create_auditor_refresh_token(str(auditor.id)),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_auditor_refresh_token(body.refresh_token)
        auditor_id: str | None = payload.get("sub")
        if auditor_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(
        select(Auditor).where(Auditor.id == uuid.UUID(auditor_id))
    )
    auditor = result.scalar_one_or_none()
    if auditor is None or not auditor.is_active:
        raise credentials_exception

    return TokenResponse(
        access_token=create_auditor_access_token(str(auditor.id)),
        refresh_token=create_auditor_refresh_token(str(auditor.id)),
    )


@router.post("/accept-invite")
async def accept_invite(
    body: AcceptInviteRequest,
    db: AsyncSession = Depends(get_db)
):
    # Find invite
    inv_result = await db.execute(
        select(AuditorInvite).where(AuditorInvite.token == body.token)
    )
    invite = inv_result.scalar_one_or_none()
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invalid invite token")
        
    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invite has expired")
        
    # Check if auditor already exists
    aud_result = await db.execute(
        select(Auditor).where(Auditor.email == invite.email)
    )
    auditor = aud_result.scalar_one_or_none()
    
    if auditor:
        # Existing auditor: skip password, just add grant
        pass
    else:
        # New auditor: require password
        if not body.password:
            raise HTTPException(status_code=400, detail="Password is required for new accounts")
        
        auditor = Auditor(
            email=invite.email,
            hashed_password=hash_password(body.password),
        )
        db.add(auditor)
        await db.flush()  # to get auditor.id
        
    # Add grant
    grant = AuditorEngagementGrant(
        auditor_id=auditor.id,
        engagement_id=invite.engagement_id
    )
    db.add(grant)
    
    # Update engagement status to active
    from app.db.models.auditease import AuditEngagement
    eng_result = await db.execute(
        select(AuditEngagement).where(AuditEngagement.id == invite.engagement_id)
    )
    engagement = eng_result.scalar_one_or_none()
    if engagement and engagement.status == "invited":
        engagement.status = "active"
    
    # Consume invite
    await db.delete(invite)
    
    await db.commit()
    return {"message": "Invite accepted successfully"}


@router.get("/me", response_model=AuditorProfile)
async def me(current_auditor: Auditor = Depends(get_current_auditor)) -> AuditorProfile:
    return AuditorProfile.model_validate(current_auditor)
