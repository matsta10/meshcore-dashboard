"""Health and status API routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import APIRouter, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meshcore_dashboard.models import DeviceInfo, LogCollectionState
from meshcore_dashboard.schemas import (
    CommandHealthResponse,
    DeviceInfoResponse,
    HealthResponse,
    LogCollectorHealthResponse,
    StatusResponse,
    TelemetryHealthResponse,
)
from meshcore_dashboard.serial.connection import RepeaterConnection

if TYPE_CHECKING:
    from meshcore_dashboard.services.poller import Poller

router = APIRouter()

_last_poll_time: datetime | None = None
_connection_ref: RepeaterConnection | None = None
_session_factory_ref: async_sessionmaker[AsyncSession] | None = None
_poller_ref: Poller | None = None


def set_dependencies(
    connection: RepeaterConnection,
    session_factory: async_sessionmaker[AsyncSession],
    poller: Poller | None = None,
) -> None:
    """Wire up dependencies from app lifespan."""
    global _connection_ref, _session_factory_ref, _poller_ref
    _connection_ref = connection
    _session_factory_ref = session_factory
    _poller_ref = poller


def update_last_poll() -> None:
    """Called by poller after successful poll."""
    global _last_poll_time
    _last_poll_time = datetime.now(UTC)


@router.get("/api/health")
async def health(response: Response) -> HealthResponse:
    """Returns 200 if last poll <5min ago, 503 otherwise."""
    if _last_poll_time is None or (
        datetime.now(UTC) - _last_poll_time > timedelta(minutes=5)
    ):
        response.status_code = 503
        return HealthResponse(status="unhealthy", last_poll=_last_poll_time)
    return HealthResponse(status="ok", last_poll=_last_poll_time)


@router.get("/api/status")
async def status() -> StatusResponse:
    """Current connection status + device info."""
    device_info = None
    logs_health = LogCollectorHealthResponse()
    if _session_factory_ref:
        async with _session_factory_ref() as session:
            result = await session.execute(select(DeviceInfo).where(DeviceInfo.id == 1))
            row = result.scalar_one_or_none()
            if row:
                device_info = DeviceInfoResponse(
                    name=row.name,
                    firmware_ver=row.firmware_ver,
                    board=row.board,
                    public_key=row.public_key,
                    radio_freq=row.radio_freq,
                    radio_bw=row.radio_bw,
                    radio_sf=row.radio_sf,
                    radio_cr=row.radio_cr,
                    tx_power=row.tx_power,
                )
            log_state = await session.get(LogCollectionState, 1)
            if log_state:
                logs_health = LogCollectorHealthResponse(
                    last_log_poll_at=log_state.last_polled_at,
                    last_log_insert_at=log_state.last_new_entry_at,
                    unchanged_buffer_count=log_state.unchanged_buffer_count,
                    last_log_buffer_hash=log_state.last_buffer_hash,
                    last_log_error=_poller_ref.last_log_error if _poller_ref else None,
                )

    state = _connection_ref.state.value if _connection_ref else "disconnected"
    failures = _connection_ref.consecutive_failures if _connection_ref else 0
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
    return StatusResponse(
        connection_state=state,
        device_info=device_info,
        consecutive_failures=failures,
        telemetry=TelemetryHealthResponse(
            stats=stats_health,
            logs=logs_health,
        ),
    )
