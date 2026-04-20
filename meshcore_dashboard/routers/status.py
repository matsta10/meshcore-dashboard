"""Health and status API routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meshcore_dashboard.models import DeviceInfo
from meshcore_dashboard.schemas import (
    DeviceInfoResponse,
    HealthResponse,
    StatusResponse,
)
from meshcore_dashboard.serial.connection import RepeaterConnection

router = APIRouter()

_last_poll_time: datetime | None = None
_connection_ref: RepeaterConnection | None = None
_session_factory_ref: async_sessionmaker[AsyncSession] | None = None


def set_dependencies(
    connection: RepeaterConnection,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Wire up dependencies from app lifespan."""
    global _connection_ref, _session_factory_ref
    _connection_ref = connection
    _session_factory_ref = session_factory


def update_last_poll() -> None:
    """Called by poller after successful poll."""
    global _last_poll_time
    _last_poll_time = datetime.now(timezone.utc)


@router.get("/api/health")
async def health(response: Response) -> HealthResponse:
    """Returns 200 if last poll <5min ago, 503 otherwise."""
    if _last_poll_time is None or (
        datetime.now(timezone.utc) - _last_poll_time
        > timedelta(minutes=5)
    ):
        response.status_code = 503
        return HealthResponse(
            status="unhealthy", last_poll=_last_poll_time
        )
    return HealthResponse(status="ok", last_poll=_last_poll_time)


@router.get("/api/status")
async def status() -> StatusResponse:
    """Current connection status + device info."""
    device_info = None
    if _session_factory_ref:
        async with _session_factory_ref() as session:
            result = await session.execute(
                select(DeviceInfo).where(DeviceInfo.id == 1)
            )
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

    state = (
        _connection_ref.state.value
        if _connection_ref
        else "disconnected"
    )
    failures = (
        _connection_ref.consecutive_failures
        if _connection_ref
        else 0
    )
    return StatusResponse(
        connection_state=state,
        device_info=device_info,
        consecutive_failures=failures,
    )
