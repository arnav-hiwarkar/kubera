"""
FastAPI dependencies for authentication and tenant scoping.

get_current_admin  — validates JWT, returns CompanyAdmin ORM object.
get_tenant_scope   — extracts company_id from the authenticated admin.
require_internal_key — guards internal-only endpoints.

CRITICAL INVARIANT:
  company_id must NEVER come from request body/path params in data queries.
  It MUST always come from get_tenant_scope(), which derives it from the
  authenticated token. This is the sole mechanism preventing cross-tenant
  data leakage.
"""
import uuid

from fastapi import Depends, Header, Path, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import decode_access_token, decode_auditor_access_token
from app.db.models.company_admin import CompanyAdmin
from app.db.models.auditor import Auditor, AuditorEngagementGrant
from app.db.models.auditease import AuditEngagement
from app.db.session import get_db

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", scheme_name="Company_Admin_Auth")
auditor_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auditor/auth/login", scheme_name="Auditor_Auth")

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_admin(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> CompanyAdmin:
    """
    Validate the Bearer token and return the CompanyAdmin.
    Raises HTTP 401 for any invalid / expired / malformed token.
    """
    try:
        payload = decode_access_token(token)
        admin_id: str | None = payload.get("sub")
        if admin_id is None:
            raise _CREDENTIALS_EXCEPTION
    except JWTError:
        raise _CREDENTIALS_EXCEPTION

    result = await db.execute(
        select(CompanyAdmin).where(CompanyAdmin.id == uuid.UUID(admin_id))
    )
    admin = result.scalar_one_or_none()
    if admin is None or not admin.is_active:
        raise _CREDENTIALS_EXCEPTION

    return admin


async def get_tenant_scope(
    current_admin: CompanyAdmin = Depends(get_current_admin),
) -> uuid.UUID:
    """
    Returns the authenticated admin's company_id.

    Every protected endpoint that queries company-owned data MUST
    call this dependency and use the returned company_id as a
    mandatory WHERE filter. Example:

        company_id: uuid.UUID = Depends(get_tenant_scope)
        rows = await db.execute(
            select(SomeModel).where(SomeModel.company_id == company_id)
        )

    Never trust a company_id from the request body or path.
    """
    return current_admin.company_id


async def require_internal_key(
    x_internal_key: str = Header(..., alias="X-Internal-Key"),
) -> None:
    """
    Guards internal-only endpoints (e.g. creating Company + CompanyAdmin).
    Compares the header value against INTERNAL_API_KEY using a
    constant-time comparison to prevent timing attacks.
    """
    import hmac

    expected = settings.internal_api_key.encode()
    provided = x_internal_key.encode()
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal API key",
        )


async def get_current_auditor(
    token: str = Depends(auditor_oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Auditor:
    try:
        payload = decode_auditor_access_token(token)
        auditor_id: str | None = payload.get("sub")
        if auditor_id is None:
            raise _CREDENTIALS_EXCEPTION
    except JWTError:
        raise _CREDENTIALS_EXCEPTION

    result = await db.execute(
        select(Auditor).where(Auditor.id == uuid.UUID(auditor_id))
    )
    auditor = result.scalar_one_or_none()
    if auditor is None or not auditor.is_active:
        raise _CREDENTIALS_EXCEPTION

    return auditor


async def get_auditor_engagement_scope(
    engagement_id: uuid.UUID = Path(..., description="The engagement ID"),
    current_auditor: Auditor = Depends(get_current_auditor),
    db: AsyncSession = Depends(get_db),
) -> AuditEngagement:
    grant_result = await db.execute(
        select(AuditorEngagementGrant).where(
            AuditorEngagementGrant.auditor_id == current_auditor.id,
            AuditorEngagementGrant.engagement_id == engagement_id
        )
    )
    if grant_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this engagement",
        )
    
    eng_result = await db.execute(
        select(AuditEngagement).where(AuditEngagement.id == engagement_id)
    )
    engagement = eng_result.scalar_one_or_none()
    
    if not engagement or engagement.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This engagement is not active or does not exist",
        )
        
    return engagement
