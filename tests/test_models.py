"""Tests for database models."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from meshcore_dashboard.database import create_engine_and_tables
from meshcore_dashboard.models import (
    ConfigCurrent,
    StatsSnapshot,
)


@pytest.fixture
async def db_session():
    engine, session_factory = await create_engine_and_tables(
        "sqlite+aiosqlite://"
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.anyio
async def test_create_stats_snapshot(db_session):
    snap = StatsSnapshot(
        timestamp=datetime.now(UTC),
        battery_mv=4168,
        uptime_secs=120,
        noise_floor=-108,
    )
    db_session.add(snap)
    await db_session.commit()
    result = await db_session.execute(select(StatsSnapshot))
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].battery_mv == 4168
    assert rows[0].noise_floor == -108


@pytest.mark.anyio
async def test_config_current(db_session):
    cfg = ConfigCurrent(
        key="name",
        value="Blue Orchid",
        updated_at=datetime.now(UTC),
    )
    db_session.add(cfg)
    await db_session.commit()
    result = await db_session.execute(
        select(ConfigCurrent).where(ConfigCurrent.key == "name")
    )
    assert result.scalar_one().value == "Blue Orchid"
