"""Packet log API routes."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meshcore_dashboard.models import PacketLog
from meshcore_dashboard.schemas import PacketLogEntry
from meshcore_dashboard.serial.connection import RepeaterConnection
from meshcore_dashboard.serial.parser import parse_log_lines

router = APIRouter()

_session_factory_ref: async_sessionmaker[AsyncSession] | None = None
_connection_ref: RepeaterConnection | None = None


def set_dependencies(
    connection: RepeaterConnection,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    global _connection_ref, _session_factory_ref
    _connection_ref = connection
    _session_factory_ref = session_factory


@router.get("/api/logs")
async def get_logs(
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0),
) -> list[PacketLogEntry]:
    """Paginated packet logs."""
    assert _session_factory_ref
    async with _session_factory_ref() as session:
        result = await session.execute(
            select(PacketLog)
            .order_by(PacketLog.timestamp.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = result.scalars().all()
        return [
            PacketLogEntry(
                id=row.id,
                timestamp=row.timestamp,
                raw_line=row.raw_line,
            )
            for row in rows
        ]


@router.post("/api/logs/start")
async def start_logging() -> dict:
    """Start logging on device."""
    assert _connection_ref
    await _connection_ref.send_command("log start", timeout=3.0)
    return {"detail": "Logging started"}


@router.post("/api/logs/stop")
async def stop_logging() -> dict:
    """Stop logging on device."""
    assert _connection_ref
    await _connection_ref.send_command("log stop", timeout=3.0)
    return {"detail": "Logging stopped"}


@router.post("/api/logs/fetch")
async def fetch_logs() -> dict:
    """Pull log from device and store in DB."""
    assert _connection_ref
    assert _session_factory_ref

    raw = await _connection_ref.send_command("log", timeout=10.0)
    lines = parse_log_lines(raw)
    now = datetime.now(UTC)

    async with _session_factory_ref() as session:
        for line in lines:
            session.add(PacketLog(timestamp=now, raw_line=line))
        await session.commit()

    return {"detail": f"Fetched {len(lines)} log entries"}


@router.post("/api/logs/erase")
async def erase_logs(confirm: bool = False) -> dict:
    """Erase device log. Requires confirm=true."""
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Must pass confirm=true to erase logs",
        )
    assert _connection_ref
    await _connection_ref.send_command("log erase", timeout=10.0)
    return {"detail": "Device logs erased"}
