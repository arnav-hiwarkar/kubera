#!/usr/bin/env python3
"""
CLI seed script — create a Company + CompanyAdmin.

Usage (from inside api/ directory, or Docker container):
    python scripts/seed_admin.py \\
        --company-name "Acme Pvt Ltd" \\
        --cin "U12345MH2020PTC123456" \\
        --email "admin@acme.com" \\
        --password "s3cr3t!"

Environment: reads DATABASE_URL from .env (or environment).
"""
import argparse
import asyncio
import sys
import uuid

# Ensure the app package is importable when run from api/
sys.path.insert(0, ".")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.core.security import hash_password
from app.db.models.company import Company
from app.db.models.company_admin import CompanyAdmin


async def seed(
    company_name: str,
    cin: str,
    email: str,
    password: str,
) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        async with session.begin():
            # Guard: duplicate CIN
            res = await session.execute(select(Company).where(Company.cin == cin))
            if res.scalar_one_or_none():
                print(f"[ERROR] Company with CIN {cin!r} already exists.")
                return

            # Guard: duplicate email
            res = await session.execute(
                select(CompanyAdmin).where(CompanyAdmin.email == email)
            )
            if res.scalar_one_or_none():
                print(f"[ERROR] Admin with email {email!r} already exists.")
                return

            company = Company(id=uuid.uuid4(), name=company_name, cin=cin)
            session.add(company)
            await session.flush()

            admin = CompanyAdmin(
                id=uuid.uuid4(),
                company_id=company.id,
                email=email,
                hashed_password=hash_password(password),
            )
            session.add(admin)

    print(f"[OK] Company created:       {company.id}")
    print(f"[OK] CompanyAdmin created:  {admin.id}")
    print(f"     email:                 {email}")
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a Kubera Company + CompanyAdmin")
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--cin", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    asyncio.run(
        seed(
            company_name=args.company_name,
            cin=args.cin,
            email=args.email,
            password=args.password,
        )
    )


if __name__ == "__main__":
    main()
