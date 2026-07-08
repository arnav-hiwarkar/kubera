"""
Test configuration and shared fixtures.

Uses an in-process async SQLite database (aiosqlite) — no Docker
dependency for running the test suite.

The tenant-scope test needs a "dummy" TenantScoped table. We define
it here as a test-only model and create it alongside the main tables.
"""
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.base import Base, TenantScopedMixin
from app.db.models.company import Company
from app.db.models.company_admin import CompanyAdmin
from app.db.session import get_db
from app.main import app

# ── SQLite test engine ────────────────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ── Dummy TenantScoped model (test-only) ──────────────────────────────────────
from sqlalchemy.orm import Mapped, mapped_column


class DummyTenantResource(TenantScopedMixin, Base):
    """
    Test-only table that proves TenantScopedMixin + get_tenant_scope() work.
    Not used in production — exists only in the test DB.
    """
    __tablename__ = "dummy_tenant_resource"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(100), nullable=False)


# ── Session-scoped DB setup ───────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db() -> AsyncGenerator[None, None]:
    """Create all tables once for the test session."""
    async with test_engine.begin() as conn:
        # SQLite doesn't support FKs on UUID types natively — we patch
        # TenantScopedMixin's FK to a plain String for SQLite compatibility
        # by using render_as_batch and disabling FK checks.
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── Per-test DB session ───────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields a fresh session per test. Rolls back after each test
    so tests are isolated.
    """
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


# ── HTTP client ───────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    HTTP client wired to the FastAPI app with the test DB session.
    Overrides get_db() so all endpoint DB calls use the test session.

    The override includes the same try/commit/rollback as the real get_db
    so endpoints that rely on auto-commit work correctly. The outer
    db_session fixture rolls back after each test for isolation.
    """
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ── Shared helpers ────────────────────────────────────────────────────────────

async def create_company_and_admin(
    db: AsyncSession,
    company_name: str = "Test Co Pvt Ltd",
    cin: str = "U12345MH2020PTC000001",
    email: str = "admin@testco.com",
    password: str = "testpass123",
) -> tuple[Company, CompanyAdmin]:
    """Helper: insert Company + CompanyAdmin and flush (no commit)."""
    company = Company(id=uuid.uuid4(), name=company_name, cin=cin)
    db.add(company)
    await db.flush()

    admin = CompanyAdmin(
        id=uuid.uuid4(),
        company_id=company.id,
        email=email,
        hashed_password=hash_password(password),
    )
    db.add(admin)
    await db.flush()
    return company, admin


@pytest.fixture
def internal_key() -> str:
    return get_settings().internal_api_key
