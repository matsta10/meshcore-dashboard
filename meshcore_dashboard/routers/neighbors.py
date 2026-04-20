"""Neighbors API routes."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meshcore_dashboard.models import Neighbor
from meshcore_dashboard.schemas import NeighborResponse
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


@router.get("/api/neighbors")
async def get_neighbors() -> list[NeighborResponse]:
    """Current neighbor list from DB."""
    assert _session_factory_ref
    async with _session_factory_ref() as session:
        result = await session.execute(
            select(Neighbor).order_by(Neighbor.last_seen.desc())
        )
        rows = result.scalars().all()
        return [
            NeighborResponse(
                public_key=row.public_key,
                name=row.name,
                first_seen=row.first_seen,
                last_seen=row.last_seen,
                last_rssi=row.last_rssi,
                last_snr=row.last_snr,
            )
            for row in rows
        ]


@router.post("/api/neighbors/discover")
async def discover_neighbors() -> JSONResponse:
    """Trigger neighbor discovery on device."""
    assert _connection_ref
    await _connection_ref.send_command(
        "discover.neighbors", timeout=3.0
    )
    return JSONResponse(
        status_code=202,
        content={"detail": "Discovery initiated"},
    )
