"""Stats API routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meshcore_dashboard.models import (
    StatsDaily,
    StatsHourly,
    StatsSnapshot,
)
from meshcore_dashboard.schemas import (
    StatsHistoryResponse,
    StatsResponse,
)

router = APIRouter()

_session_factory_ref: async_sessionmaker[AsyncSession] | None = None

RESOLUTION_MAP = {
    "raw": StatsSnapshot,
    "hourly": StatsHourly,
    "daily": StatsDaily,
}

VALID_METRICS = {
    "battery_mv",
    "uptime_secs",
    "queue_len",
    "errors",
    "noise_floor",
    "last_rssi",
    "last_snr",
    "tx_air_secs",
    "rx_air_secs",
    "packets_recv",
    "packets_sent",
    "flood_rx",
    "flood_tx",
    "direct_rx",
    "direct_tx",
    "recv_errors",
}


def set_dependencies(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    global _session_factory_ref
    _session_factory_ref = session_factory


@router.get("/api/stats/current")
async def stats_current() -> StatsResponse | None:
    """Latest stats snapshot."""
    assert _session_factory_ref
    async with _session_factory_ref() as session:
        result = await session.execute(
            select(StatsSnapshot)
            .order_by(StatsSnapshot.timestamp.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        return StatsResponse(
            timestamp=row.timestamp,
            battery_mv=row.battery_mv,
            uptime_secs=row.uptime_secs,
            queue_len=row.queue_len,
            errors=row.errors,
            noise_floor=row.noise_floor,
            last_rssi=row.last_rssi,
            last_snr=row.last_snr,
            tx_air_secs=row.tx_air_secs,
            rx_air_secs=row.rx_air_secs,
            packets_recv=row.packets_recv,
            packets_sent=row.packets_sent,
            flood_rx=row.flood_rx,
            flood_tx=row.flood_tx,
            direct_rx=row.direct_rx,
            direct_tx=row.direct_tx,
            recv_errors=row.recv_errors,
        )


@router.get("/api/stats/history")
async def stats_history(
    metrics: str = Query(default=",".join(VALID_METRICS)),
    start: datetime | None = None,
    end: datetime | None = None,
    resolution: str = Query(default="raw"),
) -> StatsHistoryResponse:
    """Stats over time with selectable resolution and metrics."""
    assert _session_factory_ref

    model = RESOLUTION_MAP.get(resolution, StatsSnapshot)
    requested = {
        m.strip()
        for m in metrics.split(",")
        if m.strip() in VALID_METRICS
    }

    async with _session_factory_ref() as session:
        query = select(model).order_by(model.timestamp.asc())
        if start:
            query = query.where(model.timestamp >= start)
        if end:
            query = query.where(model.timestamp <= end)
        # Limit to prevent huge responses
        query = query.limit(10000)

        result = await session.execute(query)
        rows = result.scalars().all()

        data = []
        for row in rows:
            entry = StatsResponse(timestamp=row.timestamp)
            for metric in requested:
                setattr(entry, metric, getattr(row, metric))
            data.append(entry)

        return StatsHistoryResponse(data=data)
