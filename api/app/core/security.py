"""
Security utilities: password hashing and JWT encode/decode.

Two-secret JWT design:
  - Access tokens:  signed with SECRET_KEY, short-lived (30 min)
  - Refresh tokens: signed with REFRESH_SECRET_KEY, long-lived (7 days)

A leaked access token cannot forge a refresh token because they use
different secrets. Token payloads carry `principal_type` so future
auditor tokens (§2.2) can never be accepted by company-side endpoints.
"""
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Token types ───────────────────────────────────────────────────────────────
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"
PRINCIPAL_TYPE_COMPANY_ADMIN = "company_admin"


# ── Password hashing ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(admin_id: str, company_id: str) -> str:
    """
    Create a short-lived access token.
    Payload: sub, company_id, principal_type, type, exp.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": admin_id,
        "company_id": company_id,
        "principal_type": PRINCIPAL_TYPE_COMPANY_ADMIN,
        "type": TOKEN_TYPE_ACCESS,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(admin_id: str) -> str:
    """
    Create a long-lived refresh token.
    Signed with a SEPARATE key — a leaked access token cannot forge a refresh.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    payload = {
        "sub": admin_id,
        "principal_type": PRINCIPAL_TYPE_COMPANY_ADMIN,
        "type": TOKEN_TYPE_REFRESH,
        "exp": expire,
    }
    return jwt.encode(
        payload, settings.refresh_secret_key, algorithm=settings.algorithm
    )


def decode_access_token(token: str) -> dict:
    """
    Decode and validate an access token.
    Raises JWTError on failure (caller converts to HTTP 401).
    """
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise JWTError("Not an access token")
    if payload.get("principal_type") != PRINCIPAL_TYPE_COMPANY_ADMIN:
        raise JWTError("Wrong principal type")
    return payload


def decode_refresh_token(token: str) -> dict:
    """
    Decode and validate a refresh token.
    Raises JWTError on failure.
    """
    payload = jwt.decode(
        token, settings.refresh_secret_key, algorithms=[settings.algorithm]
    )
    if payload.get("type") != TOKEN_TYPE_REFRESH:
        raise JWTError("Not a refresh token")
    if payload.get("principal_type") != PRINCIPAL_TYPE_COMPANY_ADMIN:
        raise JWTError("Wrong principal type")
    return payload
