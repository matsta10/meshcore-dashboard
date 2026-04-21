"""Tests for status telemetry exposure."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from meshcore_dashboard.database import create_engine_and_tables
from meshcore_dashboard.models import DeviceInfo, LogCollectionState
from meshcore_dashboard.routers import status as status_router
from meshcore_dashboard.services.poller import Poller


class _FakeConnection:
    def __init__(self) -> None:
        self.state = type("State", (), {"value": "connected"})()
        self.consecutive_failures = 0


@pytest.mark.anyio
async def test_status_exposes_telemetry_health():
    engine, session_factory = await create_engine_and_tables("sqlite+aiosqlite://")
    async with session_factory() as session:
        session.add(
            DeviceInfo(
                id=1,
                name="Blue Orchid",
                firmware_ver="v1.14.1",
                board="Generic ESP32",
                updated_at=datetime.now(UTC),
            )
        )
        session.add(
            LogCollectionState(
                id=1,
                last_polled_at=datetime.now(UTC),
                last_buffer_hash="abc123",
                unchanged_buffer_count=2,
                last_new_entry_at=datetime.now(UTC),
            )
        )
        await session.commit()

    poller = Poller(connection=None, session_factory=None)  # type: ignore[arg-type]
    poller.record_parse_error("stats-radio", "Invalid JSON")

    app = FastAPI()
    app.include_router(status_router.router)
    status_router.set_dependencies(_FakeConnection(), session_factory, poller=poller)  # type: ignore[arg-type]

    client = TestClient(app)
    response = client.get("/api/status")

    assert response.status_code == 200
    data = response.json()
    assert data["connection_state"] == "connected"
    assert data["telemetry"]["stats"]["stats-radio"]["ok"] is False
    assert data["telemetry"]["stats"]["stats-radio"]["last_error"] == "Invalid JSON"
    assert data["telemetry"]["logs"]["unchanged_buffer_count"] == 2
    assert data["telemetry"]["logs"]["last_log_buffer_hash"] == "abc123"

    await engine.dispose()
