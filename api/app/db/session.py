"""
Async SQLAlchemy engine + session factory.

The get_db() dependency yields an AsyncSession per request.
All DB I/O in the app must go through this session — no sync calls.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()

_is_sqlite = settings.database_url.startswith("sqlite")

# Pool size args only valid for PostgreSQL (not SQLite, which uses StaticPool)
_pool_kwargs = (
    {}
    if _is_sqlite
    else {"pool_size": 10, "max_overflow": 20}
)

engine = create_async_engine(
    settings.database_url,
    echo=settings.app_env == "development",
    pool_pre_ping=not _is_sqlite,
    **_pool_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a request-scoped AsyncSession."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
