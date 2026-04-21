"""Packet log API routes."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meshcore_dashboard.models import PacketLog
from meshcore_dashboard.schemas import PacketLogEntry
from meshcore_dashboard.serial.connection import RepeaterConnection

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
            .order_by(PacketLog.collected_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = result.scalars().all()
        return [
            PacketLogEntry(
                id=row.id,
                collected_at=row.collected_at,
                raw_line=row.raw_line,
                fingerprint=row.fingerprint,
                parse_status=row.parse_status,
                direction=row.direction,
                packet_type=row.packet_type,
                route=row.route,
                payload_len=row.payload_len,
                snr=row.snr,
                rssi=row.rssi,
                device_time_text=row.device_time_text,
                device_date_text=row.device_date_text,
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

    from meshcore_dashboard.services.log_collector import LogCollector

    raw = await _connection_ref.send_command("log", timeout=10.0)

    async with _session_factory_ref() as session:
        result = await session.execute(
            select(PacketLog.fingerprint).where(PacketLog.fingerprint.is_not(None))
        )
        prior_fps = {row[0] for row in result}

    collector = LogCollector()
    collection = collector.process_buffer(raw, prior_fingerprints=prior_fps)

    if collection.parsed_lines:
        now = datetime.now(UTC)
        entries = [
            PacketLog(
                collected_at=now,
                raw_line=p.raw_line,
                fingerprint=p.fingerprint,
                parse_status=p.parse_status,
                direction=p.direction,
                packet_type=p.packet_type,
                route=p.route,
                payload_len=p.payload_len,
                snr=p.snr,
                rssi=p.rssi,
                device_time_text=p.device_time_text,
                device_date_text=p.device_date_text,
            )
            for p in collection.parsed_lines
        ]
        async with _session_factory_ref() as session:
            session.add_all(entries)
            await session.commit()

    return {
        "detail": (
            f"Fetched {collection.lines_seen} lines,"
            f" inserted {collection.inserted},"
            f" skipped {collection.duplicates_skipped} duplicates"
        )
    }


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
