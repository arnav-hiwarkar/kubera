import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models.auditease import LedgerGroup, Ledger, AuditEngagement, AuditEntry, AuditEntryLine
from app.db.models.auditor import Auditor, AuditorEngagementGrant
from app.core.security import create_auditor_access_token


@pytest.fixture
async def seeded_ledger_groups(db_session: AsyncSession):
    groups = [
        LedgerGroup(name="Share Capital", schedule_iii_category="Standard"),
        LedgerGroup(name="Revenue from operations", schedule_iii_category="Standard")
    ]
    db_session.add_all(groups)
    await db_session.commit()
    for g in groups:
        await db_session.refresh(g)
    return groups


@pytest.mark.asyncio
async def test_tb_import_validates_balances(
    client: AsyncClient,
    company_a_setup
):
    company, admin, admin_token = company_a_setup
    
    csv_content = (
        "ledger_code,ledger_name,opening_balance,debit,credit,closing_balance\n"
        "1001,Cash,100,50,20,130\n" # matches
        "1002,Bank,200,0,0,300\n"   # warns: expected 200, got 300
    )
    
    files = {"file": ("tb.csv", csv_content.encode("utf-8"), "text/csv")}
    
    resp = await client.post(
        "/api/v1/auditease/trial-balance/import",
        headers={"Authorization": f"Bearer {admin_token}"},
        files=files
    )
    
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "Imported 2 ledgers"
    assert len(data["warnings"]) == 1
    assert "Bank" in data["warnings"][0]


@pytest.mark.asyncio
async def test_ledger_group_mapping(
    client: AsyncClient,
    db_session: AsyncSession,
    company_a_setup,
    seeded_ledger_groups
):
    company, admin, admin_token = company_a_setup
    ledger = Ledger(
        company_id=company.id,
        ledger_name="Test Ledger"
    )
    db_session.add(ledger)
    await db_session.commit()
    await db_session.refresh(ledger)
    
    group = seeded_ledger_groups[0]
    
    resp = await client.post(
        f"/api/v1/auditease/ledgers/{ledger.id}/map-group?group_id={group.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    
    await db_session.refresh(ledger)
    assert ledger.group_id == group.id


@pytest.fixture
async def auditor_and_token(db_session: AsyncSession):
    uid = str(uuid.uuid4())[:5]
    auditor = Auditor(email=f"test_{uid}@auditor.com", hashed_password="x")
    db_session.add(auditor)
    await db_session.commit()
    await db_session.refresh(auditor)
    token = create_auditor_access_token(str(auditor.id))
    return auditor, token


@pytest.mark.asyncio
async def test_engagement_scoped_access(
    client: AsyncClient,
    db_session: AsyncSession,
    company_a_setup,
    auditor_and_token
):
    company, _, _ = company_a_setup
    auditor, auditor_token = auditor_and_token
    
    # Engagement in Company A
    eng = AuditEngagement(company_id=company.id, period_label="A", status="active")
    db_session.add(eng)
    await db_session.commit()
    await db_session.refresh(eng)
    
    eng_id = eng.id
    auditor_id = auditor.id
    
    # 1. No grant -> reject
    resp = await client.get(
        f"/api/v1/auditor/engagements/{eng_id}/trial-balance",
        headers={"Authorization": f"Bearer {auditor_token}"}
    )
    assert resp.status_code == 403
    
    # 2. Add grant -> success
    grant = AuditorEngagementGrant(auditor_id=auditor_id, engagement_id=eng_id)
    db_session.add(grant)
    await db_session.commit()
    
    resp = await client.get(
        f"/api/v1/auditor/engagements/{eng_id}/trial-balance",
        headers={"Authorization": f"Bearer {auditor_token}"}
    )
    assert resp.status_code == 200
    
    # 3. Status closed -> reject on any endpoint enforcing 'active'
    eng_res = await db_session.execute(select(AuditEngagement).where(AuditEngagement.id == eng_id))
    eng_refetched = eng_res.scalar_one()
    eng_refetched.status = "closed"
    await db_session.commit()
    
    resp = await client.get(
        f"/api/v1/auditor/engagements/{eng_id}/trial-balance",
        headers={"Authorization": f"Bearer {auditor_token}"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_debit_credit_validation(
    client: AsyncClient,
    db_session: AsyncSession,
    company_a_setup,
    auditor_and_token
):
    company, _, _ = company_a_setup
    auditor, auditor_token = auditor_and_token
    
    eng = AuditEngagement(company_id=company.id, period_label="FY", status="active")
    db_session.add(eng)
    await db_session.commit()
    await db_session.refresh(eng)
    
    eng_id = eng.id
    auditor_id = auditor.id
    
    grant = AuditorEngagementGrant(auditor_id=auditor_id, engagement_id=eng_id)
    db_session.add(grant)
    
    ledger1 = Ledger(company_id=company.id, ledger_name="L1")
    ledger2 = Ledger(company_id=company.id, ledger_name="L2")
    db_session.add_all([ledger1, ledger2])
    await db_session.commit()
    await db_session.refresh(ledger1)
    await db_session.refresh(ledger2)
    
    ledger1_id = str(ledger1.id)
    ledger2_id = str(ledger2.id)
    
    # Unbalanced entry
    payload = {
        "description": "Test Entry",
        "lines": [
            {"ledger_id": ledger1_id, "side": "debit", "amount": 100},
            {"ledger_id": ledger2_id, "side": "credit", "amount": 90}
        ]
    }
    
    resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/entries",
        headers={"Authorization": f"Bearer {auditor_token}"},
        json=payload
    )
    assert resp.status_code == 400
    assert "unbalanced" in resp.json()["detail"].lower()
    
    # Balanced entry
    payload["lines"][1]["amount"] = 100
    resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/entries",
        headers={"Authorization": f"Bearer {auditor_token}"},
        json=payload
    )
    assert resp.status_code == 200
