import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_auditor_engagement_scope, get_current_auditor
from app.db.models.auditor import Auditor
from app.db.models.auditease import AuditEngagement, AuditEntry, AuditEntryLine, Ledger
from app.db.session import get_db

router = APIRouter(prefix="/api/v1/auditor/engagements", tags=["auditease-auditor"])

from sqlalchemy.orm import selectinload
from app.db.models.auditor import AuditorEngagementGrant
from datetime import datetime

class CompanyBase(BaseModel):
    id: uuid.UUID
    name: str
    cin: str
    model_config = {"from_attributes": True}

class AuditorEngagementResponse(BaseModel):
    id: uuid.UUID
    period_label: str
    status: str
    created_at: datetime
    company: CompanyBase
    model_config = {"from_attributes": True}

@router.get("", response_model=List[AuditorEngagementResponse])
async def list_engagements(
    current_auditor: Auditor = Depends(get_current_auditor),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(AuditEngagement)
        .join(AuditorEngagementGrant, AuditEngagement.id == AuditorEngagementGrant.engagement_id)
        .options(selectinload(AuditEngagement.company))
        .where(AuditorEngagementGrant.auditor_id == current_auditor.id)
    )
    return result.scalars().all()

@router.get("/{engagement_id}", response_model=AuditorEngagementResponse)
async def get_engagement(
    engagement: AuditEngagement = Depends(get_auditor_engagement_scope),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(AuditEngagement)
        .options(selectinload(AuditEngagement.company))
        .where(AuditEngagement.id == engagement.id)
    )
    return result.scalar_one()


@router.get("/{engagement_id}/trial-balance")
async def get_engagement_trial_balance(
    engagement: AuditEngagement = Depends(get_auditor_engagement_scope),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Ledger).where(Ledger.company_id == engagement.company_id)
    )
    return result.scalars().all()


class EntryLineInput(BaseModel):
    ledger_id: uuid.UUID
    side: str # debit, credit
    amount: float

class CreateEntryRequest(BaseModel):
    description: str
    lines: List[EntryLineInput]


@router.post("/{engagement_id}/entries")
async def create_entry(
    body: CreateEntryRequest,
    engagement: AuditEngagement = Depends(get_auditor_engagement_scope),
    current_auditor: Auditor = Depends(get_current_auditor),
    db: AsyncSession = Depends(get_db)
):
    # App-layer validation: sum(debit) == sum(credit)
    debits = sum(line.amount for line in body.lines if line.side == "debit")
    credits = sum(line.amount for line in body.lines if line.side == "credit")
    
    if abs(debits - credits) > 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Entry is unbalanced: Debits ({debits}) != Credits ({credits})"
        )
        
    entry = AuditEntry(
        engagement_id=engagement.id,
        company_id=engagement.company_id,
        created_by=current_auditor.id,
        description=body.description,
        status="proposed"
    )
    db.add(entry)
    await db.flush()
    
    for line_in in body.lines:
        line = AuditEntryLine(
            entry_id=entry.id,
            company_id=engagement.company_id,
            ledger_id=line_in.ledger_id,
            side=line_in.side,
            amount=line_in.amount
        )
        db.add(line)
        
    await db.commit()
    return {"message": "Entry submitted for approval", "entry_id": entry.id}

@router.get("/{engagement_id}/entries")
async def list_entries(
    engagement: AuditEngagement = Depends(get_auditor_engagement_scope),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(AuditEntry).where(AuditEntry.engagement_id == engagement.id)
    )
    return result.scalars().all()

@router.get("/{engagement_id}/statements")
async def get_statements(
    engagement: AuditEngagement = Depends(get_auditor_engagement_scope),
    db: AsyncSession = Depends(get_db)
):
    return {"message": "Draft Statements", "data": {}}
