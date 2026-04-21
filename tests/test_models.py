"""Tests for database models."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from meshcore_dashboard.database import create_engine_and_tables
from meshcore_dashboard.models import (
    ConfigChangelog,
    ConfigCurrent,
    LogCollectionState,
    PacketLog,
    StatsSnapshot,
)
from meshcore_dashboard.routers import config as config_router
from meshcore_dashboard.serial.parser import ParseError
from meshcore_dashboard.services.poller import CONFIG_SYNC_KEYS, Poller


@pytest.fixture
async def db_session():
    engine, session_factory = await create_engine_and_tables("sqlite+aiosqlite://")
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


@pytest.mark.anyio
async def test_config_sync_keys_expand_and_guest_password_is_masked():
    engine, session_factory = await create_engine_and_tables("sqlite+aiosqlite://")
    original_session_factory = config_router._session_factory_ref
    original_connection = config_router._connection_ref

    try:
        async with session_factory() as session:
            session.add_all([
                ConfigCurrent(
                    key="guest.password",
                    value="secret",
                    updated_at=datetime.now(UTC),
                ),
                ConfigCurrent(
                    key="owner.info",
                    value="Operator A",
                    updated_at=datetime.now(UTC),
                ),
            ])
            await session.commit()

        config_router.set_dependencies(
            connection=object(),  # type: ignore[arg-type]
            session_factory=session_factory,
        )

        assert set(CONFIG_SYNC_KEYS) == {
            "name",
            "freq",
            "bw",
            "sf",
            "cr",
            "tx_power",
            "pub.key",
            "radio.rxgain",
            "guest.password",
            "owner.info",
            "lat",
            "lon",
            "adc.multiplier",
            "powersaving",
        }

        entries = await config_router.get_all_config()
        values = {entry.key: entry.value for entry in entries}
        assert values["guest.password"] == "***"
        assert values["owner.info"] == "Operator A"

        single = await config_router.get_config_key("guest.password")
        assert single.value == "***"
    finally:
        config_router._session_factory_ref = original_session_factory
        config_router._connection_ref = original_connection
        await engine.dispose()


@pytest.mark.anyio
async def test_config_changelog_masks_password_values():
    engine, session_factory = await create_engine_and_tables("sqlite+aiosqlite://")
    original_session_factory = config_router._session_factory_ref
    original_connection = config_router._connection_ref

    try:
        async with session_factory() as session:
            session.add(
                ConfigChangelog(
                    timestamp=datetime.now(UTC),
                    key="guest.password",
                    old_value="old-secret",
                    new_value="new-secret",
                    source="detected",
                )
            )
            await session.commit()

        config_router.set_dependencies(
            connection=object(),  # type: ignore[arg-type]
            session_factory=session_factory,
        )

        changelog = await config_router.get_changelog()
        assert len(changelog) == 1
        assert changelog[0].key == "guest.password"
        assert changelog[0].old_value == "***"
        assert changelog[0].new_value == "***"
    finally:
        config_router._session_factory_ref = original_session_factory
        config_router._connection_ref = original_connection
        await engine.dispose()


@pytest.mark.anyio
async def test_sync_device_state_removes_stale_unsupported_config_keys():
    engine, session_factory = await create_engine_and_tables("sqlite+aiosqlite://")

    class _FakeConnection:
        async def get_config_value(self, key: str) -> str:
            if key == "cr":
                raise ParseError("No config value line found", "get cr\r\n  -> ??: cr\r\n")
            values = {
                "name": "Blue Orchid",
                "freq": "869.6179809",
                "radio.rxgain": "on",
                "guest.password": "secret",
                "owner.info": "",
                "lat": "51.581108",
                "lon": "0.1757428",
            }
            if key not in values:
                raise ParseError("No config value line found", "")
            return values[key]

        async def send_command(self, cmd: str, timeout: float = 1.0) -> str:
            if cmd == "ver":
                return "  -> v1.14.1\r\n"
            if cmd == "board":
                return "  -> Generic ESP32\r\n"
            raise AssertionError(f"unexpected command: {cmd}")

    async with session_factory() as session:
        session.add(
            ConfigCurrent(
                key="cr",
                value="Blue Orchid",
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()

    poller = Poller(connection=_FakeConnection(), session_factory=session_factory)  # type: ignore[arg-type]
    await poller.sync_device_state(detect_drift=False)

    async with session_factory() as session:
        result = await session.execute(select(ConfigCurrent).order_by(ConfigCurrent.key))
        keys = [row.key for row in result.scalars().all()]
        assert "cr" not in keys

    await engine.dispose()


def test_packet_log_has_structured_fields():
    """PacketLog model has all structured fields."""
    log = PacketLog(
        collected_at=datetime(2026, 4, 21, 12, 0, 0),
        raw_line="test line",
        fingerprint="abc123",
        parse_status="parsed",
        direction="RX",
        packet_type=0,
        route="F",
        payload_len=20,
        snr=12.0,
        rssi=-22,
        device_time_text="12:00:00",
        device_date_text="21/4/2026",
    )
    assert log.direction == "RX"
    assert log.fingerprint == "abc123"
    assert log.parse_status == "parsed"


def test_log_collection_state_model():
    """LogCollectionState singleton model exists."""
    state = LogCollectionState(
        id=1,
        last_polled_at=datetime(2026, 4, 21, 12, 0, 0),
        last_buffer_hash="deadbeef",
        last_buffer_size=305,
        unchanged_buffer_count=0,
    )
    assert state.last_buffer_hash == "deadbeef"
    assert state.last_buffer_size == 305
