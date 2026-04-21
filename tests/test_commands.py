"""Tests for command whitelist, classification, and admin clock routes."""

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from meshcore_dashboard.routers import commands as commands_router
from meshcore_dashboard.routers import neighbors as neighbors_router
from meshcore_dashboard.serial.commands import (
    COMMAND_WHITELIST,
    get_timeout,
    is_command_allowed,
    is_destructive,
)


def test_whitelist_contains_basics():
    assert "ver" in COMMAND_WHITELIST
    assert "stats-core" in COMMAND_WHITELIST
    assert "reboot" in COMMAND_WHITELIST
    assert "advert" in COMMAND_WHITELIST


def test_blocked_commands():
    assert not is_command_allowed("set freq 915")
    assert not is_command_allowed("get prv.key")
    assert not is_command_allowed("erase")
    assert not is_command_allowed("password foo")


def test_safe_command_allowed():
    assert is_command_allowed("advert")
    assert is_command_allowed("stats-core")
    assert is_command_allowed("ver")
    assert is_command_allowed("neighbors")
    assert is_command_allowed("discover.neighbors")


def test_neighbor_remove_stays_out_of_generic_command_runner():
    assert not is_command_allowed("neighbor.remove deadbeef")
    assert not is_command_allowed("neighbor.remove")


def test_destructive_requires_confirm():
    assert is_destructive("reboot")
    assert is_destructive("log erase")
    assert is_destructive("clear stats")
    assert not is_destructive("advert")
    assert not is_destructive("ver")


def test_timeouts():
    assert get_timeout("stats-core") == 1.0
    assert get_timeout("ver") == 1.0
    assert get_timeout("reboot") == 10.0
    assert get_timeout("advert") == 3.0


def test_clock_read_endpoint_returns_device_output(monkeypatch):
    app = FastAPI()
    app.include_router(commands_router.router)

    mock_connection = AsyncMock()
    mock_connection.send_command.return_value = (
        "20:04:27 - 21/4/2026 U: TX, len=49 (type=2, route=F, payload_len=36)\n"
        "  ->    EOF\n"
        "clock\n"
        "  -> 2026-04-21 15:00:00 UTC\n"
    )
    monkeypatch.setattr(commands_router, "_connection_ref", mock_connection)

    client = TestClient(app)
    response = client.post("/api/admin/clock/read")

    assert response.status_code == 200
    assert response.json() == {
        "output": "2026-04-21 15:00:00 UTC",
    }
    mock_connection.send_command.assert_awaited_once_with(
        "clock",
        timeout=1.0,
    )


def test_clock_sync_endpoint_sends_clock_sync(monkeypatch):
    app = FastAPI()
    app.include_router(commands_router.router)

    mock_connection = AsyncMock()
    mock_connection.send_command.return_value = "clock synced"
    monkeypatch.setattr(commands_router, "_connection_ref", mock_connection)

    client = TestClient(app)
    response = client.post("/api/admin/clock/sync")

    assert response.status_code == 200
    assert response.json() == {"detail": "Clock sync requested"}
    mock_connection.send_command.assert_awaited_once_with(
        "clock sync",
        timeout=3.0,
    )


def test_clock_set_endpoint_sends_time_command(monkeypatch):
    app = FastAPI()
    app.include_router(commands_router.router)

    mock_connection = AsyncMock()
    mock_connection.send_command.return_value = "time set"
    monkeypatch.setattr(commands_router, "_connection_ref", mock_connection)

    client = TestClient(app)
    response = client.post(
        "/api/admin/clock/set",
        json={"epoch_seconds": 1776783600},
    )

    assert response.status_code == 200
    assert response.json() == {"detail": "Clock set requested"}
    mock_connection.send_command.assert_awaited_once_with(
        "time 1776783600",
        timeout=3.0,
    )


def test_clock_set_endpoint_rejects_negative_epoch(monkeypatch):
    app = FastAPI()
    app.include_router(commands_router.router)

    mock_connection = AsyncMock()
    monkeypatch.setattr(commands_router, "_connection_ref", mock_connection)

    client = TestClient(app)
    response = client.post(
        "/api/admin/clock/set",
        json={"epoch_seconds": -1},
    )

    assert response.status_code == 422
    mock_connection.send_command.assert_not_awaited()


def test_clock_set_endpoint_rejects_string_epoch(monkeypatch):
    app = FastAPI()
    app.include_router(commands_router.router)

    mock_connection = AsyncMock()
    monkeypatch.setattr(commands_router, "_connection_ref", mock_connection)

    client = TestClient(app)
    response = client.post(
        "/api/admin/clock/set",
        json={"epoch_seconds": "1776783600"},
    )

    assert response.status_code == 422
    mock_connection.send_command.assert_not_awaited()


def test_neighbor_remove_endpoint_sends_typed_command(monkeypatch):
    app = FastAPI()
    app.include_router(neighbors_router.router)

    mock_connection = AsyncMock()
    mock_connection.send_command.return_value = "neighbor removed"
    monkeypatch.setattr(neighbors_router, "_connection_ref", mock_connection)

    client = TestClient(app)
    response = client.delete("/api/neighbors/DEADBEEF")

    assert response.status_code == 202
    assert response.json() == {"detail": "Neighbor removal requested"}
    mock_connection.send_command.assert_awaited_once_with(
        "neighbor.remove DEADBEEF",
        timeout=3.0,
    )


def test_neighbor_remove_endpoint_rejects_short_prefix(monkeypatch):
    app = FastAPI()
    app.include_router(neighbors_router.router)

    mock_connection = AsyncMock()
    monkeypatch.setattr(neighbors_router, "_connection_ref", mock_connection)

    client = TestClient(app)
    response = client.delete("/api/neighbors/abc")

    assert response.status_code == 422
    mock_connection.send_command.assert_not_awaited()


def test_neighbor_remove_endpoint_rejects_non_hex_prefix(monkeypatch):
    app = FastAPI()
    app.include_router(neighbors_router.router)

    mock_connection = AsyncMock()
    monkeypatch.setattr(neighbors_router, "_connection_ref", mock_connection)

    client = TestClient(app)
    response = client.delete("/api/neighbors/zzzz")

    assert response.status_code == 422
    mock_connection.send_command.assert_not_awaited()
