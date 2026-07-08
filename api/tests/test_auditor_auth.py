import uuid
from datetime import datetime, timezone, timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models.auditor import Auditor, AuditorInvite, AuditorEngagementGrant
from app.db.models.auditease import AuditEngagement
from app.core.security import hash_password

@pytest.fixture
async def sample_engagement(db_session: AsyncSession, company_a_setup):
    company, admin, token = company_a_setup
    eng = AuditEngagement(
        company_id=company.id,
        period_label="FY2025",
        status="invited"
    )
    db_session.add(eng)
    await db_session.commit()
    await db_session.refresh(eng)
    return eng


@pytest.mark.asyncio
async def test_auditor_invite_flow_new_account(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_engagement
):
    # Setup invite
    uid = str(uuid.uuid4())[:5]
    email = f"newauditor_{uid}@example.com"
    invite = AuditorInvite(
        email=email,
        token="token_123",
        engagement_id=sample_engagement.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1)
    )
    db_session.add(invite)
    await db_session.commit()

    # Accept invite
    resp = await client.post(
        "/api/v1/auditor/auth/accept-invite",
        json={"token": "token_123", "password": "supersecretpassword"}
    )
    assert resp.status_code == 200

    # Verify auditor created
    aud_res = await db_session.execute(select(Auditor).where(Auditor.email == email))
    auditor = aud_res.scalar_one()
    assert auditor is not None

    # Verify grant added
    grant_res = await db_session.execute(
        select(AuditorEngagementGrant).where(AuditorEngagementGrant.auditor_id == auditor.id)
    )
    grant = grant_res.scalar_one()
    assert grant.engagement_id == sample_engagement.id

    # Verify engagement status became active
    await db_session.refresh(sample_engagement)
    assert sample_engagement.status == "active"


@pytest.mark.asyncio
async def test_auditor_invite_flow_existing_account(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_engagement
):
    uid = str(uuid.uuid4())[:5]
    email = f"existauditor_{uid}@example.com"
    existing_auditor = Auditor(
        email=email,
        hashed_password=hash_password("oldpassword")
    )
    db_session.add(existing_auditor)
    await db_session.commit()
    await db_session.refresh(existing_auditor)
    old_hash = existing_auditor.hashed_password

    # Setup invite
    invite = AuditorInvite(
        email=email,
        token="token_456",
        engagement_id=sample_engagement.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1)
    )
    db_session.add(invite)
    await db_session.commit()

    # Accept invite WITHOUT password
    resp = await client.post(
        "/api/v1/auditor/auth/accept-invite",
        json={"token": "token_456"}
    )
    assert resp.status_code == 200

    # Verify grant added
    grant_res = await db_session.execute(
        select(AuditorEngagementGrant).where(AuditorEngagementGrant.auditor_id == existing_auditor.id)
    )
    grant = grant_res.scalar_one()
    assert grant.engagement_id == sample_engagement.id
    
    # Verify password hasn't changed
    await db_session.refresh(existing_auditor)
    assert existing_auditor.hashed_password == old_hash


@pytest.mark.asyncio
async def test_auditor_invite_expired(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_engagement
):
    invite = AuditorInvite(
        email="expired@example.com",
        token="token_expired",
        engagement_id=sample_engagement.id,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1)
    )
    db_session.add(invite)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/auditor/auth/accept-invite",
        json={"token": "token_expired", "password": "pass"}
    )
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cross_auth_rejection(
    client: AsyncClient,
    db_session: AsyncSession,
    company_a_setup,
    sample_engagement
):
    company, admin, admin_token = company_a_setup
    
    # 1. CompanyAdmin on Auditor route should fail
    resp = await client.get(
        f"/api/v1/auditor/engagements/{sample_engagement.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 401
    
    # Setup an auditor token
    from app.core.security import create_auditor_access_token
    uid = str(uuid.uuid4())[:5]
    auditor = Auditor(email=f"test_{uid}@auditor.com", hashed_password="x")
    db_session.add(auditor)
    await db_session.commit()
    auditor_token = create_auditor_access_token(str(auditor.id))
    
    # 2. Auditor on CompanyAdmin route should fail
    resp = await client.get(
        "/api/v1/auditease/trial-balance",
        headers={"Authorization": f"Bearer {auditor_token}"}
    )
    assert resp.status_code == 401
