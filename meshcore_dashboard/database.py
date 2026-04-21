"""Database engine and session factory."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from meshcore_dashboard.models import Base
from meshcore_dashboard.serial.parser import parse_log_line

logger = logging.getLogger(__name__)

# Columns to add to packet_logs if missing (name, type).
_PACKET_LOG_MIGRATIONS: list[tuple[str, str]] = [
    ("total_len", "INTEGER"),
    ("score", "INTEGER"),
    ("src_addr", "TEXT"),
    ("dst_addr", "TEXT"),
]


async def _migrate_packet_logs(conn) -> None:  # type: ignore[no-untyped-def]
    """Add missing columns to packet_logs table."""
    result = await conn.execute(text("PRAGMA table_info(packet_logs)"))
    existing = {row[1] for row in result.fetchall()}
    for col_name, col_type in _PACKET_LOG_MIGRATIONS:
        if col_name not in existing:
            await conn.execute(
                text(f"ALTER TABLE packet_logs ADD COLUMN {col_name} {col_type}")
            )
            logger.info("Added column packet_logs.%s", col_name)


async def _backfill_new_fields(conn) -> None:  # type: ignore[no-untyped-def]
    """Re-parse existing rows to populate newly added columns."""
    result = await conn.execute(
        text(
            "SELECT id, raw_line FROM packet_logs "
            "WHERE total_len IS NULL AND parse_status = 'parsed' "
            "LIMIT 5000"
        )
    )
    rows = result.fetchall()
    if not rows:
        return
    updated = 0
    for row_id, raw_line in rows:
        parsed = parse_log_line(raw_line)
        if parsed.parse_status != "parsed":
            continue
        await conn.execute(
            text(
                "UPDATE packet_logs SET "
                "total_len = :total_len, score = :score, "
                "src_addr = :src_addr, dst_addr = :dst_addr "
                "WHERE id = :id"
            ),
            {
                "id": row_id,
                "total_len": parsed.total_len,
                "score": parsed.score,
                "src_addr": parsed.src_addr,
                "dst_addr": parsed.dst_addr,
            },
        )
        updated += 1
    if updated:
        logger.info("Backfilled %d packet_logs rows with new fields", updated)


async def create_engine_and_tables(
    url: str = "sqlite+aiosqlite:///data/meshcore.db",
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Create engine with WAL mode and initialize all tables."""
    engine = create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_packet_logs(conn)
        await _backfill_new_fields(conn)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory
