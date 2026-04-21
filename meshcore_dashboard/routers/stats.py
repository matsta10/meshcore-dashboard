"""Stats API routes."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from meshcore_dashboard.services.poller import Poller

from meshcore_dashboard.models import (
    StatsDaily,
    StatsHourly,
    StatsSnapshot,
)
from meshcore_dashboard.schemas import (
    CommandHealthResponse,
    StatsHistoryResponse,
    StatsResponse,
)

router = APIRouter()

_session_factory_ref: async_sessionmaker[AsyncSession] | None = None
_poller_ref: Poller | None = None

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
    poller: Poller | None = None,
) -> None:
    global _session_factory_ref, _poller_ref
    _session_factory_ref = session_factory
    _poller_ref = poller


@router.get("/api/stats/current")
async def stats_current() -> StatsResponse | None:
    """Latest stats snapshot."""
    assert _session_factory_ref
    async with _session_factory_ref() as session:
        result = await session.execute(
            select(StatsSnapshot).order_by(StatsSnapshot.timestamp.desc()).limit(1)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        stale = _poller_ref.is_stale if _poller_ref else False
        stats_health = (
            {
                cmd: CommandHealthResponse(
                    ok=bool(data["ok"]),
                    last_success_at=data["last_success_at"],  # type: ignore[arg-type]
                    last_error=data["last_error"],  # type: ignore[arg-type]
                )
                for cmd, data in _poller_ref.stats_health.items()
            }
            if _poller_ref
            else {}
        )
        freshness = _poller_ref.stats_freshness if _poller_ref else "fresh"
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
            stale=stale,
            freshness=freshness,
            stale_reason=_poller_ref.last_parse_error if _poller_ref else None,
            stats_health=stats_health,
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
    requested = {m.strip() for m in metrics.split(",") if m.strip() in VALID_METRICS}

    async with _session_factory_ref() as session:
        async def load_rows(selected_model: type[StatsSnapshot]) -> list[StatsSnapshot]:
            query = select(selected_model).order_by(selected_model.timestamp.asc())
            if start:
                query = query.where(selected_model.timestamp >= start)
            if end:
                query = query.where(selected_model.timestamp <= end)
            query = query.limit(10000)
            result = await session.execute(query)
            return list(result.scalars().all())

        rows = await load_rows(model)
        if resolution == "hourly" and not rows:
            rows = await load_rows(StatsSnapshot)

        data = []
        for row in rows:
            entry = StatsResponse(timestamp=row.timestamp)
            for metric in requested:
                setattr(entry, metric, getattr(row, metric))
            data.append(entry)

        return StatsHistoryResponse(data=data)
