"""Packet log API routes."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meshcore_dashboard.models import LogCollectionState, PacketLog
from meshcore_dashboard.schemas import PacketLogEntry
from meshcore_dashboard.serial.connection import RepeaterConnection
from meshcore_dashboard.services.log_collector import LogCollector

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


async def _load_prior_fingerprints() -> set[str]:
    """Load the prior buffer snapshot fingerprints for idempotent ingestion."""
    assert _session_factory_ref
    async with _session_factory_ref() as session:
        state = await session.get(LogCollectionState, 1)
        if state and state.last_snapshot_json:
            return set(json.loads(state.last_snapshot_json))
    return set()


async def _update_collection_state(
    collection: LogCollector,  # type: ignore[type-arg]
    *,
    lines_seen: int,
    all_fingerprints: list[str],
    inserted: int,
    buffer_hash: str,
) -> None:
    """Persist manual-fetch collection state using the same semantics as the poller."""
    assert _session_factory_ref
    now = datetime.now(UTC)
    async with _session_factory_ref() as session:
        state = await session.get(LogCollectionState, 1)
        if state is None:
            state = LogCollectionState(id=1)
            session.add(state)

        state.last_polled_at = now
        state.last_buffer_hash = buffer_hash
        state.last_buffer_size = lines_seen
        if all_fingerprints:
            state.last_snapshot_json = json.dumps(all_fingerprints)

        if inserted > 0:
            state.last_new_entry_at = now
            state.unchanged_buffer_count = 0
        else:
            state.unchanged_buffer_count = (state.unchanged_buffer_count or 0) + 1

        await session.commit()


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

    raw = await _connection_ref.send_command("log", timeout=10.0)
    prior_fps = await _load_prior_fingerprints()

    collector = LogCollector()
    collection = collector.process_buffer(raw, prior_fingerprints=prior_fps)

    inserted = 0
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
            try:
                await session.commit()
                inserted = len(entries)
            except IntegrityError:
                await session.rollback()
                # Idempotent fallback: insert row-by-row so pre-existing
                # fingerprints are skipped without failing the whole fetch.
                for entry in entries:
                    session.add(entry)
                    try:
                        await session.commit()
                        inserted += 1
                    except IntegrityError:
                        await session.rollback()

    await _update_collection_state(
        collector,
        lines_seen=collection.lines_seen,
        all_fingerprints=collection.all_fingerprints,
        inserted=inserted,
        buffer_hash=collection.buffer_hash,
    )

    return {
        "detail": (
            f"Fetched {collection.lines_seen} lines,"
            f" inserted {inserted},"
            f" skipped {collection.lines_seen - inserted} duplicates"
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
