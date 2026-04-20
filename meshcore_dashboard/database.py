"""Database engine and session factory."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from meshcore_dashboard.models import Base


async def create_engine_and_tables(
    url: str = "sqlite+aiosqlite:///data/meshcore.db",
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Create engine with WAL mode and initialize all tables."""
    engine = create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, expire_on_commit=False
    )
    return engine, session_factory
