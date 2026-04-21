"""Tests for poller parse-health tracking."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from meshcore_dashboard.database import create_engine_and_tables
from meshcore_dashboard.routers import websocket as ws_router
from meshcore_dashboard.services.poller import Poller


def test_poller_starts_not_stale():
    """Fresh poller has no parse errors."""
    poller = Poller(connection=None, session_factory=None)  # type: ignore[arg-type]
    assert poller.is_stale is False
    assert poller.last_parse_error is None


def test_poller_mark_stale():
    """Recording a parse error makes poller stale."""
    poller = Poller(connection=None, session_factory=None)  # type: ignore[arg-type]
    poller.record_parse_error("stats-core", "Invalid JSON: ...")
    assert poller.is_stale is True
    assert poller.last_parse_error == "stats-core: Invalid JSON: ..."


def test_poller_clear_stale_on_success():
    """Successful poll clears stale state."""
    poller = Poller(connection=None, session_factory=None)  # type: ignore[arg-type]
    poller.record_parse_error("stats-core", "bad data")
    assert poller.is_stale is True
    poller.clear_parse_error()
    assert poller.is_stale is False
    assert poller.last_parse_error is None


def test_poller_tracks_partial_stats_health():
    poller = Poller(connection=None, session_factory=None)  # type: ignore[arg-type]
    now = datetime.now(UTC)
    poller.record_stats_success("stats-packets", now)
    poller.record_parse_error("stats-core", "Invalid JSON")

    assert poller.stats_freshness == "partial"
    assert poller.stats_health["stats-packets"]["ok"] is True
    assert poller.stats_health["stats-packets"]["last_success_at"] == now
    assert poller.stats_health["stats-core"]["ok"] is False
    assert poller.stats_health["stats-core"]["last_error"] == "Invalid JSON"


@pytest.mark.anyio
async def test_poller_stops_streaming_logs_on_startup():
    connection = AsyncMock()
    poller = Poller(connection=connection, session_factory=None)  # type: ignore[arg-type]

    await poller._ensure_log_stopped()

    connection.send_command.assert_awaited_once_with("log stop", timeout=3.0)


@pytest.mark.anyio
async def test_poller_collects_stats_before_log_dump(monkeypatch):
    engine, session_factory = await create_engine_and_tables("sqlite+aiosqlite://")
    calls: list[str] = []

    class _FakeConnection:
        state = SimpleNamespace(value="connected")

        async def send_command(self, cmd: str, timeout: float = 1.0) -> str:
            calls.append(cmd)
            if cmd == "log":
                return "log\r\n19:26:06 - 21/4/2026 U: RX, len=134 (type=5, route=F, payload_len=115)\r\n  ->    EOF\r\n"
            return "  -> ok\r\n"

        async def get_stats_json(self, cmd: str) -> dict[str, int | float]:
            calls.append(cmd)
            if cmd == "stats-core":
                return {
                    "battery_mv": 4168,
                    "uptime_secs": 120,
                    "queue_len": 1,
                    "errors": 0,
                }
            if cmd == "stats-radio":
                return {
                    "noise_floor": -109,
                    "last_rssi": -19,
                    "last_snr": 13,
                    "tx_air_secs": 10,
                    "rx_air_secs": 20,
                }
            if cmd == "stats-packets":
                return {
                    "recv": 10,
                    "sent": 11,
                    "flood_rx": 9,
                    "flood_tx": 8,
                    "direct_rx": 1,
                    "direct_tx": 2,
                    "recv_errors": 0,
                }
            raise AssertionError(f"unexpected stats command: {cmd}")

        def check_reboot(self, uptime: int) -> bool:
            return False

    async def _noop_broadcast(_: object) -> None:
        return None

    async def _noop_neighbors() -> None:
        return None

    monkeypatch.setattr(ws_router, "broadcast", _noop_broadcast)

    poller = Poller(connection=_FakeConnection(), session_factory=session_factory)  # type: ignore[arg-type]
    monkeypatch.setattr(poller, "_poll_neighbors", _noop_neighbors)

    await poller._do_poll()

    assert calls.index("stats-core") < calls.index("log")
    assert calls.index("stats-radio") < calls.index("log")
    assert calls.index("stats-packets") < calls.index("log")

    await engine.dispose()
