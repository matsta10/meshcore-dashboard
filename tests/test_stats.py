"""Tests for stats history API behavior."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from meshcore_dashboard.database import create_engine_and_tables
from meshcore_dashboard.models import StatsSnapshot
from meshcore_dashboard.routers import stats as stats_router


@pytest.mark.anyio
async def test_stats_history_hourly_falls_back_to_raw_when_hourly_empty():
    engine, session_factory = await create_engine_and_tables("sqlite+aiosqlite://")
    async with session_factory() as session:
        session.add_all([
            StatsSnapshot(
                timestamp=datetime(2026, 4, 21, 18, 0, tzinfo=UTC),
                battery_mv=4168,
                noise_floor=-113,
                last_rssi=-18,
                last_snr=12.3,
            ),
            StatsSnapshot(
                timestamp=datetime(2026, 4, 21, 19, 0, tzinfo=UTC),
                battery_mv=4167,
                noise_floor=-112,
                last_rssi=-17,
                last_snr=13.1,
            ),
        ])
        await session.commit()

    app = FastAPI()
    app.include_router(stats_router.router)
    stats_router.set_dependencies(session_factory)

    client = TestClient(app)
    response = client.get(
        "/api/stats/history",
        params={
            "metrics": "battery_mv,noise_floor,last_rssi,last_snr",
            "resolution": "hourly",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["data"]) == 2
    assert payload["data"][0]["timestamp"] == "2026-04-21T18:00:00"
    assert payload["data"][1]["timestamp"] == "2026-04-21T19:00:00"

    await engine.dispose()
