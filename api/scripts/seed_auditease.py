import asyncio
from app.db.session import SessionLocal
from app.db.models.auditease import LedgerGroup

async def seed_ledger_groups():
    groups = [
        "Share Capital",
        "Reserves and Surplus",
        "Long-term borrowings",
        "Trade payables",
        "Property, Plant and Equipment",
        "Inventories",
        "Trade receivables",
        "Cash and cash equivalents",
        "Revenue from operations",
        "Other income",
        "Employee benefits expense",
        "Finance costs",
        "Other expenses",
    ]
    
    async with SessionLocal() as db:
        for group in groups:
            db.add(LedgerGroup(name=group, schedule_iii_category="Standard"))
        await db.commit()
    print(f"Seeded {len(groups)} Schedule III groups.")

if __name__ == "__main__":
    asyncio.run(seed_ledger_groups())
